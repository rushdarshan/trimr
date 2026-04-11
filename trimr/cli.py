import sys
from pathlib import Path
import typer
from typing import Optional

from .audit import Auditor
from .reporter import print_report

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


app.command()(audit)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
