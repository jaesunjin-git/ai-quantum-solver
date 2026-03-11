"""
Stage 4 — 정규화 감사 검증기 (플랫폼 공통).

정규화 이후 데이터 변환의 무결성을 검증합니다.
데이터 손실, 변질, 비일관적 변환이 없었는지 확인합니다.

포함 검증기:
  - MappingConfidenceValidator : 매핑 신뢰도 임계값 검사 (< 0.7이면 경고)
  - TransformIntegrityValidator: 변환 전후 행 수 보존 검사
  - ColumnMappingValidator     : 필수 컬럼 매핑 누락 여부 검사

기대하는 context 키:
    mappings: dict            — {auto_confirmed: [...], needs_review: [...]}
    results: list[str]        — 생성된 출력 파일 목록
    errors: list[str]         — 정규화 에러 목록
    original_stats: dict      — (선택) 변환 전 통계
    normalized_stats: dict    — (선택) 변환 후 통계
"""

from __future__ import annotations

from engine.validation.base import BaseValidator, UserInput, ValidationResult


class MappingConfidenceValidator(BaseValidator):
    """Validates normalization mapping confidence and completeness."""

    stage = 4
    name = "MappingConfidenceValidator"
    description = "정규화 매핑 신뢰도 검증"

    LOW_CONFIDENCE_THRESHOLD = 0.7

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()

        mappings = context.get("mappings", {})
        if not mappings:
            return result

        auto_confirmed = mappings.get("auto_confirmed", [])
        needs_review = mappings.get("needs_review", [])
        total = len(auto_confirmed) + len(needs_review)

        if total == 0:
            result.add_warning(
                code="NORM_NO_MAPPINGS",
                message="정규화 매핑이 생성되지 않았습니다.",
                suggestion="데이터 파일의 구조를 확인해 주세요.",
            )
            return result

        # Review-needed mappings
        if needs_review:
            names = ", ".join(
                m.get("target_table", "?") for m in needs_review[:5]
            )
            result.add_warning(
                code="NORM_NEEDS_REVIEW",
                message=f"{len(needs_review)}개 매핑이 검토가 필요합니다: {names}",
                suggestion="매핑 결과를 확인하고 올바른지 검토해 주세요.",
                context={
                    "review_count": len(needs_review),
                    "total_count": total,
                },
            )

        # Low confidence mappings
        low_conf = [
            m for m in auto_confirmed
            if m.get("confidence", 1.0) < self.LOW_CONFIDENCE_THRESHOLD
        ]
        if low_conf:
            result.add_info(
                code="NORM_LOW_CONFIDENCE",
                message=f"{len(low_conf)}개 자동 확인 매핑의 신뢰도가 낮습니다 (<{self.LOW_CONFIDENCE_THRESHOLD:.0%}).",
                context={"count": len(low_conf)},
            )

        # Summary
        if not needs_review and not low_conf:
            result.add_info(
                code="NORM_MAPPINGS_OK",
                message=f"전체 {total}개 매핑이 높은 신뢰도로 확인되었습니다.",
            )

        return result


class TransformIntegrityValidator(BaseValidator):
    """Checks data integrity after transformation — row preservation, error detection."""

    stage = 4
    name = "TransformIntegrityValidator"
    description = "변환 무결성 검증 (행 수 보존, 오류 감지)"

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()

        results = context.get("results", [])
        errors = context.get("errors", [])

        # Transformation errors
        if errors:
            for err in errors[:5]:
                result.add_warning(
                    code="NORM_TRANSFORM_ERROR",
                    message=f"변환 오류: {err}",
                    context={"error": err},
                )

        # Check for expected output files
        if not results and not errors:
            return result

        if not results and errors:
            result.add_error(
                code="NORM_NO_OUTPUT",
                message="정규화 결과 파일이 생성되지 않았습니다.",
                suggestion="원본 데이터와 매핑 설정을 확인해 주세요.",
                context={"error_count": len(errors)},
            )

        # Row count preservation (if stats available)
        original_stats = context.get("original_stats", {})
        normalized_stats = context.get("normalized_stats", {})

        if original_stats and normalized_stats:
            orig_rows = original_stats.get("total_rows", 0)
            norm_rows = normalized_stats.get("total_rows", 0)

            if orig_rows > 0 and norm_rows == 0:
                result.add_error(
                    code="NORM_DATA_LOST",
                    message="정규화 후 데이터가 모두 손실되었습니다.",
                    suggestion="변환 규칙과 원본 데이터를 확인해 주세요.",
                    context={
                        "original_rows": orig_rows,
                        "normalized_rows": norm_rows,
                    },
                )
            elif orig_rows > 0 and norm_rows < orig_rows * 0.5:
                loss_pct = round((1 - norm_rows / orig_rows) * 100, 1)
                result.add_warning(
                    code="NORM_SIGNIFICANT_DATA_LOSS",
                    message=f"정규화 후 데이터가 {loss_pct}% 감소했습니다 ({orig_rows} → {norm_rows}행).",
                    suggestion="변환 과정에서 많은 행이 제외되었습니다. 필터링 조건을 확인해 주세요.",
                    context={
                        "original_rows": orig_rows,
                        "normalized_rows": norm_rows,
                        "loss_percent": loss_pct,
                    },
                )

        return result


class ColumnMappingValidator(BaseValidator):
    """Validates column mappings for completeness and consistency."""

    stage = 4
    name = "ColumnMappingValidator"
    description = "컬럼 매핑 완전성 검증"

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()

        mappings = context.get("mappings", {})
        all_mappings = (
            mappings.get("auto_confirmed", []) +
            mappings.get("needs_review", [])
        )

        if not all_mappings:
            return result

        # Check for missing column mappings
        for m in all_mappings:
            col_mapping = m.get("column_mapping", {})
            target = m.get("target_table", "?")

            if not col_mapping:
                result.add_warning(
                    code="NORM_MISSING_COLUMN_MAP",
                    message=f"'{target}' 매핑에 컬럼 매핑 정보가 없습니다.",
                    suggestion="소스 파일의 컬럼이 대상 테이블에 올바르게 매핑되었는지 확인해 주세요.",
                    context={"target_table": target},
                )

            # Check for unmapped columns (empty string values)
            unmapped = [k for k, v in col_mapping.items() if not v]
            if unmapped:
                result.add_info(
                    code="NORM_UNMAPPED_COLUMNS",
                    message=f"'{target}'에서 {len(unmapped)}개 컬럼이 매핑되지 않았습니다.",
                    context={
                        "target_table": target,
                        "unmapped": unmapped[:10],
                    },
                )

        return result
