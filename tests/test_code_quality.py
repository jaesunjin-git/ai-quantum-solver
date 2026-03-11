"""
tests/test_code_quality.py
──────────────────────────
Phase 7: Code Quality 검증 테스트

1. SessionState 직렬화 자동화 (_DB_FIELD_SPEC)
2. 에러 코드 표준화 (ErrorCode, error_response, warning_response)
3. 소프트 가중치 캐싱 (_load_soft_weights)
"""

import pytest


# ============================================================
# 7A: SessionState 직렬화 자동화
# ============================================================

class TestSessionFieldSpec:
    """_DB_FIELD_SPEC 기반 자동 직렬화 검증"""

    def test_field_spec_covers_all_db_columns(self):
        """_DB_FIELD_SPEC이 SessionStateDB의 주요 컬럼을 모두 커버하는지 확인"""
        from core.platform.session import _DB_FIELD_SPEC
        from core.models import SessionStateDB

        spec_fields = {name for name, _ in _DB_FIELD_SPEC}

        # SessionStateDB 컬럼 중 자동 관리 컬럼 제외
        skip_columns = {"id", "project_id", "updated_at", "domain_confidence"}
        db_columns = set()
        for col in SessionStateDB.__table__.columns:
            if col.name not in skip_columns:
                db_columns.add(col.name)

        missing = db_columns - spec_fields
        assert missing == set(), f"DB columns not in _DB_FIELD_SPEC: {missing}"

    def test_field_spec_no_unknown_fields(self):
        """_DB_FIELD_SPEC에 DB에 없는 필드가 포함되지 않도록 확인"""
        from core.platform.session import _DB_FIELD_SPEC
        from core.models import SessionStateDB

        spec_fields = {name for name, _ in _DB_FIELD_SPEC}
        db_columns = {col.name for col in SessionStateDB.__table__.columns}

        extra = spec_fields - db_columns
        assert extra == set(), f"_DB_FIELD_SPEC has fields not in DB: {extra}"

    def test_field_spec_types_valid(self):
        """직렬화 타입이 'direct' 또는 'json'만 허용"""
        from core.platform.session import _DB_FIELD_SPEC
        for name, ser_type in _DB_FIELD_SPEC:
            assert ser_type in ("direct", "json"), \
                f"Invalid ser_type '{ser_type}' for field '{name}'"

    def test_json_fields_match_dict_or_list_types(self):
        """json 타입 필드가 SessionState에서 Dict/List 타입인지 확인"""
        from core.platform.session import _DB_FIELD_SPEC, SessionState
        import dataclasses
        from typing import get_type_hints

        hints = get_type_hints(SessionState)
        json_fields = {name for name, st in _DB_FIELD_SPEC if st == "json"}

        for fname in json_fields:
            assert fname in hints, f"json field '{fname}' not in SessionState"
            hint_str = str(hints[fname])
            assert any(t in hint_str for t in ("Dict", "List", "dict", "list")), \
                f"json field '{fname}' has type {hints[fname]}, expected Dict/List"

    def test_roundtrip_serialization_logic(self):
        """SessionState → _DB_FIELD_SPEC 직렬화 → 역직렬화 라운드트립"""
        import json
        from core.platform.session import _DB_FIELD_SPEC, SessionState

        state = SessionState()
        state.file_uploaded = True
        state.uploaded_files = ["test.csv"]
        state.math_model = {"objective": {"type": "minimize"}}
        state.problem_defined = True
        state.current_run_id = 42

        # 직렬화 시뮬레이션
        serialized = {}
        for field_name, ser_type in _DB_FIELD_SPEC:
            value = getattr(state, field_name, None)
            if ser_type == "json" and value is not None:
                value = json.dumps(value, ensure_ascii=False)
            serialized[field_name] = value

        # 역직렬화 시뮬레이션
        restored = SessionState()
        for field_name, ser_type in _DB_FIELD_SPEC:
            db_val = serialized[field_name]
            if ser_type == "json":
                if db_val:
                    setattr(restored, field_name, json.loads(db_val))
            else:
                if db_val is not None:
                    setattr(restored, field_name, db_val)

        assert restored.file_uploaded is True
        assert restored.uploaded_files == ["test.csv"]
        assert restored.math_model == {"objective": {"type": "minimize"}}
        assert restored.problem_defined is True
        assert restored.current_run_id == 42
        # False 기본값 유지 확인
        assert restored.optimization_done is False
        assert restored.data_normalized is False


# ============================================================
# 7B: 에러 코드 표준화
# ============================================================

class TestErrorCodes:
    """ErrorCode enum 및 error_response/warning_response 함수"""

    def test_error_code_enum_values(self):
        from core.platform.errors import ErrorCode
        assert ErrorCode.FILE_NOT_UPLOADED == "FILE_NOT_UPLOADED"
        assert ErrorCode.SOLVER_INFEASIBLE == "SOLVER_INFEASIBLE"
        assert ErrorCode.LLM_CONNECTION_ERROR == "LLM_CONNECTION_ERROR"

    def test_error_code_is_string(self):
        from core.platform.errors import ErrorCode
        assert isinstance(ErrorCode.INTERNAL_ERROR, str)
        assert isinstance(ErrorCode.INTERNAL_ERROR.value, str)

    def test_error_response_basic(self):
        from core.platform.errors import error_response
        resp = error_response("테스트 에러")
        assert resp["type"] == "error"
        assert "테스트 에러" in resp["text"]
        assert resp["data"] is None
        assert len(resp["options"]) == 2
        assert "error_code" not in resp

    def test_error_response_with_code(self):
        from core.platform.errors import error_response, ErrorCode
        resp = error_response("파일 없음", code=ErrorCode.FILE_NOT_UPLOADED)
        assert resp["error_code"] == "FILE_NOT_UPLOADED"
        assert resp["type"] == "error"

    def test_error_response_custom_options(self):
        from core.platform.errors import error_response
        opts = [{"label": "커스텀", "action": "send", "message": "test"}]
        resp = error_response("에러", options=opts)
        assert len(resp["options"]) == 1
        assert resp["options"][0]["label"] == "커스텀"

    def test_warning_response_basic(self):
        from core.platform.errors import warning_response
        resp = warning_response("경고 메시지")
        assert resp["type"] == "warning"
        assert "경고 메시지" in resp["text"]
        assert resp["data"] is None

    def test_warning_response_with_code(self):
        from core.platform.errors import warning_response, ErrorCode
        resp = warning_response("분석 필요", code=ErrorCode.ANALYSIS_NOT_DONE)
        assert resp["error_code"] == "ANALYSIS_NOT_DONE"

    def test_backward_compat_import_from_utils(self):
        """기존 import 경로 호환 확인"""
        from core.platform.utils import error_response
        resp = error_response("호환성 테스트")
        assert resp["type"] == "error"

    def test_backward_compat_import_from_init(self):
        """core.platform에서 직접 import 가능 확인"""
        from core.platform import error_response, ErrorCode, warning_response
        assert callable(error_response)
        assert callable(warning_response)
        assert hasattr(ErrorCode, "INTERNAL_ERROR")


# ============================================================
# 7C: 소프트 가중치 캐싱
# ============================================================

class TestSoftWeightsCache:
    """_load_soft_weights 캐싱 검증"""

    def test_load_soft_weights_returns_dict(self):
        from engine.compiler.ortools_compiler import _load_soft_weights
        weights = _load_soft_weights(force_reload=True)
        assert isinstance(weights, dict)

    def test_load_soft_weights_has_known_keys(self):
        """railway + logistics 도메인의 soft constraint가 로딩되어야 함"""
        from engine.compiler.ortools_compiler import _load_soft_weights
        weights = _load_soft_weights(force_reload=True)
        # logistics soft constraints
        assert "workload_balance" in weights

    def test_load_soft_weights_cache_works(self):
        """두 번째 호출은 캐시에서 반환 (동일 객체)"""
        from engine.compiler.ortools_compiler import _load_soft_weights
        w1 = _load_soft_weights(force_reload=True)
        w2 = _load_soft_weights()  # 캐시 사용
        assert w1 is w2

    def test_load_soft_weights_force_reload(self):
        """force_reload=True이면 새 객체 생성"""
        from engine.compiler.ortools_compiler import _load_soft_weights
        w1 = _load_soft_weights(force_reload=True)
        w2 = _load_soft_weights(force_reload=True)
        assert w1 is not w2
        assert w1 == w2  # 내용은 동일

    def test_weight_values_are_positive_floats(self):
        from engine.compiler.ortools_compiler import _load_soft_weights
        weights = _load_soft_weights(force_reload=True)
        for key, val in weights.items():
            assert isinstance(val, float), f"weight '{key}' is not float: {type(val)}"
            assert val > 0, f"weight '{key}' should be positive: {val}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
