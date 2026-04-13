"""LangChain framework adapter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .base import AdapterConfig, FrameworkAdapter
from ..parser import (
    extract_frontmatter,
    extract_skill_body,
    get_skill_description,
    get_skill_name,
    is_skill_file as parser_is_skill_file,
)


LANGCHAIN_CONFIG = AdapterConfig(
    framework_name="langchain",
    global_instruction_files={
        # common agent-global files
        "CLAUDE.md",
        "AGENTS.md",
        ".cursorrules",
        "INSTRUCTIONS.md",
        "SYSTEM.md",
        # langchain-specific common names
        "langchain.yaml",
        "langchain.yml",
    },
    config_files_with_system_prompts={
        ".json": ["prompt", "prompts", "config", "agent", "agents", "system", "instructions", "langchain"],
        ".yaml": ["prompt", "prompts", "config", "agent", "agents", "system", "instructions", "langchain"],
        ".yml": ["prompt", "prompts", "config", "agent", "agents", "system", "instructions", "langchain"],
        ".toml": ["prompt", "prompts", "config", "agent", "agents", "system", "instructions", "langchain"],
    },
    vault_dirs={".vault", "vault", "_vault"},
    pointer_file_markers={
        "load_skill",
        "skill_id",
        "list_dir",
        "ls",
        "view_file",
        "read_file",
        "cat",
    },
    hidden_dir_whitelist={".claude", ".cursor", ".agents", ".vault", ".anthropic", ".langchain"},
)


@dataclass(frozen=True)
class PythonSkill:
    name: str
    description: str
    kind: str  # "tool" | "agent" | "task"


class LangChainAdapter(FrameworkAdapter):
    """Adapter for LangChain-style projects."""

    def __init__(self, target_path: Path):
        super().__init__(target_path, LANGCHAIN_CONFIG)

    def detect_framework(self) -> bool:
        # Strong signals
        if (self.target_path / ".langchain").exists():
            return True
        if (self.target_path / "langchain.yaml").exists() or (self.target_path / "langchain.yml").exists():
            return True

        # Soft signal: dependency in pyproject
        pyproject = self.target_path / "pyproject.toml"
        if pyproject.exists():
            try:
                txt = pyproject.read_text(encoding="utf-8", errors="ignore").lower()
            except Exception:
                txt = ""
            if "langchain" in txt:
                return True

        return False

    def is_skill_file(self, file_path: Path, content: str) -> bool:
        return parser_is_skill_file(file_path, content)

    def get_global_files(self, file_path: Path, content: str) -> Optional[Dict]:
        # Common markdown globals
        if self.is_global_instruction_file(file_path) and file_path.suffix.lower() in {".md", ".markdown", ""}:
            return {"type": "markdown"}

        # LangChain configs often store prompts in YAML
        suffix = file_path.suffix.lower()
        if suffix in self.config.config_files_with_system_prompts and self.is_config_with_system_prompt(file_path, content):
            return {"type": "config", "subtype": suffix}

        # Treat key framework entrypoints as global context sources
        if file_path.name in {"agents.py", "tasks.py"} and file_path.suffix.lower() == ".py":
            extracted = self.extract_python_skills(content)
            if extracted:
                return {"type": "code", "subtype": "python", "skills_count": len(extracted)}

        return None

    def get_skill_info(self, file_path: Path, content: str, tokens: int) -> Optional[Dict]:
        # Primary skill format: frontmatter markdown
        if self.is_skill_file(file_path, content):
            frontmatter = extract_frontmatter(content)
            desc = get_skill_description(frontmatter)
            name = get_skill_name(frontmatter)
            rel_path = file_path.relative_to(self.target_path)
            is_ungated = not self.is_in_vault(rel_path) and not self.is_pointer_file(content)
            body = extract_skill_body(content)
            return {
                "name": name,
                "description": desc,
                "description_length": len(desc),
                "ungated": is_ungated,
                "vaultable": is_ungated,
                "body_tokens": 0,
                "frontmatter": frontmatter,
                "body": body,
            }

        # Secondary: python-declared tool/task definitions (best-effort)
        if file_path.suffix.lower() == ".py" and file_path.name in {"agents.py", "tasks.py"}:
            extracted = self.extract_python_skills(content)
            if not extracted:
                return None
            # Summarize; agent-3 can decide how to surface these in reports
            return {
                "name": f"{file_path.name} (definitions)",
                "description": f"{len(extracted)} definitions found in {file_path.name}",
                "description_length": 0,
                "ungated": False,
                "vaultable": False,
                "body_tokens": 0,
                "python_skills": [s.__dict__ for s in extracted],
            }

        return None

    def extract_python_skills(self, content: str) -> List[PythonSkill]:
        """
        Best-effort extraction for common LangChain patterns:
        - @tool decorated functions with docstrings
        - Task(...) / Agent(...) calls with name/description-like fields
        """
        out: List[PythonSkill] = []

        # @tool
        tool_blocks = re.finditer(
            r"@tool\b[\s\S]*?^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            content,
            flags=re.M,
        )
        for m in tool_blocks:
            fn = m.group(1)
            doc = _first_docstring_after_def(content, def_name=fn)
            if doc:
                out.append(PythonSkill(name=fn, description=doc, kind="tool"))

        # Task(...) / Agent(...)
        for kind, ctor in (("task", "Task"), ("agent", "Agent")):
            for blob in _iter_ctor_blobs(content, ctor=ctor):
                name = _extract_kw_string(blob, keys=("name", "id", "title")) or ctor
                desc = _extract_kw_string(blob, keys=("description", "prompt", "system_prompt", "instructions")) or ""
                if desc:
                    out.append(PythonSkill(name=name, description=desc, kind=kind))

        # Deduplicate by (kind,name)
        seen = set()
        unique: List[PythonSkill] = []
        for s in out:
            key = (s.kind, s.name)
            if key in seen:
                continue
            seen.add(key)
            unique.append(s)
        return unique


def _first_docstring_after_def(content: str, def_name: str) -> str:
    lines = content.splitlines()
    def_re = re.compile(rf"^\s*def\s+{re.escape(def_name)}\s*\(", flags=0)
    start_idx = None
    for i, line in enumerate(lines):
        if def_re.search(line):
            start_idx = i
            break
    if start_idx is None:
        return ""

    # Scan forward for the first triple-quoted string literal
    i = start_idx + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return ""

    line = lines[i].lstrip()
    if not (line.startswith('"""') or line.startswith("'''")):
        return ""

    quote = line[:3]
    rest = line[3:]
    # single-line docstring
    if quote in rest:
        doc = rest.split(quote, 1)[0]
        return re.sub(r"\s+", " ", doc).strip()[:300]

    doc_lines = []
    if rest:
        doc_lines.append(rest)
    i += 1
    while i < len(lines):
        cur = lines[i]
        if quote in cur:
            before = cur.split(quote, 1)[0]
            doc_lines.append(before)
            break
        doc_lines.append(cur)
        i += 1

    doc = "\n".join(doc_lines)
    return re.sub(r"\s+", " ", doc).strip()[:300]


def _iter_ctor_blobs(content: str, ctor: str) -> List[str]:
    # Very light "parse": grab text from ctor( ... ) with balanced-ish parens on one line span
    blobs: List[str] = []
    for m in re.finditer(rf"\b{re.escape(ctor)}\s*\(", content):
        start = m.start()
        i = m.end() - 1
        depth = 0
        while i < len(content):
            ch = content[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    blobs.append(content[start : i + 1])
                    break
            i += 1
    return blobs


def _extract_kw_string(blob: str, keys: tuple[str, ...]) -> str:
    for k in keys:
        # name="x" or name='x'
        m = re.search(rf"\b{k}\s*=\s*([\"'])(.*?)\1", blob, flags=re.S)
        if m:
            val = re.sub(r"\s+", " ", m.group(2)).strip()
            if val:
                return val[:300]
    return ""

