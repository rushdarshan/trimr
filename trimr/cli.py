import sys
from pathlib import Path
import typer
from typing import Optional

from .audit import Auditor
from .fixer import Fixer
from .migrator import Migrator
from .backup_manager import BackupManager, BackupRestorer
from .reporter import print_report, print_migration_report, print_fix_report

app = typer.Typer(
    name="trimr",
    help="Token audit and migration tool for AI agent projects",
)


def audit(
    path: str = typer.Argument(
        ".",
        help="Path to audit",
    ),
    format: str = typer.Option(
        "text",
        "--format",
        "-f",
        help="Output format: text or json",
    ),
    framework: str = typer.Option(
        None,
        "--framework",
        help="Framework hint: claude, langchain, crewai, or openai (auto-detect if omitted)",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Apply fixes (v0.2+)",
    ),
) -> None:
    """Audit a project for token bloat and skill migration opportunities."""
    try:
        target = Path(path).resolve()
        if not target.exists():
            typer.secho(f"Error: Path does not exist: {path}", fg="red", err=True)
            raise typer.Exit(code=1)
        
        auditor = Auditor(target, framework_hint=framework)
        result = auditor.audit()
        
        print_report(result, format=format)
        
    except Exception as e:
        typer.secho(f"Error: {e}", fg="red", err=True)
        raise typer.Exit(code=1)


def migrate(
    path: str = typer.Argument(
        ".",
        help="Path to migrate",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview changes without modifying files",
    ),
    framework: str = typer.Option(
        None,
        "--framework",
        help="Framework hint: claude, langchain, crewai, or openai (auto-detect if omitted)",
    ),
    format: str = typer.Option(
        "text",
        "--format",
        "-f",
        help="Output format: text or json",
    ),
) -> None:
    """Migrate ungated skills to .vault/ and fix bloat violations."""
    try:
        target = Path(path).resolve()
        if not target.exists():
            typer.secho(f"Error: Path does not exist: {path}", fg="red", err=True)
            raise typer.Exit(code=1)
        
        # Run pre-flight validation if dry-run
        if dry_run:
            migrator_check = Migrator(target, dry_run=True)
            validation_ok, validation_report = migrator_check.validate_dry_run()
            typer.secho(validation_report, fg="cyan")
            if not validation_ok:
                typer.secho("Pre-flight validation failed. Aborting.", fg="red", err=True)
                raise typer.Exit(code=1)
        
        # Run audit first to get violations
        auditor = Auditor(target, framework_hint=framework)
        audit_result = auditor.audit()
        
        # Check for violations
        if not audit_result.violations:
            typer.secho("✓ No violations found. Nothing to migrate.", fg="green")
            raise typer.Exit(code=0)
        
        # Run migration
        migrator = Migrator(target, dry_run=dry_run)
        migration_plan = migrator.migrate(audit_result)
        
        # Print results
        print_migration_report(audit_result, migration_plan, format=format, dry_run=dry_run)
        
    except Exception as e:
        typer.secho(f"Error: {e}", fg="red", err=True)
        raise typer.Exit(code=1)


def fix(
    path: str = typer.Argument(
        ".",
        help="Path to fix",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview changes without modifying files",
    ),
    backup: bool = typer.Option(
        True,
        "--backup/--no-backup",
        help="Create backup before applying fixes (recommended)",
    ),
    auto: bool = typer.Option(
        True,
        "--auto/--no-auto",
        help="Run automatic safe fixes",
    ),
    framework: str = typer.Option(
        None,
        "--framework",
        help="Framework hint: claude, langchain, crewai, or openai (auto-detect if omitted)",
    ),
    format: str = typer.Option(
        "text",
        "--format",
        "-f",
        help="Output format: text or json",
    ),
) -> None:
    """Apply safe automatic fixes for skill frontmatter and vault migration."""
    try:
        target = Path(path).resolve()
        if not target.exists():
            typer.secho(f"Error: Path does not exist: {path}", fg="red", err=True)
            raise typer.Exit(code=1)

        # Create backup if not dry-run
        backup_mgr = None
        if backup and not dry_run:
            backup_mgr = BackupManager(target)
            # Backup all Python files
            backed_up = backup_mgr.backup_directory(target, "**/*.py")
            if backed_up > 0:
                typer.secho(f"✓ Backed up {backed_up} files", fg="green")
                backup_mgr.save_manifest()

        auditor = Auditor(target, framework_hint=framework)
        audit_result = auditor.audit()

        fixer = Fixer(target, dry_run=dry_run, auto=auto)
        fix_plan = fixer.fix(audit_result)

        print_fix_report(audit_result, fix_plan, format=format, dry_run=dry_run)
        
        if backup_mgr and backup_mgr.has_backups():
            typer.secho(backup_mgr.get_backup_summary(), fg="cyan")

    except Exception as e:
        typer.secho(f"Error: {e}", fg="red", err=True)
        raise typer.Exit(code=1)



def rollback(
    path: str = typer.Argument(
        ".",
        help="Path to rollback",
    ),
    backup_index: int = typer.Option(
        0,
        "--index",
        "-i",
        help="Backup index to restore from (0=most recent, 1=previous, etc)",
    ),
    list_backups: bool = typer.Option(
        False,
        "--list",
        "-l",
        help="List available backups instead of restoring",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Rollback to a previous backup state."""
    try:
        target = Path(path).resolve()
        if not target.exists():
            typer.secho(f"Error: Path does not exist: {path}", fg="red", err=True)
            raise typer.Exit(code=1)

        backups = BackupRestorer.list_backups(target)
        
        if not backups:
            typer.secho("✓ No backups found", fg="yellow")
            raise typer.Exit(code=0)
        
        if list_backups:
            typer.secho("Available backups (newest first):", fg="cyan")
            for idx, backup_path in enumerate(backups):
                info = BackupRestorer.get_backup_info(backup_path)
                if info:
                    backup_name = backup_path.name
                    timestamp = info.get("timestamp", "unknown")
                    file_count = info.get("files_count", 0)
                    size_kb = info.get("total_size_bytes", 0) / 1024
                    typer.secho(
                        f"  [{idx}] {backup_name}\n"
                        f"      Time: {timestamp}\n"
                        f"      Files: {file_count}, Size: {size_kb:.1f} KB",
                        fg="white"
                    )
            raise typer.Exit(code=0)
        
        # Validate index
        if backup_index < 0 or backup_index >= len(backups):
            typer.secho(
                f"Error: Invalid backup index {backup_index} (available: 0-{len(backups)-1})",
                fg="red",
                err=True
            )
            raise typer.Exit(code=1)
        
        backup_to_restore = backups[backup_index]
        info = BackupRestorer.get_backup_info(backup_to_restore)
        
        typer.secho(f"Restoring from: {backup_to_restore.name}", fg="yellow")
        if info:
            typer.secho(f"  Files: {info.get('files_count', 0)}, Size: {info.get('total_size_bytes', 0) / 1024:.1f} KB")
        
        # Confirm restore (skip if --yes provided)
        if not yes:
            confirm = typer.confirm("Proceed with rollback?")
            if not confirm:
                typer.secho("Rollback cancelled", fg="yellow")
                raise typer.Exit(code=0)
        
        # Restore
        success = BackupRestorer.restore(backup_to_restore, target)
        
        if success:
            typer.secho("✓ Rollback completed successfully", fg="green")
            raise typer.Exit(code=0)
        else:
            typer.secho("⚠ Rollback completed with errors (see logs)", fg="yellow")
            raise typer.Exit(code=1)

    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(f"Error: {e}", fg="red", err=True)
        raise typer.Exit(code=1)


app.command()(audit)
app.command()(migrate)
app.command()(fix)
app.command()(rollback)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
