"""
domains/crew/utils.py — Re-export wrapper
──────────────────────────────────────────
실제 구현은 core.platform.utils로 이동됨.
기존 import 경로 호환을 위한 re-export.
"""
from core.platform.utils import (
    build_facts_summary,
    clean_report,
    extract_text_from_llm,
    domain_display,
    build_guide_text,
    build_next_options,
    error_response,
)

__all__ = [
    "build_facts_summary",
    "clean_report",
    "extract_text_from_llm",
    "domain_display",
    "build_guide_text",
    "build_next_options",
    "error_response",
]
