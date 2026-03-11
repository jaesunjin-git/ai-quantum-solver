"""
core/platform/errors.py
───────────────────────
플랫폼 공통 에러 코드 및 표준 에러 응답.

에러 코드를 기계가 읽을 수 있는 문자열로 정의하고,
프론트엔드에서 에러 유형별 분기 처리를 가능하게 합니다.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional


class ErrorCode(str, Enum):
    """기계가 읽을 수 있는 에러 코드 (프론트엔드 분기용)"""

    # ── 파일/데이터 ──
    FILE_NOT_UPLOADED = "FILE_NOT_UPLOADED"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_FORMAT_INVALID = "FILE_FORMAT_INVALID"

    # ── 워크플로 상태 ──
    ANALYSIS_NOT_DONE = "ANALYSIS_NOT_DONE"
    PROBLEM_NOT_DEFINED = "PROBLEM_NOT_DEFINED"
    DATA_NOT_NORMALIZED = "DATA_NOT_NORMALIZED"
    MODEL_NOT_CONFIRMED = "MODEL_NOT_CONFIRMED"
    SOLVER_NOT_SELECTED = "SOLVER_NOT_SELECTED"

    # ── 솔버/엔진 ──
    COMPILE_FAILED = "COMPILE_FAILED"
    SOLVER_TIMEOUT = "SOLVER_TIMEOUT"
    SOLVER_INFEASIBLE = "SOLVER_INFEASIBLE"
    SOLVER_ERROR = "SOLVER_ERROR"
    DWAVE_TOKEN_MISSING = "DWAVE_TOKEN_MISSING"

    # ── LLM ──
    LLM_CONNECTION_ERROR = "LLM_CONNECTION_ERROR"
    LLM_PARSE_ERROR = "LLM_PARSE_ERROR"

    # ── 일반 ──
    NOT_FOUND = "NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INVALID_INPUT = "INVALID_INPUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def error_response(
    text: str,
    *,
    code: Optional[ErrorCode] = None,
    retry_msg: str = "다시 시도",
    options: Optional[List[Dict]] = None,
) -> Dict:
    """표준 에러 응답 딕셔너리 생성.

    기존 error_response()와 하위 호환 유지하면서
    code 필드를 추가로 전달할 수 있습니다.
    """
    resp: Dict = {
        "type": "error",
        "text": f"❌ {text}",
        "data": None,
        "options": options or [
            {"label": "🔄 다시 시도", "action": "send", "message": retry_msg},
            {"label": "📖 가이드", "action": "send", "message": "가이드"},
        ],
    }
    if code is not None:
        resp["error_code"] = code.value
    return resp


def warning_response(
    text: str,
    *,
    code: Optional[ErrorCode] = None,
    options: Optional[List[Dict]] = None,
) -> Dict:
    """표준 경고 응답 딕셔너리 생성."""
    resp: Dict = {
        "type": "warning",
        "text": f"⚠️ {text}",
        "data": None,
        "options": options or [],
    }
    if code is not None:
        resp["error_code"] = code.value
    return resp
