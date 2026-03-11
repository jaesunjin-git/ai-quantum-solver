"""
engine.validation — 플랫폼 레벨 검증 프레임워크.

6단계 파이프라인의 각 스테이지에서 데이터·모델·결과의 품질을 검증합니다.

설계 원칙:
  - 플랫폼이 규칙을 실행하고, 도메인이 규칙을 정의 (YAML 설정)
  - 모든 검증기는 상태 없이 독립 테스트 가능
  - 레지스트리 패턴으로 스테이지별 검증기 관리
  - REST API / 프론트엔드용 직렬화 가능한 결과
  - MSA 대응: 각 검증기를 마이크로서비스로 추출 가능

사용법:
    from engine.validation import ValidationRegistry, BaseValidator

    registry = ValidationRegistry()
    registry.register(MyUploadValidator())
    results = registry.run_stage(stage=1, context={...})
"""

from engine.validation.base import (
    BaseValidator,
    Severity,
    ValidationItem,
    ValidationResult,
)
from engine.validation.registry import ValidationRegistry
from engine.validation.report import StageValidation

__all__ = [
    "BaseValidator",
    "Severity",
    "ValidationItem",
    "ValidationResult",
    "ValidationRegistry",
    "StageValidation",
]
