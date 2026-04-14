import json
from typing import Optional

from .models import AuditResult, ViolationSeverity
from .migrator import MigrationPlan


# Claude 3.5 Sonnet pricing: $3 per million input tokens
TOKENS_PER_DOLLAR = 1_000_000 / 3
SESSIONS_PER_DAY = 100

def _format_cost(tokens: int) -> str:
    """Format tokens as cost estimate."""
    cost = tokens / TOKENS_PER_DOLLAR
    return f"${cost:.4f}"

def _monthly_savings(tokens_saved: int) -> str:
    """Calculate monthly savings at 100 sessions/day."""
    daily_savings = (tokens_saved * SESSIONS_PER_DAY) / TOKENS_PER_DOLLAR
    monthly_savings = daily_savings * 30
    return f"${monthly_savings:.2f}/month"


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
    current_cost = _format_cost(result.startup_tokens_current)
    projected_cost = _format_cost(result.startup_tokens_projected)
    tokens_saved = result.startup_tokens_current - result.startup_tokens_projected
    monthly_savings = _monthly_savings(tokens_saved) if tokens_saved > 0 else "$0.00/month"
    
    lines.append(f"  Current:                     ~{result.startup_tokens_current:,} tokens  ({current_cost}/session)")
    lines.append(f"  After migration:             ~{result.startup_tokens_projected:,} tokens  ({projected_cost}/session)")
    lines.append(f"  Reduction:                   {result.reduction_percent:.1f}% — saves {monthly_savings} @ 100 sessions/day")
    lines.append("")
    
    if result.violations:
        lines.append(f"Violations ({len(result.violations)})")
        
        # Group violations by type
        config_violations = [v for v in result.violations if v.violation_type.value == "CONFIG"]
        arch_violations = [v for v in result.violations if v.violation_type.value == "ARCH"]
        
        if config_violations:
            lines.append("  [CONFIG] Quick fixes — 10 minutes each:")
            for v in config_violations:
                lines.append(f"    {v.file} | {v.detail}")
        
        if arch_violations:
            lines.append("  [ARCH] Structural improvements (real token savings):")
            for v in arch_violations:
                lines.append(f"    {v.file} | {v.detail}")
        
        lines.append("")
        lines.append("Run `trimr fix ./path` to auto-fix.")

    
    return "\n".join(lines)


def render_stats_section(result: AuditResult) -> str:
    """Render detailed statistics section."""
    lines = []
    
    lines.append("Statistics")
    lines.append("-" * 60)
    
    # File counts
    total_skills = len(result.skills)
    ungated_skills = sum(1 for s in result.skills if s.ungated)
    vaultable_skills = sum(1 for s in result.skills if s.vaultable)
    global_files = len(result.global_files)
    
    lines.append("")
    lines.append(f"Files:                           {global_files} global + {total_skills} skills")
    
    # Token distribution
    if result.skills:
        total_skill_tokens = sum(s.tokens for s in result.skills)
        avg_skill_tokens = total_skill_tokens // total_skills if total_skills > 0 else 0
        max_skill_tokens = max((s.tokens for s in result.skills), default=0)
        min_skill_tokens = min((s.tokens for s in result.skills), default=0)
        
        lines.append(f"Skill tokens:                    {total_skill_tokens:,} total")
        lines.append(f"  Average:                       {avg_skill_tokens:,} tokens/skill")
        lines.append(f"  Range:                         {min_skill_tokens:,}–{max_skill_tokens:,} tokens")
    
    if result.global_files:
        total_global_tokens = sum(g.tokens for g in result.global_files)
        avg_global_tokens = total_global_tokens // global_files if global_files > 0 else 0
        max_global_tokens = max((g.tokens for g in result.global_files), default=0)
        
        lines.append(f"Global file tokens:              {total_global_tokens:,} total")
        lines.append(f"  Average:                       {avg_global_tokens:,} tokens/file")
        lines.append(f"  Largest:                       {max_global_tokens:,} tokens")
    
    # Violation stats
    if result.violations:
        critical = sum(1 for v in result.violations if v.severity.value == "CRITICAL")
        warnings = sum(1 for v in result.violations if v.severity.value == "WARN")
        info = sum(1 for v in result.violations if v.severity.value == "INFO")
        
        lines.append(f"Violations:                      {critical} critical, {warnings} warnings, {info} info")
    
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


def render_fix_text_report(audit_result: AuditResult, fix_plan: MigrationPlan, dry_run: bool = False) -> str:
    """Render fix results as formatted text output."""
    lines = []

    dry_run_marker = " [DRY-RUN]" if dry_run else ""
    lines.append(f"trimr fix{dry_run_marker} - {fix_plan.target_path}")
    lines.append("-" * 60)
    lines.append("")

    if not fix_plan.changes:
        lines.append("No automatic fixes available.")
        return "\n".join(lines)

    lines.append("Changes to be applied:" if dry_run else "Changes applied:")
    lines.append("")

    frontmatter_added = [c for c in fix_plan.changes if c.change_type == "frontmatter_added"]
    skills_moved = [c for c in fix_plan.changes if c.change_type == "skill_moved"]

    if frontmatter_added:
        lines.append(f"Frontmatter added ({len(frontmatter_added)} files)")
        for change in frontmatter_added:
            lines.append(f"  -> {change.source}")
        lines.append("")

    if skills_moved:
        lines.append(f"Skills moved to .vault/ ({len(skills_moved)} files)")
        for change in skills_moved:
            lines.append(f"  -> {change.source}")
            if change.target:
                lines.append(f"    Vault: {change.target}")
            lines.append(f"    Saved: {change.tokens_saved:,} tokens")
        lines.append("")

    lines.append(f"Total tokens saved: {fix_plan.total_tokens_saved:,}")
    lines.append("")

    if dry_run:
        lines.append("DRY-RUN: No files were modified.")
        lines.append("Run `trimr fix ./path` without --dry-run to apply changes.")
    else:
        lines.append("Fix complete.")

    return "\n".join(lines)


def render_fix_json_report(audit_result: AuditResult, fix_plan: MigrationPlan, dry_run: bool = False) -> str:
    """Render fix results as JSON."""
    data = {
        "target": str(fix_plan.target_path),
        "dry_run": dry_run,
        "startup_tokens_current": audit_result.startup_tokens_current,
        "startup_tokens_projected": audit_result.startup_tokens_projected,
        "reduction_percent": round(audit_result.reduction_percent, 1),
        "total_tokens_saved": fix_plan.total_tokens_saved,
        "changes": [
            {
                "type": c.change_type,
                "source": c.source,
                "target": c.target,
                "tokens_saved": c.tokens_saved,
                "reason": c.reason,
            }
            for c in fix_plan.changes
        ],
        "summary": {
            "frontmatter_added": sum(1 for c in fix_plan.changes if c.change_type == "frontmatter_added"),
            "skills_moved": sum(1 for c in fix_plan.changes if c.change_type == "skill_moved"),
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


def print_fix_report(audit_result: AuditResult, fix_plan: MigrationPlan, format: str = "text", dry_run: bool = False) -> None:
    """Print fix report to console."""
    if format == "json":
        output = render_fix_json_report(audit_result, fix_plan, dry_run=dry_run)
        print(output)
    else:
        output = render_fix_text_report(audit_result, fix_plan, dry_run=dry_run)
        for line in output.split("\n"):
            print(line)
