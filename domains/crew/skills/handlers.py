"""
domains/crew/skills/handlers.py — Re-export wrapper
─────────────────────────────────────────────────────
실제 구현은 domains.common.skills.handlers로 이동됨.
기존 import 경로 호환을 위한 re-export.
"""
from domains.common.skills.handlers import (
    handle_file_upload,
    handle_reset,
    handle_guide,
    handle_domain_change,
)

__all__ = [
    "handle_file_upload",
    "handle_reset",
    "handle_guide",
    "handle_domain_change",
]
