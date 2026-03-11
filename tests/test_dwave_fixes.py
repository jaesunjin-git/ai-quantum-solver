"""
tests/test_dwave_fixes.py
─────────────────────────
D-Wave 관련 버그 수정 테스트

1. BQM Executor success 변수 미정의 수정 확인
2. CQM BuildContext model 전달 확인
"""

import pytest


class TestBQMExecutorFix:
    """BQM Executor에서 success 변수 미정의 버그 수정"""

    def test_execute_result_success_field(self):
        """ExecuteResult 생성 시 success 필드가 정상 동작"""
        from engine.executor.base import ExecuteResult

        # obj_val is not None → success=True
        r1 = ExecuteResult(success=True, objective_value=42.0)
        assert r1.success is True

        # success=False 명시
        r2 = ExecuteResult(success=False, objective_value=None)
        assert r2.success is False

    def test_bqm_executor_no_name_error(self):
        """BQM executor 코드에서 'success' 변수 참조가 없어야 함"""
        import inspect
        from engine.executor.dwave_executor import DWaveExecutor

        source = inspect.getsource(DWaveExecutor._execute_bqm)
        # 'success=success' 패턴이 없어야 함 (이전 버그)
        assert "success=success" not in source


class TestCQMBuildContext:
    """CQM BuildContext에 model 전달 확인"""

    def test_build_context_accepts_model(self):
        """BuildContext가 model 파라미터를 받을 수 있어야 함"""
        from engine.compiler.struct_builder import BuildContext

        ctx = BuildContext(
            var_map={}, param_map={}, set_map={}, model="dummy_model"
        )
        assert ctx.model == "dummy_model"

    def test_cqm_compiler_passes_model(self):
        """CQM 컴파일러 소스에서 model=cqm이 전달되는지 확인"""
        import inspect
        from engine.compiler.dwave_cqm_compiler import DWaveCQMCompiler

        source = inspect.getsource(DWaveCQMCompiler.compile)
        assert "model=cqm" in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
