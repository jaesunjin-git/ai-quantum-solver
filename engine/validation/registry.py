"""
ValidationRegistry — 스테이지 기반 검증 오케스트레이터.

검증기를 스테이지별로 등록하고, 해당 스테이지의 모든 검증을 실행합니다.

설계:
  - 싱글턴 가능하지만 강제하지 않음 (테스트 용이성 > 편의성)
  - 앱 시작 시 한 번 검증기 등록
  - run_stage()로 특정 스테이지의 전체 검증 실행
  - 읽기는 스레드 안전; 등록은 시작 시에만

MSA 참고:
  마이크로서비스 환경에서는 각 서비스가 자신의 파이프라인
  스테이지에 해당하는 검증기만 가진 별도 레지스트리를 유지합니다.
  The StageValidation output format is the shared contract.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from engine.validation.base import (
    BaseValidator,
    Severity,
    ValidationItem,
    ValidationResult,
)
from engine.validation.report import StageValidation

logger = logging.getLogger(__name__)


class ValidationRegistry:
    """Manages and executes validators per pipeline stage.

    Usage:
        registry = ValidationRegistry()
        registry.register(UploadEmptyFileValidator())
        registry.register(UploadDuplicateValidator())

        stage_result = registry.run_stage(1, context={"files": [...]})
        # stage_result is a StageValidation ready for JSON serialization
    """

    # Stage name mapping for logging and display
    STAGE_NAMES = {
        1: "upload",
        2: "structuring",
        3: "problem_definition",
        4: "normalization",
        5: "compile",
        6: "post_solve",
    }

    def __init__(self):
        self._validators: dict[int, list[BaseValidator]] = defaultdict(list)

    # ── Registration ──

    def register(self, validator: BaseValidator) -> None:
        """Register a validator for its declared stage."""
        if validator.stage < 1 or validator.stage > 6:
            raise ValueError(
                f"{validator.name}: stage must be 1–6, got {validator.stage}"
            )
        self._validators[validator.stage].append(validator)
        logger.debug(
            "Registered validator '%s' for stage %d (%s)",
            validator.name, validator.stage,
            self.STAGE_NAMES.get(validator.stage, "unknown"),
        )

    def register_many(self, *validators: BaseValidator) -> None:
        """Convenience: register multiple validators at once."""
        for v in validators:
            self.register(v)

    def unregister(self, validator_name: str, stage: Optional[int] = None) -> bool:
        """Remove a validator by name. Returns True if found and removed."""
        stages = [stage] if stage else list(self._validators.keys())
        for s in stages:
            before = len(self._validators[s])
            self._validators[s] = [
                v for v in self._validators[s] if v.name != validator_name
            ]
            if len(self._validators[s]) < before:
                logger.debug("Unregistered validator '%s' from stage %d",
                             validator_name, s)
                return True
        return False

    # ── Execution ──

    def run_stage(self, stage: int, context: dict) -> StageValidation:
        """Execute all validators registered for the given stage.

        Args:
            stage:   pipeline stage number (1–6)
            context: stage-specific data (see BaseValidator.validate docstring)

        Returns:
            StageValidation — aggregated result ready for frontend
        """
        validators = self._validators.get(stage, [])
        results: list[ValidationResult] = []

        for validator in validators:
            try:
                result = validator.validate(context)
                results.append(result)
                if result.items:
                    logger.info(
                        "Stage %d [%s]: %d errors, %d warnings, %d info",
                        stage, validator.name,
                        result.error_count, result.warning_count, result.info_count,
                    )
            except Exception as e:
                # Validator failure should not block the pipeline
                logger.error(
                    "Stage %d [%s] raised exception: %s",
                    stage, validator.name, e, exc_info=True,
                )
                fallback = ValidationResult(
                    stage=stage,
                    validator_name=validator.name,
                )
                fallback.add_warning(
                    code="VALIDATOR_INTERNAL_ERROR",
                    message=f"검증기 '{validator.name}' 실행 중 오류가 발생했습니다.",
                    detail=str(e),
                )
                results.append(fallback)

        return StageValidation.from_results(stage, results)

    def run_all_stages(self, contexts: dict[int, dict]) -> dict[int, StageValidation]:
        """Run validation for multiple stages at once.

        Args:
            contexts: {stage_number: context_dict}

        Returns:
            {stage_number: StageValidation}
        """
        return {
            stage: self.run_stage(stage, ctx)
            for stage, ctx in contexts.items()
        }

    # ── Introspection ──

    def list_validators(self, stage: Optional[int] = None) -> list[dict]:
        """List registered validators, optionally filtered by stage."""
        result = []
        stages = [stage] if stage else sorted(self._validators.keys())
        for s in stages:
            for v in self._validators.get(s, []):
                result.append({
                    "stage": s,
                    "stage_name": self.STAGE_NAMES.get(s, "unknown"),
                    "name": v.name,
                    "description": v.description,
                })
        return result

    @property
    def validator_count(self) -> int:
        return sum(len(vs) for vs in self._validators.values())


# ── Global registry instance ────────────────────────────────────────
# App startup should populate this via register().
# Individual tests can create their own isolated instances.

_global_registry: Optional[ValidationRegistry] = None


def get_registry() -> ValidationRegistry:
    """Get or create the global ValidationRegistry singleton."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ValidationRegistry()
    return _global_registry


def reset_registry() -> None:
    """Reset global registry (for testing only)."""
    global _global_registry
    _global_registry = None
