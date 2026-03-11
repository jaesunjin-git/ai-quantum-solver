"""
tests/test_nl_compiler.py
─────────────────────────
D-Wave NL/Stride 컴파일러 테스트

1. 기본 변수 생성 (binary, integer, continuous)
2. 인덱싱된 변수 생성
3. 제약조건 적용
4. 목적함수 파싱
5. 전체 모델 컴파일 (승무원 스케줄링 간소화)
"""

import pytest
from engine.compiler.dwave_nl_compiler import DWaveNLCompiler


def _simple_math_model():
    """간소화된 승무원 스케줄링 수학 모델"""
    return {
        "variables": [
            {
                "id": "x",
                "type": "binary",
                "indices": [{"set": "I"}, {"set": "J"}],
                "description": "trip i assigned to duty j",
            },
            {
                "id": "y",
                "type": "binary",
                "indices": [{"set": "J"}],
                "description": "duty j is active",
            },
        ],
        "sets": [
            {"id": "I", "name": "trips", "size": 5},
            {"id": "J", "name": "duties", "size": 3},
        ],
        "parameters": [],
        "constraints": [
            {
                "name": "trip_coverage",
                "expression": "sum(x[i,j] for j in J) == 1",
                "for_each": "i in I",
                "operator": "==",
                "category": "hard",
            },
        ],
        "objective": {
            "direction": "minimize",
            "expression": "sum(y[j] for j in J)",
        },
    }


def _bound_data(n_trips=5, n_duties=3):
    """바인딩된 데이터"""
    return {
        "sets": {
            "I": list(range(n_trips)),
            "J": list(range(n_duties)),
        },
        "parameters": {},
        "set_sizes": {"I": n_trips, "J": n_duties},
    }


class TestNLCompilerBasic:
    """기본 컴파일 기능"""

    def test_compile_success(self):
        """간단한 모델이 성공적으로 컴파일되어야 함"""
        compiler = DWaveNLCompiler()
        result = compiler.compile(_simple_math_model(), _bound_data())

        assert result.success is True
        assert result.solver_type == "nl"
        assert result.variable_count > 0

    def test_variable_creation(self):
        """변수가 올바르게 생성되어야 함"""
        compiler = DWaveNLCompiler()
        result = compiler.compile(_simple_math_model(), _bound_data())

        # x: 5*3=15, y: 3 → 총 18
        assert result.variable_count == 18
        assert "x" in result.variable_map
        assert "y" in result.variable_map

    def test_constraint_count(self):
        """제약조건이 적용되어야 함"""
        compiler = DWaveNLCompiler()
        result = compiler.compile(_simple_math_model(), _bound_data())

        # trip_coverage: 5개 (각 trip에 대해)
        assert result.constraint_count == 5

    def test_metadata_constraint_info(self):
        """constraint_info가 metadata에 기록되어야 함"""
        compiler = DWaveNLCompiler()
        result = compiler.compile(_simple_math_model(), _bound_data())

        assert "constraint_info" in result.metadata
        info = result.metadata["constraint_info"]
        assert len(info) >= 1
        assert info[0]["name"] == "trip_coverage"
        assert info[0]["count"] == 5

    def test_solver_model_type(self):
        """solver_model이 dwave.optimization.Model이어야 함"""
        from dwave.optimization import Model as NLModel

        compiler = DWaveNLCompiler()
        result = compiler.compile(_simple_math_model(), _bound_data())

        assert isinstance(result.solver_model, NLModel)


class TestNLCompilerVariableTypes:
    """다양한 변수 타입 테스트"""

    def test_integer_variables(self):
        """정수 변수가 생성되어야 함"""
        model = {
            "variables": [
                {"id": "z", "type": "integer", "lower_bound": 0, "upper_bound": 10, "indices": []},
            ],
            "sets": [],
            "parameters": [],
            "constraints": [],
            "objective": {},
        }
        compiler = DWaveNLCompiler()
        result = compiler.compile(model, {"sets": {}, "parameters": {}})
        assert result.success
        assert result.variable_count == 1

    def test_continuous_variables(self):
        """연속 변수가 생성되어야 함"""
        model = {
            "variables": [
                {"id": "w", "type": "continuous", "lower_bound": 0.0, "upper_bound": 100.0, "indices": []},
            ],
            "sets": [],
            "parameters": [],
            "constraints": [],
            "objective": {},
        }
        compiler = DWaveNLCompiler()
        result = compiler.compile(model, {"sets": {}, "parameters": {}})
        assert result.success
        assert result.variable_count == 1


class TestNLCompilerSoftConstraints:
    """Soft 제약 처리 테스트"""

    def test_soft_constraint_warning(self):
        """soft 제약은 경고와 함께 penalty로 처리됨을 표시해야 함"""
        model = {
            "variables": [
                {"id": "x", "type": "binary", "indices": [{"set": "I"}]},
            ],
            "sets": [{"id": "I", "size": 3}],
            "parameters": [],
            "constraints": [
                {
                    "name": "preferred_assignment",
                    "category": "soft",
                    "expression": "sum(x[i] for i in I) <= 2",
                },
            ],
            "objective": {},
        }
        compiler = DWaveNLCompiler()
        result = compiler.compile(model, {"sets": {"I": [0, 1, 2]}, "parameters": {}})

        assert result.success
        # constraint_info에 soft로 기록 (penalty 변환 성공 시 method="penalty")
        soft_info = [c for c in result.metadata["constraint_info"] if c["category"] == "soft"]
        assert len(soft_info) == 1
        # expression이 있으므로 penalty로 변환되어야 함
        assert soft_info[0]["method"] == "penalty"
        assert soft_info[0]["count"] > 0


class TestNLCompilerRegistration:
    """컴파일러 등록 테스트"""

    def test_registered_in_compiler_map(self):
        """COMPILER_MAP에 dwave_nl이 등록되어야 함"""
        from engine.compiler import COMPILER_MAP
        assert "dwave_nl" in COMPILER_MAP

    def test_get_compiler(self):
        """get_compiler('dwave_nl')이 NLCompiler를 반환해야 함"""
        from engine.compiler import get_compiler
        compiler = get_compiler("dwave_nl")
        assert isinstance(compiler, DWaveNLCompiler)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
