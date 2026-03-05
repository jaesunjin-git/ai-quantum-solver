"""
knowledge/domain_loader.py

범용 도메인 지식 로더.
knowledge/domains/{domain_name}/ 폴더 구조(분리형)와
knowledge/domains/{domain_name}.yaml 단일 파일 모두 지원.

사용법:
    from knowledge.domain_loader import load_domain_knowledge
    dk = load_domain_knowledge("railway")
    # dk.index, dk.constraints, dk.templates, dk.reference_ranges
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent  # knowledge/


def _safe_load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"YAML load failed: {path} -> {e}")
        return {}


@dataclass
class DomainKnowledge:
    """도메인 지식 번들. 분리형이든 단일형이든 동일한 인터페이스."""
    domain_name: str = ""
    index: Dict = field(default_factory=dict)
    constraints: Dict = field(default_factory=dict)
    templates: Dict = field(default_factory=dict)
    reference_ranges: Dict = field(default_factory=dict)
    raw_single: Optional[Dict] = None  # 단일 YAML 전체 (레거시 호환)

    @property
    def detection_keywords(self) -> list:
        return self.index.get("detection_keywords", [])

    @property
    def sub_domains(self) -> dict:
        return self.index.get("sub_domains", {})

    @property
    def network_topologies(self) -> dict:
        return self.index.get("network_topologies", {})

    @property
    def hard_constraints(self) -> dict:
        return self.constraints.get("hard", {})

    @property
    def soft_constraints(self) -> dict:
        return self.constraints.get("soft", {})

    def get_constraint(self, name: str) -> Optional[dict]:
        return self.hard_constraints.get(name) or self.soft_constraints.get(name)

    def get_reference_range(self, sub_domain: str, param: str) -> Optional[dict]:
        sd = self.reference_ranges.get(sub_domain, {})
        return sd.get(param)

    def all_constraint_names(self) -> List[str]:
        return list(self.hard_constraints.keys()) + list(self.soft_constraints.keys())

    def constraints_by_type(self, ctype: str) -> Dict[str, dict]:
        result = {}
        for name, cdata in self.hard_constraints.items():
            if cdata.get("type") == ctype:
                result[name] = cdata
        for name, cdata in self.soft_constraints.items():
            if cdata.get("type") == ctype:
                result[name] = cdata
        return result


# ── 캐시 ──
_cache: Dict[str, DomainKnowledge] = {}


def load_domain_knowledge(domain_name: str, force_reload: bool = False) -> DomainKnowledge:
    """
    도메인 지식을 로드한다.
    1) knowledge/domains/{domain_name}/ 폴더가 있으면 분리형으로 로드
    2) 없으면 knowledge/domains/{domain_name}.yaml 단일 파일 로드
    3) 둘 다 없으면 빈 DomainKnowledge 반환
    """
    if domain_name in _cache and not force_reload:
        return _cache[domain_name]

    domains_dir = _BASE / "domains"
    dk = DomainKnowledge(domain_name=domain_name)

    # 방법 1: 폴더 구조
    folder = domains_dir / domain_name
    if folder.is_dir():
        dk.index = _safe_load_yaml(folder / "_index.yaml")
        dk.constraints = _safe_load_yaml(folder / "constraints.yaml")
        dk.templates = _safe_load_yaml(folder / "templates.yaml")
        dk.reference_ranges = _safe_load_yaml(folder / "reference_ranges.yaml")
        logger.info(
            f"DomainLoader: loaded '{domain_name}' (folder) - "
            f"hard={len(dk.hard_constraints)}, soft={len(dk.soft_constraints)}"
        )
        _cache[domain_name] = dk
        return dk

    # 방법 2: 단일 파일
    single_file = domains_dir / f"{domain_name}.yaml"
    if single_file.exists():
        raw = _safe_load_yaml(single_file)
        dk.raw_single = raw
        # 단일 파일에서 호환 매핑
        dk.index = {
            "detection_keywords": raw.get("detection_keywords", []),
            "sub_domains": raw.get("sub_domains", {}),
            "network_topologies": raw.get("network_topologies", {}),
        }
        dk.constraints = raw.get("constraints", {})
        dk.templates = {"constraint_templates": raw.get("constraint_templates", {})}
        dk.reference_ranges = raw.get("reference_values", {})
        logger.info(
            f"DomainLoader: loaded '{domain_name}' (single file) - "
            f"hard={len(dk.hard_constraints)}, soft={len(dk.soft_constraints)}"
        )
        _cache[domain_name] = dk
        return dk

    # 방법 3: 없음
    logger.warning(f"DomainLoader: domain '{domain_name}' not found")
    _cache[domain_name] = dk
    return dk


def detect_domain_from_keywords(search_text: str) -> Optional[str]:
    """주어진 텍스트에서 도메인을 감지한다."""
    domains_dir = _BASE / "domains"
    if not domains_dir.exists():
        return None

    search_lower = search_text.lower()
    best_domain = None
    best_score = 0

    for entry in domains_dir.iterdir():
        if entry.is_dir():
            idx = _safe_load_yaml(entry / "_index.yaml")
            keywords = idx.get("detection_keywords", [])
            domain_name = entry.name
        elif entry.is_file() and entry.suffix == ".yaml":
            raw = _safe_load_yaml(entry)
            keywords = raw.get("detection_keywords", [])
            domain_name = entry.stem
        else:
            continue

        score = 0
        for group in keywords:
            if isinstance(group, list):
                if any(kw.lower() in search_lower for kw in group):
                    score += 1
            elif isinstance(group, str):
                if group.lower() in search_lower:
                    score += 1

        if score > best_score:
            best_score = score
            best_domain = domain_name

    return best_domain if best_score > 0 else None


def list_available_domains() -> List[str]:
    """사용 가능한 도메인 목록 반환."""
    domains_dir = _BASE / "domains"
    if not domains_dir.exists():
        return []

    result = set()
    for entry in domains_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith("_"):
            result.add(entry.name)
        elif entry.is_file() and entry.suffix == ".yaml":
            result.add(entry.stem)
    return sorted(result)
