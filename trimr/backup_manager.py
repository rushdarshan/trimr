"""Backup and rollback management for safe migrations."""

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

BACKUP_MANIFEST_FILENAME = ".trimr_backup.json"


@dataclass
class BackupEntry:
    """Single file backup entry."""
    relative_path: str  # relative to project root
    backup_path: str    # where it's backed up
    original_size: int
    timestamp: str


@dataclass
class BackupManifest:
    """Manifest for a backup session."""
    version: str = "1.0"
    timestamp: str = ""
    project_root: str = ""
    backup_root: str = ""  # where backups are stored
    entries: List[BackupEntry] = field(default_factory=list)
    total_files: int = 0
    total_size_bytes: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to serializable dict."""
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "project_root": self.project_root,
            "backup_root": self.backup_root,
            "entries": [
                {
                    "relative_path": e.relative_path,
                    "backup_path": e.backup_path,
                    "original_size": e.original_size,
                    "timestamp": e.timestamp,
                }
                for e in self.entries
            ],
            "total_files": self.total_files,
            "total_size_bytes": self.total_size_bytes,
        }
    
    @staticmethod
    def from_dict(data: Dict) -> "BackupManifest":
        """Create manifest from dict."""
        manifest = BackupManifest(
            version=data.get("version", "1.0"),
            timestamp=data.get("timestamp", ""),
            project_root=data.get("project_root", ""),
            backup_root=data.get("backup_root", ""),
            total_files=data.get("total_files", 0),
            total_size_bytes=data.get("total_size_bytes", 0),
        )
        manifest.entries = [
            BackupEntry(
                relative_path=e["relative_path"],
                backup_path=e["backup_path"],
                original_size=e["original_size"],
                timestamp=e["timestamp"],
            )
            for e in data.get("entries", [])
        ]
        return manifest


class BackupManager:
    """Manages backup creation and restoration."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.backup_root = self.project_root / f".trimr_backup_{self._timestamp_str()}"
        self.manifest = BackupManifest(
            timestamp=datetime.now().isoformat(),
            project_root=str(self.project_root),
            backup_root=str(self.backup_root),
        )
    
    @staticmethod
    def _timestamp_str() -> str:
        """Generate backup directory timestamp (YYYY-MM-DD-HH-MM-SS)."""
        return datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    
    def backup_file(self, file_path: Path, relative_to: Path) -> bool:
        """
        Backup a single file.
        
        Args:
            file_path: Absolute path to file to back up
            relative_to: Root path to compute relative path from
        
        Returns:
            True if backed up successfully, False if failed
        """
        try:
            if not file_path.exists():
                logger.warning(f"File not found, skipping backup: {file_path}")
                return False
            
            # Compute relative path
            try:
                rel_path = file_path.relative_to(relative_to)
            except ValueError:
                logger.warning(f"File not under project root, skipping: {file_path}")
                return False
            
            # Create backup directory structure
            backup_dir = self.backup_root / rel_path.parent
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / file_path.name
            
            # Copy file
            shutil.copy2(file_path, backup_path)
            
            # Record in manifest
            entry = BackupEntry(
                relative_path=str(rel_path),
                backup_path=str(backup_path),
                original_size=file_path.stat().st_size,
                timestamp=datetime.now().isoformat(),
            )
            self.manifest.entries.append(entry)
            self.manifest.total_files += 1
            self.manifest.total_size_bytes += entry.original_size
            
            logger.debug(f"Backed up: {rel_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to backup {file_path}: {e}")
            return False
    
    def backup_directory(self, dir_path: Path, pattern: str = "**/*") -> int:
        """
        Backup all files matching pattern in directory.
        
        Args:
            dir_path: Directory to back up
            pattern: Glob pattern for files to back up (relative to dir_path)
        
        Returns:
            Number of files backed up
        """
        if not dir_path.exists():
            logger.warning(f"Directory not found: {dir_path}")
            return 0
        
        backed_up = 0
        for file_path in dir_path.glob(pattern):
            if file_path.is_file():
                if self.backup_file(file_path, self.project_root):
                    backed_up += 1
        
        return backed_up
    
    def save_manifest(self) -> Path:
        """
        Save backup manifest to backup directory.
        
        Returns:
            Path to manifest file
        """
        self.backup_root.mkdir(parents=True, exist_ok=True)
        manifest_path = self.backup_root / BACKUP_MANIFEST_FILENAME
        
        with open(manifest_path, "w") as f:
            json.dump(self.manifest.to_dict(), f, indent=2)
        
        logger.info(f"Backup manifest saved: {manifest_path}")
        return manifest_path
    
    def has_backups(self) -> bool:
        """Check if backup directory was created with files."""
        return (
            self.backup_root.exists()
            and self.manifest.total_files > 0
        )
    
    def get_backup_summary(self) -> str:
        """Get human-readable backup summary."""
        if not self.has_backups():
            return "No backups created"
        
        return (
            f"Backup created at {self.manifest.backup_root}\n"
            f"  Files backed up: {self.manifest.total_files}\n"
            f"  Total size: {self.manifest.total_size_bytes / 1024:.1f} KB\n"
            f"  Use 'trimr rollback' to restore"
        )


class BackupRestorer:
    """Restores files from backup manifest."""
    
    @staticmethod
    def list_backups(project_root: Path) -> List[Path]:
        """
        List all backup directories in project.
        
        Returns:
            List of backup directory paths (sorted newest first)
        """
        backups = sorted(
            project_root.glob(".trimr_backup_*"),
            reverse=True
        )
        return [b for b in backups if b.is_dir()]
    
    @staticmethod
    def load_manifest(backup_path: Path) -> Optional[BackupManifest]:
        """Load backup manifest from backup directory."""
        manifest_file = backup_path / BACKUP_MANIFEST_FILENAME
        
        if not manifest_file.exists():
            logger.error(f"Manifest not found: {manifest_file}")
            return None
        
        try:
            with open(manifest_file, "r") as f:
                data = json.load(f)
            return BackupManifest.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
            return None
    
    @staticmethod
    def restore(backup_path: Path, project_root: Path) -> bool:
        """
        Restore all files from backup.
        
        Args:
            backup_path: Path to backup directory
            project_root: Project root to restore to
        
        Returns:
            True if fully restored, False if any errors occurred
        """
        manifest = BackupRestorer.load_manifest(backup_path)
        if not manifest:
            return False
        
        all_success = True
        restored_count = 0
        
        for entry in manifest.entries:
            src = Path(entry.backup_path)
            dst = project_root / entry.relative_path
            
            try:
                if not src.exists():
                    logger.warning(f"Backup file not found: {src}")
                    all_success = False
                    continue
                
                # Create parent directory if needed
                dst.parent.mkdir(parents=True, exist_ok=True)
                
                # Restore file
                shutil.copy2(src, dst)
                logger.debug(f"Restored: {entry.relative_path}")
                restored_count += 1
                
            except Exception as e:
                logger.error(f"Failed to restore {entry.relative_path}: {e}")
                all_success = False
        
        if all_success:
            logger.info(f"Successfully restored {restored_count} files")
        else:
            logger.warning(f"Restored {restored_count} files with errors")
        
        return all_success
    
    @staticmethod
    def get_backup_info(backup_path: Path) -> Optional[Dict]:
        """Get human-readable backup information."""
        manifest = BackupRestorer.load_manifest(backup_path)
        if not manifest:
            return None
        
        return {
            "timestamp": manifest.timestamp,
            "files_count": manifest.total_files,
            "total_size_bytes": manifest.total_size_bytes,
            "project_root": manifest.project_root,
            "files": [e.relative_path for e in manifest.entries],
        }
