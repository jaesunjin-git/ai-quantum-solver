"""
검증 API 라우터 — /api/validation/*

프론트엔드 ValidationDrawer의 사용자 액션을 처리하는 REST 엔드포인트입니다.

제공 엔드포인트:
  1. apply-fix  : 자동 수정 적용 또는 사용자 입력값으로 검증 항목 해결
  2. dismiss    : 경고 항목 무시 처리
  3. run-stage  : 특정 스테이지 검증 수동 실행 (개발/디버그용)

MSA 참고:
  이 라우터는 독립적입니다. 마이크로서비스 구조에서는
  검증 레지스트리와 세션 상태에 접근하는 별도 서비스가 됩니다.
  /apply-fix 엔드포인트는 다른 서비스를 호출할 수 있습니다.
  APIs to propagate parameter changes.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.validation.registry import get_registry
from engine.validation.report import StageValidation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/validation", tags=["Validation"])


# ── Request/Response Models ─────────────────────────────────────────

class FixRequest(BaseModel):
    """Single fix to apply."""
    code: str                        # ValidationItem.code
    action: str = "auto_fix"         # "auto_fix" | "user_input" | "dismiss"
    value: Optional[dict] = None     # user-provided value for "user_input"


class ApplyFixRequest(BaseModel):
    """Apply one or more fixes to a stage's validation."""
    project_id: int
    stage: int
    fixes: List[FixRequest]


class ApplyFixResponse(BaseModel):
    """Response after applying fixes."""
    applied: List[str]               # codes that were successfully applied
    failed: List[str]                # codes that could not be applied
    validation: dict                 # updated StageValidation.to_dict()
    can_proceed: bool                # True if no remaining errors


class RunStageRequest(BaseModel):
    """Manual stage validation trigger (for dev/debug)."""
    project_id: int
    stage: int
    context: dict = {}


# ── Endpoints ───────────────────────────────────────────────────────

@router.post("/apply-fix", response_model=ApplyFixResponse)
async def apply_fix(request: ApplyFixRequest):
    """Apply user fixes to validation findings.

    Flow:
      1. Load current StageValidation from session cache
      2. For each fix:
         - auto_fix:    apply the suggested correction, dismiss the item
         - user_input:  apply user-provided value, dismiss the item
         - dismiss:     mark the item as dismissed
      3. Re-run validation with updated context
      4. Return the new StageValidation

    MSA note: In production, step 2 would call domain-specific
    parameter update services via internal API.
    """
    registry = get_registry()
    applied = []
    failed = []

    # TODO: Load stage validation from session state (DB/cache)
    # For now, create empty and run fresh validation
    # This will be connected when session integration is done

    for fix in request.fixes:
        if fix.action == "dismiss":
            # Dismiss is always safe
            applied.append(fix.code)
            logger.info(
                "Dismissed validation item: project=%d stage=%d code=%s",
                request.project_id, request.stage, fix.code,
            )
        elif fix.action == "auto_fix":
            # TODO: Apply the auto_fix to the actual parameter/data
            # This requires session state access to modify parameters
            applied.append(fix.code)
            logger.info(
                "Applied auto-fix: project=%d stage=%d code=%s",
                request.project_id, request.stage, fix.code,
            )
        elif fix.action == "user_input":
            if fix.value is None:
                failed.append(fix.code)
                continue
            # TODO: Apply user-provided value to parameter
            applied.append(fix.code)
            logger.info(
                "Applied user input: project=%d stage=%d code=%s value=%s",
                request.project_id, request.stage, fix.code, fix.value,
            )
        else:
            failed.append(fix.code)

    # Re-run validation after fixes
    # TODO: Build context from updated session state
    context = {}
    stage_result = registry.run_stage(request.stage, context)

    # Mark dismissed items from the applied fixes
    for code in applied:
        stage_result.dismiss(code)

    return ApplyFixResponse(
        applied=applied,
        failed=failed,
        validation=stage_result.to_dict(),
        can_proceed=stage_result.passed,
    )


@router.post("/run-stage")
async def run_stage(request: RunStageRequest):
    """Manually trigger validation for a specific stage.

    Useful for dev/debug and for re-running validation after changes.
    """
    registry = get_registry()
    result = registry.run_stage(request.stage, request.context)
    return result.to_dict()


@router.get("/validators")
async def list_validators(stage: Optional[int] = None):
    """List all registered validators, optionally filtered by stage."""
    registry = get_registry()
    return registry.list_validators(stage)
