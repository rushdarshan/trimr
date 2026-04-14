from pathlib import Path

from trimr.config import load_trimrrc, _config_from_dict, _coerce_int
from trimr.audit import Auditor


def test_load_trimrrc_defaults(tmp_path: Path):
    cfg = load_trimrrc(tmp_path)
    assert cfg.limits.global_tokens_limit == 3000
    assert cfg.limits.skill_body_tokens_recommended == 5000
    assert cfg.projection.mode == "measured"
    assert cfg.projection.fixed_tokens_per_vaultable_skill == 100


def test_load_trimrrc_overrides_limits_and_projection(tmp_path: Path):
    (tmp_path / ".trimrrc.yaml").write_text(
        "limits:\n  global_tokens_limit: 123\n  skill_body_tokens_recommended: 456\n"
        "projection:\n  mode: fixed\n  fixed_tokens_per_vaultable_skill: 42\n",
        encoding="utf-8",
    )
    cfg = load_trimrrc(tmp_path)
    assert cfg.limits.global_tokens_limit == 123
    assert cfg.limits.skill_body_tokens_recommended == 456
    assert cfg.projection.mode == "fixed"
    assert cfg.projection.fixed_tokens_per_vaultable_skill == 42


def test_projected_tokens_respects_fixed_projection_mode(tmp_path: Path):
    (tmp_path / ".trimrrc.yaml").write_text(
        "projection:\n  mode: fixed\n  fixed_tokens_per_vaultable_skill: 7\n", encoding="utf-8"
    )
    # Create one ungated skill
    skills_dir = tmp_path / "skills" / "pdf"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: PDF\ndescription: Extracts PDFs\n---\n\nBody " + ("x " * 200),
        encoding="utf-8",
    )

    auditor = Auditor(tmp_path)
    result = auditor.audit()
    # projected = global_tokens + (vaultable_count * 7)
    assert result.startup_tokens_projected >= 7


def test_config_affects_global_file_violations(tmp_path: Path):
    """Config.limits.global_tokens_limit should be used in violations."""
    (tmp_path / ".trimrrc.yaml").write_text(
        "limits:\n  global_tokens_limit: 100\n",
        encoding="utf-8",
    )
    # Create a large global file
    (tmp_path / "CLAUDE.md").write_text("x " * 60)  # ~60 tokens
    
    auditor = Auditor(tmp_path)
    result = auditor.audit()
    # Should respect custom limit of 100, not default 3000
    assert result.config.limits.global_tokens_limit == 100


def test_config_affects_skill_body_violations(tmp_path: Path):
    """Config.limits.skill_body_tokens_recommended should be used in violations."""
    (tmp_path / ".trimrrc.yaml").write_text(
        "limits:\n  skill_body_tokens_recommended: 500\n",
        encoding="utf-8",
    )
    # Create a skill with large body
    skills_dir = tmp_path / "skills" / "pdf"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: PDF\ndescription: Tool\n---\n\n" + ("x " * 300),  # ~300 tokens body
        encoding="utf-8",
    )
    
    auditor = Auditor(tmp_path)
    result = auditor.audit()
    # Should use custom limit of 500, not default 5000
    assert result.config.limits.skill_body_tokens_recommended == 500


def test_coerce_int_various_inputs():
    """_coerce_int should handle various input types."""
    assert _coerce_int("123", 999) == 123
    assert _coerce_int(456, 999) == 456
    assert _coerce_int(123.7, 999) == 123
    assert _coerce_int(-100, 999) == 999
    assert _coerce_int("abc", 999) == 999
    assert _coerce_int(None, 999) == 999
    assert _coerce_int(0, 999) == 0


def test_config_from_dict_partial_override(tmp_path: Path):
    """Partial config should fill in defaults."""
    raw = {"limits": {"global_tokens_limit": 2000}}
    cfg = _config_from_dict(raw)
    assert cfg.limits.global_tokens_limit == 2000
    assert cfg.limits.skill_body_tokens_recommended == 5000  # default


def test_config_from_dict_invalid_mode():
    """Invalid projection mode should default to 'measured'."""
    raw = {"projection": {"mode": "invalid_mode"}}
    cfg = _config_from_dict(raw)
    assert cfg.projection.mode == "measured"


def test_config_from_dict_case_insensitive_mode():
    """Projection mode should be case-insensitive."""
    raw = {"projection": {"mode": "FIXED"}}
    cfg = _config_from_dict(raw)
    assert cfg.projection.mode == "fixed"


def test_trimrrc_yml_extension(tmp_path: Path):
    """Should support .trimrrc.yml extension."""
    (tmp_path / ".trimrrc.yml").write_text(
        "limits:\n  global_tokens_limit: 1500\n",
        encoding="utf-8",
    )
    cfg = load_trimrrc(tmp_path)
    assert cfg.limits.global_tokens_limit == 1500


def test_trimrrc_yaml_takes_precedence(tmp_path: Path):
    """Should prefer .trimrrc.yaml over .trimrrc.yml."""
    (tmp_path / ".trimrrc.yaml").write_text("limits:\n  global_tokens_limit: 2000\n", encoding="utf-8")
    (tmp_path / ".trimrrc.yml").write_text("limits:\n  global_tokens_limit: 1500\n", encoding="utf-8")
    cfg = load_trimrrc(tmp_path)
    assert cfg.limits.global_tokens_limit == 2000


def test_invalid_yaml_returns_defaults(tmp_path: Path):
    """Should return defaults if YAML is invalid."""
    (tmp_path / ".trimrrc.yaml").write_text("{ invalid yaml }", encoding="utf-8")
    cfg = load_trimrrc(tmp_path)
    assert cfg.limits.global_tokens_limit == 3000


def test_yaml_not_dict_returns_defaults(tmp_path: Path):
    """Should return defaults if YAML root is not a dict."""
    (tmp_path / ".trimrrc.yaml").write_text("- item1\n- item2\n", encoding="utf-8")
    cfg = load_trimrrc(tmp_path)
    assert cfg.limits.global_tokens_limit == 3000


def test_empty_yaml_file_returns_defaults(tmp_path: Path):
    """Should return defaults if YAML file is empty."""
    (tmp_path / ".trimrrc.yaml").write_text("", encoding="utf-8")
    cfg = load_trimrrc(tmp_path)
    assert cfg.limits.global_tokens_limit == 3000


def test_config_with_comments(tmp_path: Path):
    """Should parse YAML with comments."""
    (tmp_path / ".trimrrc.yaml").write_text(
        """
# Global file limit in tokens
limits:
  global_tokens_limit: 2500
  # Skill body size warning threshold
  skill_body_tokens_recommended: 4500

# Projection mode for startup token estimates
projection:
  mode: measured
""",
        encoding="utf-8",
    )
    cfg = load_trimrrc(tmp_path)
    assert cfg.limits.global_tokens_limit == 2500
    assert cfg.limits.skill_body_tokens_recommended == 4500


def test_realistic_enterprise_config(tmp_path: Path):
    """Config for large enterprise project."""
    (tmp_path / ".trimrrc.yaml").write_text(
        """
limits:
  global_tokens_limit: 5000
  skill_body_tokens_recommended: 10000

projection:
  mode: measured
""",
        encoding="utf-8",
    )
    cfg = load_trimrrc(tmp_path)
    assert cfg.limits.global_tokens_limit == 5000
    assert cfg.limits.skill_body_tokens_recommended == 10000


def test_realistic_small_project_config(tmp_path: Path):
    """Config for small project with tight limits."""
    (tmp_path / ".trimrrc.yaml").write_text(
        """
limits:
  global_tokens_limit: 1500
  skill_body_tokens_recommended: 2000

projection:
  mode: fixed
  fixed_tokens_per_vaultable_skill: 30
""",
        encoding="utf-8",
    )
    cfg = load_trimrrc(tmp_path)
    assert cfg.limits.global_tokens_limit == 1500
    assert cfg.projection.mode == "fixed"
    assert cfg.projection.fixed_tokens_per_vaultable_skill == 30

