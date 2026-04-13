"""OpenAI Assistants/Responses framework adapter."""

from pathlib import Path
from typing import Dict, Optional

from .base import AdapterConfig, FrameworkAdapter
from ..parser import (
    extract_frontmatter,
    extract_skill_body,
    get_skill_description,
    get_skill_name,
    is_skill_file as parser_is_skill_file,
)


OPENAI_CONFIG = AdapterConfig(
    framework_name="openai",
    global_instruction_files={
        "assistant.json",
        "assistants.json",
        "openai.json",
        "OPENAI.md",
        "INSTRUCTIONS.md",
        "SYSTEM.md",
        "AGENTS.md",
        "CLAUDE.md",
        "system_prompt.md",
    },
    config_files_with_system_prompts={
        ".json": [
            "assistant",
            "assistants",
            "openai",
            "prompt",
            "prompts",
            "instructions",
            "system",
            "responses",
        ],
        ".yaml": ["assistant", "openai", "prompt", "prompts", "instructions", "system"],
        ".yml": ["assistant", "openai", "prompt", "prompts", "instructions", "system"],
        ".toml": ["assistant", "openai", "prompt", "prompts", "instructions", "system"],
    },
    vault_dirs={".vault", "vault", "_vault"},
    pointer_file_markers={
        "load_skill",
        "skill_id",
        "list_dir",
        "view_file",
        "read_file",
        "cat",
        "file_search",
        "function_call",
    },
    hidden_dir_whitelist={".claude", ".cursor", ".agents", ".vault", ".openai", ".env"},
)


class OpenAIAdapter(FrameworkAdapter):
    """Adapter for OpenAI Assistants/Responses style projects."""

    def __init__(self, target_path: Path):
        super().__init__(target_path, OPENAI_CONFIG)

    def detect_framework(self) -> bool:
        """Check if target is an OpenAI project."""
        if any(
            (self.target_path / name).exists()
            for name in ("assistant.json", "assistants.json", "openai.json")
        ):
            return True

        if (self.target_path / ".openai").exists():
            return True

        for env_path in self._env_files():
            try:
                if self.has_openai_credentials(env_path.read_text(encoding="utf-8", errors="replace")):
                    return True
            except Exception:
                continue

        return False

    def is_skill_file(self, file_path: Path, content: str) -> bool:
        """Check if file is an OpenAI-compatible skill or tool definition."""
        if parser_is_skill_file(file_path, content):
            return True

        if file_path.suffix.lower() != ".json":
            return False

        return self._extract_tool_metadata(file_path, content) is not None

    def get_global_files(self, file_path: Path, content: str) -> Optional[Dict]:
        """Extract global file info for OpenAI projects."""
        if file_path.name in self.config.global_instruction_files:
            if file_path.suffix.lower() == ".json":
                return {"type": "assistant_json"}
            return {"type": "markdown"}

        if self._is_env_file(file_path):
            if self.is_config_with_system_prompt(file_path, content):
                return {"type": "env", "subtype": "system_prompt"}
            return None

        suffix = file_path.suffix.lower()
        if suffix in self.config.config_files_with_system_prompts:
            if self.is_config_with_system_prompt(file_path, content):
                return {"type": "config", "subtype": suffix}

        return None

    def get_skill_info(self, file_path: Path, content: str, tokens: int) -> Optional[Dict]:
        """Extract skill metadata for markdown skills and OpenAI function tools."""
        rel_path = file_path.relative_to(self.target_path)
        is_ungated = not self.is_in_vault(rel_path)

        if parser_is_skill_file(file_path, content):
            frontmatter = extract_frontmatter(content)
            body = extract_skill_body(content)
            description = get_skill_description(frontmatter)
            name = get_skill_name(frontmatter)

            return {
                "name": name,
                "description": description,
                "description_length": len(description),
                "ungated": is_ungated,
                "vaultable": is_ungated,
                "body_tokens": 0,
                "body": body,
                "frontmatter": frontmatter,
            }

        tool_metadata = self._extract_tool_metadata(file_path, content)
        if tool_metadata is None:
            return None

        description = tool_metadata["description"]
        return {
            "name": tool_metadata["name"],
            "description": description,
            "description_length": len(description),
            "ungated": is_ungated,
            "vaultable": is_ungated,
            "body_tokens": tokens,
            "frontmatter": {
                "name": tool_metadata["name"],
                "description": description,
            },
        }

    def is_config_with_system_prompt(self, file_path: Path, content: str) -> bool:
        """Check OpenAI JSON/YAML/TOML/.env files for global instructions."""
        if self._is_env_file(file_path):
            return self._env_has_system_prompt(content)

        if self._is_assistant_json(file_path):
            parsed = self._parse_config_content(".json", content)
            return self._assistant_config_has_instructions(parsed)

        return super().is_config_with_system_prompt(file_path, content)

    def has_openai_credentials(self, content: str) -> bool:
        """Check .env-style content for OpenAI credential keys."""
        env = self._parse_env(content)
        credential_keys = {
            "OPENAI_API_KEY",
            "AZURE_OPENAI_API_KEY",
            "OPENAI_PROJECT",
            "OPENAI_ORGANIZATION",
        }
        return any(bool(env.get(key, "").strip()) for key in credential_keys)

    def _should_exclude(self, rel_path: Path) -> bool:
        """Include root .env files while preserving hidden-directory exclusions."""
        if self._is_env_path(rel_path):
            hidden_parent = any(part.startswith(".") and part not in self.config.hidden_dir_whitelist for part in rel_path.parts[:-1])
            return hidden_parent

        return super()._should_exclude(rel_path)

    def _env_files(self):
        for name in (".env", ".env.local", ".env.development", ".env.test"):
            path = self.target_path / name
            if path.exists() and path.is_file():
                yield path

    def _is_env_file(self, file_path: Path) -> bool:
        return self._is_env_path(file_path.relative_to(self.target_path) if file_path.is_absolute() else file_path)

    def _is_env_path(self, path: Path) -> bool:
        return path.name == ".env" or path.name.startswith(".env.")

    def _parse_env(self, content: str) -> Dict[str, str]:
        values: Dict[str, str] = {}
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                values[key] = value

        return values

    def _env_has_system_prompt(self, content: str) -> bool:
        env = self._parse_env(content)
        prompt_keys = {
            "OPENAI_SYSTEM_PROMPT",
            "OPENAI_INSTRUCTIONS",
            "ASSISTANT_INSTRUCTIONS",
            "SYSTEM_PROMPT",
        }
        return any(len(env.get(key, "").strip()) >= 50 for key in prompt_keys)

    def _is_assistant_json(self, file_path: Path) -> bool:
        return file_path.name in {"assistant.json", "assistants.json", "openai.json"}

    def _assistant_config_has_instructions(self, parsed) -> bool:
        if parsed is None:
            return False

        instruction_keys = {
            "instructions",
            "system_prompt",
            "system",
            "developer",
            "prompt",
        }

        def has_instruction_value(value) -> bool:
            return isinstance(value, str) and bool(value.strip())

        def walk(node) -> bool:
            if isinstance(node, dict):
                for key, value in node.items():
                    if isinstance(key, str) and key.lower() in instruction_keys and has_instruction_value(value):
                        return True
                    if walk(value):
                        return True
                return False
            if isinstance(node, list):
                return any(walk(item) for item in node)
            return False

        return walk(parsed)

    def _extract_tool_metadata(self, file_path: Path, content: str) -> Optional[Dict[str, str]]:
        parsed = self._parse_config_content(".json", content)
        if not isinstance(parsed, dict):
            return None

        if "function" in parsed and isinstance(parsed["function"], dict):
            return self._metadata_from_dict(parsed["function"])

        if parsed.get("type") == "function":
            return self._metadata_from_dict(parsed)

        if self._is_tool_path(file_path):
            return self._metadata_from_dict(parsed)

        return None

    def _metadata_from_dict(self, data: Dict) -> Optional[Dict[str, str]]:
        name = data.get("name")
        description = data.get("description")
        if not isinstance(name, str) or not name.strip():
            return None
        if not isinstance(description, str) or not description.strip():
            return None

        return {
            "name": name.strip(),
            "description": description.strip(),
        }

    def _is_tool_path(self, file_path: Path) -> bool:
        try:
            rel_path = file_path.relative_to(self.target_path)
        except ValueError:
            rel_path = file_path

        return any(part in {"tools", "functions", "skills"} for part in rel_path.parts)
