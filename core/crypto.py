"""
core/crypto.py
──────────────
Fernet 대칭 암호화로 민감 데이터(API Key 등) 보호.

환경변수 FERNET_KEY가 없으면 자동 생성하여 .env에 추가합니다.
"""
from __future__ import annotations

import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    key = os.getenv("FERNET_KEY")
    if not key:
        key = Fernet.generate_key().decode()
        logger.warning(
            "FERNET_KEY not set — generated a new key. "
            "Add FERNET_KEY=%s to your .env file to persist encrypted data across restarts.",
            key,
        )
        os.environ["FERNET_KEY"] = key
    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt(plaintext: str) -> str:
    """평문을 Fernet 암호화하여 base64 문자열로 반환."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Fernet 암호화된 문자열을 복호화."""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
