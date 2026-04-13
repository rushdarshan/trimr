import json

from typer.testing import CliRunner

from trimr.audit import Auditor
from trimr.cli import app
from trimr.fixer import Fixer
from trimr.models import ViolationCode
from trimr.reporter import render_fix_json_report


runner = CliRunner()


def run_fix(target, dry_run=False):
    audit_result = Auditor(target).audit()
    fixer = Fixer(target, dry_run=dry_run)
    return audit_result, fixer.fix(audit_result)


def test_fix_dry_run_preserves_orphan_markdown(tmp_path):
    skill_file = tmp_path / "skills" / "pdf" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    original = "# PDF helper\n\nExtract text from PDF files."
    skill_file.write_text(original, encoding="utf-8")

    audit_result, plan = run_fix(tmp_path, dry_run=True)

    assert any(v.code == ViolationCode.NO_FRONTMATTER for v in audit_result.violations)
    assert skill_file.read_text(encoding="utf-8") == original
    assert not (tmp_path / ".vault").exists()
    assert {change.change_type for change in plan.changes} == {"frontmatter_added", "skill_moved"}


def test_fix_adds_frontmatter_to_vaulted_orphan(tmp_path):
    skill_file = tmp_path / ".vault" / "skills" / "pdf" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("# PDF helper\n\nExtract text from PDF files.", encoding="utf-8")

    _, plan = run_fix(tmp_path)

    fixed = skill_file.read_text(encoding="utf-8")
    assert fixed.startswith("---\n")
    assert "name: PDF helper" in fixed
    assert "description:" in fixed
    assert [change.change_type for change in plan.changes] == ["frontmatter_added"]


def test_fix_orphan_skill_gets_frontmatter_then_moves_to_vault(tmp_path):
    skill_file = tmp_path / "skills" / "docx" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    body = "# DOCX helper\n\nExtract structured content from Word documents."
    skill_file.write_text(body, encoding="utf-8")

    _, plan = run_fix(tmp_path)

    vault_file = tmp_path / ".vault" / "skills" / "docx" / "SKILL.md"
    assert vault_file.exists()
    vault_content = vault_file.read_text(encoding="utf-8")
    assert vault_content.startswith("---\n")
    assert "name: DOCX helper" in vault_content
    assert body in vault_content

    pointer = skill_file.read_text(encoding="utf-8")
    assert 'load_skill(".vault/skills/docx/SKILL.md")' in pointer
    assert [change.change_type for change in plan.changes] == ["frontmatter_added", "skill_moved"]


def test_fix_migrates_ungated_skill_and_writes_pointer(tmp_path):
    skill_file = tmp_path / "skills" / "pdf" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    original = """---
name: PDF Extraction
description: Extracts text and metadata from PDF files
---

Body content for PDF extraction.
"""
    skill_file.write_text(original, encoding="utf-8")

    _, plan = run_fix(tmp_path)

    vault_file = tmp_path / ".vault" / "skills" / "pdf" / "SKILL.md"
    assert vault_file.read_text(encoding="utf-8") == original
    pointer = skill_file.read_text(encoding="utf-8")
    assert pointer.startswith("---\n")
    assert "load_skill" in pointer
    assert ".vault/skills/pdf/SKILL.md" in pointer
    assert [change.change_type for change in plan.changes] == ["skill_moved"]


def test_fix_migrates_claude_skill_root_to_shared_vault(tmp_path):
    skill_file = tmp_path / ".claude" / "skills" / "search" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: Search\ndescription: Searches project documents\n---\n\nSearch body.",
        encoding="utf-8",
    )

    run_fix(tmp_path)

    assert (tmp_path / ".vault" / "skills" / "search" / "SKILL.md").exists()
    assert ".vault/skills/search/SKILL.md" in skill_file.read_text(encoding="utf-8")


def test_fix_does_not_move_global_instruction_with_skill_frontmatter(tmp_path):
    claude_file = tmp_path / "CLAUDE.md"
    original = "---\nname: Project\ndescription: Project instructions\n---\n\nGlobal instructions."
    claude_file.write_text(original, encoding="utf-8")

    _, plan = run_fix(tmp_path)

    assert claude_file.read_text(encoding="utf-8") == original
    assert not (tmp_path / ".vault").exists()
    assert plan.changes == []


def test_fix_skips_existing_pointer_file(tmp_path):
    pointer_file = tmp_path / "skills" / "pdf" / "SKILL.md"
    pointer_file.parent.mkdir(parents=True)
    original = """---
name: PDF Extraction
description: Pointer for PDF extraction
---

Use `load_skill(".vault/skills/pdf/SKILL.md")`.
"""
    pointer_file.write_text(original, encoding="utf-8")

    _, plan = run_fix(tmp_path)

    assert pointer_file.read_text(encoding="utf-8") == original
    assert plan.changes == []


def test_fix_uses_unique_vault_path_when_target_exists(tmp_path):
    existing = tmp_path / ".vault" / "skills" / "pdf" / "SKILL.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("existing vault content", encoding="utf-8")

    skill_file = tmp_path / "skills" / "pdf" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: PDF\ndescription: Extracts PDF files\n---\n\nnew content",
        encoding="utf-8",
    )

    _, plan = run_fix(tmp_path)

    new_vault_file = tmp_path / ".vault" / "skills" / "pdf-2" / "SKILL.md"
    assert new_vault_file.exists()
    assert "new content" in new_vault_file.read_text(encoding="utf-8")
    assert ".vault/skills/pdf-2/SKILL.md" in skill_file.read_text(encoding="utf-8")
    moved_change = next(change for change in plan.changes if change.change_type == "skill_moved")
    assert moved_change.target in {".vault\\skills\\pdf-2\\SKILL.md", ".vault/skills/pdf-2/SKILL.md"}


def test_fix_json_report_is_valid(tmp_path):
    skill_file = tmp_path / "skills" / "pdf" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: PDF\ndescription: Extracts PDF files\n---\n\ncontent",
        encoding="utf-8",
    )

    audit_result, plan = run_fix(tmp_path, dry_run=True)
    data = json.loads(render_fix_json_report(audit_result, plan, dry_run=True))

    assert data["dry_run"] is True
    assert data["summary"]["skills_moved"] == 1
    assert data["changes"][0]["type"] == "skill_moved"


def test_cli_fix_dry_run_command_works(tmp_path):
    skill_file = tmp_path / "skills" / "pdf" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: PDF\ndescription: Extracts PDF files\n---\n\ncontent",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["fix", "--dry-run", str(tmp_path)])

    assert result.exit_code == 0
    assert "trimr fix [DRY-RUN]" in result.output
    assert "DRY-RUN: No files were modified." in result.output
    assert skill_file.exists()
    assert not (tmp_path / ".vault").exists()


def test_cli_fix_json_output_works(tmp_path):
    skill_file = tmp_path / "skills" / "pdf" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: PDF\ndescription: Extracts PDF files\n---\n\ncontent",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["fix", str(tmp_path), "--dry-run", "--format", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert data["summary"]["skills_moved"] == 1


def test_audit_does_not_flag_plain_pointer_without_frontmatter(tmp_path):
    pointer_file = tmp_path / "skills" / "pointer.md"
    pointer_file.parent.mkdir(parents=True)
    pointer_file.write_text(
        "# Pointer\n\nUse `load_skill(\".vault/skills/pdf/SKILL.md\")`.",
        encoding="utf-8",
    )

    result = Auditor(tmp_path).audit()

    assert not any(v.code == ViolationCode.NO_FRONTMATTER for v in result.violations)
