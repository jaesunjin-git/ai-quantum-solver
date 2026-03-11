"""
StageValidation — 파이프라인 스테이지의 통합 검증 리포트.

백엔드와 프론트엔드 간의 **계약(contract)** 역할을 합니다.
프론트엔드 ValidationDrawer가 이 구조를 직접 렌더링합니다.

포함 정보:
  - stage, passed, blocking 플래그
  - error/warning/info 개수
  - validators_run 목록
  - items: ValidationItem 배열 (개별 검증 결과)

MSA 참고:
  이 클래스는 API 응답 페이로드입니다. 마이크로서비스 분리 시
  각 서비스가 StageValidation을 JSON으로 반환하고,
  API 게이트웨이가 스테이지 번호로 병합합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from engine.validation.base import (
    Severity,
    ValidationItem,
    ValidationResult,
)


@dataclass
class StageValidation:
    """Aggregated validation result for one pipeline stage.

    Frontend receives this as part of every stage response:
        { "view_mode": "...", "validation": StageValidation.to_dict(), ... }

    Attributes:
        stage:          pipeline stage number (1–6)
        passed:         True if no unresolved errors
        blocking:       True if errors prevent stage progression
        error_count:    total errors across all validators
        warning_count:  total warnings across all validators
        info_count:     total info items
        items:          flattened list of all ValidationItems
        validators_run: names of validators that executed
    """
    stage: int
    passed: bool = True
    blocking: bool = False
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    items: list[ValidationItem] = field(default_factory=list)
    validators_run: list[str] = field(default_factory=list)

    @classmethod
    def from_results(
        cls, stage: int, results: list[ValidationResult]
    ) -> "StageValidation":
        """Aggregate multiple ValidationResults into a single StageValidation."""
        all_items: list[ValidationItem] = []
        validators_run: list[str] = []

        for r in results:
            all_items.extend(r.items)
            validators_run.append(r.validator_name)

        error_count = sum(
            1 for i in all_items
            if i.severity == Severity.ERROR and not i.dismissed
        )
        warning_count = sum(
            1 for i in all_items
            if i.severity == Severity.WARNING and not i.dismissed
        )
        info_count = sum(
            1 for i in all_items if i.severity == Severity.INFO
        )

        return cls(
            stage=stage,
            passed=error_count == 0,
            blocking=error_count > 0,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            items=all_items,
            validators_run=validators_run,
        )

    @classmethod
    def empty(cls, stage: int) -> "StageValidation":
        """Create an empty (no validators run) validation for a stage."""
        return cls(stage=stage, passed=True)

    # ── Mutation ──

    def dismiss(self, code: str) -> bool:
        """Mark a finding as dismissed by code. Returns True if found."""
        for item in self.items:
            if item.code == code and not item.dismissed:
                item.dismissed = True
                self._recount()
                return True
        return False

    def apply_fix(self, code: str) -> Optional[dict]:
        """Get the auto_fix for a given code, then dismiss it.

        Returns the auto_fix dict if found, None otherwise.
        The caller is responsible for actually applying the fix.
        """
        for item in self.items:
            if item.code == code and item.auto_fix and not item.dismissed:
                fix = item.auto_fix.to_dict()
                item.dismissed = True
                self._recount()
                return fix
        return None

    def _recount(self) -> None:
        """Recalculate counts after dismiss/fix."""
        self.error_count = sum(
            1 for i in self.items
            if i.severity == Severity.ERROR and not i.dismissed
        )
        self.warning_count = sum(
            1 for i in self.items
            if i.severity == Severity.WARNING and not i.dismissed
        )
        self.passed = self.error_count == 0
        self.blocking = self.error_count > 0

    # ── Serialization ──

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict for REST API response."""
        return {
            "stage": self.stage,
            "passed": self.passed,
            "blocking": self.blocking,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "validators_run": self.validators_run,
            "items": [i.to_dict() for i in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StageValidation":
        """Deserialize from dict (e.g., stored in session or DB)."""
        items = []
        for item_data in data.get("items", []):
            items.append(ValidationItem(
                code=item_data["code"],
                severity=Severity(item_data["severity"]),
                message=item_data["message"],
                stage=item_data.get("stage", data.get("stage", 0)),
                detail=item_data.get("detail"),
                suggestion=item_data.get("suggestion"),
                dismissed=item_data.get("dismissed", False),
            ))
        return cls(
            stage=data["stage"],
            passed=data.get("passed", True),
            blocking=data.get("blocking", False),
            error_count=data.get("error_count", 0),
            warning_count=data.get("warning_count", 0),
            info_count=data.get("info_count", 0),
            items=items,
            validators_run=data.get("validators_run", []),
        )
