"""Pre-flight validation checks for safe migrations."""

import logging
from pathlib import Path
from typing import List, Tuple
import shutil
import re

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when pre-flight validation fails."""
    pass


class PrefightChecker:
    """Performs pre-flight validation before migrations."""
    
    # Configuration
    MIN_DISK_SPACE_MULTIPLIER = 2  # Require 2x the largest file
    RESERVED_DISK_SPACE_MB = 50  # Keep at least 50MB free
    
    def __init__(self, target_path: Path):
        self.target_path = target_path.resolve()
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate_all(self) -> bool:
        """
        Run all validation checks.
        
        Returns:
            True if all checks pass, False if any errors found
        """
        self.errors = []
        self.warnings = []
        
        # Run all checks
        self._check_disk_space()
        self._check_file_permissions()
        self._check_path_traversal()
        self._check_symlink_loops()
        self._check_windows_paths()
        
        if self.errors:
            logger.error(f"Pre-flight validation failed: {len(self.errors)} error(s)")
            return False
        
        if self.warnings:
            logger.warning(f"Pre-flight validation warnings: {len(self.warnings)}")
        
        return True
    
    def get_report(self) -> str:
        """Get human-readable validation report."""
        lines = []
        
        if not self.errors and not self.warnings:
            return "✓ All pre-flight checks passed"
        
        if self.errors:
            lines.append(f"⚠ {len(self.errors)} error(s):")
            for error in self.errors:
                lines.append(f"  ✗ {error}")
        
        if self.warnings:
            lines.append(f"⚠ {len(self.warnings)} warning(s):")
            for warning in self.warnings:
                lines.append(f"  ! {warning}")
        
        return "\n".join(lines)
    
    def _check_disk_space(self) -> None:
        """Check if there's sufficient disk space for migration."""
        try:
            stat = shutil.disk_usage(self.target_path)
            free_mb = stat.free / (1024 * 1024)
            
            # Estimate largest file size
            largest_file_mb = 0
            for file_path in self.target_path.rglob("*"):
                if file_path.is_file():
                    try:
                        size_mb = file_path.stat().st_size / (1024 * 1024)
                        largest_file_mb = max(largest_file_mb, size_mb)
                    except OSError:
                        pass
            
            required_mb = (largest_file_mb * self.MIN_DISK_SPACE_MULTIPLIER) + self.RESERVED_DISK_SPACE_MB
            
            if free_mb < required_mb:
                self.errors.append(
                    f"Insufficient disk space: {free_mb:.1f} MB free, "
                    f"need ~{required_mb:.1f} MB "
                    f"(largest file {largest_file_mb:.1f} MB × {self.MIN_DISK_SPACE_MULTIPLIER} + {self.RESERVED_DISK_SPACE_MB} MB buffer)"
                )
            elif free_mb < 100:
                self.warnings.append(f"Low disk space: only {free_mb:.1f} MB free")
        
        except Exception as e:
            self.errors.append(f"Failed to check disk space: {e}")
    
    def _check_file_permissions(self) -> None:
        """Check if all Python files are readable and target is writable."""
        try:
            # Check if target directory is writable
            test_file = self.target_path / ".trimr_permission_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
            except PermissionError:
                self.errors.append(f"No write permission for target directory: {self.target_path}")
                return
            except Exception as e:
                self.errors.append(f"Cannot write to target directory: {e}")
                return
            
            # Check readability of Python files
            unreadable_files = []
            for py_file in self.target_path.rglob("*.py"):
                if py_file.is_file():
                    try:
                        py_file.read_bytes()
                    except PermissionError:
                        unreadable_files.append(str(py_file))
                    except Exception:
                        pass
            
            if unreadable_files:
                self.errors.append(f"Cannot read {len(unreadable_files)} Python files (permission denied)")
        
        except Exception as e:
            self.errors.append(f"Failed to check file permissions: {e}")
    
    def _check_path_traversal(self) -> None:
        """Check for path traversal attempts (.. in paths)."""
        try:
            for py_file in self.target_path.rglob("*.py"):
                # Ensure all paths are under target
                try:
                    py_file.relative_to(self.target_path)
                except ValueError:
                    # File is outside target (shouldn't happen with rglob)
                    self.warnings.append(f"File outside target: {py_file}")
        
        except Exception as e:
            logger.debug(f"Path traversal check error: {e}")
    
    def _check_symlink_loops(self) -> None:
        """Check for symlink loops that could cause infinite recursion."""
        try:
            visited = set()
            max_depth = 10  # Prevent infinite recursion in check
            
            def check_symlinks(path: Path, depth: int = 0) -> None:
                if depth > max_depth:
                    self.warnings.append(f"Directory nesting too deep (>10 levels): {path}")
                    return
                
                if path in visited:
                    self.errors.append(f"Symlink loop detected: {path}")
                    return
                
                visited.add(path)
                
                try:
                    for item in path.iterdir():
                        if item.is_symlink():
                            # Check if symlink target is under project or loops
                            try:
                                resolved = item.resolve(strict=True)
                                if resolved == path or resolved.parent == path:
                                    self.warnings.append(f"Symlink points to parent: {item}")
                            except (OSError, RuntimeError):
                                self.warnings.append(f"Broken or circular symlink: {item}")
                        elif item.is_dir():
                            check_symlinks(item, depth + 1)
                except (PermissionError, OSError):
                    pass
            
            check_symlinks(self.target_path)
        
        except Exception as e:
            logger.debug(f"Symlink check error: {e}")
    
    def _check_windows_paths(self) -> None:
        """Check for Windows-specific path issues."""
        try:
            import platform
            
            if platform.system() != "Windows":
                return
            
            # Check for invalid characters in paths
            invalid_chars = r'[<>:"|?*]'
            
            for py_file in self.target_path.rglob("*.py"):
                filename = py_file.name
                if re.search(invalid_chars, filename):
                    self.errors.append(f"Invalid characters in filename: {filename}")
                
                # Check for path length issues
                full_path = str(py_file)
                if len(full_path) > 260:  # Windows MAX_PATH
                    self.warnings.append(f"Path exceeds 260 chars (Windows limit): {full_path[:50]}...")
        
        except Exception as e:
            logger.debug(f"Windows path check error: {e}")


class DryRunValidator:
    """Validates dry-run operation."""
    
    def __init__(self, target_path: Path):
        self.target_path = target_path.resolve()
        self.checker = PrefightChecker(target_path)
    
    def validate_dry_run(self) -> Tuple[bool, str]:
        """
        Validate that dry-run would succeed.
        
        Returns:
            (success: bool, report: str)
        """
        success = self.checker.validate_all()
        report = self.checker.get_report()
        
        return success, report
