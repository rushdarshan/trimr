import logging
from pathlib import Path
from typing import Set, List, Dict, Optional

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
from .adapters import ClaudeAdapter
from .adapters.base import FrameworkAdapter

logger = logging.getLogger(__name__)


class Auditor:
    def __init__(self, target_path: Path, framework_hint: Optional[str] = None):
        self.target_path = target_path.resolve()
        self.tokenizer = get_tokenizer()
        self.violations: List[Violation] = []
        self.global_files: List[GlobalFileReport] = []
        self.skills: List[SkillReport] = []
        self.framework_hint = framework_hint
        self.adapter = self._detect_and_load_adapter()

    def _detect_and_load_adapter(self) -> FrameworkAdapter:
        """Auto-detect framework and load appropriate adapter.
        
        Detection order: Claude → LangChain → CrewAI → OpenAI → default Claude
        Can be overridden with framework_hint parameter.
        """
        if self.framework_hint:
            adapter_map = {
                'claude': ClaudeAdapter,
                'langchain': self._get_langchain_adapter,
                'crewai': self._get_crewai_adapter,
                'openai': self._get_openai_adapter,
            }
            adapter_class = adapter_map.get(self.framework_hint.lower())
            if adapter_class:
                if adapter_class == ClaudeAdapter:
                    return ClaudeAdapter(self.target_path)
                return adapter_class()
        
        # Auto-detection: try each framework in order
        # First try Claude
        claude_adapter = ClaudeAdapter(self.target_path)
        if claude_adapter.detect_framework():
            logger.info("✓ Detected Claude framework")
            return claude_adapter
        
        # Try other frameworks
        adapter_factories = [
            self._get_langchain_adapter,
            self._get_crewai_adapter,
            self._get_openai_adapter,
        ]
        
        for adapter_factory in adapter_factories:
            try:
                adapter = adapter_factory()
                if adapter.detect_framework():
                    logger.info(f"✓ Detected {adapter.__class__.__name__} framework")
                    return adapter
            except Exception as e:
                logger.debug(f"Error checking {adapter_factory.__name__}: {e}")
        
        # Default to Claude if nothing detected
        logger.debug("No framework detected; defaulting to Claude")
        return ClaudeAdapter(self.target_path)

    def _get_langchain_adapter(self) -> FrameworkAdapter:
        """Lazily import LangChain adapter."""
        try:
            from .adapters.langchain_adapter import LangChainAdapter
            return LangChainAdapter(self.target_path)
        except ImportError:
            logger.debug("LangChain adapter not available")
            return ClaudeAdapter(self.target_path)

    def _get_crewai_adapter(self) -> FrameworkAdapter:
        """Lazily import CrewAI adapter."""
        try:
            from .adapters.crewai_adapter import CrewAIAdapter
            return CrewAIAdapter(self.target_path)
        except ImportError:
            logger.debug("CrewAI adapter not available")
            return ClaudeAdapter(self.target_path)

    def _get_openai_adapter(self) -> FrameworkAdapter:
        """Lazily import OpenAI adapter."""
        try:
            from .adapters.openai_adapter import OpenAIAdapter
            return OpenAIAdapter(self.target_path)
        except ImportError:
            logger.debug("OpenAI adapter not available")
            return ClaudeAdapter(self.target_path)

    def walk_files(self) -> List[Path]:
        """Recursively walk target directory, respecting exclusions."""
        return self.adapter.walk_files()

    def audit(self) -> AuditResult:
        """Run full audit on target directory."""
        if not self.target_path.exists():
            raise FileNotFoundError(f"Target path does not exist: {self.target_path}")

        files = self.walk_files()
        
        for file_path in files:
            self._audit_file(file_path)
        
        self._compute_violations()
        
        # Check if this looks like a Claude/Cursor project
        if not self.adapter.detect_framework():
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
        
        # Check markdown files
        if suffix in [".md", ".markdown"]:
            self._check_non_ascii(file_path, content)
            
            if self.adapter.is_global_instruction_file(file_path):
                self.global_files.append(GlobalFileReport(path=str(rel_path), tokens=tokens))
            
            if is_skill_file(file_path, content):
                frontmatter = extract_frontmatter(content)
                body = extract_skill_body(content)
                body_tokens = self.tokenizer.count_tokens(body)
                desc = get_skill_description(frontmatter)
                is_pointer = self.adapter.is_pointer_file(content)
                is_ungated = not self.adapter.is_in_vault(rel_path) and not is_pointer
                
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
                self.violations.append(
                    Violation(
                        file=str(rel_path),
                        code=ViolationCode.MALFORMED_FRONTMATTER,
                        detail="Frontmatter delimiter (---) not on line 1. Expected format: --- at line 1, then YAML, then --- to close.",
                        severity=ViolationSeverity.WARN,
                    )
                )
            elif "skills" in rel_path.parts and not self.adapter.is_pointer_file(content):
                self.violations.append(
                    Violation(
                        file=str(rel_path),
                        code=ViolationCode.NO_FRONTMATTER,
                        severity=ViolationSeverity.WARN,
                        detail="Skill file in skills/ directory missing YAML frontmatter",
                    )
                )
        
        # Check config files for system prompts
        elif suffix in self.adapter.config.config_files_with_system_prompts:
            if self.adapter.is_config_with_system_prompt(file_path, content):
                self.global_files.append(
                    GlobalFileReport(
                        path=str(rel_path),
                        tokens=tokens,
                        note=f"Config file with system prompt ({suffix})"
                    )
                )
    
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
