import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict
import shutil

from .models import AuditResult, SkillReport, GlobalFileReport
from .tokenizer import get_tokenizer
from .parser import extract_frontmatter, extract_skill_body

logger = logging.getLogger(__name__)

VAULT_DIRS = {".vault", "vault", "_vault"}


@dataclass
class MigrationChange:
    """Represents a single file change during migration."""
    change_type: str  # "skill_moved", "pointer_created", "global_truncated"
    source: str
    target: Optional[str] = None
    tokens_saved: int = 0
    reason: str = ""


@dataclass
class MigrationPlan:
    """Tracks all intended changes during migration."""
    target_path: Path
    changes: List[MigrationChange] = field(default_factory=list)
    total_tokens_saved: int = 0
    dry_run: bool = False
    
    def add_change(self, change: MigrationChange) -> None:
        self.changes.append(change)
        self.total_tokens_saved += change.tokens_saved


class Migrator:
    """Handles migration of ungated skills to .vault/ and truncation of bloated globals."""
    
    def __init__(self, target_path: Path, dry_run: bool = False):
        self.target_path = target_path.resolve()
        self.dry_run = dry_run
        self.tokenizer = get_tokenizer()
        self.plan = MigrationPlan(target_path=self.target_path, dry_run=dry_run)
    
    def migrate(self, audit_result: AuditResult) -> MigrationPlan:
        """Execute migration based on audit results."""
        # Step 1: Migrate ungated skills (only if they save tokens when moved)
        for skill in audit_result.skills:
            if skill.ungated and skill.vaultable and skill.has_frontmatter:
                # Only migrate if the skill is large enough to benefit
                # Pointer file is typically 50-100 tokens, so only migrate if skill > 150 tokens
                if skill.tokens > 150:
                    self._migrate_skill(skill)
        
        # Step 2: Truncate global files that exceed limit
        for global_file in audit_result.global_files:
            if global_file.over_limit:
                self._truncate_global_file(global_file)
        
        return self.plan
    
    def _migrate_skill(self, skill: SkillReport) -> None:
        """Move a skill file to .vault/skills/ and create pointer file."""
        source_path = self.target_path / skill.path
        
        if not source_path.exists():
            logger.warning(f"Skill file not found: {skill.path}")
            return
        
        # Read skill content
        try:
            content = source_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read skill: {skill.path}: {e}")
            return
        
        # Extract skill name from frontmatter
        from .parser import extract_frontmatter
        frontmatter_dict = extract_frontmatter(content)
        skill_name = skill.name if skill.name else (frontmatter_dict.get("name", "") if frontmatter_dict else "")
        if not skill_name:
            skill_name = Path(skill.path).stem
        
        # Determine vault location (.vault/skills/category/SKILL.md)
        rel_parent = source_path.parent
        vault_parent = self.target_path / ".vault" / "skills" / rel_parent.name
        vault_path = vault_parent / "SKILL.md"
        
        # Create pointer file content
        pointer_content = self._create_pointer_file(skill_name, vault_path)
        pointer_tokens = self.tokenizer.count_tokens(pointer_content)
        
        if not self.dry_run:
            # Create vault directory structure
            vault_parent.mkdir(parents=True, exist_ok=True)
            
            # Move skill to vault
            shutil.move(str(source_path), str(vault_path))
            logger.info(f"Moved {skill.path} → {vault_path.relative_to(self.target_path)}")
            
            # Create pointer file in original location
            source_path.write_text(pointer_content, encoding="utf-8")
            logger.info(f"Created pointer file at {skill.path}")
        
        # Record changes
        tokens_saved = skill.tokens - pointer_tokens
        
        change = MigrationChange(
            change_type="skill_moved",
            source=skill.path,
            target=str(vault_path.relative_to(self.target_path)),
            tokens_saved=tokens_saved,
            reason=f"Ungated skill: {tokens_saved} tokens saved (was {skill.tokens}, now {pointer_tokens} pointer)"
        )
        self.plan.add_change(change)
    
    def _create_pointer_file(self, skill_name: str, vault_path: Path) -> str:
        """Generate pointer file content with load_skill instruction."""
        vault_rel = vault_path.relative_to(self.target_path)
        
        # Construct pointer file with YAML frontmatter
        content = f"""---
name: {skill_name} (pointer)
description: Load {skill_name} from vault. Managed by trimr migrate.
---

This skill has been migrated to progressive-disclosure architecture.

Use the load_skill instruction:

```
load_skill(".vault/skills/{vault_rel.parent.name}/SKILL.md")
```

Or reference directly via skill_id: {skill_name.lower().replace(' ', '_')}
"""
        return content.strip() + "\n"
    
    def _truncate_global_file(self, global_file: GlobalFileReport) -> None:
        """Truncate global file to <3000 tokens while preserving frontmatter."""
        file_path = self.target_path / global_file.path
        
        if not file_path.exists():
            logger.warning(f"Global file not found: {global_file.path}")
            return
        
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read global file: {global_file.path}: {e}")
            return
        
        # Extract frontmatter to preserve it
        frontmatter_dict = extract_frontmatter(content)
        frontmatter_lines = []
        
        if frontmatter_dict:
            # Reconstruct YAML frontmatter
            import yaml
            frontmatter_lines = [
                "---",
                yaml.dump(frontmatter_dict, default_flow_style=False).strip(),
                "---",
                ""
            ]
        
        # Extract body (after frontmatter)
        if content.startswith("---"):
            end_fm = content.find("\n---\n", 4)
            if end_fm != -1:
                body = content[end_fm + 5:]
            else:
                body = content
        else:
            body = content
        
        # Truncate body to fit within 3000 tokens total
        frontmatter_text = "\n".join(frontmatter_lines)
        frontmatter_tokens = self.tokenizer.count_tokens(frontmatter_text)
        
        available_body_tokens = 3000 - frontmatter_tokens - 100  # Leave margin
        if available_body_tokens <= 0:
            available_body_tokens = 500  # Minimum body size
        
        # Estimate where to truncate (rough approximation)
        truncated_body = self._truncate_to_tokens(body, available_body_tokens)
        truncated_body += "\n\n[... truncated by trimr. Run `trimr migrate --help` for migration details ...]\n"
        
        new_content = frontmatter_text + truncated_body
        
        if not self.dry_run:
            file_path.write_text(new_content, encoding="utf-8")
            logger.info(f"Truncated {global_file.path} to <3000 tokens")
        
        # Calculate tokens saved
        tokens_after = self.tokenizer.count_tokens(new_content)
        tokens_saved = global_file.tokens - tokens_after
        
        change = MigrationChange(
            change_type="global_truncated",
            source=global_file.path,
            tokens_saved=tokens_saved,
            reason=f"Global file exceeded 3000 token limit by {global_file.excess} tokens"
        )
        self.plan.add_change(change)
    
    def _truncate_to_tokens(self, text: str, target_tokens: int) -> str:
        """Truncate text to approximately target token count."""
        if self.tokenizer.count_tokens(text) <= target_tokens:
            return text
        
        # Rough heuristic: truncate by character count
        # Assumes ~4 chars per token on average
        target_chars = int(target_tokens * 4)
        
        # Find last sentence or paragraph boundary
        truncated = text[:target_chars]
        
        # Try to end at a paragraph or sentence boundary
        last_newline = truncated.rfind("\n\n")
        if last_newline > target_chars * 0.8:  # If close to target
            truncated = truncated[:last_newline]
        else:
            last_sentence = truncated.rfind(". ")
            if last_sentence > target_chars * 0.8:
                truncated = truncated[:last_sentence + 1]
        
        return truncated.rstrip()
