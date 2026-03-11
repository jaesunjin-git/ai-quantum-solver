"""
tests/test_infeasibility_diagnosis.py
─────────────────────────────────────
INFEASIBLE 진단 기능 테스트

1. CP-SAT에서 INFEASIBLE 발생 시 infeasibility_info가 정상 생성되는지
2. constraint_info가 metadata에 올바르게 기록되는지
3. conflict_hints 휴리스틱이 동작하는지
"""

import pytest
from ortools.sat.python import cp_model

from engine.executor.base import ExecuteResult
from engine.executor.ortools_executor import ORToolsExecutor


class MockCompileResult:
    """컴파일 결과 모의 객체 (솔버 공통 인터페이스)"""

    def __init__(self, model, var_map, solver_type="ortools_cp", metadata=None):
        self.solver_model = model
        self.variable_map = var_map
        self.solver_type = solver_type
        self.metadata = metadata or {}
        self.variable_count = len(var_map)
        self.constraint_count = 0
        self.warnings = []


class TestInfeasibilityDiagnosis:
    """INFEASIBLE 진단 기능 테스트"""

    def _make_infeasible_model(self):
        """명백히 INFEASIBLE한 CP-SAT 모델 생성: x >= 5 AND x <= 3"""
        model = cp_model.CpModel()
        x = model.new_int_var(0, 10, "x")
        model.add(x >= 5)
        model.add(x <= 3)
        model.minimize(x)
        return model, {"x": x}

    def _make_feasible_model(self):
        """정상적으로 풀리는 CP-SAT 모델"""
        model = cp_model.CpModel()
        x = model.new_int_var(0, 10, "x")
        model.add(x >= 2)
        model.add(x <= 8)
        model.minimize(x)
        return model, {"x": x}

    def test_infeasible_returns_diagnosis(self):
        """INFEASIBLE 시 infeasibility_info가 생성되어야 함"""
        model, var_map = self._make_infeasible_model()

        constraint_info = [
            {"name": "min_value", "category": "hard", "count": 1, "method": "expression_parser"},
            {"name": "max_value", "category": "hard", "count": 1, "method": "expression_parser"},
        ]
        compile_result = MockCompileResult(
            model, var_map,
            metadata={"constraint_info": constraint_info}
        )

        executor = ORToolsExecutor()
        result = executor.execute(compile_result, time_limit_sec=10)

        assert result.success is False
        assert result.status == "INFEASIBLE"
        assert result.infeasibility_info is not None

        info = result.infeasibility_info
        assert "summary" in info
        assert "applied_constraints" in info
        assert "solver_stats" in info
        assert "conflict_hints" in info

        # 2개의 hard 제약이 기록되어야 함
        assert info["summary"]["hard_constraint_count"] == 2
        assert info["summary"]["hard_instance_count"] == 2
        assert len(info["applied_constraints"]) == 2

    def test_feasible_no_diagnosis(self):
        """FEASIBLE/OPTIMAL 시 infeasibility_info가 None이어야 함"""
        model, var_map = self._make_feasible_model()
        compile_result = MockCompileResult(model, var_map)

        executor = ORToolsExecutor()
        result = executor.execute(compile_result, time_limit_sec=10)

        assert result.success is True
        assert result.infeasibility_info is None

    def test_trivial_infeasibility_hint(self):
        """즉시 판정된 INFEASIBLE은 trivial_infeasibility 힌트가 나와야 함"""
        model, var_map = self._make_infeasible_model()
        compile_result = MockCompileResult(
            model, var_map,
            metadata={"constraint_info": [
                {"name": "c1", "category": "hard", "count": 1, "method": "structured"},
            ]}
        )

        executor = ORToolsExecutor()
        result = executor.execute(compile_result, time_limit_sec=10)

        info = result.infeasibility_info
        hint_types = [h["type"] for h in info["conflict_hints"]]
        assert "trivial_infeasibility" in hint_types

    def test_numeric_conflict_hint(self):
        """count 관련 제약이 여러 개면 numeric_conflict 힌트가 나와야 함"""
        model, var_map = self._make_infeasible_model()
        compile_result = MockCompileResult(
            model, var_map,
            metadata={"constraint_info": [
                {"name": "fixed_day_crew_count", "category": "hard", "count": 1, "method": "expression_parser"},
                {"name": "fixed_night_crew_count", "category": "hard", "count": 1, "method": "expression_parser"},
                {"name": "total_duties_count", "category": "hard", "count": 1, "method": "structured"},
            ]}
        )

        executor = ORToolsExecutor()
        result = executor.execute(compile_result, time_limit_sec=10)

        info = result.infeasibility_info
        hint_types = [h["type"] for h in info["conflict_hints"]]
        assert "numeric_conflict" in hint_types

    def test_coverage_capacity_hint(self):
        """coverage + capacity 제약이 동시에 있으면 힌트가 나와야 함"""
        model, var_map = self._make_infeasible_model()
        compile_result = MockCompileResult(
            model, var_map,
            metadata={"constraint_info": [
                {"name": "trip_coverage", "category": "hard", "count": 45, "method": "structured"},
                {"name": "max_trips_per_duty", "category": "hard", "count": 10, "method": "expression_parser"},
            ]}
        )

        executor = ORToolsExecutor()
        result = executor.execute(compile_result, time_limit_sec=10)

        info = result.infeasibility_info
        hint_types = [h["type"] for h in info["conflict_hints"]]
        assert "coverage_capacity_conflict" in hint_types

    def test_empty_constraint_info_graceful(self):
        """constraint_info가 없어도 진단이 graceful하게 동작해야 함"""
        model, var_map = self._make_infeasible_model()
        compile_result = MockCompileResult(model, var_map, metadata={})

        executor = ORToolsExecutor()
        result = executor.execute(compile_result, time_limit_sec=10)

        assert result.infeasibility_info is not None
        info = result.infeasibility_info
        assert info["summary"]["hard_constraint_count"] == 0
        assert len(info["applied_constraints"]) == 0

    def test_failed_constraints_tracked(self):
        """컴파일 실패한 제약도 진단에 포함되어야 함"""
        model, var_map = self._make_infeasible_model()
        compile_result = MockCompileResult(
            model, var_map,
            metadata={"constraint_info": [
                {"name": "applied_ok", "category": "hard", "count": 5, "method": "structured"},
                {"name": "parse_failed", "category": "hard", "count": 0, "method": "failed"},
            ]}
        )

        executor = ORToolsExecutor()
        result = executor.execute(compile_result, time_limit_sec=10)

        info = result.infeasibility_info
        assert info["summary"]["failed_constraint_count"] == 1
        assert len(info["failed_constraints"]) == 1
        assert info["failed_constraints"][0]["name"] == "parse_failed"


class TestExecuteResultDataclass:
    """ExecuteResult에 infeasibility_info 필드가 정상적으로 동작하는지"""

    def test_default_none(self):
        r = ExecuteResult(success=True)
        assert r.infeasibility_info is None

    def test_with_info(self):
        info = {"summary": {"hard_constraint_count": 3}}
        r = ExecuteResult(success=False, infeasibility_info=info)
        assert r.infeasibility_info == info


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
