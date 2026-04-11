import logging
from pathlib import Path
from typing import Set, List, Dict, Optional
import pathspec

from .tokenizer import get_tokenizer
from .parser import (
    has_frontmatter,
    has_malformed_frontmatter,
    extract_frontmatter,
    is_skill_file,
    extract_skill_body,
    get_skill_description,
    get_skill_name,
)
from .models import (
    AuditResult,
    GlobalFileReport,
    SkillReport,
    Violation,
    ViolationCode,
    ViolationSeverity,
)

logger = logging.getLogger(__name__)

GLOBAL_INSTRUCTION_FILES = {
    "CLAUDE.md",
    "AGENTS.md",
    ".cursorrules",
    ".codesandbox",
    ".codestudio",
    "INSTRUCTIONS.md",
    "SYSTEM.md",
    ".instructions.md",
    ".prompt.md",
}

CONFIG_FILES_WITH_SYSTEM_PROMPTS = {
    ".json": ["prompts", "config", "agents", "system", "instructions"],
    ".yaml": ["prompts", "config", "agents", "system", "instructions"],
    ".yml": ["prompts", "config", "agents", "system", "instructions"],
    ".toml": ["prompts", "config", "agents", "system", "instructions"],
}

HARDCODED_EXCLUSIONS = {
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    "site-packages",
}

VAULT_DIRS = {".vault", "vault", "_vault"}
POINTER_FILE_MARKERS = {
    "load_skill",
    "skill_id",
    "list_dir",
    "ls",
    "view_file",
    "read_file",
    "cat",
}


class Auditor:
    def __init__(self, target_path: Path):
        self.target_path = target_path.resolve()
        self.tokenizer = get_tokenizer()
        self.violations: List[Violation] = []
        self.global_files: List[GlobalFileReport] = []
        self.skills: List[SkillReport] = []
        self.pathspec_obj: Optional[pathspec.PathSpec] = None
        self._load_gitignore()

    def _load_gitignore(self) -> None:
        """Load .gitignore patterns if present."""
        gitignore_path = self.target_path / ".gitignore"
        if gitignore_path.exists():
            try:
                patterns = gitignore_path.read_text(encoding="utf-8", errors="replace").strip().split("\n")
                self.pathspec_obj = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
            except Exception as e:
                logger.warning(f"[WARN] Failed to parse .gitignore: {e}")

    def _should_exclude(self, rel_path: Path) -> bool:
        """Check if path should be excluded based on hardcoded rules and .gitignore."""
        parts = rel_path.parts
        
        for part in parts:
            if part.startswith(".") and part not in {".claude", ".cursor", ".agents", ".vault", ".anthropic"}:
                return True
            if part in HARDCODED_EXCLUSIONS:
                return True
        
        if self.pathspec_obj:
            if self.pathspec_obj.match_file(str(rel_path)):
                return True
        
        return False

    def _is_pointer_file(self, content: str) -> bool:
        """Check if file contains pointer file markers."""
        return any(marker in content for marker in POINTER_FILE_MARKERS)

    def _is_in_vault(self, rel_path: Path) -> bool:
        """Check if file is within a vault directory."""
        for vault_dir in VAULT_DIRS:
            if vault_dir in rel_path.parts:
                return True
        return False

    def _is_ungated_skill(self, rel_path: Path, skill_path: Path) -> bool:
        """Check if skill is ungated (outside vault, not referenced via pointer)."""
        if self._is_in_vault(rel_path):
            return False
        
        return True

    def walk_files(self) -> List[Path]:
        """Recursively walk target directory, respecting exclusions."""
        result = []
        try:
            for path in self.target_path.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    rel_path = path.relative_to(self.target_path)
                    if not self._should_exclude(rel_path):
                        result.append(path)
        except Exception as e:
            logger.error(f"Error walking directory: {e}")
        return result

    def audit(self) -> AuditResult:
        """Run full audit on target directory."""
        if not self.target_path.exists():
            raise FileNotFoundError(f"Target path does not exist: {self.target_path}")

        files = self.walk_files()
        
        for file_path in files:
            self._audit_file(file_path)
        
        self._compute_violations()
        
        # Check if this looks like a Claude/Cursor project
        has_claude_structure = any([
            (self.target_path / "CLAUDE.md").exists(),
            (self.target_path / ".claude").exists(),
            (self.target_path / ".cursor").exists(),
            (self.target_path / ".agents").exists(),
        ])
        
        if not has_claude_structure:
            logger.warning("⚠  No Claude/Cursor project structure detected. Results may be incomplete.")
        
        current_tokens = self._calculate_current_startup_tokens()
        projected_tokens = self._calculate_projected_startup_tokens()
        reduction = 0.0
        if current_tokens > 0:
            reduction = ((current_tokens - projected_tokens) / current_tokens) * 100

        return AuditResult(
            path=str(self.target_path),
            startup_tokens_current=current_tokens,
            startup_tokens_projected=projected_tokens,
            reduction_percent=reduction,
            global_files=self.global_files,
            skills=self.skills,
            violations=self.violations,
        )

    def _audit_file(self, file_path: Path) -> None:
        """Audit a single file: markdown, config files with system prompts, etc."""
        rel_path = file_path.relative_to(self.target_path)
        suffix = file_path.suffix.lower()
        
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning(f"[WARN] Skipping non-UTF-8 file: {rel_path} (not valid UTF-8 encoding)")
            return
        except Exception as e:
            logger.warning(f"[WARN] Failed to read {rel_path}: {e}")
            return
        
        tokens = self.tokenizer.count_tokens(content)
        
        # Check markdown files (original behavior)
        if suffix in [".md", ".markdown"]:
            self._check_non_ascii(file_path, content)
            
            if file_path.name in GLOBAL_INSTRUCTION_FILES:
                self.global_files.append(GlobalFileReport(path=str(rel_path), tokens=tokens))
            
            if is_skill_file(file_path, content):
                frontmatter = extract_frontmatter(content)
                body = extract_skill_body(content)
                body_tokens = self.tokenizer.count_tokens(body)
                desc = get_skill_description(frontmatter)
                is_ungated = self._is_ungated_skill(rel_path, file_path)
                
                skill_report = SkillReport(
                    path=str(rel_path),
                    name=get_skill_name(frontmatter),
                    body_tokens=body_tokens,
                    tokens=tokens,
                    has_frontmatter=True,
                    description_length=len(desc),
                    ungated=is_ungated,
                    vaultable=is_ungated,
                )
                self.skills.append(skill_report)
            elif has_frontmatter(content):
                self.violations.append(
                    Violation(
                        file=str(rel_path),
                        code=ViolationCode.MALFORMED_FRONTMATTER,
                        detail="Frontmatter found but missing required 'name' or 'description' field",
                        severity=ViolationSeverity.INFO,
                    )
                )
            elif has_malformed_frontmatter(content):
                # Flaw 5 fix: Detect malformed frontmatter and still count tokens
                self.violations.append(
                    Violation(
                        file=str(rel_path),
                        code=ViolationCode.MALFORMED_FRONTMATTER,
                        detail="Frontmatter delimiter (---) not on line 1. Expected format: --- at line 1, then YAML, then --- to close.",
                        severity=ViolationSeverity.WARN,
                    )
                )
            elif "skills" in rel_path.parts:
                # File is in skills/ but has no frontmatter
                self.violations.append(
                    Violation(
                        file=str(rel_path),
                        code=ViolationCode.NO_FRONTMATTER,
                        severity=ViolationSeverity.WARN,
                        detail="Skill file in skills/ directory missing YAML frontmatter",
                    )
                )
        
        # Check config files for system prompts (Flaw 3 fix)
        elif suffix in CONFIG_FILES_WITH_SYSTEM_PROMPTS:
            if self._is_config_with_system_prompt(file_path, content):
                self.global_files.append(
                    GlobalFileReport(
                        path=str(rel_path),
                        tokens=tokens,
                        note=f"Config file with system prompt ({suffix})"
                    )
                )
        
    def _is_config_with_system_prompt(self, file_path: Path, content: str) -> bool:
        """Check if config file contains system prompts or agent instructions."""
        suffix = file_path.suffix.lower()
        basename = file_path.stem.lower()
        
        # Check filename heuristics
        for keyword in CONFIG_FILES_WITH_SYSTEM_PROMPTS.get(suffix, []):
            if keyword in basename:
                return True
        
        # Check content for system prompt keys
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
        
        content_lower = content.lower()
        for key in system_prompt_keys:
            if f'"{key}"' in content_lower or f"'{key}'" in content_lower or f"{key}:" in content_lower:
                return True
        
        return False
    
    def _check_non_ascii(self, file_path: Path, content: str) -> None:
        """Check for high non-ASCII character ratio."""
        if not content:
            return
        
        non_ascii_count = sum(1 for c in content if ord(c) > 127)
        ratio = non_ascii_count / len(content)
        
        if ratio > 0.2:
            rel_path = file_path.relative_to(self.target_path)
            self.violations.append(
                Violation(
                    code=ViolationCode.NON_ASCII_ESTIMATE,
                    severity=ViolationSeverity.INFO,
                    file=str(rel_path),
                    detail=f"{ratio*100:.1f}% non-ASCII characters; token count may be understated",
                )
            )

    def _compute_violations(self) -> None:
        """Compute all violations."""
        cumulative_global_tokens = sum(g.tokens for g in self.global_files)
        
        for global_file in self.global_files:
            if global_file.tokens > 3000:
                global_file.over_limit = True
                global_file.excess = global_file.tokens - 3000
                self.violations.append(
                    Violation(
                        code=ViolationCode.GLOBAL_BLOAT,
                        severity=ViolationSeverity.CRITICAL,
                        file=global_file.path,
                        detail=f"Exceeds 3000 token limit by {global_file.excess} tokens",
                    )
                )
        
        if cumulative_global_tokens > 3000:
            self.violations.append(
                Violation(
                    code=ViolationCode.CUMULATIVE_GLOBAL_BLOAT,
                    severity=ViolationSeverity.CRITICAL,
                    file="(all global files)",
                    detail=f"Cumulative global files exceed 3000 tokens by {cumulative_global_tokens - 3000} tokens",
                )
            )
        
        for skill in self.skills:
            if skill.ungated:
                self.violations.append(
                    Violation(
                        code=ViolationCode.SKILL_UNGATED,
                        severity=ViolationSeverity.WARN,
                        file=skill.path,
                        detail="Ungated skill eligible for migration to .vault/",
                    )
                )
            
            if skill.description_length < 10:
                self.violations.append(
                    Violation(
                        code=ViolationCode.EMPTY_DESCRIPTION,
                        severity=ViolationSeverity.WARN,
                        file=skill.path,
                        detail=f"Description is {skill.description_length} chars; routing may fail",
                    )
                )
            
            if skill.body_tokens > 5000:
                self.violations.append(
                    Violation(
                        code=ViolationCode.SKILL_BODY_LARGE,
                        severity=ViolationSeverity.INFO,
                        file=skill.path,
                        detail=f"Skill body is {skill.body_tokens} tokens (>5000 recommended limit)",
                    )
                )

    def _calculate_current_startup_tokens(self) -> int:
        """Calculate current startup token cost (global + ungated skills)."""
        global_tokens = sum(g.tokens for g in self.global_files)
        ungated_tokens = sum(s.tokens for s in self.skills if s.ungated)
        return global_tokens + ungated_tokens

    def _calculate_projected_startup_tokens(self) -> int:
        """
        Calculate projected startup cost after migration.
        
        Progressive-disclosure architecture:
        - Global files: loaded at startup (unchanged)
        - Vaulted skills: L1 metadata only (~100 tokens per skill for name+description)
        
        Formula: global_tokens + (vaultable_skill_count × 100)
        """
        global_tokens = sum(g.tokens for g in self.global_files)
        vaultable_skill_count = sum(1 for s in self.skills if s.vaultable)
        l1_metadata_tokens = vaultable_skill_count * 100
        return global_tokens + l1_metadata_tokens
