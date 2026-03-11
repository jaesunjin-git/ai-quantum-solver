# core/platform/__init__.py
# Platform infrastructure: session management, intent classification, orchestration
# These are domain-agnostic components shared across all domains.

from core.platform.session import SessionState, CrewSession, save_session_state, load_session_state, get_session
from core.platform.classifier import InputClassifier, SKILL_TO_INTENT, parse_skill_from_llm
from core.platform.utils import (
    build_facts_summary, clean_report, extract_text_from_llm,
    domain_display, build_guide_text, build_next_options, error_response,
)
from core.platform.errors import ErrorCode, error_response, warning_response  # noqa: F811
