"""
tests/test_nl_executor.py
─────────────────────────
NL/Stride 실행기 등록 및 구조 테스트
(D-Wave API 호출 없이 구조적 검증)
"""

import pytest
from engine.executor.dwave_executor import DWaveExecutor
from engine.executor.base import ExecuteResult


class TestNLExecutorRegistration:
    """NL 실행기 등록 테스트"""

    def test_executor_map_has_nl(self):
        from engine.executor import EXECUTOR_MAP
        assert "nl" in EXECUTOR_MAP

    def test_get_executor_nl(self):
        from engine.executor import get_executor
        executor = get_executor("nl")
        assert isinstance(executor, DWaveExecutor)

    def test_execute_routes_to_nl(self):
        """solver_type='nl'이면 _execute_nl로 라우팅되어야 함"""
        import inspect
        source = inspect.getsource(DWaveExecutor.execute)
        assert '"nl"' in source or "'nl'" in source

    def test_execute_nl_without_token(self):
        """토큰 없이 실행 시 에러 반환 (토큰 에러 또는 모델 에러)"""
        import os
        original = os.environ.pop("DWAVE_API_TOKEN", None)

        try:
            executor = DWaveExecutor()
            executor.token = None

            class MockCompileResult:
                solver_type = "nl"
                solver_model = None
                variable_map = {}
                metadata = {}

            result = executor.execute(MockCompileResult())
            assert result.success is False
            assert result.error is not None
        finally:
            if original:
                os.environ["DWAVE_API_TOKEN"] = original


class TestNLEndToEnd:
    """NL 컴파일러 + 실행기 통합 구조 테스트"""

    def test_compiler_output_type_matches_executor(self):
        """컴파일러 출력 solver_type이 실행기 맵에 있어야 함"""
        from engine.compiler.dwave_nl_compiler import DWaveNLCompiler
        from engine.executor import EXECUTOR_MAP

        compiler = DWaveNLCompiler()
        model = {
            "variables": [{"id": "x", "type": "binary", "indices": []}],
            "sets": [],
            "parameters": [],
            "constraints": [],
            "objective": {},
        }
        result = compiler.compile(model, {"sets": {}, "parameters": {}})
        assert result.success
        assert result.solver_type in EXECUTOR_MAP

    def test_full_pipeline_registration(self):
        """solver_id 'dwave_nl'이 컴파일러+실행기 모두 연결됨"""
        from engine.compiler import get_compiler, COMPILER_MAP
        from engine.executor import EXECUTOR_MAP

        # 컴파일러 등록 확인
        assert "dwave_nl" in COMPILER_MAP

        # 컴파일러가 반환하는 solver_type으로 실행기 찾기
        compiler = get_compiler("dwave_nl")
        model = {
            "variables": [{"id": "x", "type": "binary", "indices": []}],
            "sets": [],
            "parameters": [],
            "constraints": [],
            "objective": {},
        }
        result = compiler.compile(model, {"sets": {}, "parameters": {}})
        assert result.solver_type == "nl"
        assert result.solver_type in EXECUTOR_MAP


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
