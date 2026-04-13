from dataclasses import dataclass, field
from typing import List
from enum import Enum


class ViolationSeverity(Enum):
    CRITICAL = "CRITICAL"
    WARN = "WARN"
    INFO = "INFO"


class ViolationType(Enum):
    """Type of violation fix effort."""
    CONFIG = "CONFIG"    # Quick fix (10 min)
    ARCH = "ARCH"        # Structural problem (requires migration)


class ViolationCode(Enum):
    MALFORMED_FRONTMATTER = "MALFORMED_FRONTMATTER"
    GLOBAL_BLOAT = "GLOBAL_BLOAT"
    CUMULATIVE_GLOBAL_BLOAT = "CUMULATIVE_GLOBAL_BLOAT"
    SKILL_UNGATED = "SKILL_UNGATED"
    NO_FRONTMATTER = "NO_FRONTMATTER"
    EMPTY_DESCRIPTION = "EMPTY_DESCRIPTION"
    SKILL_BODY_LARGE = "SKILL_BODY_LARGE"
    NON_ASCII_ESTIMATE = "NON_ASCII_ESTIMATE"


@dataclass
class Violation:
    code: ViolationCode
    severity: ViolationSeverity
    file: str
    detail: str
    violation_type: ViolationType = ViolationType.ARCH  # Default to architectural



@dataclass
class GlobalFileReport:
    path: str
    tokens: int
    over_limit: bool = False
    excess: int = 0
    note: str = ""


@dataclass
class SkillReport:
    path: str
    tokens: int
    has_frontmatter: bool
    description_length: int
    name: str = ""
    ungated: bool = False
    vaultable: bool = False
    body_tokens: int = 0


@dataclass
class AuditResult:
    path: str
    startup_tokens_current: int
    startup_tokens_projected: int
    reduction_percent: float
    global_files: List[GlobalFileReport] = field(default_factory=list)
    skills: List[SkillReport] = field(default_factory=list)
    violations: List[Violation] = field(default_factory=list)
