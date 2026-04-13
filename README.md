# Trimr v0.2

**Token audit and migration tool for AI agent projects**

Audits AI agent projects for token bloat, enforces context budget limits, and automatically migrates skills to progressive-disclosure architecture (`.vault/` directories).

## Who This Is For

**trimr is optimized for Claude Code and Cursor IDE** projects using markdown-based skills with YAML frontmatter. Audits token bloat in global instruction files and ungated skills, calculates startup costs, and auto-migrates to progressive-disclosure architecture.

## Quick Start

```bash
# Install
pip install trimr

# Audit a project
trimr audit ./path/to/agent
trimr audit ./path/to/agent --format json

# Preview migration (dry-run)
trimr fix ./path/to/agent --dry-run

# Apply migration (actually moves files)
trimr fix ./path/to/agent
```

## What It Does

### `trimr audit` — Detect violations

1. **Walks** your project recursively (respecting `.gitignore` and excluding `node_modules/`, `__pycache__/`, hidden dirs)
2. **Detects** global instruction files (CLAUDE.md, AGENTS.md, .cursorrules, etc.)
3. **Identifies** skill files (markdown with YAML frontmatter containing `name` and `description` fields)
4. **Counts** tokens using tiktoken (cl100k_base encoding) with word-count fallback
5. **Detects** violations:
   - `MALFORMED_FRONTMATTER`: `---` not at line 1 or invalid YAML
   - `GLOBAL_BLOAT`: Single global file > 3,000 tokens
   - `CUMULATIVE_GLOBAL_BLOAT`: All global files combined > 3,000 tokens
   - `SKILL_UNGATED`: Skill outside vault, eligible for migration
   - `NO_FRONTMATTER`: Markdown in skills/ without YAML frontmatter
   - `EMPTY_DESCRIPTION`: Skill description < 10 chars
   - `SKILL_BODY_LARGE`: Skill body > 5,000 tokens
   - `NON_ASCII_ESTIMATE`: File > 20% non-ASCII characters
6. **Reports** startup token costs and post-migration projections

### `trimr migrate` — Auto-fix violations (v0.2)

1. **Moves** ungated skills (> 150 tokens) to `.vault/skills/<category>/SKILL.md`
2. **Generates** pointer files in original locations with `load_skill` instructions
3. **Updates** CLAUDE.md with load_skill blocks for migrated skills
4. **Truncates** global files exceeding 3,000 tokens while preserving YAML frontmatter
5. **Supports** `--dry-run` to preview changes without modifying files
6. **Calculates** token savings for each change

## Example Workflows

### Audit workflow

```bash
$ trimr audit ./my-agent

trimr audit - ./my-agent
────────────────────────────────────────────────────

Global instruction files
  CLAUDE.md                      4,847 tokens ! EXCEEDS 3,000 token limit (+1,847)

Skill files (12 found)
  Ungated (globally loaded):   9 skills       ~13,500 tokens at startup
  Vaultable:                   9 skills       eligible for migration

Startup token cost
  Current:                     ~18,347 tokens
  After migration:             ~1,547 tokens
  Reduction:                   91.6%

Violations (4)
  [CRITICAL]  CLAUDE.md | exceeds global limit by 1,847 tokens
  [WARN]      skills/pdf/SKILL.md | ungated, only used in 1 workflow
  [WARN]      skills/search/SKILL.md | description is 6 chars, routing will fail

Run `trimr migrate ./path` to auto-fix.
```

### Migration workflow

```bash
# Preview changes
$ trimr migrate ./my-agent --dry-run

trimr migrate [DRY-RUN] - ./my-agent
────────────────────────────────────────────────────

Changes to be applied:

Skills migrated to .vault/ (9 moved)
  → skills/pdf/SKILL.md
    Saved: 1,823 tokens
  → skills/docx/SKILL.md
    Saved: 1,450 tokens
  [... 7 more ...]

Global files truncated (1 truncated)
  → CLAUDE.md
    Saved: 1,847 tokens

Total tokens saved: 13,000

DRY-RUN: No files were modified.
Run `trimr migrate ./path` (without --dry-run) to apply changes.

# Apply changes
$ trimr migrate ./my-agent

trimr migrate - ./my-agent
────────────────────────────────────────────────────

Changes to be applied:
[... migration complete ...]

✓ Migration complete!
```

## Requirements

- Python 3.11+
- Dependencies:
  - typer (CLI framework)
  - tiktoken (token counting)
  - PyYAML (YAML parsing)
  - pathspec (.gitignore parsing)

## Project Structure

```
trimr/
  trimr/
    __init__.py          # Package init
    cli.py               # Typer app entry point (audit + migrate)
    audit.py             # Core audit logic
    migrator.py          # Migration logic (v0.2)
    models.py            # Dataclasses for results
    tokenizer.py         # Tiktoken wrapper + fallback
    parser.py            # YAML frontmatter detection (strict line 1 rule)
    reporter.py          # Text + JSON output formatters
  tests/
    test_audit.py
    test_migrator.py      # Migration tests (v0.2)
    test_tokenizer.py
    test_parser.py
    fixtures/
      bloated_project/   # Sample project with violations
      clean_project/     # Reference project
  pyproject.toml
  README.md
```

## Key Features

- **Strict line 1 rule**: Frontmatter delimiters (`---`) must be at byte offset 0. Files with blank lines or spaces before `---` are rejected.
- **Token counting**: Accurate via tiktoken (cl100k_base), falls back to 1.3x word-count if unavailable.
- **Directory exclusions**: Hardcoded (node_modules, __pycache__, .venv, etc.) + respects .gitignore.
- **Vault-aware**: Recognizes `.vault/`, `vault/`, `_vault/` directories for gated skills.
- **Safe migration**: Dry-run preview + actual migration preserve all original content (pointer files, truncation markers).
- **Portable**: No heavy dependencies; pure static analysis.

## Development

```bash
# Setup
pip install -e .

# Run all tests (66 tests)
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_migrator.py -v

# Audit a fixture
trimr audit tests/fixtures/bloated_project
trimr audit tests/fixtures/clean_project --format json

# Test migration on fixture (dry-run)
trimr migrate tests/fixtures/bloated_project --dry-run
```

## Status

✅ All 66 tests passing (54 v0.1 + 12 v0.2)
✅ `trimr audit` command tested on real projects
✅ `trimr migrate --dry-run` tested on job folder (previewed 1,476 tokens saved)
✅ JSON output valid for both commands
✅ `pip install -e .` works
✅ `--dry-run` prevents file modifications
✅ Pointer file generation with `load_skill` instructions
✅ Global file truncation with frontmatter preservation
