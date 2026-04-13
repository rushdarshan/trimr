"""Base adapter interface for framework-specific audit logic."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Set, Dict, Optional
from dataclasses import dataclass
import pathspec
import json

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


@dataclass
class AdapterConfig:
    """Configuration for a framework adapter."""
    framework_name: str
    global_instruction_files: Set[str]
    config_files_with_system_prompts: Dict[str, List[str]]
    vault_dirs: Set[str]
    pointer_file_markers: Set[str]
    hidden_dir_whitelist: Set[str]


class FrameworkAdapter(ABC):
    """Abstract base class for framework-specific adapters."""
    
    def __init__(self, target_path: Path, config: AdapterConfig):
        """Initialize adapter with target path and framework config."""
        self.target_path = target_path.resolve()
        self.config = config
        self.pathspec_obj: Optional[pathspec.PathSpec] = None
        self._load_gitignore()
    
    def _load_gitignore(self) -> None:
        """Load .gitignore patterns if present."""
        gitignore_path = self.target_path / ".gitignore"
        if gitignore_path.exists():
            try:
                patterns = gitignore_path.read_text(encoding="utf-8").strip().split("\n")
                self.pathspec_obj = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
            except Exception:
                pass
    
    def _should_exclude(self, rel_path: Path) -> bool:
        """Check if path should be excluded based on rules."""
        HARDCODED_EXCLUSIONS = {
            "node_modules", "dist", "build", "__pycache__",
            ".venv", "venv", "site-packages",
        }
        
        parts = rel_path.parts
        for part in parts:
            if part.startswith(".") and part not in self.config.hidden_dir_whitelist:
                return True
            if part in HARDCODED_EXCLUSIONS:
                return True
        
        if self.pathspec_obj:
            if self.pathspec_obj.match_file(str(rel_path)):
                return True
        
        return False
    
    def walk_files(self) -> List[Path]:
        """Recursively walk target directory, respecting exclusions."""
        result = []
        try:
            for path in self.target_path.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    rel_path = path.relative_to(self.target_path)
                    if not self._should_exclude(rel_path):
                        result.append(path)
        except Exception:
            pass
        return result
    
    def is_global_instruction_file(self, file_path: Path) -> bool:
        """Check if file is a global instruction file."""
        return file_path.name in self.config.global_instruction_files
    
    def is_config_with_system_prompt(self, file_path: Path, content: str) -> bool:
        """Check if config file contains system prompts."""
        suffix = file_path.suffix.lower()
        if suffix not in self.config.config_files_with_system_prompts:
            return False
        
        basename = file_path.stem.lower()
        for keyword in self.config.config_files_with_system_prompts.get(suffix, []):
            if keyword in basename:
                return True
        
        system_prompt_keys = {
            "system_prompt",
            "system",
            "prompt",
            "instructions",
            "instruction",
            "agent_prompt",
            "context",
            "preamble",
            "rules",
        }

        # Prefer structured parsing to reduce false negatives
        parsed = self._parse_config_content(suffix=suffix, content=content)
        if parsed is not None:
            if self._object_contains_system_prompt(parsed, system_prompt_keys=system_prompt_keys):
                return True

        # Fallback: string heuristics (works even if parse fails)
        content_lower = content.lower()
        for key in system_prompt_keys:
            if f'"{key}"' in content_lower or f"'{key}'" in content_lower or f"{key}:" in content_lower:
                return True

        return False

    def _parse_config_content(self, suffix: str, content: str):
        if suffix == ".json":
            try:
                return json.loads(content)
            except Exception:
                return None
        if suffix in {".yaml", ".yml"}:
            if yaml is None:
                return None
            try:
                return yaml.safe_load(content)
            except Exception:
                return None
        if suffix == ".toml":
            if tomllib is None:
                return None
            try:
                return tomllib.loads(content)
            except Exception:
                return None
        return None

    def _object_contains_system_prompt(self, obj, system_prompt_keys: Set[str]) -> bool:
        """
        Heuristics:
        - Any key matching system_prompt_keys with a sizeable string value.
        - Any list of {role: system, content: "..."} messages.
        """
        min_len = 200

        def is_big_string(v) -> bool:
            if not isinstance(v, str):
                return False
            s = v.strip()
            if len(s) >= min_len:
                return True
            # shorter but likely a system prompt
            markers = ("you are", "system prompt", "instructions:", "rules:")
            lower = s.lower()
            return any(m in lower for m in markers) and len(s) >= 50

        def walk(node) -> bool:
            if isinstance(node, dict):
                for k, v in node.items():
                    if isinstance(k, str) and k.lower() in system_prompt_keys and is_big_string(v):
                        return True

                    # Common chat schema: messages: [{role: system, content: "..."}]
                    if isinstance(k, str) and k.lower() in {"messages", "chat", "conversation"} and isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict):
                                role = item.get("role")
                                content = item.get("content")
                                if isinstance(role, str) and role.lower() == "system" and is_big_string(content):
                                    return True

                    if walk(v):
                        return True
                return False
            if isinstance(node, list):
                return any(walk(x) for x in node)
            return False

        return walk(obj)
    
    def is_pointer_file(self, content: str) -> bool:
        """Check if file contains pointer file markers."""
        return any(marker in content for marker in self.config.pointer_file_markers)
    
    def is_in_vault(self, rel_path: Path) -> bool:
        """Check if file is within a vault directory."""
        for vault_dir in self.config.vault_dirs:
            if vault_dir in rel_path.parts:
                return True
        return False
    
    @abstractmethod
    def is_skill_file(self, file_path: Path, content: str) -> bool:
        """Check if file is a skill file (framework-specific)."""
        pass
    
    @abstractmethod
    def get_global_files(self, file_path: Path, content: str) -> Optional[Dict]:
        """Extract global file info (framework-specific)."""
        pass
    
    @abstractmethod
    def get_skill_info(self, file_path: Path, content: str, tokens: int) -> Optional[Dict]:
        """Extract skill info (framework-specific)."""
        pass
    
    @abstractmethod
    def detect_framework(self) -> bool:
        """Check if target directory matches this framework."""
        pass
