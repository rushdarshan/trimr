import sys
from pathlib import Path
import typer
from typing import Optional

from .audit import Auditor
from .fixer import Fixer
from .migrator import Migrator
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
        
        auditor = Auditor(target)
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
        
        # Run audit first to get violations
        auditor = Auditor(target)
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
    auto: bool = typer.Option(
        True,
        "--auto/--no-auto",
        help="Run automatic safe fixes",
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

        auditor = Auditor(target)
        audit_result = auditor.audit()

        fixer = Fixer(target, dry_run=dry_run, auto=auto)
        fix_plan = fixer.fix(audit_result)

        print_fix_report(audit_result, fix_plan, format=format, dry_run=dry_run)

    except Exception as e:
        typer.secho(f"Error: {e}", fg="red", err=True)
        raise typer.Exit(code=1)


app.command()(audit)
app.command()(migrate)
app.command()(fix)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
