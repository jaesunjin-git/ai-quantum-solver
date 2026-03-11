"""
domains/crew/classifier.py — Re-export wrapper
────────────────────────────────────────────────
실제 구현은 core.platform.classifier로 이동됨.
기존 import 경로 호환을 위한 re-export.
"""
from core.platform.classifier import (
    InputClassifier,
    SKILL_TO_INTENT,
    parse_skill_from_llm,
)

__all__ = [
    "InputClassifier",
    "SKILL_TO_INTENT",
    "parse_skill_from_llm",
]
