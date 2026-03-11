"""
core/auth_router.py
────────────────────
인증 API: 로그인, 회원가입, 내 정보 조회.
"""
from __future__ import annotations

import logging
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.rate_limit import limiter
from core.models import UserDB
from core.auth import (
    hash_password, verify_password,
    create_access_token, get_current_user,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ── 스키마 ────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    role: str = "user"


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str | None
    role: str

    class Config:
        from_attributes = True


# ── 회원가입 ──────────────────────────────────────────────
@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(UserDB).filter(UserDB.username == body.username).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 사용자입니다.")

    user = UserDB(
        username=body.username,
        hashed_password=hash_password(body.password),
        display_name=body.display_name or body.username,
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.username, "role": user.role})
    logger.info(f"User registered: {user.username} (role={user.role})")
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(user),
    )


# ── 로그인 ────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == body.username).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다.")

    token = create_access_token({"sub": user.username, "role": user.role})
    logger.info(f"User logged in: {user.username}")
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(user),
    )


# ── 내 정보 조회 ─────────────────────────────────────────
@router.get("/me", response_model=UserOut)
def get_me(user: UserDB = Depends(get_current_user)):
    return UserOut.model_validate(user)
