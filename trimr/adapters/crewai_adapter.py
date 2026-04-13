"""CrewAI framework adapter."""

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


CREWAI_CONFIG = AdapterConfig(
    framework_name="crewai",
    global_instruction_files={
        "CLAUDE.md",
        "AGENTS.md",
        ".cursorrules",
        "INSTRUCTIONS.md",
        "SYSTEM.md",
        # common CrewAI entrypoints
        "crew.py",
        "agents.py",
        "tasks.py",
    },
    config_files_with_system_prompts={
        ".json": ["prompt", "prompts", "config", "agent", "agents", "system", "instructions", "crewai", "crew"],
        ".yaml": ["prompt", "prompts", "config", "agent", "agents", "system", "instructions", "crewai", "crew"],
        ".yml": ["prompt", "prompts", "config", "agent", "agents", "system", "instructions", "crewai", "crew"],
        ".toml": ["prompt", "prompts", "config", "agent", "agents", "system", "instructions", "crewai", "crew"],
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
    hidden_dir_whitelist={".claude", ".cursor", ".agents", ".vault", ".anthropic", ".crewai"},
)


@dataclass(frozen=True)
class CrewDefinition:
    name: str
    description: str
    kind: str  # "agent" | "task" | "tool"


class CrewAIAdapter(FrameworkAdapter):
    """Adapter for CrewAI-style projects."""

    def __init__(self, target_path: Path):
        super().__init__(target_path, CREWAI_CONFIG)

    def detect_framework(self) -> bool:
        if (self.target_path / ".crewai").exists():
            return True

        # Typical CrewAI structure
        if (self.target_path / "crew.py").exists() and (
            (self.target_path / "agents.py").exists() or (self.target_path / "tasks.py").exists()
        ):
            return True

        # Soft signal: dependency in pyproject
        pyproject = self.target_path / "pyproject.toml"
        if pyproject.exists():
            try:
                txt = pyproject.read_text(encoding="utf-8", errors="ignore").lower()
            except Exception:
                txt = ""
            if "crewai" in txt:
                return True

        return False

    def is_skill_file(self, file_path: Path, content: str) -> bool:
        return parser_is_skill_file(file_path, content)

    def get_global_files(self, file_path: Path, content: str) -> Optional[Dict]:
        if self.is_global_instruction_file(file_path) and file_path.suffix.lower() in {".md", ".markdown", ""}:
            return {"type": "markdown"}

        suffix = file_path.suffix.lower()
        if suffix in self.config.config_files_with_system_prompts and self.is_config_with_system_prompt(file_path, content):
            return {"type": "config", "subtype": suffix}

        if file_path.suffix.lower() == ".py" and file_path.name in {"crew.py", "agents.py", "tasks.py"}:
            extracted = self.extract_definitions(content)
            if extracted:
                return {"type": "code", "subtype": "python", "definitions_count": len(extracted)}

        return None

    def get_skill_info(self, file_path: Path, content: str, tokens: int) -> Optional[Dict]:
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

        if file_path.suffix.lower() == ".py" and file_path.name in {"crew.py", "agents.py", "tasks.py"}:
            extracted = self.extract_definitions(content)
            if not extracted:
                return None
            return {
                "name": f"{file_path.name} (definitions)",
                "description": f"{len(extracted)} definitions found in {file_path.name}",
                "description_length": 0,
                "ungated": False,
                "vaultable": False,
                "body_tokens": 0,
                "crewai_definitions": [d.__dict__ for d in extracted],
            }

        return None

    def extract_definitions(self, content: str) -> List[CrewDefinition]:
        """
        Best-effort extraction for common CrewAI patterns:
        - Agent(... role=..., goal=..., backstory=...)
        - Task(... description=..., expected_output=...)
        - @tool decorated functions with docstrings
        """
        out: List[CrewDefinition] = []

        # @tool decorated functions
        tool_blocks = re.finditer(
            r"@tool\b[\s\S]*?^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            content,
            flags=re.M,
        )
        for m in tool_blocks:
            fn = m.group(1)
            doc = _first_docstring_after_def(content, def_name=fn)
            if doc:
                out.append(CrewDefinition(name=fn, description=doc, kind="tool"))

        # Agent(...)
        for blob in _iter_ctor_blobs(content, ctor="Agent"):
            name = _extract_kw_string(blob, keys=("role", "name", "id", "title")) or "Agent"
            desc = (
                _extract_kw_string(blob, keys=("goal", "backstory", "system_prompt", "prompt", "instructions"))
                or ""
            )
            if desc:
                out.append(CrewDefinition(name=name, description=desc, kind="agent"))

        # Task(...)
        for blob in _iter_ctor_blobs(content, ctor="Task"):
            name = _extract_kw_string(blob, keys=("name", "id", "title")) or "Task"
            desc = _extract_kw_string(blob, keys=("description", "expected_output", "prompt", "instructions")) or ""
            if desc:
                out.append(CrewDefinition(name=name, description=desc, kind="task"))

        # Deduplicate by (kind,name)
        seen = set()
        unique: List[CrewDefinition] = []
        for d in out:
            key = (d.kind, d.name)
            if key in seen:
                continue
            seen.add(key)
            unique.append(d)
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
        m = re.search(rf"\b{k}\s*=\s*([\"'])(.*?)\1", blob, flags=re.S)
        if m:
            val = re.sub(r"\s+", " ", m.group(2)).strip()
            if val:
                return val[:300]
    return ""

