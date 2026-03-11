"""
tests/test_domain_knowledge_pack.py
──────────────────────────────
Phase 6: Domain Knowledge Pack 검증 테스트

1. 도메인 별칭 해석 (domain_aliases.yaml)
2. Knowledge Pack 검증 (필수 파일 체크)
3. 다중 도메인 로딩 (railway + logistics)
4. 도메인 프로필 로딩 (domain_profiles.yaml)
5. problem_definition.py에서 하드코딩 제거 확인
"""

import pytest


class TestDomainAliases:
    """domain_aliases.yaml 기반 별칭 해석"""

    def test_resolve_crew_to_railway(self):
        from knowledge.domain_loader import resolve_domain_alias
        assert resolve_domain_alias("crew") == "railway"

    def test_resolve_train_to_railway(self):
        from knowledge.domain_loader import resolve_domain_alias
        assert resolve_domain_alias("train") == "railway"

    def test_resolve_flight_to_aviation(self):
        from knowledge.domain_loader import resolve_domain_alias
        assert resolve_domain_alias("flight") == "aviation"

    def test_resolve_delivery_to_logistics(self):
        from knowledge.domain_loader import resolve_domain_alias
        assert resolve_domain_alias("delivery") == "logistics"

    def test_resolve_nurse_to_hospital(self):
        from knowledge.domain_loader import resolve_domain_alias
        assert resolve_domain_alias("nurse") == "hospital"

    def test_resolve_unknown_returns_self(self):
        from knowledge.domain_loader import resolve_domain_alias
        assert resolve_domain_alias("unknown_domain") == "unknown_domain"

    def test_resolve_already_canonical(self):
        from knowledge.domain_loader import resolve_domain_alias
        assert resolve_domain_alias("railway") == "railway"

    def test_case_insensitive(self):
        from knowledge.domain_loader import resolve_domain_alias
        assert resolve_domain_alias("Crew") == "railway"
        assert resolve_domain_alias("TRAIN") == "railway"


class TestKnowledgePackValidation:
    """Knowledge Pack 필수 파일 존재 여부 검증"""

    def test_railway_pack_valid(self):
        from knowledge.domain_loader import validate_knowledge_pack
        result = validate_knowledge_pack("railway")
        assert result["valid"] is True
        assert result["has_folder"] is True
        assert result["files"]["_index.yaml"] is True
        assert result["files"]["constraints.yaml"] is True
        assert len(result["missing_required"]) == 0

    def test_logistics_pack_valid(self):
        from knowledge.domain_loader import validate_knowledge_pack
        result = validate_knowledge_pack("logistics")
        assert result["valid"] is True
        assert result["has_folder"] is True
        assert result["files"]["_index.yaml"] is True
        assert result["files"]["constraints.yaml"] is True

    def test_alias_resolves_in_validation(self):
        from knowledge.domain_loader import validate_knowledge_pack
        result = validate_knowledge_pack("crew")
        assert result["domain"] == "railway"
        assert result["valid"] is True

    def test_nonexistent_domain_invalid(self):
        from knowledge.domain_loader import validate_knowledge_pack
        result = validate_knowledge_pack("nonexistent_xyz")
        assert result["valid"] is False
        assert len(result["missing_required"]) > 0


class TestMultiDomainLoading:
    """다중 도메인 knowledge pack 로딩"""

    def test_railway_loads(self):
        from knowledge.domain_loader import load_domain_knowledge
        dk = load_domain_knowledge("railway", force_reload=True)
        assert dk.domain_name == "railway"
        assert len(dk.hard_constraints) > 0
        assert len(dk.soft_constraints) > 0
        assert dk.yaml_version == "v3"

    def test_logistics_loads(self):
        from knowledge.domain_loader import load_domain_knowledge
        dk = load_domain_knowledge("logistics", force_reload=True)
        assert dk.domain_name == "logistics"
        assert len(dk.hard_constraints) > 0
        assert len(dk.soft_constraints) > 0
        assert dk.yaml_version == "v3"

    def test_logistics_has_expected_constraints(self):
        from knowledge.domain_loader import load_domain_knowledge
        dk = load_domain_knowledge("logistics", force_reload=True)
        assert "order_coverage" in dk.hard_constraints
        assert "vehicle_capacity_weight" in dk.hard_constraints
        assert "time_window" in dk.hard_constraints
        assert "workload_balance" in dk.soft_constraints

    def test_logistics_reference_ranges(self):
        from knowledge.domain_loader import load_domain_knowledge
        dk = load_domain_knowledge("logistics", force_reload=True)
        last_mile = dk.reference_ranges.get("last_mile", {})
        assert "max_driving_min" in last_mile
        assert last_mile["max_driving_min"]["default"] == 480

    def test_logistics_sub_domains(self):
        from knowledge.domain_loader import load_domain_knowledge
        dk = load_domain_knowledge("logistics", force_reload=True)
        subs = dk.sub_domains
        assert "last_mile" in subs
        assert "line_haul" in subs
        assert "cold_chain" in subs

    def test_alias_loads_correct_domain(self):
        from knowledge.domain_loader import load_domain_knowledge, resolve_domain_alias
        canonical = resolve_domain_alias("delivery")
        dk = load_domain_knowledge(canonical, force_reload=True)
        assert dk.domain_name == "logistics"
        assert len(dk.hard_constraints) > 0

    def test_list_domains_includes_logistics(self):
        from knowledge.domain_loader import list_available_domains
        domains = list_available_domains()
        assert "railway" in domains
        assert "logistics" in domains


class TestDomainProfile:
    """domain_profiles.yaml 통합 로딩"""

    def test_get_railway_profile(self):
        from knowledge.domain_loader import get_domain_profile
        profile = get_domain_profile("railway")
        assert profile["display_name"] == "철도 승무원 스케줄링"
        assert "detection_keywords" in profile

    def test_get_profile_via_alias(self):
        from knowledge.domain_loader import get_domain_profile
        profile = get_domain_profile("crew")
        assert profile["display_name"] == "철도 승무원 스케줄링"

    def test_get_logistics_profile(self):
        from knowledge.domain_loader import get_domain_profile
        profile = get_domain_profile("logistics")
        assert profile["display_name"] == "물류 배송 스케줄링"

    def test_list_all_profiles(self):
        from knowledge.domain_loader import list_domain_profiles
        profiles = list_domain_profiles()
        assert "railway" in profiles
        assert "logistics" in profiles
        assert "aviation" in profiles
        assert len(profiles) >= 6

    def test_nonexistent_profile_returns_empty(self):
        from knowledge.domain_loader import get_domain_profile
        profile = get_domain_profile("nonexistent_xyz")
        assert profile == {}


class TestHardcodeRemoval:
    """problem_definition.py에서 하드코딩 alias_map 제거 확인"""

    def test_no_hardcoded_alias_map(self):
        """alias_map 딕셔너리 리터럴이 더 이상 존재하지 않아야 함"""
        from pathlib import Path
        code = Path("domains/crew/skills/problem_definition.py").read_text(encoding="utf-8")
        assert 'alias_map = {' not in code, "Hardcoded alias_map should be removed"

    def test_uses_resolve_domain_alias(self):
        """resolve_domain_alias 함수를 사용해야 함"""
        from pathlib import Path
        code = Path("domains/crew/skills/problem_definition.py").read_text(encoding="utf-8")
        assert "resolve_domain_alias" in code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
