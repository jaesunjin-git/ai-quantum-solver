"""
Stage 5 — 프리솔브/컴파일 검증기 (플랫폼 공통).

솔버 실행 전 컴파일 결과의 구조적 문제를 검출합니다.
조기에 모델 결함을 잡아 불필요한 솔버 시간 낭비를 방지합니다.

포함 검증기:
  - CompileQualityValidator: 컴파일 경고·실패 제약 수 검사
  - VariableBoundValidator : 변수 바운드 누락·이상 범위 검사
  - ObjectiveExprValidator : 목적함수 파싱 성공 여부 검사

기대하는 context 키:
    compile_summary: dict   — 파이프라인 결과 (variables_created, constraints, warnings 등)
    model_stats: dict       — {total_variables, total_constraints}
    math_model: dict        — 컴파일 대상 수학 모델
    warnings: list[str]     — 컴파일 경고 목록
    gate3_result: dict      — (선택) gate3 출력 (pass, errors, warnings, stats)
"""

from __future__ import annotations

from engine.validation.base import BaseValidator, UserInput, ValidationResult


class ModelDimensionValidator(BaseValidator):
    """Checks model dimensions for sanity: zero vars, zero constraints, extreme sizes."""

    stage = 5
    name = "ModelDimensionValidator"
    description = "모델 차원 검증 (변수/제약 수)"

    # Thresholds for warnings
    LARGE_VARIABLE_THRESHOLD = 100_000
    LARGE_CONSTRAINT_THRESHOLD = 200_000
    VERY_LARGE_VARIABLE_THRESHOLD = 1_000_000

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()

        compile_summary = context.get("compile_summary", {})
        model_stats = context.get("model_stats", {})

        var_count = (
            compile_summary.get("variables_created")
            or model_stats.get("total_variables", 0)
        )
        constraint_info = compile_summary.get("constraints", {})
        constraint_count = (
            constraint_info.get("total_in_model")
            or model_stats.get("total_constraints", 0)
        )

        if var_count == 0:
            result.add_error(
                code="PRESOLVE_ZERO_VARIABLES",
                message="변수가 0개 생성되었습니다. 모델 정의에 오류가 있습니다.",
                suggestion="수학 모델의 변수 정의와 데이터 바인딩을 확인해 주세요.",
                context={"variable_count": var_count},
            )

        if constraint_count == 0 and var_count > 0:
            result.add_error(
                code="PRESOLVE_ZERO_CONSTRAINTS",
                message="제약조건이 0개 적용되었습니다.",
                suggestion="모든 제약조건 파싱이 실패했을 수 있습니다. 수학 모델을 확인해 주세요.",
                context={"constraint_count": constraint_count},
            )

        if var_count > self.VERY_LARGE_VARIABLE_THRESHOLD:
            result.add_warning(
                code="PRESOLVE_VERY_LARGE_MODEL",
                message=f"변수 {var_count:,}개로 매우 큰 모델입니다. 실행 시간이 오래 걸릴 수 있습니다.",
                suggestion="시간 제한을 충분히 설정하거나 모델 단순화를 검토하세요.",
                context={"variable_count": var_count, "constraint_count": constraint_count},
            )
        elif var_count > self.LARGE_VARIABLE_THRESHOLD:
            result.add_info(
                code="PRESOLVE_LARGE_MODEL",
                message=f"변수 {var_count:,}개, 제약 {constraint_count:,}개 — 중대형 모델입니다.",
                context={"variable_count": var_count, "constraint_count": constraint_count},
            )

        return result


class ConstraintApplyRatioValidator(BaseValidator):
    """Checks the ratio of successfully applied constraints vs defined."""

    stage = 5
    name = "ConstraintApplyRatioValidator"
    description = "제약조건 적용률 검증"

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()

        compile_summary = context.get("compile_summary", {})
        constraints = compile_summary.get("constraints", {})
        total = constraints.get("total_in_model", 0)
        failed = constraints.get("failed", 0)
        applied = constraints.get("applied", total - failed)

        if total == 0:
            return result

        ratio = applied / total if total > 0 else 0

        if ratio < 0.5:
            result.add_error(
                code="PRESOLVE_LOW_CONSTRAINT_RATIO",
                message=f"제약 적용률 {ratio:.0%} ({applied}/{total}) — 50% 미만으로 결과 신뢰 불가.",
                suggestion="수학 모델의 제약조건 표현식을 확인해 주세요.",
                context={"total": total, "applied": applied, "failed": failed, "ratio": round(ratio, 2)},
            )
        elif ratio < 0.8:
            result.add_warning(
                code="PRESOLVE_PARTIAL_CONSTRAINTS",
                message=f"제약 적용률 {ratio:.0%} ({applied}/{total}) — 일부 제약 누락으로 결과가 부정확할 수 있습니다.",
                suggestion="실패한 제약조건의 표현식을 확인해 주세요.",
                context={"total": total, "applied": applied, "failed": failed, "ratio": round(ratio, 2)},
            )
        else:
            result.add_info(
                code="PRESOLVE_CONSTRAINT_RATIO_OK",
                message=f"제약 적용률 {ratio:.0%} ({applied}/{total})",
                context={"total": total, "applied": applied, "ratio": round(ratio, 2)},
            )

        return result


class CompileWarningAnalyzer(BaseValidator):
    """Analyzes compile warnings for actionable patterns."""

    stage = 5
    name = "CompileWarningAnalyzer"
    description = "컴파일 경고 분석"

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()

        compile_summary = context.get("compile_summary", {})
        warnings = compile_summary.get("warnings", []) or context.get("warnings", [])

        if not warnings:
            return result

        unknown_op = 0
        type_errors = 0
        binding_failures = 0
        parse_failures = 0

        for w in warnings:
            w_lower = str(w).lower()
            if "unknown operator" in w_lower:
                unknown_op += 1
            if "type" in w_lower and ("error" in w_lower or "incompatible" in w_lower):
                type_errors += 1
            if "binding" in w_lower or "not found" in w_lower:
                binding_failures += 1
            if "all parse methods failed" in w_lower:
                parse_failures += 1

        if parse_failures > 0:
            result.add_warning(
                code="PRESOLVE_PARSE_FAILURES",
                message=f"{parse_failures}개 제약조건의 파싱이 모두 실패했습니다.",
                suggestion="해당 제약의 수학적 표현식을 확인해 주세요.",
                context={"count": parse_failures},
            )

        if unknown_op > 0:
            result.add_warning(
                code="PRESOLVE_UNKNOWN_OPERATORS",
                message=f"미지원 연산자가 {unknown_op}건 감지되었습니다.",
                suggestion="제약조건에 사용된 수식을 확인해 주세요.",
                context={"count": unknown_op},
            )

        if type_errors > 0:
            result.add_warning(
                code="PRESOLVE_TYPE_ERRORS",
                message=f"타입 오류가 {type_errors}건 감지되었습니다.",
                suggestion="파라미터 값의 타입(정수/실수)을 확인해 주세요.",
                context={"count": type_errors},
            )

        if binding_failures > 0:
            result.add_warning(
                code="PRESOLVE_BINDING_FAILURES",
                message=f"데이터 바인딩 실패가 {binding_failures}건 감지되었습니다.",
                suggestion="데이터 파일의 컬럼명과 모델의 변수/파라미터 매핑을 확인해 주세요.",
                context={"count": binding_failures},
            )

        # Objective fallback
        if not compile_summary.get("objective_parsed", True):
            result.add_warning(
                code="PRESOLVE_OBJECTIVE_FALLBACK",
                message="목적함수 파싱에 실패하여 기본값이 사용되었습니다.",
                suggestion="수학 모델의 목적함수 정의를 확인해 주세요.",
            )

        return result
