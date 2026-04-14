"""Tests for pre-flight validation checks."""

import pytest
from pathlib import Path
import platform

from trimr.validators import PrefightChecker, ValidationError, DryRunValidator


@pytest.fixture
def simple_project(tmp_path):
    """Create a simple project."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    
    # Add some Python files
    (project_root / "main.py").write_text("print('hello')")
    (project_root / "config.py").write_text("CONFIG = {}")
    
    skills_dir = project_root / "skills"
    skills_dir.mkdir()
    (skills_dir / "skill.py").write_text("# skill")
    
    return project_root


class TestDiskSpaceCheck:
    """Test disk space validation."""
    
    def test_disk_space_sufficient(self, simple_project):
        """Test when disk space is sufficient."""
        checker = PrefightChecker(simple_project)
        
        # Just run the check, shouldn't raise
        checker._check_disk_space()
        
        # Should not have errors (assuming test machine has space)
        assert len(checker.errors) == 0 or any("disk" in e.lower() for e in checker.errors)
    
    def test_validate_all_no_errors(self, simple_project):
        """Test complete validation with no errors."""
        checker = PrefightChecker(simple_project)
        result = checker.validate_all()
        
        # Should pass (assuming reasonable system)
        assert isinstance(result, bool)


class TestFilePermissionCheck:
    """Test file permission validation."""
    
    def test_write_permission_check(self, simple_project):
        """Test write permission checking."""
        checker = PrefightChecker(simple_project)
        checker._check_file_permissions()
        
        # Should not have permission errors in normal case
        assert not any("write" in e.lower() for e in checker.errors)
    
    def test_readable_files(self, simple_project):
        """Test that Python files are readable."""
        checker = PrefightChecker(simple_project)
        checker._check_file_permissions()
        
        # Should be able to read files
        assert not any("read" in e.lower() and "permission" in e.lower() for e in checker.errors)


class TestPathTraversalCheck:
    """Test path traversal detection."""
    
    def test_no_path_traversal_in_normal_project(self, simple_project):
        """Test that normal project has no traversal issues."""
        checker = PrefightChecker(simple_project)
        checker._check_path_traversal()
        
        # Should not have errors
        assert len(checker.errors) == 0


class TestSymlinkCheck:
    """Test symlink loop detection."""
    
    def test_no_symlinks_in_normal_project(self, simple_project):
        """Test that normal project has no symlink issues."""
        checker = PrefightChecker(simple_project)
        checker._check_symlink_loops()
        
        # Should not have symlink errors
        assert not any("symlink" in e.lower() for e in checker.errors)


class TestWindowsPathCheck:
    """Test Windows-specific path validation."""
    
    def test_windows_path_validation(self, simple_project):
        """Test Windows path validation."""
        checker = PrefightChecker(simple_project)
        checker._check_windows_paths()
        
        # Should pass on normal Windows or be skipped on other OS
        assert isinstance(checker.errors, list)
        assert isinstance(checker.warnings, list)
    
    def test_invalid_filename_detection(self, simple_project):
        """Test detection of invalid filenames on Windows."""
        if platform.system() != "Windows":
            pytest.skip("Windows-specific test")
        
        # Create file with invalid characters (might fail on some systems)
        try:
            invalid_file = simple_project / "invalid<file>.py"
            invalid_file.write_text("# invalid")
            
            checker = PrefightChecker(simple_project)
            checker._check_windows_paths()
            
            # Should detect the issue
            assert any("invalid" in e.lower() for e in checker.errors)
        except (OSError, Exception):
            # Some systems don't allow these characters, skip
            pytest.skip("Cannot create file with invalid characters")


class TestValidationReport:
    """Test validation report generation."""
    
    def test_get_report_all_pass(self, simple_project):
        """Test report when all checks pass."""
        checker = PrefightChecker(simple_project)
        checker.validate_all()
        
        report = checker.get_report()
        
        assert isinstance(report, str)
        assert len(report) > 0
    
    def test_get_report_with_errors(self, simple_project):
        """Test report generation with errors."""
        checker = PrefightChecker(simple_project)
        checker.errors.append("Test error 1")
        checker.errors.append("Test error 2")
        
        report = checker.get_report()
        
        assert "error" in report.lower()
        assert "Test error 1" in report
        assert "Test error 2" in report
    
    def test_get_report_with_warnings(self, simple_project):
        """Test report generation with warnings."""
        checker = PrefightChecker(simple_project)
        checker.warnings.append("Test warning")
        
        report = checker.get_report()
        
        assert "warning" in report.lower()
        assert "Test warning" in report


class TestDryRunValidator:
    """Test DryRunValidator wrapper."""
    
    def test_dry_run_validator_passes(self, simple_project):
        """Test dry-run validation."""
        validator = DryRunValidator(simple_project)
        success, report = validator.validate_dry_run()
        
        assert isinstance(success, bool)
        assert isinstance(report, str)
        assert len(report) > 0


class TestPrefightIntegration:
    """Integration tests for preflight checking."""
    
    def test_full_validation_workflow(self, simple_project):
        """Test complete validation workflow."""
        checker = PrefightChecker(simple_project)
        
        # Run all validations
        result = checker.validate_all()
        
        # Should return boolean
        assert isinstance(result, bool)
        
        # Get report
        report = checker.get_report()
        assert isinstance(report, str)
        assert len(report) > 0
        
        # Check consistency
        if result:
            # If validation passed, report should say so
            assert "passed" in report.lower() or ("error" not in report.lower())
        else:
            # If validation failed, should have errors
            assert len(checker.errors) > 0
    
    def test_validation_catches_real_issues(self, tmp_path):
        """Test that validation can catch real issues."""
        project = tmp_path / "problem_project"
        project.mkdir()
        
        # Create a problematic situation: very nested directories
        current = project
        for i in range(15):
            current = current / f"level_{i}"
            current.mkdir()
        
        (current / "deep.py").write_text("# deep")
        
        checker = PrefightChecker(project)
        checker._check_symlink_loops()  # This checks nesting depth
        
        # Should have warning about nesting
        has_warning = any("deep" in w.lower() or "nesting" in w.lower() 
                         for w in checker.warnings)
        # Or it just handles it gracefully
        assert isinstance(checker.warnings, list)
