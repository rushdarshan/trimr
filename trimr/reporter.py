import json
from typing import Optional

from .models import AuditResult, ViolationSeverity
from .migrator import MigrationPlan


def render_text_report(result: AuditResult) -> str:
    """Render audit result as formatted text output."""
    lines = []
    
    lines.append(f"trimr audit - {result.path}")
    lines.append("-" * 60)
    lines.append("")
    
    if result.global_files:
        lines.append("Global instruction files")
        for gf in result.global_files:
            marker = " ! EXCEEDS 3,000 token limit" if gf.over_limit else ""
            if gf.over_limit:
                lines.append(f"  {gf.path:<30} {gf.tokens:>6,} tokens{marker} (+{gf.excess})")
            else:
                lines.append(f"  {gf.path:<30} {gf.tokens:>6,} tokens")
        lines.append("")
    
    if result.skills:
        ungated_count = sum(1 for s in result.skills if s.ungated)
        vaultable_count = sum(1 for s in result.skills if s.vaultable)
        
        lines.append(f"Skill files ({len(result.skills)} found)")
        if ungated_count > 0:
            ungated_tokens = sum(s.tokens for s in result.skills if s.ungated)
            lines.append(f"  Ungated (globally loaded):   {ungated_count} skills       ~{ungated_tokens:,} tokens at startup")
        if vaultable_count > 0:
            lines.append(f"  Vaultable:                   {vaultable_count} skills       eligible for migration")
        lines.append("")
    
    lines.append("Startup token cost")
    lines.append(f"  Current:                     ~{result.startup_tokens_current:,} tokens")
    lines.append(f"  After migration:             ~{result.startup_tokens_projected:,} tokens")
    lines.append(f"  Reduction:                   {result.reduction_percent:.1f}%")
    lines.append("")
    
    if result.violations:
        lines.append(f"Violations ({len(result.violations)})")
        for v in result.violations:
            severity_str = f"[{v.severity.value}]"
            lines.append(f"  {severity_str:<12} {v.file} | {v.detail}")
        lines.append("")
        lines.append("Run `trimr migrate ./path` to auto-fix.")

    
    return "\n".join(lines)


def render_json_report(result: AuditResult) -> str:
    """Render audit result as JSON."""
    data = {
        "path": result.path,
        "startup_tokens_current": result.startup_tokens_current,
        "startup_tokens_projected": result.startup_tokens_projected,
        "reduction_percent": round(result.reduction_percent, 1),
        "global_files": [
            {
                "path": gf.path,
                "tokens": gf.tokens,
                "over_limit": gf.over_limit,
                "excess": gf.excess,
            }
            for gf in result.global_files
        ],
        "skills": [
            {
                "path": s.path,
                "tokens": s.tokens,
                "has_frontmatter": s.has_frontmatter,
                "description_length": s.description_length,
                "ungated": s.ungated,
                "vaultable": s.vaultable,
            }
            for s in result.skills
        ],
        "violations": [
            {
                "code": v.code.value,
                "severity": v.severity.value,
                "file": v.file,
                "detail": v.detail,
            }
            for v in result.violations
        ],
    }
    return json.dumps(data, indent=2)


def render_migration_text_report(audit_result: AuditResult, migration_plan: MigrationPlan, dry_run: bool = False) -> str:
    """Render migration results as formatted text output."""
    lines = []
    
    dry_run_marker = " [DRY-RUN]" if dry_run else ""
    lines.append(f"trimr migrate{dry_run_marker} - {migration_plan.target_path}")
    lines.append("-" * 60)
    lines.append("")
    
    if not migration_plan.changes:
        lines.append("No changes needed.")
        return "\n".join(lines)
    
    lines.append("Changes to be applied:")
    lines.append("")
    
    skills_moved = [c for c in migration_plan.changes if c.change_type == "skill_moved"]
    globals_truncated = [c for c in migration_plan.changes if c.change_type == "global_truncated"]
    
    if skills_moved:
        lines.append(f"Skills migrated to .vault/ ({len(skills_moved)} moved)")
        for change in skills_moved:
            lines.append(f"  → {change.source}")
            lines.append(f"    Saved: {change.tokens_saved:,} tokens")
        lines.append("")
    
    if globals_truncated:
        lines.append(f"Global files truncated ({len(globals_truncated)} truncated)")
        for change in globals_truncated:
            lines.append(f"  → {change.source}")
            lines.append(f"    Saved: {change.tokens_saved:,} tokens")
        lines.append("")
    
    lines.append(f"Total tokens saved: {migration_plan.total_tokens_saved:,}")
    lines.append("")
    
    if dry_run:
        lines.append("DRY-RUN: No files were modified.")
        lines.append("Run `trimr migrate ./path` (without --dry-run) to apply changes.")
    else:
        lines.append("✓ Migration complete!")
    
    return "\n".join(lines)


def render_migration_json_report(audit_result: AuditResult, migration_plan: MigrationPlan, dry_run: bool = False) -> str:
    """Render migration results as JSON."""
    data = {
        "target": str(migration_plan.target_path),
        "dry_run": dry_run,
        "changes": [
            {
                "type": c.change_type,
                "source": c.source,
                "target": c.target,
                "tokens_saved": c.tokens_saved,
                "reason": c.reason,
            }
            for c in migration_plan.changes
        ],
        "total_tokens_saved": migration_plan.total_tokens_saved,
        "summary": {
            "skills_moved": sum(1 for c in migration_plan.changes if c.change_type == "skill_moved"),
            "globals_truncated": sum(1 for c in migration_plan.changes if c.change_type == "global_truncated"),
        },
    }
    return json.dumps(data, indent=2)


def print_report(result: AuditResult, format: str = "text") -> None:
    """Print audit report to console."""
    if format == "json":
        output = render_json_report(result)
        print(output)
    else:
        output = render_text_report(result)
        for line in output.split("\n"):
            print(line)


def print_migration_report(audit_result: AuditResult, migration_plan: MigrationPlan, format: str = "text", dry_run: bool = False) -> None:
    """Print migration report to console."""
    if format == "json":
        output = render_migration_json_report(audit_result, migration_plan, dry_run=dry_run)
        print(output)
    else:
        output = render_migration_text_report(audit_result, migration_plan, dry_run=dry_run)
        for line in output.split("\n"):
            print(line)
