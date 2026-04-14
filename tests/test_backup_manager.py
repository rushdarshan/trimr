"""Tests for backup and rollback functionality."""

import json
import pytest
from pathlib import Path
from datetime import datetime

from trimr.backup_manager import (
    BackupManager,
    BackupRestorer,
    BackupManifest,
    BackupEntry,
    BACKUP_MANIFEST_FILENAME,
)


@pytest.fixture
def project_with_files(tmp_path):
    """Create a temporary project with some files."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    
    # Create some files
    (project_root / "main.py").write_text("print('hello')")
    (project_root / "config.py").write_text("CONFIG = {}")
    
    # Create subdirectory with file
    subdir = project_root / "agents"
    subdir.mkdir()
    (subdir / "agent.py").write_text("class Agent: pass")
    
    return project_root


class TestBackupManager:
    """Test BackupManager creation and backup operations."""
    
    def test_init_creates_backup_root(self, project_with_files):
        """Test that BackupManager initializes with backup root path."""
        mgr = BackupManager(project_with_files)
        
        assert mgr.project_root == project_with_files
        assert ".trimr_backup_" in str(mgr.backup_root)
        assert mgr.manifest is not None
        assert mgr.manifest.total_files == 0
    
    def test_backup_single_file(self, project_with_files):
        """Test backing up a single file."""
        mgr = BackupManager(project_with_files)
        main_file = project_with_files / "main.py"
        
        success = mgr.backup_file(main_file, project_with_files)
        
        assert success
        assert mgr.manifest.total_files == 1
        assert mgr.manifest.entries[0].relative_path == "main.py"
        assert mgr.manifest.total_size_bytes > 0
    
    def test_backup_file_not_found(self, project_with_files):
        """Test backing up non-existent file."""
        mgr = BackupManager(project_with_files)
        non_existent = project_with_files / "nonexistent.py"
        
        success = mgr.backup_file(non_existent, project_with_files)
        
        assert not success
        assert mgr.manifest.total_files == 0
    
    def test_backup_file_outside_root(self, project_with_files, tmp_path):
        """Test backing up file outside project root."""
        mgr = BackupManager(project_with_files)
        outside_file = tmp_path / "outside.py"
        outside_file.write_text("x = 1")
        
        success = mgr.backup_file(outside_file, project_with_files)
        
        assert not success
        assert mgr.manifest.total_files == 0
    
    def test_backup_directory(self, project_with_files):
        """Test backing up all files in directory."""
        mgr = BackupManager(project_with_files)
        
        backed_up = mgr.backup_directory(project_with_files, "**/*.py")
        
        assert backed_up == 3  # main.py, config.py, agents/agent.py
        assert mgr.manifest.total_files == 3
    
    def test_backup_directory_with_pattern(self, project_with_files):
        """Test backing up with specific glob pattern."""
        mgr = BackupManager(project_with_files)
        
        # Only backup root-level files
        backed_up = mgr.backup_directory(project_with_files, "*.py")
        
        assert backed_up == 2  # Only main.py and config.py
        assert mgr.manifest.total_files == 2
    
    def test_save_manifest(self, project_with_files):
        """Test saving backup manifest."""
        mgr = BackupManager(project_with_files)
        mgr.backup_directory(project_with_files, "**/*.py")
        
        manifest_path = mgr.save_manifest()
        
        assert manifest_path.exists()
        assert manifest_path.name == BACKUP_MANIFEST_FILENAME
        
        # Verify manifest content
        with open(manifest_path) as f:
            data = json.load(f)
        
        assert data["version"] == "1.0"
        assert data["total_files"] == 3
        assert len(data["entries"]) == 3
    
    def test_has_backups(self, project_with_files):
        """Test checking if backups exist."""
        mgr = BackupManager(project_with_files)
        
        assert not mgr.has_backups()
        
        mgr.backup_directory(project_with_files, "**/*.py")
        assert mgr.has_backups()
    
    def test_get_backup_summary(self, project_with_files):
        """Test getting human-readable backup summary."""
        mgr = BackupManager(project_with_files)
        
        # No backups
        summary = mgr.get_backup_summary()
        assert "No backups" in summary
        
        # With backups
        mgr.backup_directory(project_with_files, "**/*.py")
        mgr.save_manifest()
        summary = mgr.get_backup_summary()
        assert "Files backed up: 3" in summary
        assert "rollback" in summary.lower()
    
    def test_backup_manifest_serialization(self, project_with_files):
        """Test manifest to_dict and from_dict."""
        mgr = BackupManager(project_with_files)
        mgr.backup_directory(project_with_files, "**/*.py")
        
        # Serialize
        data = mgr.manifest.to_dict()
        assert data["version"] == "1.0"
        assert len(data["entries"]) == 3
        
        # Deserialize
        restored = BackupManifest.from_dict(data)
        assert restored.total_files == 3
        assert len(restored.entries) == 3
        assert restored.entries[0].relative_path == data["entries"][0]["relative_path"]


class TestBackupRestorer:
    """Test BackupRestorer recovery operations."""
    
    def test_list_backups_empty(self, tmp_path):
        """Test listing backups when none exist."""
        project = tmp_path / "project"
        project.mkdir()
        
        backups = BackupRestorer.list_backups(project)
        
        assert backups == []
    
    def test_list_backups(self, project_with_files):
        """Test listing multiple backups (sorted newest first)."""
        # Create first backup
        mgr1 = BackupManager(project_with_files)
        mgr1.backup_directory(project_with_files, "**/*.py")
        mgr1.save_manifest()
        backup1 = mgr1.backup_root
        
        # Create second backup (after some time)
        mgr2 = BackupManager(project_with_files)
        mgr2.backup_directory(project_with_files, "**/*.py")
        mgr2.save_manifest()
        backup2 = mgr2.backup_root
        
        backups = BackupRestorer.list_backups(project_with_files)
        
        assert len(backups) == 2
        assert backups[0] == backup2  # Newest first
        assert backups[1] == backup1
    
    def test_load_manifest(self, project_with_files):
        """Test loading manifest from backup."""
        mgr = BackupManager(project_with_files)
        mgr.backup_directory(project_with_files, "**/*.py")
        mgr.save_manifest()
        
        manifest = BackupRestorer.load_manifest(mgr.backup_root)
        
        assert manifest is not None
        assert manifest.total_files == 3
        assert len(manifest.entries) == 3
    
    def test_load_manifest_missing(self, tmp_path):
        """Test loading manifest when file doesn't exist."""
        fake_backup = tmp_path / "fake_backup"
        fake_backup.mkdir()
        
        manifest = BackupRestorer.load_manifest(fake_backup)
        
        assert manifest is None
    
    def test_restore_basic(self, project_with_files, tmp_path):
        """Test basic restore operation."""
        # Create backup
        mgr = BackupManager(project_with_files)
        mgr.backup_directory(project_with_files, "**/*.py")
        mgr.save_manifest()
        
        # Modify original file
        main_file = project_with_files / "main.py"
        original_content = main_file.read_text()
        main_file.write_text("modified content")
        
        # Restore
        success = BackupRestorer.restore(mgr.backup_root, project_with_files)
        
        assert success
        assert main_file.read_text() == original_content
    
    def test_restore_multiple_files(self, project_with_files):
        """Test restoring multiple files."""
        # Create backup
        mgr = BackupManager(project_with_files)
        mgr.backup_directory(project_with_files, "**/*.py")
        mgr.save_manifest()
        
        # Store original contents
        original_contents = {}
        for py_file in project_with_files.glob("**/*.py"):
            rel_path = py_file.relative_to(project_with_files)
            original_contents[str(rel_path)] = py_file.read_text()
        
        # Modify all files
        for py_file in project_with_files.glob("**/*.py"):
            py_file.write_text("# modified")
        
        # Restore
        success = BackupRestorer.restore(mgr.backup_root, project_with_files)
        
        assert success
        for py_file in project_with_files.glob("**/*.py"):
            rel_path = str(py_file.relative_to(project_with_files))
            assert py_file.read_text() == original_contents[rel_path]
    
    def test_restore_with_missing_backup_file(self, project_with_files):
        """Test restore when backup file is missing (partial failure)."""
        mgr = BackupManager(project_with_files)
        mgr.backup_directory(project_with_files, "**/*.py")
        manifest_path = mgr.save_manifest()
        
        # Delete one backup file to simulate corruption
        for entry in mgr.manifest.entries:
            backup_file = Path(entry.backup_path)
            if backup_file.exists():
                backup_file.unlink()
                break
        
        # Restore should fail but try to restore others
        success = BackupRestorer.restore(mgr.backup_root, project_with_files)
        
        assert not success  # Partial failure
    
    def test_get_backup_info(self, project_with_files):
        """Test getting backup information."""
        mgr = BackupManager(project_with_files)
        mgr.backup_directory(project_with_files, "**/*.py")
        mgr.save_manifest()
        
        info = BackupRestorer.get_backup_info(mgr.backup_root)
        
        assert info is not None
        assert info["files_count"] == 3
        assert len(info["files"]) == 3
        assert "timestamp" in info
        assert info["total_size_bytes"] > 0
    
    def test_get_backup_info_invalid(self, tmp_path):
        """Test getting info for invalid backup."""
        fake_backup = tmp_path / "fake"
        fake_backup.mkdir()
        
        info = BackupRestorer.get_backup_info(fake_backup)
        
        assert info is None


class TestBackupIntegration:
    """Integration tests for backup and restore workflow."""
    
    def test_full_cycle_backup_modify_restore(self, project_with_files):
        """Test complete cycle: backup -> modify -> restore."""
        # Store original state
        original_main = (project_with_files / "main.py").read_text()
        original_config = (project_with_files / "config.py").read_text()
        
        # Create backup
        mgr = BackupManager(project_with_files)
        mgr.backup_directory(project_with_files, "**/*.py")
        mgr.save_manifest()
        
        # Modify files
        (project_with_files / "main.py").write_text("# hacked")
        (project_with_files / "config.py").write_text("# destroyed")
        
        # Restore
        success = BackupRestorer.restore(mgr.backup_root, project_with_files)
        
        assert success
        assert (project_with_files / "main.py").read_text() == original_main
        assert (project_with_files / "config.py").read_text() == original_config
    
    def test_multiple_backups_selective_restore(self, project_with_files):
        """Test restoring from a specific backup when multiple exist."""
        # Create first backup
        mgr1 = BackupManager(project_with_files)
        mgr1.backup_directory(project_with_files, "**/*.py")
        mgr1.save_manifest()
        state1 = (project_with_files / "main.py").read_text()
        
        # Modify and create second backup
        (project_with_files / "main.py").write_text("# state2")
        mgr2 = BackupManager(project_with_files)
        mgr2.backup_directory(project_with_files, "**/*.py")
        mgr2.save_manifest()
        state2 = (project_with_files / "main.py").read_text()
        
        # List backups
        backups = BackupRestorer.list_backups(project_with_files)
        assert len(backups) == 2
        
        # Restore to first backup
        success = BackupRestorer.restore(backups[1], project_with_files)
        assert success
        assert (project_with_files / "main.py").read_text() == state1
