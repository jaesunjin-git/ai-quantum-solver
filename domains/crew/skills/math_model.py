"""
domains/crew/skills/math_model.py — Re-export wrapper
──────────────────────────────────────────────────────
실제 구현은 domains.common.skills.math_model로 이동됨.
기존 import 경로 호환을 위한 re-export.
"""
from domains.common.skills.math_model import (
    skill_math_model,
    skill_show_math_model,
    handle_math_model_confirm,
)

__all__ = [
    "skill_math_model",
    "skill_show_math_model",
    "handle_math_model_confirm",
]
