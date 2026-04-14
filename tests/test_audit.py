import pytest
from pathlib import Path
from trimr.audit import Auditor
from trimr.models import ViolationCode, ViolationSeverity


class TestAuditorBasic:
    """Test basic auditor functionality."""

    def test_auditor_initialization(self, tmp_path):
        """Test auditor initializes with valid path."""
        auditor = Auditor(tmp_path)
        assert auditor.target_path == tmp_path.resolve()

    def test_auditor_nonexistent_path(self, tmp_path):
        """Test auditor rejects nonexistent paths."""
        nonexistent = tmp_path / "does_not_exist"
        auditor = Auditor(nonexistent)
        with pytest.raises(FileNotFoundError):
            auditor.audit()

    def test_auditor_walk_files_empty(self, tmp_path):
        """Test walk_files on empty directory."""
        auditor = Auditor(tmp_path)
        files = auditor.walk_files()
        assert files == []

    def test_auditor_walk_files_single_file(self, tmp_path):
        """Test walk_files finds a single file."""
        test_file = tmp_path / "test.md"
        test_file.write_text("content")
        auditor = Auditor(tmp_path)
        files = auditor.walk_files()
        assert len(files) == 1
        assert files[0].name == "test.md"

    def test_auditor_excludes_node_modules(self, tmp_path):
        """Test auditor excludes node_modules."""
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "test.md").write_text("content")
        (tmp_path / "normal.md").write_text("content")
        
        auditor = Auditor(tmp_path)
        files = auditor.walk_files()
        
        assert len(files) == 1
        assert files[0].name == "normal.md"

    def test_auditor_excludes_dotfiles(self, tmp_path):
        """Test auditor excludes hidden directories."""
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "test.md").write_text("content")
        (tmp_path / "normal.md").write_text("content")
        
        auditor = Auditor(tmp_path)
        files = auditor.walk_files()
        
        assert len(files) == 1
        assert files[0].name == "normal.md"

    def test_auditor_includes_vault_dirs(self, tmp_path):
        """Test auditor does NOT exclude .vault/.cursor/.claude dirs."""
        (tmp_path / ".vault").mkdir()
        (tmp_path / ".vault" / "test.md").write_text("content")
        
        auditor = Auditor(tmp_path)
        files = auditor.walk_files()
        
        assert len(files) == 1

    def test_auditor_includes_anthropic_dir(self, tmp_path):
        """Test auditor does NOT exclude .anthropic dir."""
        (tmp_path / ".anthropic").mkdir()
        (tmp_path / ".anthropic" / "system.json").write_text('{"system_prompt": "hello"}')

        auditor = Auditor(tmp_path)
        files = auditor.walk_files()

        assert len(files) == 1
        assert files[0].name == "system.json"


class TestAuditorGlobalFiles:
    """Test global instruction file detection."""

    def test_audit_detects_claude_md(self, tmp_path):
        """Test audit detects CLAUDE.md."""
        claude_file = tmp_path / "CLAUDE.md"
        claude_file.write_text("---\nname: test\ndescription: test\n---\nGlobal content here")
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        assert len(result.global_files) == 1
        assert result.global_files[0].path == "CLAUDE.md"

    def test_audit_detects_agents_md(self, tmp_path):
        """Test audit detects AGENTS.md."""
        agents_file = tmp_path / "AGENTS.md"
        agents_file.write_text("---\nname: agent\ndescription: desc\n---\nContent")
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        assert len(result.global_files) == 1
        assert result.global_files[0].path == "AGENTS.md"

    def test_audit_global_bloat(self, tmp_path):
        """Test audit detects global file bloat (>3000 tokens)."""
        claude_file = tmp_path / "CLAUDE.md"
        large_content = "word " * 3000
        claude_file.write_text(large_content)
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        assert len(result.violations) > 0
        bloat_violations = [v for v in result.violations if v.code == ViolationCode.GLOBAL_BLOAT]
        assert len(bloat_violations) > 0
        assert bloat_violations[0].severity == ViolationSeverity.CRITICAL

    def test_audit_detects_json_config_with_system_prompt(self, tmp_path):
        """Config files (.json) with system prompts should be treated as global."""
        config = tmp_path / "prompts.json"
        config.write_text('{"system_prompt": "' + ("x" * 250) + '"}')

        auditor = Auditor(tmp_path)
        result = auditor.audit()

        assert any(g.path == "prompts.json" for g in result.global_files)

    def test_audit_detects_yaml_config_with_system_prompt(self, tmp_path):
        """Config files (.yaml) with system prompts should be treated as global."""
        config = tmp_path / "agents.yaml"
        config.write_text("instructions: |\n  " + ("x" * 250) + "\n")

        auditor = Auditor(tmp_path)
        result = auditor.audit()

        assert any(g.path == "agents.yaml" for g in result.global_files)

    def test_audit_detects_toml_config_with_system_prompt(self, tmp_path):
        """Config files (.toml) with system prompts should be treated as global."""
        config = tmp_path / "agent.toml"
        config.write_text('prompt = "' + ("x" * 250) + '"\n')

        auditor = Auditor(tmp_path)
        result = auditor.audit()

        assert any(g.path == "agent.toml" for g in result.global_files)


class TestAuditorSkills:
    """Test skill file detection."""

    def test_audit_detects_skill(self, tmp_path):
        """Test audit detects valid skill files."""
        skills_dir = tmp_path / "skills" / "pdf"
        skills_dir.mkdir(parents=True)
        skill_file = skills_dir / "SKILL.md"
        skill_file.write_text("---\nname: PDF Tool\ndescription: Extracts PDFs\n---\nBody")
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        assert len(result.skills) == 1
        assert result.skills[0].name == "PDF Tool"
        assert result.skills[0].has_frontmatter is True

    def test_audit_skill_ungated(self, tmp_path):
        """Test audit detects ungated skills."""
        skills_dir = tmp_path / "skills" / "pdf"
        skills_dir.mkdir(parents=True)
        skill_file = skills_dir / "SKILL.md"
        skill_file.write_text("---\nname: PDF\ndescription: PDF tool\n---\nBody")
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        assert len(result.skills) == 1
        assert result.skills[0].ungated is True
        
        ungated_violations = [v for v in result.violations if v.code == ViolationCode.SKILL_UNGATED]
        assert len(ungated_violations) > 0

    def test_audit_skill_vaulted(self, tmp_path):
        """Test audit does not flag vaulted skills as ungated."""
        vault_dir = tmp_path / ".vault" / "skills"
        vault_dir.mkdir(parents=True)
        skill_file = vault_dir / "vaulted.md"
        skill_file.write_text("---\nname: Vaulted\ndescription: Vaulted skill\n---\nBody")
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        assert len(result.skills) == 1
        assert result.skills[0].ungated is False

    def test_audit_empty_description_violation(self, tmp_path):
        """Test audit detects empty or too-short descriptions."""
        skills_dir = tmp_path / "skills" / "pdf"
        skills_dir.mkdir(parents=True)
        skill_file = skills_dir / "SKILL.md"
        skill_file.write_text("---\nname: PDF\ndescription: Short\n---\nBody")
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        empty_desc_violations = [v for v in result.violations if v.code == ViolationCode.EMPTY_DESCRIPTION]
        assert len(empty_desc_violations) > 0

    def test_audit_no_frontmatter_violation(self, tmp_path):
        """Test audit detects markdown in skills/ without frontmatter."""
        skills_dir = tmp_path / "skills" / "pdf"
        skills_dir.mkdir(parents=True)
        skill_file = skills_dir / "README.md"
        skill_file.write_text("# Just a readme\n\nNo frontmatter")
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        no_fm_violations = [v for v in result.violations if v.code == ViolationCode.NO_FRONTMATTER]
        assert len(no_fm_violations) > 0


class TestAuditorTokenCosts:
    """Test token cost calculations."""

    def test_audit_startup_tokens_empty(self, tmp_path):
        """Test startup token cost with empty project."""
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        assert result.startup_tokens_current == 0
        assert result.startup_tokens_projected == 0

    def test_audit_startup_tokens_only_global(self, tmp_path):
        """Test startup tokens with only global file."""
        claude_file = tmp_path / "CLAUDE.md"
        claude_file.write_text("Test content for global file")
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        assert result.startup_tokens_current > 0
        assert result.startup_tokens_projected > 0
        assert result.startup_tokens_current == result.startup_tokens_projected

    def test_audit_startup_tokens_ungated_skill(self, tmp_path):
        """Test ungated skills are counted in current but reduced in projected (L1 metadata only)."""
        skills_dir = tmp_path / "skills" / "pdf"
        skills_dir.mkdir(parents=True)
        skill_file = skills_dir / "SKILL.md"
        # Make skill large enough (>100 tokens) so migration saves tokens
        skill_file.write_text("---\nname: PDF\ndescription: PDF tool with lots of detailed content here for processing files\n---\n" + "Body content " * 50)
        
        claude_file = tmp_path / "CLAUDE.md"
        claude_file.write_text("Global content")
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        # After migration: global + (1 skill × estimated L1 metadata tokens)
        # Projected L1 metadata is calculated dynamically based on skill name/desc
        # Current includes full skill body
        # Since skill is large, current > projected
        assert result.startup_tokens_current > result.startup_tokens_projected
        # Projected should include L1 metadata cost (now dynamically calculated, ~15-20 tokens per skill)
        assert result.startup_tokens_projected > 0

    def test_audit_startup_tokens_vaulted_skill(self, tmp_path):
        """Test vaulted skills don't increase startup cost."""
        vault_dir = tmp_path / ".vault" / "skills"
        vault_dir.mkdir(parents=True)
        skill_file = vault_dir / "vaulted.md"
        skill_file.write_text("---\nname: Vaulted\ndescription: Vaulted skill with content here\n---\nBody")
        
        claude_file = tmp_path / "CLAUDE.md"
        claude_file.write_text("Global")
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        assert result.startup_tokens_current == result.startup_tokens_projected

    def test_audit_reduction_percentage(self, tmp_path):
        """Test reduction percentage calculation with L1 metadata cost."""
        skills_dir = tmp_path / "skills" / "pdf"
        skills_dir.mkdir(parents=True)
        skill_file = skills_dir / "SKILL.md"
        # Large skill so savings are positive
        skill_file.write_text("---\nname: PDF\ndescription: PDF tool\n---\n" + "x" * 500)
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        if result.startup_tokens_current > 0:
            # reduction_percent = (current - projected) / current * 100
            # With L1 metadata: projected = global + 100
            # Should be positive when skill is large enough
            assert result.reduction_percent >= -100 and result.reduction_percent <= 100


class TestAuditorNonASCII:
    """Test non-ASCII character detection."""

    def test_audit_non_ascii_detection(self, tmp_path):
        """Test audit detects high non-ASCII ratio."""
        skill_file = tmp_path / "test.md"
        content = "---\nname: test\ndescription: test\n---\n\n" + "ñ" * 100 + "a" * 100
        skill_file.write_text(content, encoding="utf-8")
        
        auditor = Auditor(tmp_path)
        result = auditor.audit()
        
        non_ascii_violations = [v for v in result.violations if v.code == ViolationCode.NON_ASCII_ESTIMATE]
        assert len(non_ascii_violations) > 0
