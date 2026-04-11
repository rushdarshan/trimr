# Trimr v0.1

**Token audit and migration tool for AI agent projects**

Audits AI agent projects for token bloat, enforces context budget limits, and identifies skills eligible for progressive-disclosure migration to `.vault/` directories.

## Quick Start

```bash
# Install
pip install -e .

# Audit a project
trimr ./path/to/agent
trimr ./path/to/agent --format json
```

## What It Does

The `trimr audit` command:

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

## Example Output (Text)

```
trimr audit - ./my-agent
------------------------------------------------------------
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
    cli.py               # Typer app entry point
    audit.py             # Core audit logic
    models.py            # Dataclasses for results
    tokenizer.py         # Tiktoken wrapper + fallback
    parser.py            # YAML frontmatter detection (strict line 1 rule)
    reporter.py          # Text + JSON output formatters
  tests/
    test_audit.py
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
- **Portable**: No heavy dependencies; pure static analysis.

## Development

```bash
# Setup
uv sync
pip install -e . --quiet

# Run tests
python -m pytest tests/ -v

# Single test
python -m pytest tests/test_parser.py::TestLineOneRule -v

# Audit a fixture
trimr tests/fixtures/bloated_project
trimr tests/fixtures/clean_project --format json
```

## Future (v0.2)

`trimr migrate --dry-run` will auto-fix:
- Move ungated skills to `.vault/skills/`
- Generate pointer files
- Inject `load_skill` instructions
- Truncate global files to <3K tokens

## Status

✅ All 54 tests passing
✅ CLI runs without error
✅ JSON output valid
✅ `pip install -e .` works
