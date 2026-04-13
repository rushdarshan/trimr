"""Claude Code framework adapter."""

from pathlib import Path
from typing import Optional, Dict, Set
from .base import FrameworkAdapter, AdapterConfig
from ..parser import (
    has_frontmatter,
    is_skill_file as parser_is_skill_file,
    extract_frontmatter,
    extract_skill_body,
    get_skill_description,
    get_skill_name,
)


CLAUDE_CONFIG = AdapterConfig(
    framework_name="claude",
    global_instruction_files={
        "CLAUDE.md",
        "AGENTS.md",
        ".cursorrules",
        ".codesandbox",
        ".codestudio",
        "INSTRUCTIONS.md",
        "SYSTEM.md",
        ".instructions.md",
        ".prompt.md",
    },
    config_files_with_system_prompts={
        ".json": ["prompts", "config", "agents", "system", "instructions"],
        ".yaml": ["prompts", "config", "agents", "system", "instructions"],
        ".yml": ["prompts", "config", "agents", "system", "instructions"],
        ".toml": ["prompts", "config", "agents", "system", "instructions"],
    },
    vault_dirs={".vault", "vault", "_vault"},
    pointer_file_markers={
        "load_skill", "skill_id", "list_dir", "ls",
        "view_file", "read_file", "cat",
    },
    hidden_dir_whitelist={".claude", ".cursor", ".agents", ".vault", ".anthropic"},
)


class ClaudeAdapter(FrameworkAdapter):
    """Adapter for Claude Code projects."""
    
    def __init__(self, target_path: Path):
        """Initialize Claude adapter."""
        super().__init__(target_path, CLAUDE_CONFIG)
    
    def detect_framework(self) -> bool:
        """Check if target is a Claude Code project."""
        return any([
            (self.target_path / "CLAUDE.md").exists(),
            (self.target_path / ".claude").exists(),
            (self.target_path / ".cursor").exists(),
            (self.target_path / ".agents").exists(),
        ])
    
    def is_skill_file(self, file_path: Path, content: str) -> bool:
        """Check if file is a Claude skill file."""
        return parser_is_skill_file(file_path, content)
    
    def get_global_files(self, file_path: Path, content: str) -> Optional[Dict]:
        """Extract global file info for Claude."""
        if self.is_global_instruction_file(file_path):
            return {"type": "markdown"}
        
        suffix = file_path.suffix.lower()
        if suffix in self.config.config_files_with_system_prompts:
            if self.is_config_with_system_prompt(file_path, content):
                return {"type": "config", "subtype": suffix}
        
        return None
    
    def get_skill_info(self, file_path: Path, content: str, tokens: int) -> Optional[Dict]:
        """Extract skill info for Claude."""
        if not self.is_skill_file(file_path, content):
            return None
        
        frontmatter = extract_frontmatter(content)
        body = extract_skill_body(content)
        
        # Tokenizer needs to be passed in or handled at audit level
        desc = get_skill_description(frontmatter)
        name = get_skill_name(frontmatter)
        
        rel_path = file_path.relative_to(self.target_path)
        is_ungated = not self.is_in_vault(rel_path)
        
        return {
            "name": name,
            "description": desc,
            "description_length": len(desc),
            "ungated": is_ungated,
            "vaultable": is_ungated,
            "body_tokens": 0,  # Will be calculated by auditor
            "frontmatter": frontmatter,
        }
