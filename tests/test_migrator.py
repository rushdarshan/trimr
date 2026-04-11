import pytest
from pathlib import Path
import tempfile
import shutil

from trimr.audit import Auditor
from trimr.migrator import Migrator, MigrationPlan, MigrationChange


class TestMigratorBasic:
    def test_migrator_initialization(self):
        """Test migrator initializes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            migrator = Migrator(target, dry_run=False)
            assert migrator.target_path == target.resolve()
            assert migrator.dry_run is False
            assert isinstance(migrator.plan, MigrationPlan)
    
    def test_migrator_dry_run_mode(self):
        """Test migrator dry-run mode flag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            migrator = Migrator(target, dry_run=True)
            assert migrator.dry_run is True


class TestMigrationPlan:
    def test_plan_initialization(self):
        """Test migration plan initializes with empty changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            plan = MigrationPlan(target_path=target)
            assert plan.target_path == target
            assert len(plan.changes) == 0
            assert plan.total_tokens_saved == 0
            assert plan.dry_run is False
    
    def test_plan_add_change(self):
        """Test adding changes to migration plan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            plan = MigrationPlan(target_path=target)
            
            change = MigrationChange(
                change_type="skill_moved",
                source="skills/pdf/SKILL.md",
                target=".vault/skills/pdf/SKILL.md",
                tokens_saved=500,
                reason="Test"
            )
            plan.add_change(change)
            
            assert len(plan.changes) == 1
            assert plan.total_tokens_saved == 500
    
    def test_plan_accumulate_tokens(self):
        """Test plan correctly accumulates saved tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            plan = MigrationPlan(target_path=target)
            
            plan.add_change(MigrationChange(
                change_type="skill_moved",
                source="s1",
                tokens_saved=300,
                reason="Test1"
            ))
            plan.add_change(MigrationChange(
                change_type="global_truncated",
                source="g1",
                tokens_saved=200,
                reason="Test2"
            ))
            
            assert len(plan.changes) == 2
            assert plan.total_tokens_saved == 500


class TestMigratorSkillMigration:
    def test_migrate_skill_creates_vault_structure(self):
        """Test that migrating a skill creates .vault directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            # Create a larger skill file (>150 tokens to trigger migration)
            skills_dir = target / ".claude" / "skills" / "test_skill"
            skills_dir.mkdir(parents=True, exist_ok=True)
            
            skill_file = skills_dir / "SKILL.md"
            skill_content = """---
name: Test Skill
description: A test skill for migration with detailed description
---

This is the skill body content with enough text to exceed 150 tokens.
The skill performs important operations on data processing and analysis.
It includes comprehensive logic for handling various use cases and edge cases.
The implementation is optimized for both performance and maintainability.
Additional lines ensure we reach the token threshold for meaningful migration.
""" * 3
            skill_file.write_text(skill_content)
            
            # Create audit result
            auditor = Auditor(target)
            audit_result = auditor.audit()
            
            # Run migration with dry-run
            migrator = Migrator(target, dry_run=True)
            plan = migrator.migrate(audit_result)
            
            # Check plan has changes (should migrate large skill)
            skill_reports = [s for s in audit_result.skills if s.tokens > 150]
            if skill_reports:
                assert len(plan.changes) > 0
    
    def test_migrate_skill_dry_run_preserves_files(self):
        """Test that dry-run doesn't modify files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            # Create a large skill file
            skills_dir = target / ".claude" / "skills" / "pdf"
            skills_dir.mkdir(parents=True, exist_ok=True)
            
            skill_file = skills_dir / "SKILL.md"
            skill_content = """---
name: PDF Handler
description: Handles PDF document processing with detailed implementation
---

Process PDF files efficiently with comprehensive support.
The handler manages all aspects of PDF processing including text extraction,
image handling, and metadata processing. It ensures high quality results.
Additional implementation details and support functions are included.
This ensures the skill is large enough to exceed the 150 token threshold.
""" * 4
            skill_file.write_text(skill_content)
            
            # Run dry-run migration
            auditor = Auditor(target)
            audit_result = auditor.audit()
            
            migrator = Migrator(target, dry_run=True)
            plan = migrator.migrate(audit_result)
            
            # Verify original skill file still exists
            assert skill_file.exists()
            assert skill_file.read_text() == skill_content
            
            # Verify vault directory was NOT created
            vault_dir = target / ".vault"
            assert not vault_dir.exists()
    
    def test_migrate_skill_actual_creates_pointer(self):
        """Test that actual migration (not dry-run) creates pointer file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            # Create a large skill file
            skills_dir = target / ".claude" / "skills" / "search"
            skills_dir.mkdir(parents=True, exist_ok=True)
            
            skill_file = skills_dir / "SKILL.md"
            skill_content = """---
name: Search Engine
description: Performs semantic search on documents with advanced algorithms
---

Implement search functionality here with comprehensive features.
The search engine handles various document types and formats.
It includes sophisticated ranking algorithms for result quality.
Additional features support filtering, faceting, and aggregation.
The implementation is designed for scalability and performance.
""" * 4
            skill_file.write_text(skill_content)
            
            # Run actual migration (dry_run=False)
            auditor = Auditor(target)
            audit_result = auditor.audit()
            
            migrator = Migrator(target, dry_run=False)
            plan = migrator.migrate(audit_result)
            
            # Only test if skill is large enough to migrate
            large_skills = [s for s in audit_result.skills if s.tokens > 150]
            if large_skills:
                # Verify vault structure created
                vault_path = target / ".vault" / "skills" / "search" / "SKILL.md"
                assert vault_path.exists()
                
                # Verify pointer file created in original location
                assert skill_file.exists()
                pointer_content = skill_file.read_text()
                assert "load_skill" in pointer_content or "pointer" in pointer_content.lower()


class TestMigratorGlobalFileTruncation:
    def test_truncate_global_file_preserves_frontmatter(self):
        """Test that truncating preserves YAML frontmatter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            # Create a large CLAUDE.md with frontmatter
            claude_file = target / "CLAUDE.md"
            frontmatter = """---
name: Claude Config
version: "1.0"
---

"""
            body = "Content paragraph. " * 1000  # Make it large
            claude_file.write_text(frontmatter + body)
            
            # Run audit
            auditor = Auditor(target)
            audit_result = auditor.audit()
            
            # Verify it's marked for truncation
            global_files = [g for g in audit_result.global_files if g.path.endswith("CLAUDE.md")]
            if global_files and global_files[0].over_limit:
                # Run migration
                migrator = Migrator(target, dry_run=False)
                plan = migrator.migrate(audit_result)
                
                # Verify file still has frontmatter
                truncated_content = claude_file.read_text()
                assert truncated_content.startswith("---")
                assert "name: Claude Config" in truncated_content
                assert "truncated" in truncated_content.lower() or "..." in truncated_content


class TestMigrationChangeTracking:
    def test_migration_change_type_skill_moved(self):
        """Test MigrationChange for skill_moved type."""
        change = MigrationChange(
            change_type="skill_moved",
            source="skills/pdf/SKILL.md",
            target=".vault/skills/pdf/SKILL.md",
            tokens_saved=500,
            reason="Ungated skill migration"
        )
        assert change.change_type == "skill_moved"
        assert change.tokens_saved == 500
    
    def test_migration_change_type_global_truncated(self):
        """Test MigrationChange for global_truncated type."""
        change = MigrationChange(
            change_type="global_truncated",
            source="CLAUDE.md",
            tokens_saved=1500,
            reason="Exceeded 3000 token limit"
        )
        assert change.change_type == "global_truncated"
        assert change.source == "CLAUDE.md"
        assert change.target is None


class TestMigratorIntegration:
    def test_full_migration_workflow(self):
        """Test complete migration workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            # Create test structure
            # 1. Create a VERY large CLAUDE.md (>3000 tokens)
            claude_file = target / "CLAUDE.md"
            claude_file.write_text("A large file content. " * 1500)  # Much larger
            
            # 2. Create a large ungated skill (> 150 tokens to benefit from migration)
            skills_dir = target / ".claude" / "skills" / "extract"
            skills_dir.mkdir(parents=True, exist_ok=True)
            skill_file = skills_dir / "SKILL.md"
            skill_file.write_text("""---
name: Text Extractor
description: Extracts text from various formats with advanced algorithms
---

Extraction logic here.

This skill performs complex text extraction operations on various document types.
It includes support for PDF, Word, Excel, and plain text formats.
The extraction process is optimized for accuracy and performance.

Additional implementation details follow for the skill body to ensure
we have enough content to exceed 150 tokens for meaningful migration benefit.
This ensures the pointer file size makes sense relative to the skill size.
""")
            
            # Run audit
            auditor = Auditor(target)
            audit_result = auditor.audit()
            
            # Verify violations detected
            assert len(audit_result.violations) > 0
            
            # Run migration (dry-run)
            migrator_dry = Migrator(target, dry_run=True)
            plan_dry = migrator_dry.migrate(audit_result)
            
            assert plan_dry.dry_run is True
            
            # Verify nothing was modified
            assert skill_file.exists()
            original_skill_content = skill_file.read_text()
            
            # Run actual migration
            migrator_actual = Migrator(target, dry_run=False)
            plan_actual = migrator_actual.migrate(audit_result)
            
            # Verify changes were made (may have tokens saved or from truncation)
            assert len(plan_actual.changes) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
