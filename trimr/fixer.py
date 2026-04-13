import logging
import re
import shutil
from pathlib import Path
from typing import Optional, Set

import yaml

from .models import AuditResult, SkillReport, ViolationCode
from .migrator import MigrationChange, MigrationPlan
from .parser import extract_frontmatter, get_skill_description, get_skill_name
from .tokenizer import get_tokenizer

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


class Fixer:
    def __init__(self, target_path: Path, dry_run: bool = False, auto: bool = True):
        self.target_path = target_path.resolve()
        self.dry_run = dry_run
        self.auto = auto
        self.tokenizer = get_tokenizer()
        self.plan = MigrationPlan(target_path=self.target_path, dry_run=dry_run)
        self._reserved_vault_paths: Set[Path] = set()

    def fix(self, audit_result: AuditResult) -> MigrationPlan:
        if not self.auto:
            return self.plan

        handled_paths: Set[Path] = set()

        # Migrate existing valid skills first so that vault-collision handling
        # is deterministic (e.g. when a vaulted orphan also needs frontmatter).
        for skill in audit_result.skills:
            rel_path = Path(skill.path)
            if rel_path in handled_paths:
                continue

            if self._should_migrate_skill(skill, rel_path):
                self._migrate_skill(skill)
                handled_paths.add(rel_path)

        for violation in audit_result.violations:
            if violation.code != ViolationCode.NO_FRONTMATTER:
                continue

            rel_path = Path(violation.file)
            if rel_path in handled_paths:
                continue

            self._fix_orphan_markdown(rel_path)
            handled_paths.add(rel_path)

        return self.plan

    def _fix_orphan_markdown(self, rel_path: Path) -> None:
        source_path = self._resolve_target_file(rel_path)
        if source_path is None:
            return

        try:
            content = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.error(f"Failed to read {rel_path}: file is not valid UTF-8")
            return
        except Exception as e:
            logger.error(f"Failed to read {rel_path}: {e}")
            return

        if self._is_pointer_file(content):
            return

        name = self._infer_skill_name(rel_path, content)
        description = self._infer_description(name, content)
        fixed_content = self._add_frontmatter(content, name, description)

        self._record_frontmatter_added(rel_path, name)

        if self._is_in_vault(rel_path):
            if not self.dry_run:
                source_path.write_text(fixed_content, encoding="utf-8")
            return

        self._migrate_content(
            rel_path=rel_path,
            content=fixed_content,
            skill_name=name,
            description=description,
            original_tokens=self.tokenizer.count_tokens(content),
        )

    def _migrate_skill(self, skill: SkillReport) -> None:
        rel_path = Path(skill.path)
        source_path = self._resolve_target_file(rel_path)
        if source_path is None:
            return

        try:
            content = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.error(f"Failed to read {rel_path}: file is not valid UTF-8")
            return
        except Exception as e:
            logger.error(f"Failed to read {rel_path}: {e}")
            return

        frontmatter = extract_frontmatter(content)
        skill_name = skill.name or get_skill_name(frontmatter) or self._infer_skill_name(rel_path, content)
        description = get_skill_description(frontmatter) or self._infer_description(skill_name, content)

        self._migrate_content(
            rel_path=rel_path,
            content=content,
            skill_name=skill_name,
            description=description,
            original_tokens=skill.tokens,
        )

    def _migrate_content(
        self,
        rel_path: Path,
        content: str,
        skill_name: str,
        description: str,
        original_tokens: int,
    ) -> None:
        source_path = self._resolve_target_file(rel_path)
        if source_path is None:
            return

        vault_path = self._next_available_vault_path(rel_path)
        pointer_content = self._create_pointer_file(skill_name, description, vault_path)
        pointer_tokens = self.tokenizer.count_tokens(pointer_content)

        if not self.dry_run:
            vault_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, vault_path)
            vault_path.write_text(content, encoding="utf-8")
            source_path.write_text(pointer_content, encoding="utf-8")

        tokens_saved = max(original_tokens - pointer_tokens, 0)
        self.plan.add_change(
            MigrationChange(
                change_type="skill_moved",
                source=str(rel_path),
                target=str(vault_path.relative_to(self.target_path)),
                tokens_saved=tokens_saved,
                reason=f"Moved ungated skill to vault and left a pointer file ({pointer_tokens} pointer tokens)",
            )
        )

    def _should_migrate_skill(self, skill: SkillReport, rel_path: Path) -> bool:
        if not skill.has_frontmatter or not skill.ungated or not skill.vaultable:
            return False
        if self._is_in_vault(rel_path):
            return False
        if self._is_global_instruction_file(rel_path):
            return False

        source_path = self._resolve_target_file(rel_path)
        if source_path is None:
            return False

        try:
            content = source_path.read_text(encoding="utf-8")
        except Exception:
            return False

        return not self._is_pointer_file(content)

    def _record_frontmatter_added(self, rel_path: Path, skill_name: str) -> None:
        self.plan.add_change(
            MigrationChange(
                change_type="frontmatter_added",
                source=str(rel_path),
                tokens_saved=0,
                reason=f"Added generated name and description for {skill_name}",
            )
        )

    def _resolve_target_file(self, rel_path: Path) -> Optional[Path]:
        if rel_path.is_absolute():
            logger.error(f"Refusing to fix absolute path outside target: {rel_path}")
            return None

        file_path = (self.target_path / rel_path).resolve()
        try:
            file_path.relative_to(self.target_path)
        except ValueError:
            logger.error(f"Refusing to fix path outside target: {rel_path}")
            return None

        if not file_path.exists() or not file_path.is_file():
            logger.warning(f"File not found: {rel_path}")
            return None

        return file_path

    def _is_pointer_file(self, content: str) -> bool:
        return any(
            re.search(rf"(?<![A-Za-z0-9_]){re.escape(marker)}(?![A-Za-z0-9_])", content)
            for marker in POINTER_FILE_MARKERS
        )

    def _is_in_vault(self, rel_path: Path) -> bool:
        return any(part in VAULT_DIRS for part in rel_path.parts)

    def _is_global_instruction_file(self, rel_path: Path) -> bool:
        return rel_path.name in GLOBAL_INSTRUCTION_FILES

    def _next_available_vault_path(self, rel_path: Path) -> Path:
        vault_path = self._vault_path_for(rel_path)
        if not vault_path.exists() and vault_path not in self._reserved_vault_paths:
            self._reserved_vault_paths.add(vault_path)
            return vault_path

        for index in range(2, 1000):
            candidate = self._vault_collision_candidate(vault_path, index)
            if not candidate.exists() and candidate not in self._reserved_vault_paths:
                self._reserved_vault_paths.add(candidate)
                return candidate

        raise RuntimeError(f"Unable to find available vault path for {rel_path}")

    def _vault_path_for(self, rel_path: Path) -> Path:
        parts = rel_path.parts
        if "skills" in parts:
            skill_root_index = parts.index("skills")
            tail_parts = parts[skill_root_index + 1 :]
            tail = Path(*tail_parts) if tail_parts else Path(rel_path.name)
            return self.target_path / ".vault" / "skills" / tail

        slug = self._slugify(rel_path.stem)
        return self.target_path / ".vault" / "skills" / slug / rel_path.name

    def _vault_collision_candidate(self, vault_path: Path, index: int) -> Path:
        if vault_path.name == "SKILL.md":
            return vault_path.parent.with_name(f"{vault_path.parent.name}-{index}") / vault_path.name

        return vault_path.with_name(f"{vault_path.stem}-{index}{vault_path.suffix}")

    def _create_pointer_file(self, skill_name: str, description: str, vault_path: Path) -> str:
        vault_rel = vault_path.relative_to(self.target_path).as_posix()
        frontmatter = {
            "name": skill_name,
            "description": self._pointer_description(skill_name, description),
        }
        frontmatter_yaml = yaml.safe_dump(
            frontmatter,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        ).strip()

        return (
            f"---\n{frontmatter_yaml}\n---\n\n"
            f'This skill is stored in the vault. Use `load_skill("{vault_rel}")` when this workflow is needed.\n'
        )

    def _pointer_description(self, skill_name: str, description: str) -> str:
        if description:
            return f"Pointer for {skill_name}: {description}"
        return f"Pointer for {skill_name}; loads the vaulted skill on demand."

    def _add_frontmatter(self, content: str, name: str, description: str) -> str:
        frontmatter = {
            "name": name,
            "description": description,
        }
        frontmatter_yaml = yaml.safe_dump(
            frontmatter,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        ).strip()

        return f"---\n{frontmatter_yaml}\n---\n\n{content}"

    def _infer_skill_name(self, rel_path: Path, content: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return self._clean_text(stripped[2:]) or self._fallback_name(rel_path)

        return self._fallback_name(rel_path)

    def _fallback_name(self, rel_path: Path) -> str:
        if rel_path.stem.lower() in {"skill", "readme", "index"} and rel_path.parent.name:
            return self._humanize(rel_path.parent.name)
        return self._humanize(rel_path.stem)

    def _infer_description(self, name: str, content: str) -> str:
        for line in content.splitlines():
            stripped = self._clean_text(line)
            if not stripped or stripped.startswith("#") or stripped == "---":
                continue
            if len(stripped) >= 10:
                return stripped[:180]

        return f"Skill instructions for {name}."

    def _humanize(self, value: str) -> str:
        cleaned = re.sub(r"[_\-]+", " ", value).strip()
        if not cleaned:
            return "Generated Skill"
        return " ".join(word.capitalize() for word in cleaned.split())

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
        return slug or "skill"

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()
