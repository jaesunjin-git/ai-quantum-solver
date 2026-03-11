"""
domains/crew/skills/data_normalization.py — Re-export wrapper
──────────────────────────────────────────────────────────────
실제 구현은 domains.common.skills.data_normalization으로 이동됨.
기존 import 경로 호환을 위한 re-export.
"""
from domains.common.skills.data_normalization import (
    skill_data_normalization,
)

__all__ = [
    "skill_data_normalization",
]
