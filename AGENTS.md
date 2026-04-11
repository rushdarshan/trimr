---
name: trimr
description: Token audit and migration tool for AI agent projects
---

# Trimr — Workspace Instructions

## What we're building

A Python CLI tool that audits AI agent projects for token bloat, enforces context budget limits, and migrates skill folder structures to progressive-disclosure-compatible layouts.

Target user: developers building or maintaining LLM agent projects (Claude Code, Cursor, Copilot, any SKILL.md-compatible agent).

## Tech stack

- Python 3.11+
- **Typer** — CLI framework
- **tiktoken** — token counting (cl100k_base encoding)
- **PyYAML** — YAML frontmatter parsing
- **rich** — terminal output formatting
- **pathspec** — .gitignore parsing
- Package management: **uv**

## v0.1 scope

**Command:** `trimr audit <path> [--format text|json] [--fix]`

**What it does:**
1. Recursively walk target directory (respecting .gitignore and hardcoded exclusions)
2. Identify global instruction files (CLAUDE.md, AGENTS.md, .cursorrules, etc.)
3. Detect skill files (YAML frontmatter with `name` + `description` fields, opening `---` on line 1)
4. Count tokens using tiktoken cl100k_base
5. Detect violations (malformed frontmatter, bloat, empty descriptions, etc.)
6. Calculate current vs. post-migration startup token cost
7. Print report in text or JSON format

**Key thresholds:**
- Global instruction file limit: **3,000 tokens**
- Skill body recommendation: **under 5,000 tokens**
- Pointer file limit (ungated → vaultable): **under 200 tokens**
- Non-ASCII character threshold for warning: **>20%**

**Ungated skill detection:** Skill lives outside `.vault/`, `vault/`, `_vault/` AND not referenced via pointer file.

**Pointer file markers:** Contains `load_skill`, `skill_id`, `list_dir`, `ls`, `view_file`, `read_file`, or `cat`.

## Project structure

```
trimr/
  trimr/
    __init__.py         ← package init
    cli.py              ← typer app entry point
    audit.py            ← core audit logic
    models.py           ← AuditResult, SkillReport, Violation dataclasses
    tokenizer.py        ← tiktoken wrapper + fallback
    parser.py           ← YAML frontmatter detection & parsing
    reporter.py         ← rich terminal output renderer
  tests/
    test_audit.py
    test_tokenizer.py
    test_parser.py
    fixtures/
      bloated_project/    ← sample with violations
      clean_project/      ← reference project
  pyproject.toml
  README.md
```

## Development workflow

### Setup
```bash
# Using uv
uv sync
uv run trimr audit ./tests/fixtures/bloated_project

# Or install in dev mode
pip install -e .
trimr audit ./tests/fixtures/bloated_project
```

### Run tests
```bash
uv run pytest tests/ -v
```

### Build & publish
```bash
uv build
# Then: twine upload dist/* or use uv publish (when available)
```

## Code conventions

- **No docstrings required** for simple functions; use type hints instead
- **Rich output** for all user-facing text (use `console` instance from reporter.py)
- **Dataclasses** for all domain objects (models.py)
- **Fallback to word-count approximation** if tiktoken fails to load (log [WARN])
- **Never silently fail** — surface all errors with actionable messages
- **Exit code 1** if target path doesn't exist

## Violation detection rules

| Code | Severity | Condition |
|------|----------|-----------|
| `MALFORMED_FRONTMATTER` | CRITICAL | Skill file with `---` not on line 1 or invalid YAML between delimiters |
| `GLOBAL_BLOAT` | CRITICAL | Single global instruction file > 3,000 tokens |
| `CUMULATIVE_GLOBAL_BLOAT` | CRITICAL | Sum of all global instruction files > 3,000 tokens |
| `SKILL_UNGATED` | WARN | Skill is globally loaded and eligible for migration |
| `NO_FRONTMATTER` | WARN | .md file in `skills/` dir has no YAML frontmatter |
| `EMPTY_DESCRIPTION` | WARN | Skill description is empty or < 10 chars |
| `SKILL_BODY_LARGE` | INFO | Skill body > 5,000 tokens |
| `NON_ASCII_ESTIMATE` | INFO | File > 20% non-ASCII characters (token estimate may be understated) |

## Directory exclusions

**Unconditional (hardcoded):**
- Any dir starting with `.` except `.claude`, `.cursor`, `.agents`
- `node_modules/`, `dist/`, `build/`, `__pycache__/`, `.venv/`, `venv/`, `site-packages/`

**Conditional:** Parse `.gitignore` at target root using pathspec; skip matched paths.

## Output formats

### Text (default)
```
📊 trimr audit — ./my-agent
──────────────────────────────────────────────────
Global instruction files
  CLAUDE.md                    4,847 tokens   ⚠ EXCEEDS 3,000 token limit (+1,847)

Skill files (12 found)
  Ungated (globally loaded):   9 skills       ~13,500 tokens at startup
  Vaultable:                   9 skills       eligible for migration
  No frontmatter:              2 skills       unroutable

Startup token cost
  Current:                     ~18,347 tokens
  After migration:             ~1,547 tokens
  Reduction:                   91.6%

Violations (4)
  [CRITICAL]  CLAUDE.md — exceeds global limit by 1,847 tokens
  [WARN]      skills/pdf/SKILL.md — ungated, only used in 1 workflow
  [WARN]      skills/docx/SKILL.md — ungated, only used in 1 workflow
  [WARN]      skills/search/SKILL.md — description is 6 chars, routing will fail

Run `trimr migrate ./my-agent` to auto-fix.
```

### JSON
```json
{
  "path": "./my-agent",
  "startup_tokens_current": 18347,
  "startup_tokens_projected": 1547,
  "reduction_percent": 91.6,
  "global_files": [
    { "path": "CLAUDE.md", "tokens": 4847, "over_limit": true, "excess": 1847 }
  ],
  "skills": [
    {
      "path": "skills/pdf/SKILL.md",
      "tokens": 1823,
      "has_frontmatter": true,
      "description_length": 47,
      "ungated": true,
      "vaultable": true
    }
  ],
  "violations": [
    { "code": "GLOBAL_BLOAT", "severity": "CRITICAL", "file": "CLAUDE.md", "detail": "Exceeds 3000 token limit by 1847 tokens" }
  ]
}
```

## v0.2 scope (future)

`trimr migrate <path> [--dry-run]` — moves ungated skills into `.vault/skills/`, generates pointer files, injects load_skill instructions, truncates global files to <3K.

## Definition of done (v0.1)

- [x] Workspace instructions created
- [ ] Implement tokenizer.py (tiktoken + fallback)
- [ ] Implement parser.py (frontmatter detection, skill detection)
- [ ] Implement models.py (dataclasses)
- [ ] Implement audit.py (core logic)
- [ ] Implement reporter.py (rich text + JSON output)
- [ ] Implement cli.py (typer entry point)
- [ ] Write test fixtures (bloated_project, clean_project)
- [ ] Write tests (test_audit.py, test_tokenizer.py, test_parser.py)
- [ ] README with 30-second quickstart
- [ ] `trimr audit ./path` runs without error
- [ ] `--format json` emits valid JSON
- [ ] `pip install .` works
- [ ] `uvx trimr audit ./path` works

## Imports & dependencies

Keep imports minimal. Standard library first, then typer, tiktoken, yaml, rich, pathspec.

Avoid: pandas, numpy, requests, or any heavy dependencies. This is a CLI tool, not a data processing pipeline.
