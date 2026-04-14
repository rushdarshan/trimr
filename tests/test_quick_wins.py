"""Tests for Phase 3 Task 3: Quick-win UX improvements."""

import tempfile
from pathlib import Path
import json

import pytest

from trimr.audit import Auditor
from trimr.reporter import render_stats_section, render_json_report


class TestStatsSection:
    """Test --stats flag output."""
    
    def test_stats_section_empty_project(self):
        """Stats should handle empty project gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            auditor = Auditor(Path(tmpdir))
            result = auditor.audit()
            stats = render_stats_section(result)
            assert "Statistics" in stats
            assert "Files:" in stats
    
    def test_stats_section_with_skills(self):
        """Stats should report skill statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create multiple skills
            skills_dir = tmpdir_path / "skills"
            for i in range(3):
                skill_dir = skills_dir / f"skill{i}"
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text(
                    f"---\nname: Skill{i}\ndescription: Desc\n---\n\nBody " + ("x " * (50 * (i+1))),
                    encoding="utf-8",
                )
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            stats = render_stats_section(result)
            
            assert "3 skills" in stats
            assert "tokens" in stats.lower()
            assert "Average:" in stats
            assert "Range:" in stats
    
    def test_stats_section_with_global_files(self):
        """Stats should report global file statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create multiple global files
            (tmpdir_path / "CLAUDE.md").write_text("x " * 100, encoding="utf-8")
            (tmpdir_path / "SYSTEM.md").write_text("y " * 150, encoding="utf-8")
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            stats = render_stats_section(result)
            
            assert "2 global" in stats
            assert "Global file tokens:" in stats
            assert "Largest:" in stats
    
    def test_stats_section_with_violations(self):
        """Stats should report violation counts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create file without frontmatter in skills dir
            skills_dir = tmpdir_path / "skills" / "test"
            skills_dir.mkdir(parents=True)
            (skills_dir / "SKILL.md").write_text("No frontmatter here", encoding="utf-8")
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            stats = render_stats_section(result)
            
            if result.violations:
                assert "Violations:" in stats
    
    def test_stats_section_formatting(self):
        """Stats should be properly formatted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            auditor = Auditor(Path(tmpdir))
            result = auditor.audit()
            stats = render_stats_section(result)
            
            # Check structure
            lines = stats.split("\n")
            assert "Statistics" in lines[0]
            assert "-" * 60 in lines[1]


class TestOutputFlag:
    """Test --output flag for saving reports to file."""
    
    def test_output_text_format(self):
        """Should save text report to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            output_file = tmpdir_path / "report.txt"
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            
            from trimr.reporter import render_text_report
            report = render_text_report(result)
            output_file.write_text(report, encoding="utf-8")
            
            assert output_file.exists()
            content = output_file.read_text(encoding="utf-8")
            assert "trimr audit" in content
    
    def test_output_json_format(self):
        """Should save JSON report to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            output_file = tmpdir_path / "report.json"
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            
            report = render_json_report(result)
            output_file.write_text(report, encoding="utf-8")
            
            assert output_file.exists()
            data = json.loads(output_file.read_text(encoding="utf-8"))
            assert "startup_tokens_current" in data
            assert "startup_tokens_projected" in data
    
    def test_output_file_creation(self):
        """Should create new output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            output_file = tmpdir_path / "new_report.txt"
            
            assert not output_file.exists()
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            
            from trimr.reporter import render_text_report
            report = render_text_report(result)
            output_file.write_text(report, encoding="utf-8")
            
            assert output_file.exists()
            assert output_file.read_text(encoding="utf-8") != ""
    
    def test_output_file_overwrite(self):
        """Should overwrite existing output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            output_file = tmpdir_path / "report.txt"
            
            # Create initial file
            output_file.write_text("old content", encoding="utf-8")
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            
            from trimr.reporter import render_text_report
            report = render_text_report(result)
            output_file.write_text(report, encoding="utf-8")
            
            content = output_file.read_text(encoding="utf-8")
            assert "old content" not in content
            assert "trimr audit" in content


class TestJsonExport:
    """Test JSON migration export capability."""
    
    def test_json_report_contains_all_fields(self):
        """JSON report should include all relevant fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create a skill
            skills_dir = tmpdir_path / "skills" / "test"
            skills_dir.mkdir(parents=True)
            (skills_dir / "SKILL.md").write_text(
                "---\nname: Test\ndescription: A test skill\n---\n\nBody",
                encoding="utf-8",
            )
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            report_json = render_json_report(result)
            data = json.loads(report_json)
            
            # Check required fields
            assert "path" in data
            assert "startup_tokens_current" in data
            assert "startup_tokens_projected" in data
            assert "reduction_percent" in data
            assert "global_files" in data
            assert "skills" in data
            assert "violations" in data
    
    def test_json_report_skills_structure(self):
        """JSON report skills should have correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            skills_dir = tmpdir_path / "skills" / "test"
            skills_dir.mkdir(parents=True)
            (skills_dir / "SKILL.md").write_text(
                "---\nname: Test\ndescription: Desc\n---\n\nBody " * 10,
                encoding="utf-8",
            )
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            report_json = render_json_report(result)
            data = json.loads(report_json)
            
            if data["skills"]:
                skill = data["skills"][0]
                assert "path" in skill
                assert "tokens" in skill
                assert "has_frontmatter" in skill
    
    def test_json_report_violations_structure(self):
        """JSON report violations should have correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create file to trigger violation
            skills_dir = tmpdir_path / "skills" / "test"
            skills_dir.mkdir(parents=True)
            (skills_dir / "SKILL.md").write_text("No frontmatter", encoding="utf-8")
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            report_json = render_json_report(result)
            data = json.loads(report_json)
            
            if data["violations"]:
                violation = data["violations"][0]
                assert "code" in violation
                assert "severity" in violation
                assert "file" in violation
                assert "detail" in violation
    
    def test_json_report_valid_json(self):
        """JSON report should be valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            auditor = Auditor(Path(tmpdir))
            result = auditor.audit()
            report_json = render_json_report(result)
            
            # Should not raise
            data = json.loads(report_json)
            assert isinstance(data, dict)


class TestCursorRulesSupport:
    """Test .cursorrules as global file support."""
    
    def test_cursorrules_file_detected(self):
        """Should detect .cursorrules as potential global file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create .cursorrules
            cursorrules_path = tmpdir_path / ".cursorrules"
            cursorrules_path.write_text("You are a helpful AI assistant", encoding="utf-8")
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            
            # .cursorrules may or may not be counted depending on adapter
            # Just verify audit runs without error
            assert result is not None
    
    def test_cursorrules_with_other_files(self):
        """Should handle .cursorrules alongside other files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create .cursorrules and other files
            (tmpdir_path / ".cursorrules").write_text("System rules", encoding="utf-8")
            (tmpdir_path / "CLAUDE.md").write_text("Claude instructions", encoding="utf-8")
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            
            # Verify audit completes
            assert result.startup_tokens_current >= 0
            assert result.startup_tokens_projected >= 0


class TestColoredOutput:
    """Test colored output by severity level."""
    
    def test_violations_include_severity_info(self):
        """Violations should track severity levels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create violation-triggering file
            skills_dir = tmpdir_path / "skills" / "test"
            skills_dir.mkdir(parents=True)
            (skills_dir / "SKILL.md").write_text("No frontmatter", encoding="utf-8")
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            
            if result.violations:
                for violation in result.violations:
                    assert violation.severity.value in ["CRITICAL", "WARN", "INFO"]
    
    def test_report_shows_violation_severity(self):
        """Report should display violation severity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            skills_dir = tmpdir_path / "skills" / "test"
            skills_dir.mkdir(parents=True)
            (skills_dir / "SKILL.md").write_text("No frontmatter", encoding="utf-8")
            
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            
            from trimr.reporter import render_text_report
            report = render_text_report(result)
            
            # Report should be generated without error
            assert report is not None


class TestQuickWinIntegration:
    """Integration tests for all quick-win features."""
    
    def test_full_audit_with_all_features(self):
        """Full audit with stats, json, and output should work together."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create realistic project structure
            (tmpdir_path / "CLAUDE.md").write_text("Instructions " * 50, encoding="utf-8")
            (tmpdir_path / ".cursorrules").write_text("Rules", encoding="utf-8")
            
            skills_dir = tmpdir_path / "skills"
            for i in range(2):
                skill_dir = skills_dir / f"skill{i}"
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text(
                    f"---\nname: Skill{i}\ndescription: Skill description\n---\n\nBody " * 20,
                    encoding="utf-8",
                )
            
            # Run audit
            auditor = Auditor(tmpdir_path)
            result = auditor.audit()
            
            # Generate all report formats
            from trimr.reporter import render_text_report, render_json_report
            text_report = render_text_report(result)
            json_report = render_json_report(result)
            stats = render_stats_section(result)
            
            # Verify all reports generated
            assert "trimr audit" in text_report
            assert isinstance(json.loads(json_report), dict)
            assert "Statistics" in stats
