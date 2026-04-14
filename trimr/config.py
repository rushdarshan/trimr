from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass(frozen=True)
class TrimrLimits:
    global_tokens_limit: int = 3000
    skill_body_tokens_recommended: int = 5000


@dataclass(frozen=True)
class TrimrProjection:
    # measured: estimate projected startup cost by generating the pointer/L1 text and counting tokens
    # fixed: use fixed_tokens_per_vaultable_skill
    mode: str = "measured"  # "measured" | "fixed"
    fixed_tokens_per_vaultable_skill: int = 100


@dataclass(frozen=True)
class TrimrConfig:
    limits: TrimrLimits = TrimrLimits()
    projection: TrimrProjection = TrimrProjection()


def load_trimrrc(target_path: Path) -> TrimrConfig:
    """
    Load `.trimrrc.yaml` (or `.trimrrc.yml`) from target root if present.

    Schema (minimal):
      limits:
        global_tokens_limit: 3000
        skill_body_tokens_recommended: 5000
      projection:
        mode: measured|fixed
        fixed_tokens_per_vaultable_skill: 100
    """
    for name in (".trimrrc.yaml", ".trimrrc.yml"):
        path = target_path / name
        if path.exists() and path.is_file():
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                return TrimrConfig()
            return _config_from_dict(raw)
    return TrimrConfig()


def _config_from_dict(raw: Dict[str, Any]) -> TrimrConfig:
    limits_raw = raw.get("limits", {})
    proj_raw = raw.get("projection", {})

    limits = TrimrLimits(
        global_tokens_limit=_coerce_int(limits_raw.get("global_tokens_limit"), default=3000),
        skill_body_tokens_recommended=_coerce_int(limits_raw.get("skill_body_tokens_recommended"), default=5000),
    )

    mode = str(proj_raw.get("mode", "measured")).strip().lower()
    if mode not in {"measured", "fixed"}:
        mode = "measured"

    projection = TrimrProjection(
        mode=mode,
        fixed_tokens_per_vaultable_skill=_coerce_int(
            proj_raw.get("fixed_tokens_per_vaultable_skill"), default=100
        ),
    )

    return TrimrConfig(limits=limits, projection=projection)


def _coerce_int(value: Any, default: int) -> int:
    try:
        i = int(value)
        return i if i >= 0 else default
    except Exception:
        return default

