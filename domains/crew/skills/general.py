"""
domains/crew/skills/general.py — Re-export wrapper
────────────────────────────────────────────────────
실제 구현은 domains.common.skills.general로 이동됨.
기존 import 경로 호환을 위한 re-export.
"""
from domains.common.skills.general import (
    skill_answer,
    skill_general,
    skill_ask_for_data,
)

__all__ = [
    "skill_answer",
    "skill_general",
    "skill_ask_for_data",
]
