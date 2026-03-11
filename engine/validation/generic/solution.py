"""
Stage 6 — 솔버 후 결과 품질 검증기 (플랫폼 공통).

솔버 실행 결과의 상태·품질·제약 만족도를 검증합니다.
KPI 임계값은 context에서 받으며, 도메인별 로직은 포함하지 않습니다.

포함 검증기:
  - StatusValidator       : 솔버 상태 검사 (INFEASIBLE → 에러, TIMEOUT → 경고)
  - KpiRangeValidator     : KPI 값이 합리적 범위 내인지 검사
  - ConstraintSatValidator: 하드/소프트 제약 만족률 검사

기대하는 context 키:
    status: str              — "OPTIMAL", "FEASIBLE", "INFEASIBLE", "TIMEOUT", "ERROR"
    objective_value: float   — 목적함수 값
    best_bound: float | None — 최적 바운드 (갭 계산용)
    solution: dict           — 변수 할당 결과
    math_model: dict         — 풀이 대상 수학 모델
    interpreted_result: dict — output from result_interpreter (kpi, constraints, etc.)
    domain: str              — domain identifier
    execution_time_sec: float
    compile_summary: dict    — compile metadata (warnings, failed constraints)
"""

from __future__ import annotations

from engine.validation.base import AutoFix, BaseValidator, UserInput, ValidationResult


class SolutionStatusValidator(BaseValidator):
    """Validates the solver execution status and surfaces actionable messages."""

    stage = 6
    name = "SolutionStatusValidator"
    description = "솔버 실행 상태 검증"

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()
        status = context.get("status", "").upper()
        obj_val = context.get("objective_value")
        exec_time = context.get("execution_time_sec", 0)

        if status == "OPTIMAL":
            result.add_info(
                code="SOLVE_OPTIMAL",
                message="최적해를 찾았습니다.",
                context={"objective_value": obj_val, "execution_time_sec": exec_time},
            )
        elif status == "FEASIBLE":
            result.add_warning(
                code="SOLVE_FEASIBLE_NOT_OPTIMAL",
                message="실행 가능한 해를 찾았으나 최적해가 아닐 수 있습니다.",
                suggestion="시간 제한을 늘려 더 나은 해를 탐색할 수 있습니다.",
                auto_fix=AutoFix(
                    param="time_limit_sec",
                    old_val=None,
                    new_val=300,
                    action="set",
                    label="시간 제한 5분으로 증가",
                ),
                context={"objective_value": obj_val, "execution_time_sec": exec_time},
            )
        elif status == "INFEASIBLE":
            result.add_error(
                code="SOLVE_INFEASIBLE",
                message="실행 가능한 해가 존재하지 않습니다.",
                suggestion="제약조건을 완화하거나 데이터를 확인해 주세요.",
                context={"execution_time_sec": exec_time},
            )
        elif status in ("TIMEOUT", "UNKNOWN"):
            result.add_warning(
                code="SOLVE_TIMEOUT",
                message=f"시간 제한({exec_time:.0f}초) 내에 해를 찾지 못했습니다.",
                suggestion="시간 제한을 늘리거나 문제 크기를 줄여 보세요.",
                auto_fix=AutoFix(
                    param="time_limit_sec",
                    old_val=None,
                    new_val=600,
                    action="set",
                    label="시간 제한 10분으로 증가",
                ),
                context={"execution_time_sec": exec_time},
            )
        elif status == "ERROR":
            result.add_error(
                code="SOLVE_ERROR",
                message="솔버 실행 중 오류가 발생했습니다.",
                suggestion="모델 정의와 데이터를 확인해 주세요.",
            )
        elif status == "UNBOUNDED":
            result.add_error(
                code="SOLVE_UNBOUNDED",
                message="목적함수가 무한히 개선될 수 있습니다 (Unbounded).",
                suggestion="목적함수 또는 제약조건 정의를 확인해 주세요.",
            )

        return result


class OptimalityGapValidator(BaseValidator):
    """Calculates and grades the optimality gap when best_bound is available.

    Grading (for minimization problems):
        A: gap ≤ 1%   (near-optimal)
        B: gap ≤ 5%   (good)
        C: gap ≤ 15%  (acceptable)
        D: gap > 15%  (poor — consider re-solving)
    """

    stage = 6
    name = "OptimalityGapValidator"
    description = "최적성 갭 등급 산정 (A/B/C/D)"

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()
        obj_val = context.get("objective_value")
        best_bound = context.get("best_bound")
        status = context.get("status", "").upper()

        if status not in ("OPTIMAL", "FEASIBLE") or obj_val is None:
            return result

        # Gap calculation
        gap_pct = None
        if best_bound is not None and best_bound != 0:
            gap_pct = abs(obj_val - best_bound) / abs(best_bound) * 100
        elif best_bound is not None and obj_val != 0:
            gap_pct = abs(obj_val - best_bound) / abs(obj_val) * 100

        if gap_pct is None:
            if status == "OPTIMAL":
                grade = "A"
                gap_pct = 0.0
            else:
                # FEASIBLE without bound info — can't grade precisely
                result.add_info(
                    code="SOLVE_GAP_UNKNOWN",
                    message="최적성 갭을 계산할 수 없습니다 (Best Bound 정보 없음).",
                    context={"status": status, "objective_value": obj_val},
                )
                return result
        else:
            gap_pct = round(gap_pct, 2)

        # Grade assignment
        if gap_pct <= 1.0:
            grade = "A"
        elif gap_pct <= 5.0:
            grade = "B"
        elif gap_pct <= 15.0:
            grade = "C"
        else:
            grade = "D"

        grade_ctx = {
            "grade": grade,
            "gap_percent": gap_pct,
            "objective_value": obj_val,
            "best_bound": best_bound,
        }

        if grade in ("A", "B"):
            result.add_info(
                code="SOLVE_QUALITY_GRADE",
                message=f"해 품질 등급: {grade} (갭 {gap_pct}%)",
                context=grade_ctx,
            )
        elif grade == "C":
            result.add_warning(
                code="SOLVE_QUALITY_GRADE",
                message=f"해 품질 등급: {grade} (갭 {gap_pct}%) — 수용 가능하나 개선 여지가 있습니다.",
                suggestion="시간 제한을 늘리면 더 나은 해를 찾을 수 있습니다.",
                auto_fix=AutoFix(
                    param="time_limit_sec",
                    old_val=None,
                    new_val=600,
                    action="set",
                    label="시간 제한 10분으로 증가",
                ),
                context=grade_ctx,
            )
        else:  # D
            result.add_warning(
                code="SOLVE_QUALITY_GRADE",
                message=f"해 품질 등급: {grade} (갭 {gap_pct}%) — 해 품질이 낮습니다.",
                suggestion="시간 제한을 크게 늘리거나 모델 단순화를 검토하세요.",
                auto_fix=AutoFix(
                    param="time_limit_sec",
                    old_val=None,
                    new_val=1200,
                    action="set",
                    label="시간 제한 20분으로 증가",
                ),
                context=grade_ctx,
            )

        return result


class ConstraintSatisfactionValidator(BaseValidator):
    """Checks constraint satisfaction from the interpreted result."""

    stage = 6
    name = "ConstraintSatisfactionValidator"
    description = "제약조건 충족 여부 검증"

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()
        interpreted = context.get("interpreted_result", {})

        if not interpreted:
            return result

        # Hard constraint check
        constraint_status = interpreted.get("constraint_status", [])
        violated = [c for c in constraint_status if not c.get("satisfied", True)]

        if violated:
            names = ", ".join(c.get("name", "?") for c in violated[:5])
            result.add_error(
                code="SOLVE_CONSTRAINT_VIOLATED",
                message=f"{len(violated)}개 하드 제약조건이 위반되었습니다: {names}",
                suggestion="해당 제약조건의 파라미터를 확인하거나 소프트 제약으로 전환을 검토하세요.",
                context={
                    "violated_count": len(violated),
                    "violated_names": [c.get("name") for c in violated],
                },
            )
        elif constraint_status:
            result.add_info(
                code="SOLVE_ALL_CONSTRAINTS_MET",
                message=f"모든 하드 제약조건({len(constraint_status)}개)이 충족되었습니다.",
            )

        # KPI-based checks
        kpi = interpreted.get("kpi", {})

        # Coverage rate check (generic: any optimization domain may have coverage)
        coverage = kpi.get("coverage_rate")
        if coverage is not None and coverage < 100:
            result.add_warning(
                code="SOLVE_INCOMPLETE_COVERAGE",
                message=f"커버리지 {coverage}% — 일부 항목이 미배정 상태입니다.",
                suggestion="데이터와 제약조건을 확인하여 전체 커버리지를 달성할 수 있는지 검토하세요.",
                context={"coverage_rate": coverage},
            )

        # Constraint violations count from KPI
        violation_count = kpi.get("constraint_violations", 0)
        if violation_count > 0:
            result.add_warning(
                code="SOLVE_KPI_VIOLATIONS",
                message=f"솔루션 내 {violation_count}건의 제약 위반이 감지되었습니다.",
                context={"violation_count": violation_count},
            )

        # Warnings from interpreter
        warnings = interpreted.get("warnings", [])
        for w in warnings[:5]:  # Limit to 5 to avoid noise
            result.add_info(
                code="SOLVE_INTERPRETER_WARNING",
                message=w,
            )

        return result


class CompileQualityValidator(BaseValidator):
    """Checks compile-time quality: failed constraints, missing objectives."""

    stage = 6
    name = "CompileQualityValidator"
    description = "컴파일 품질 검증 (제약조건 파싱, 목적함수)"

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()
        compile_summary = context.get("compile_summary", {})

        if not compile_summary:
            return result

        # Check for failed constraints
        constraints = compile_summary.get("constraints", {})
        failed = constraints.get("failed", 0)
        total = constraints.get("total_in_model", 0)

        if failed > 0:
            result.add_warning(
                code="COMPILE_CONSTRAINTS_FAILED",
                message=f"{total}개 중 {failed}개 제약조건이 파싱에 실패했습니다.",
                suggestion="수학 모델의 제약조건 정의를 확인해 주세요.",
                context={
                    "total": total,
                    "applied": constraints.get("applied", 0),
                    "failed": failed,
                },
            )

        # Check objective parsing
        if not compile_summary.get("objective_parsed", True):
            result.add_warning(
                code="COMPILE_OBJECTIVE_FALLBACK",
                message="목적함수 파싱에 실패하여 기본 목적함수가 사용되었습니다.",
                suggestion="수학 모델의 목적함수 정의를 확인해 주세요.",
            )

        # Compile warnings
        warnings = compile_summary.get("warnings", [])
        if len(warnings) > 3:
            result.add_info(
                code="COMPILE_MANY_WARNINGS",
                message=f"컴파일 경고 {len(warnings)}건이 발생했습니다.",
                context={"warning_count": len(warnings)},
            )

        return result
