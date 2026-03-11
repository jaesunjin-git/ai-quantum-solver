"""
검증 프레임워크 기본 클래스 및 데이터 모델.

모든 검증 결과는 순수 dataclass로, ORM이나 프레임워크 의존성이 없습니다.
JSON 직렬화(REST API용)와 독립 테스트가 가능합니다.

주요 클래스:
  - ValidationItem : 개별 검증 결과 (code, severity, message, auto_fix, user_input 등)
  - BaseValidator  : 모든 검증기의 추상 베이스 클래스 (validate 메서드 구현 필요)

MSA 참고: 이 모듈은 외부 의존성이 없습니다(stdlib만 사용).
마이크로서비스 간 공유 라이브러리로 패키징 가능합니다.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Severity ────────────────────────────────────────────────────────

class Severity(str, Enum):
    """Validation finding severity.

    ERROR   — blocks progression to next stage (user must fix)
    WARNING — user should review but can dismiss and proceed
    INFO    — informational, no action required
    """
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# ── AutoFix ─────────────────────────────────────────────────────────

@dataclass
class AutoFix:
    """Describes an automatic correction the platform can apply.

    Attributes:
        param:   parameter or field to modify
        old_val: current (problematic) value
        new_val: suggested corrected value
        action:  fix strategy — "set", "cap_to", "remove", "replace"
        label:   human-readable button label for the frontend
    """
    param: str
    old_val: Any = None
    new_val: Any = None
    action: str = "set"
    label: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


# ── UserInput ───────────────────────────────────────────────────────

@dataclass
class UserInput:
    """Describes a value the user needs to provide.

    Attributes:
        param:        parameter name
        input_type:   "number", "text", "select", "time"
        placeholder:  hint shown in the input field
        options:      choices for "select" type
        default:      pre-filled value suggestion
        unit:         display unit (e.g., "분", "%", "km")
    """
    param: str
    input_type: str = "number"
    placeholder: Optional[str] = None
    options: Optional[list] = None
    default: Any = None
    unit: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


# ── ValidationItem ──────────────────────────────────────────────────

@dataclass
class ValidationItem:
    """A single validation finding.

    This is the atomic unit of validation output.  The frontend renders
    each item as a card in the ValidationDrawer.

    Attributes:
        code:        machine-readable identifier (e.g., "UPLOAD_EMPTY_FILE")
        severity:    error / warning / info
        message:     user-facing description (Korean or English)
        stage:       pipeline stage number (1–6)
        detail:      technical detail (optional, collapsible)
        suggestion:  plain-text recommendation
        auto_fix:    platform can fix this automatically
        user_input:  user needs to provide a value
        context:     arbitrary metadata for downstream processing
        dismissed:   user chose to ignore this finding
    """
    code: str
    severity: Severity
    message: str
    stage: int = 0
    detail: Optional[str] = None
    suggestion: Optional[str] = None
    auto_fix: Optional[AutoFix] = None
    user_input: Optional[UserInput] = None
    context: dict = field(default_factory=dict)
    dismissed: bool = False

    def to_dict(self) -> dict:
        d = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "stage": self.stage,
            "dismissed": self.dismissed,
        }
        if self.detail:
            d["detail"] = self.detail
        if self.suggestion:
            d["suggestion"] = self.suggestion
        if self.auto_fix:
            d["auto_fix"] = self.auto_fix.to_dict()
        if self.user_input:
            d["user_input"] = self.user_input.to_dict()
        if self.context:
            d["context"] = self.context
        return d


# ── ValidationResult ────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Output of a single validator's run.

    Groups multiple ValidationItems under a named validator.
    """
    stage: int
    validator_name: str
    items: list[ValidationItem] = field(default_factory=list)

    # ── Convenience properties ──

    @property
    def passed(self) -> bool:
        """True if no ERROR-level items (dismissed errors still count)."""
        return not any(
            i.severity == Severity.ERROR and not i.dismissed
            for i in self.items
        )

    @property
    def error_count(self) -> int:
        return sum(
            1 for i in self.items
            if i.severity == Severity.ERROR and not i.dismissed
        )

    @property
    def warning_count(self) -> int:
        return sum(
            1 for i in self.items
            if i.severity == Severity.WARNING and not i.dismissed
        )

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.items if i.severity == Severity.INFO)

    def add(self, item: ValidationItem) -> None:
        """Append a finding, auto-setting stage if not set."""
        if item.stage == 0:
            item.stage = self.stage
        self.items.append(item)

    def add_error(self, code: str, message: str, **kwargs) -> None:
        self.add(ValidationItem(code=code, severity=Severity.ERROR,
                                message=message, **kwargs))

    def add_warning(self, code: str, message: str, **kwargs) -> None:
        self.add(ValidationItem(code=code, severity=Severity.WARNING,
                                message=message, **kwargs))

    def add_info(self, code: str, message: str, **kwargs) -> None:
        self.add(ValidationItem(code=code, severity=Severity.INFO,
                                message=message, **kwargs))

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "validator_name": self.validator_name,
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "items": [i.to_dict() for i in self.items],
        }


# ── BaseValidator ABC ───────────────────────────────────────────────

class BaseValidator(ABC):
    """Abstract base class for all validators.

    Subclass this and implement `validate()`.  Register the instance
    with `ValidationRegistry` to have it executed at the right stage.

    Attributes:
        stage:       pipeline stage (1=upload, 2=structuring, 3=problem_def,
                     4=normalization, 5=compile, 6=post_solve)
        name:        human-readable validator name (auto-derived from class)
        description: brief purpose description
    """

    stage: int = 0
    name: str = ""
    description: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.name:
            cls.name = cls.__name__

    @abstractmethod
    def validate(self, context: dict) -> ValidationResult:
        """Run validation and return findings.

        Args:
            context: stage-specific data.  Keys vary by stage:
                Stage 1 (upload):
                    files: list[dict]  — file metadata
                    project_id: int
                Stage 2 (structuring):
                    data_profile: dict  — Gate1 output
                    dataframes: dict[str, DataFrame]
                Stage 3 (problem_definition):
                    confirmed_problem: dict
                    parameters: dict
                    math_model: dict (if generated)
                    domain: str
                Stage 4 (normalization):
                    original_stats: dict  — pre-transform metrics
                    normalized_stats: dict  — post-transform metrics
                    mappings: list[dict]
                Stage 5 (compile):
                    compile_summary: dict
                    model_stats: dict
                    warnings: list[str]
                Stage 6 (post_solve):
                    status: str
                    objective_value: float
                    best_bound: float (if available)
                    solution: dict
                    math_model: dict
                    domain: str

        Returns:
            ValidationResult with findings.
        """
        ...

    def _make_result(self) -> ValidationResult:
        """Helper to create a result pre-filled with stage and name."""
        return ValidationResult(stage=self.stage, validator_name=self.name)
