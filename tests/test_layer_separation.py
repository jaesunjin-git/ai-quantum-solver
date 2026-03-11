"""
tests/test_layer_separation.py
──────────────────────────────
Phase 3: 3계층 분리 (core/platform, domains/common, domains/crew) 구조 검증.

1. core.platform에서 직접 import 가능
2. domains.crew re-export wrapper가 동일 객체를 반환
3. domains.common.skills에서 스킬 함수 import 가능
4. agent.py가 정상 import됨
"""

import pytest


class TestCoreplatformImports:
    """core.platform 모듈 직접 import 테스트"""

    def test_session_imports(self):
        from core.platform.session import SessionState, CrewSession, get_session
        assert SessionState is not None
        assert CrewSession is not None
        assert callable(get_session)

    def test_classifier_imports(self):
        from core.platform.classifier import InputClassifier, SKILL_TO_INTENT, parse_skill_from_llm
        assert InputClassifier is not None
        assert isinstance(SKILL_TO_INTENT, dict)
        assert callable(parse_skill_from_llm)

    def test_utils_imports(self):
        from core.platform.utils import clean_report, build_next_options, error_response
        assert callable(clean_report)
        assert callable(build_next_options)
        assert callable(error_response)

    def test_platform_init_reexports(self):
        from core.platform import SessionState, InputClassifier, clean_report
        assert SessionState is not None
        assert InputClassifier is not None
        assert callable(clean_report)


class TestReexportWrappers:
    """domains.crew re-export wrapper가 동일 객체 반환 확인"""

    def test_session_identity(self):
        from core.platform.session import SessionState, CrewSession, get_session
        from domains.crew.session import SessionState as S2, CrewSession as C2, get_session as G2
        assert SessionState is S2
        assert CrewSession is C2
        assert get_session is G2

    def test_classifier_identity(self):
        from core.platform.classifier import InputClassifier, SKILL_TO_INTENT
        from domains.crew.classifier import InputClassifier as I2, SKILL_TO_INTENT as SK2
        assert InputClassifier is I2
        assert SKILL_TO_INTENT is SK2

    def test_utils_identity(self):
        from core.platform.utils import clean_report, error_response
        from domains.crew.utils import clean_report as CR2, error_response as ER2
        assert clean_report is CR2
        assert error_response is ER2


class TestCommonSkillsImport:
    """domains.common.skills 스킬 함수 import 테스트"""

    def test_solver_skills(self):
        from domains.common.skills.solver import skill_pre_decision, skill_start_optimization
        assert callable(skill_pre_decision)
        assert callable(skill_start_optimization)

    def test_general_skills(self):
        from domains.common.skills.general import skill_answer, skill_general
        assert callable(skill_answer)
        assert callable(skill_general)

    def test_handlers_skills(self):
        from domains.common.skills.handlers import handle_file_upload, handle_reset
        assert callable(handle_file_upload)
        assert callable(handle_reset)

    def test_analyze_skills(self):
        from domains.common.skills.analyze import skill_analyze, skill_show_analysis
        assert callable(skill_analyze)
        assert callable(skill_show_analysis)

    def test_math_model_skills(self):
        from domains.common.skills.math_model import skill_math_model, handle_math_model_confirm
        assert callable(skill_math_model)
        assert callable(handle_math_model_confirm)

    def test_data_normalization_skills(self):
        from domains.common.skills.data_normalization import skill_data_normalization
        assert callable(skill_data_normalization)


class TestSkillReexportWrappers:
    """domains.crew.skills re-export가 domains.common.skills와 동일 객체"""

    def test_solver_identity(self):
        from domains.common.skills.solver import skill_pre_decision
        from domains.crew.skills.solver import skill_pre_decision as sp2
        assert skill_pre_decision is sp2

    def test_general_identity(self):
        from domains.common.skills.general import skill_general
        from domains.crew.skills.general import skill_general as sg2
        assert skill_general is sg2

    def test_analyze_identity(self):
        from domains.common.skills.analyze import skill_analyze
        from domains.crew.skills.analyze import skill_analyze as sa2
        assert skill_analyze is sa2

    def test_math_model_identity(self):
        from domains.common.skills.math_model import skill_math_model
        from domains.crew.skills.math_model import skill_math_model as sm2
        assert skill_math_model is sm2


class TestAgentIntegration:
    """agent.py가 re-export wrapper 경유로 정상 import됨"""

    def test_agent_import(self):
        from domains.crew.agent import crew_agent
        assert crew_agent is not None

    def test_crew_specific_skills_still_in_crew(self):
        """crew 전용 스킬은 domains/crew/skills/에 남아있어야 함"""
        from domains.crew.skills.structural_normalization import skill_structural_normalization
        assert callable(skill_structural_normalization)

        from domains.crew.skills.problem_definition import skill_problem_definition
        assert callable(skill_problem_definition)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
