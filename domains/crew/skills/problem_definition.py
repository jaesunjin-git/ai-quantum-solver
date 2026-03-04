from __future__ import annotations
"""
domains/crew/skills/problem_definition.py

Problem Definition Skill.

기존 분석 결과(csv_summary, data_facts, data_profile, analysis_report)를 읽고,
도메인 지식(knowledge/domains/*.yaml)을 참조하여
문제 유형, 목적함수, 제약조건, 파라미터를 확정한다.

데이터 유형 감지: knowledge/data_detection.yaml
문제 매칭 규칙: knowledge/matching_rules.yaml
문제 단계 분류: knowledge/taxonomy.yaml
도메인 지식:     knowledge/domains/{domain}.yaml

입력: session.state의 기존 분석 결과
출력: session.state.confirmed_problem
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from domains.crew.session import CrewSession, save_session_state

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parents[3]


def _load_yaml(rel_path: str) -> dict:
    full = _BASE / rel_path
    if not full.exists():
        logger.warning(f"YAML not found: {full}")
        return {}
    with open(full, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class ProblemDefinitionSkill:

    def __init__(self):
        self.taxonomy = _load_yaml("knowledge/taxonomy.yaml")
        self.data_detection = _load_yaml("knowledge/data_detection.yaml")
        self.matching_rules = _load_yaml("knowledge/matching_rules.yaml")
        self.prompt_config = _load_yaml("prompts/problem_definition.yaml")
        self._domain_cache: Dict[str, dict] = {}

        # data_detection.yaml에서 데이터 유형별 키워드 맵 구축
        self._detection_keywords: Dict[str, List[List[str]]] = {}
        self._extraction_keys: Dict[str, List[str]] = {}
        for dtype, dinfo in self.data_detection.get("data_types", {}).items():
            self._detection_keywords[dtype] = dinfo.get("column_keywords", [])
            self._extraction_keys[dtype] = dinfo.get("extraction_keys", [])

        # matching_rules.yaml에서 규칙 맵 구축
        self._matching_rules: Dict[str, dict] = self.matching_rules.get("rules", {})

        # taxonomy.yaml에서 stage→variant_group 매핑 동적 구축
        self._stage_variant_group: Dict[str, str] = {}
        for stage_key, stage_info in self.taxonomy.get("stages", {}).items():
            vg = stage_info.get("variant_group", stage_key)
            self._stage_variant_group[stage_key] = vg

        # taxonomy.yaml에서 목적함수 설명 맵 동적 구축
        self._obj_descriptions: Dict[str, str] = {}
        for stage_key, stage_info in self.taxonomy.get("stages", {}).items():
            for obj in stage_info.get("typical_objectives", []):
                self._obj_descriptions[obj] = obj.replace("_", " ")

        logger.info(
            f"ProblemDefinitionSkill init: "
            f"detection_types={list(self._detection_keywords.keys())}, "
            f"matching_rules={list(self._matching_rules.keys())}, "
            f"taxonomy_stages={list(self.taxonomy.get('stages', {}).keys())}"
        )

    # ──────────────────────────────────────
    # public entry point
    # ──────────────────────────────────────
    async def handle(
        self, session: CrewSession, project_id: str,
        message: str, params: Dict
    ) -> Dict:
        state = session.state

        # 이미 제안을 보냈고 사용자 응답 대기 중
        if state.problem_definition_proposed and not state.problem_defined:
            return self._handle_user_response(session, project_id, message)

        # 첫 진입: 분석 결과 기반 제안 생성
        domain_yaml = self._load_domain_yaml(state)
        detected_data_types = self._detect_data_types(state)
        problem_type = self._determine_problem_type(state, domain_yaml, detected_data_types)
        objective = self._determine_objective(problem_type, domain_yaml)
        constraints = self._determine_constraints(problem_type, domain_yaml)
        parameters = self._collect_parameters(state, domain_yaml)

        proposal = {
            "stage": problem_type.get("stage", "task_generation"),
            "variant": problem_type.get("variant"),
            "detected_data_types": list(detected_data_types),
            "objective": objective,
            "hard_constraints": constraints.get("hard", {}),
            "soft_constraints": constraints.get("soft", {}),
            "parameters": parameters,
        }

        state.problem_definition = proposal
        state.problem_definition_proposed = True
        save_session_state(project_id, state)

        response_text = self._format_proposal(state, domain_yaml, proposal)

        return {
            "type": "problem_definition",
            "text": response_text,
            "data": {
                "view_mode": "problem_definition",
                "proposal": proposal,
                "agent_status": "problem_definition_proposed",
            },
            "options": [
                {"label": "confirm", "action": "send", "message": "confirm"},
                {"label": "modify", "action": "send", "message": "modify"},
                {"label": "reanalyze", "action": "send", "message": "reanalyze"},
            ],
        }

    # ──────────────────────────────────────
    # 0. 데이터 유형 감지 (data_detection.yaml 기반)
    # ──────────────────────────────────────
    def _detect_data_types(self, state) -> Set[str]:
        """data_detection.yaml의 column_keywords를 사용하여 데이터 유형 감지"""
        detected = set()
        facts = state.data_facts or {}
        all_columns = facts.get("all_columns", {})

        # 전체 컬럼 텍스트를 시트별로 수집
        for sheet_key, columns in all_columns.items():
            col_text = " ".join(str(c).lower() for c in columns)

            for dtype, keyword_groups in self._detection_keywords.items():
                if dtype in detected:
                    continue
                # keyword_groups: [["departure","arrival","출발","도착"], ["station","역"]]
                # 각 그룹에서 하나라도 매치되면 해당 데이터 유형으로 감지
                for group in keyword_groups:
                    if any(kw.lower() in col_text for kw in group):
                        detected.add(dtype)
                        break

        # data_profile에서 구조 기반 추가 감지
        if state.data_profile and isinstance(state.data_profile, dict):
            for sheet_key, info in state.data_profile.get("files", {}).items():
                if info.get("structure") == "non_tabular_block":
                    detected.add("existing_duty")

        logger.info(f"Detected data types: {detected}")
        return detected

    # ──────────────────────────────────────
    # 1. 도메인 YAML 로드
    # ──────────────────────────────────────
    def _load_domain_yaml(self, state) -> dict:
        domain = state.detected_domain or "generic"

        # knowledge/domains/ 폴더에서 동적으로 매칭
        domains_dir = _BASE / "knowledge" / "domains"
        if domains_dir.exists():
            # 정확 매칭 시도
            exact_path = domains_dir / f"{domain}.yaml"
            if exact_path.exists():
                return self._get_cached_yaml(str(exact_path))

            # crew -> railway 등 도메인 프로파일에서 매핑 조회
            # domain_profiles.yaml의 키 목록으로 유사 매칭
            for yaml_file in domains_dir.glob("*.yaml"):
                domain_key = yaml_file.stem  # railway, aviation 등
                cached = self._get_cached_yaml(str(yaml_file))
                # 도메인 YAML의 detection_keywords에서 현재 domain과 매칭
                det_kws = cached.get("detection_keywords", [])
                flat_kws = []
                for item in det_kws:
                    if isinstance(item, list):
                        flat_kws.extend(item)
                    else:
                        flat_kws.append(str(item))
                if domain.lower() in [k.lower() for k in flat_kws]:
                    return cached

            # fallback: 첫 번째 yaml
            for yaml_file in domains_dir.glob("*.yaml"):
                return self._get_cached_yaml(str(yaml_file))

        return {}

    def _get_cached_yaml(self, path: str) -> dict:
        if path not in self._domain_cache:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._domain_cache[path] = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Failed to load {path}: {e}")
                self._domain_cache[path] = {}
        return self._domain_cache[path]

    # ──────────────────────────────────────
    # 2. 문제 유형 결정 (matching_rules.yaml 기반)
    # ──────────────────────────────────────
    def _determine_problem_type(
        self, state, domain_yaml: dict, detected_data_types: Set[str]
    ) -> dict:
        best = {"stage": "task_generation", "variant": None, "confidence": 0.0}

        # matching_rules.yaml의 각 규칙을 평가
        for rule_name, rule in self._matching_rules.items():
            required = set(rule.get("required_data", []))
            optional = set(rule.get("optional_data", []))
            base_conf = rule.get("base_confidence", 0.5)
            stage = rule.get("recommended_stage", "task_generation")

            # 필수 데이터가 모두 감지되었는지 확인
            if not required.issubset(detected_data_types):
                continue

            confidence = base_conf

            # boost 조건 평가
            for boost in rule.get("boost_conditions", []):
                condition = boost.get("condition", "")
                boost_val = boost.get("boost", 0)

                # 조건 해석 (간단한 패턴 매칭)
                if "detected" in condition:
                    # "existing_duty detected" → existing_duty가 감지되었으면 boost
                    for dtype in detected_data_types:
                        if dtype in condition:
                            confidence += boost_val
                            break
                elif "trip_count" in condition or "crew_count" in condition:
                    # 데이터 팩트에서 수치 확인
                    facts = state.data_facts or {}
                    unique = facts.get("unique_counts", {})
                    for key, count in unique.items():
                        if "trip" in key.lower() and "trip_count" in condition:
                            try:
                                threshold = int(re.search(r"\d+", condition).group())
                                if count >= threshold:
                                    confidence += boost_val
                            except (AttributeError, ValueError):
                                pass
                        if "crew" in key.lower() and "crew_count" in condition:
                            try:
                                threshold = int(re.search(r"\d+", condition).group())
                                if count >= threshold:
                                    confidence += boost_val
                            except (AttributeError, ValueError):
                                pass
                elif "all five data types" in condition:
                    if len(detected_data_types) >= 5:
                        confidence += boost_val

            confidence = min(confidence, 1.0)

            if confidence > best["confidence"]:
                best = {
                    "stage": stage,
                    "variant": None,
                    "confidence": confidence,
                    "matched_rule": rule_name,
                }

        # variant 결정 (도메인 YAML의 problem_variants에서)
        variants = domain_yaml.get("problem_variants", {})
        # stage에 해당하는 variant 그룹 찾기
        stage = best.get("stage", "task_generation")
        variant_group_key = self._stage_variant_group.get(stage, stage)

        if variant_group_key and variant_group_key in variants:
            variant_group = variants[variant_group_key]
            best_variant = None
            best_variant_score = 0

            facts = state.data_facts or {}
            all_columns = facts.get("all_columns", {})

            for vkey, vinfo in variant_group.items():
                hints = vinfo.get("detection_hints", [])
                score = 0
                for hint in hints:
                    hint_lower = hint.lower()
                    # 힌트를 데이터 특성과 매칭
                    if "2 termini" in hint_lower or "bidirectional" in hint_lower:
                        # direction 컬럼 존재 여부
                        for cols in all_columns.values():
                            col_text = " ".join(str(c).lower() for c in cols)
                            if "direction" in col_text or "방향" in col_text or "상행" in col_text:
                                score += 1
                                break
                    if "single line" in hint_lower:
                        score += 0.5  # 기본 가정
                    if "one direction" in hint_lower:
                        pass  # 단방향 감지 로직
                    if "multiple line" in hint_lower or "3+ termini" in hint_lower:
                        pass  # 다중 노선 감지 로직

                if score > best_variant_score:
                    best_variant_score = score
                    best_variant = vkey

            if best_variant:
                best["variant"] = best_variant
            else:
                # 첫 번째 variant를 기본값으로
                first_variant = next(iter(variant_group.keys()), None)
                best["variant"] = first_variant

        logger.info(
            f"Problem type determined: stage={best.get('stage')}, "
            f"variant={best.get('variant')}, confidence={best.get('confidence')}, "
            f"rule={best.get('matched_rule')}"
        )
        return best

    # ──────────────────────────────────────
    # 3. 목적함수 결정
    # ──────────────────────────────────────
    def _determine_objective(self, problem_type: dict, domain_yaml: dict) -> dict:
        stage = problem_type.get("stage", "task_generation")
        variant = problem_type.get("variant")

        # 도메인 YAML에서 variant별 목적함수 후보 가져오기
        variant_group_key = self._stage_variant_group.get(stage, stage)
        variant_info = (
            domain_yaml
            .get("problem_variants", {})
            .get(variant_group_key, {})
            .get(variant, {})
        ) if variant else {}
        example_objectives = variant_info.get("example_objectives", [])

        # taxonomy에서 stage별 기본 목적함수
        stage_info = self.taxonomy.get("stages", {}).get(stage, {})
        typical_objectives = stage_info.get("typical_objectives", [])

        # 기본 목적함수 선택
        primary = None
        if example_objectives:
            primary = example_objectives[0]
        elif typical_objectives:
            primary = typical_objectives[0]
        else:
            # taxonomy 전체에서 첫 번째 objective를 fallback으로 사용
            all_stage_objs = []
            for _si in self.taxonomy.get("stages", {}).values():
                all_stage_objs.extend(_si.get("typical_objectives", []))
            primary = all_stage_objs[0] if all_stage_objs else "minimize"

        # 도메인 YAML의 constraints에서 목적함수 설명 보강
        domain_objectives = domain_yaml.get("constraints", {}).get("soft", {})
        # taxonomy의 typical_objectives에서 설명 동적 구축
        all_obj_descriptions = dict(self._obj_descriptions)
        # 도메인 YAML의 typical_objectives (있으면)
        for obj_text in domain_yaml.get("problem_variants", {}).get(
            variant_group_key, {}
        ).get(variant, {}).get("example_objectives", []):
            all_obj_descriptions[obj_text.lower().strip()] = obj_text

        primary_clean = primary.lower().strip()
        description = all_obj_descriptions.get(primary_clean, primary)
        # 부분 매칭
        for key, desc in all_obj_descriptions.items():
            if key in primary_clean or primary_clean in key:
                description = desc
                break

        alternatives = []
        all_objs = example_objectives or typical_objectives
        for obj in all_objs[1:3]:
            obj_clean = obj.lower().strip()
            alt_desc = all_obj_descriptions.get(obj_clean, obj)
            for key, desc in all_obj_descriptions.items():
                if key in obj_clean or obj_clean in key:
                    alt_desc = desc
                    break
            alternatives.append({"target": obj, "description": alt_desc})

        return {
            "type": "minimize",
            "target": primary,
            "description": description,
            "alternatives": alternatives,
        }

    # ──────────────────────────────────────
    # 4. 제약조건 결정
    # ──────────────────────────────────────
    def _determine_constraints(self, problem_type: dict, domain_yaml: dict) -> dict:
        constraints_def = domain_yaml.get("constraints", {})

        hard = {}
        for cname, cdata in constraints_def.get("hard", {}).items():
            hard[cname] = {
                "name_ko": cdata.get("name_ko", cname),
                "description": cdata.get("description", ""),
                "parameter": cdata.get("parameter"),
                "parameters": cdata.get("parameters"),
                "formulation": cdata.get("formulation"),
            }

        soft = {}
        for cname, cdata in constraints_def.get("soft", {}).items():
            weight_range = cdata.get("weight_range", [0.1, 0.5])
            default_weight = round((weight_range[0] + weight_range[1]) / 2, 2)
            soft[cname] = {
                "name_ko": cdata.get("name_ko", cname),
                "description": cdata.get("description", ""),
                "weight": default_weight,
                "weight_range": weight_range,
            }

        return {"hard": hard, "soft": soft}

    # ──────────────────────────────────────
    # 5. 파라미터 수집
    # ──────────────────────────────────────
    def _collect_parameters(self, state, domain_yaml: dict) -> dict:
        parameters = {}

        # 도메인 YAML에서 필요한 파라미터 목록과 기본값 가져오기
        ref_values = domain_yaml.get("reference_values", {})
        sub_domain = self._detect_sub_domain(state, domain_yaml)
        ref = self._find_reference(ref_values, sub_domain)

        # 제약조건에서 필요한 파라미터 추출
        constraints = domain_yaml.get("constraints", {})
        required_params = set()

        for ctype in ["hard", "soft"]:
            for cname, cdata in constraints.get(ctype, {}).items():
                param = cdata.get("parameter")
                if param and param != "null":
                    required_params.add(param)
                for pname in cdata.get("parameters", {}).keys():
                    required_params.add(pname)

        # 데이터에서 추출 시도 (data_detection.yaml 기반)
        extracted = self._try_extract_from_data(state, required_params)

        # 각 파라미터에 대해 값 결정
        for param_name in required_params:
            if param_name in extracted:
                parameters[param_name] = {
                    "value": extracted[param_name],
                    "source": "data",
                }
            elif param_name in ref:
                parameters[param_name] = {
                    "value": ref[param_name],
                    "source": "default",
                }
            else:
                parameters[param_name] = {
                    "value": None,
                    "source": "user_input_required",
                }

        return parameters

    def _detect_sub_domain(self, state, domain_yaml: dict) -> Optional[str]:
        search_text = ""
        if state.uploaded_files:
            search_text += " ".join(str(f).lower() for f in state.uploaded_files)
        if state.csv_summary:
            search_text += " " + state.csv_summary.lower()

        for sub_key, sub_data in domain_yaml.get("sub_domains", {}).items():
            keywords = sub_data.get("detection_keywords", [])
            if any(kw.lower() in search_text for kw in keywords):
                return sub_key
        return None

    def _find_reference(self, ref_values: dict, sub_domain: Optional[str]) -> dict:
        if not ref_values:
            return {}
        if sub_domain:
            for key in ref_values:
                if sub_domain.replace("_", "") in key.replace("_", ""):
                    return ref_values[key]
        return next(iter(ref_values.values()), {})

    def _try_extract_from_data(self, state, required_params: set) -> dict:
        """data_detection.yaml의 work_regulations.column_keywords를 사용하여 파라미터 추출"""
        extracted = {}
        if not state.data_facts:
            return extracted

        all_columns = state.data_facts.get("all_columns", {})

        # data_detection.yaml에서 work_regulations의 extraction_keys와
        # column_keywords를 사용하여 파라미터-키워드 매핑 구축
        work_reg = self.data_detection.get("data_types", {}).get("work_regulations", {})
        work_keywords = work_reg.get("column_keywords", [])
        extraction_keys = work_reg.get("extraction_keys", [])

        # extraction_keys에서 required_params와 매칭되는 것 찾기
        # 키워드 그룹을 평탄화하여 사용
        flat_keywords = []
        for group in work_keywords:
            if isinstance(group, list):
                flat_keywords.extend(group)
            else:
                flat_keywords.append(str(group))

        for sheet_key, columns in all_columns.items():
            for param_name in required_params:
                if param_name in extracted:
                    continue

                # param_name이 extraction_keys에 있는지 확인
                if param_name not in extraction_keys:
                    continue

                # param_name에서 키워드 추출 (snake_case 분리)
                param_words = set(param_name.lower().replace("_", " ").split())
                # "minutes", "min", "time" 등 단위어 제거
                stop_words = {"minutes", "min", "time", "per", "param"}
                param_core = param_words - stop_words

                for col in columns:
                    col_l = str(col).lower()
                    # 1차: flat_keywords 중 하나라도 컬럼명에 포함
                    kw_match = any(kw.lower() in col_l for kw in flat_keywords)
                    # 2차: param 핵심 단어가 컬럼명에 포함
                    core_match = any(w in col_l for w in param_core) if param_core else False

                    if kw_match and core_match:
                        # data_profile에서 샘플값 추출
                        if state.data_profile:
                            col_info = (
                                state.data_profile
                                .get("files", {})
                                .get(sheet_key, {})
                                .get("columns", {})
                                .get(str(col), {})
                            )
                            samples = col_info.get("sample_values", [])
                            if samples:
                                try:
                                    extracted[param_name] = float(samples[0])
                                    break
                                except (ValueError, IndexError):
                                    pass

        return extracted

    # ──────────────────────────────────────
    # 응답 포맷팅
    # ──────────────────────────────────────
    def _format_proposal(self, state, domain_yaml: dict, proposal: dict) -> str:
        lines = []
        lines.append("## 문제 정의 제안\n")

        # 1. 문제 유형
        stage = proposal.get("stage", "")
        variant = proposal.get("variant", "")
        stage_info = self.taxonomy.get("stages", {}).get(stage, {})
        stage_ko = stage_info.get("name_ko", stage)

        # variant 한국어 이름을 도메인 YAML에서 동적 조회
        variant_group_key = self._stage_variant_group.get(stage, stage)
        variant_info = (
            domain_yaml
            .get("problem_variants", {})
            .get(variant_group_key, {})
            .get(variant, {})
        ) if variant else {}
        variant_ko = variant_info.get("name_ko", variant or "")

        lines.append("### 1. 문제 유형")
        lines.append(f"- **단계**: {stage_ko}")
        if variant_ko:
            lines.append(f"- **세부 유형**: {variant_ko}")
        lines.append("")

        # 2. 목적함수
        obj = proposal.get("objective", {})
        lines.append("### 2. 목적함수")
        lines.append(f"- **방향**: {obj.get('type', 'minimize')}")
        lines.append(f"- **대상**: {obj.get('description', '')}")

        alts = obj.get("alternatives", [])
        if alts:
            alt_texts = [a.get("description", a.get("target", "")) for a in alts]
            lines.append(f"- **대안**: {', '.join(alt_texts)}")
        lines.append("")

        # 3. 제약조건
        lines.append("### 3. 제약조건")
        lines.append("")
        lines.append("**필수 제약 (Hard):**")
        for cname, cdata in proposal.get("hard_constraints", {}).items():
            name_ko = cdata.get("name_ko", cname)
            desc = cdata.get("description", "")
            lines.append(f"- **{name_ko}**: {desc}")
        lines.append("")

        lines.append("**선택 제약 (Soft):**")
        for cname, cdata in proposal.get("soft_constraints", {}).items():
            name_ko = cdata.get("name_ko", cname)
            desc = cdata.get("description", "")
            weight = cdata.get("weight", 0)
            lines.append(f"- **{name_ko}**: {desc} (가중치: {weight})")
        lines.append("")

        # 4. 파라미터
        lines.append("### 4. 파라미터")
        params = proposal.get("parameters", {})

        data_params = {k: v for k, v in params.items() if v.get("source") == "data"}
        default_params = {k: v for k, v in params.items() if v.get("source") == "default"}
        missing_params = {k: v for k, v in params.items() if v.get("source") == "user_input_required"}

        if data_params:
            lines.append("")
            lines.append("**데이터에서 추출:**")
            for pname, pinfo in data_params.items():
                lines.append(f"- {pname}: **{pinfo['value']}**")

        if default_params:
            lines.append("")
            lines.append("**기본값 제안 (수정 가능):**")
            for pname, pinfo in default_params.items():
                lines.append(f"- {pname}: **{pinfo['value']}**")

        if missing_params:
            lines.append("")
            lines.append("**입력 필요:**")
            for pname in missing_params:
                lines.append(f"- {pname}: ???")

        lines.append("")
        lines.append("---")
        lines.append("위 내용을 확인하고 **확인**, **수정**, 또는 **다시 분석**을 입력해주세요.")

        return "\n".join(lines)

    # ──────────────────────────────────────
    # 사용자 응답 처리
    # ──────────────────────────────────────
    def _handle_user_response(
        self, session: CrewSession, project_id: str, message: str
    ) -> Dict:
        state = session.state
        keywords = self.prompt_config.get("confirmation_keywords", {})
        msg_lower = message.strip().lower()

        positive = [k.lower() for k in keywords.get("positive", [])]
        modify = [k.lower() for k in keywords.get("modify", [])]
        restart = [k.lower() for k in keywords.get("restart", [])]

        # 확인
        if any(kw in msg_lower for kw in positive):
            state.problem_defined = True
            state.confirmed_problem = state.problem_definition
            save_session_state(project_id, state)

            return {
                "type": "problem_definition",
                "text": (
                    "**문제 정의가 확정되었습니다.**\n\n"
                    "다음 단계: 데이터 정규화\n"
                    "데이터를 수학 모델에 맞는 형태로 변환합니다."
                ),
                "data": {
                    "view_mode": "problem_defined",
                    "confirmed_problem": state.confirmed_problem,
                    "agent_status": "problem_defined",
                },
                "options": [
                    {"label": "데이터 정규화 시작",
                     "action": "send",
                     "message": "데이터 정규화 시작"},
                ],
            }

        # 수정 요청
        if any(kw in msg_lower for kw in modify):
            return {
                "type": "problem_definition",
                "text": (
                    "수정할 항목을 알려주세요. 예시:\n\n"
                    "- 목적함수를 [목적함수명]으로 변경\n"
                    "- [파라미터명] = [값]\n"
                    "- [제약조건명] 제거\n"
                ),
                "data": {"agent_status": "modification_pending"},
                "options": [],
            }

        # 재시작
        if any(kw in msg_lower for kw in restart):
            state.problem_definition = None
            state.problem_definition_proposed = False
            state.problem_defined = False
            state.confirmed_problem = None
            save_session_state(project_id, state)

            return {
                "type": "info",
                "text": "문제 정의를 초기화했습니다. 다시 분석을 시작합니다.",
                "data": {"agent_status": "reset"},
                "options": [
                    {"label": "분석 시작",
                     "action": "send",
                     "message": "분석 시작해줘"},
                ],
            }

        # 파라미터 수정 (key = value 패턴)
        param_pattern = re.compile(r"(\w+)\s*[=:：]\s*(\d+(?:\.\d+)?)")
        matches = param_pattern.findall(message)
        if matches and state.problem_definition:
            params = state.problem_definition.get("parameters", {})
            updated = []
            for key, val in matches:
                val_num = float(val)
                if key in params:
                    params[key]["value"] = val_num
                    params[key]["source"] = "user_modified"
                    updated.append(f"{key} = {val_num}")
                else:
                    params[key] = {"value": val_num, "source": "user_input"}
                    updated.append(f"{key} = {val_num}")

            if updated:
                save_session_state(project_id, state)
                return {
                    "type": "problem_definition",
                    "text": (
                        f"파라미터를 수정했습니다: {', '.join(updated)}\n\n"
                        "**확인**을 입력하면 문제 정의가 확정됩니다."
                    ),
                    "data": {
                        "proposal": state.problem_definition,
                        "agent_status": "parameters_modified",
                    },
                    "options": [
                        {"label": "확인", "action": "send", "message": "확인"},
                        {"label": "추가 수정", "action": "send", "message": "수정"},
                    ],
                }

        # 목적함수 변경 요청 감지 (taxonomy + 도메인 YAML 기반)
        if state.problem_definition:
            # taxonomy의 모든 objectives에서 한국어 매핑 동적 구축
            for stage_key, stage_info in self.taxonomy.get("stages", {}).items():
                for obj in stage_info.get("typical_objectives", []):
                    obj_ko = obj.replace("_", " ")
                    if obj_ko in message or obj in message:
                        state.problem_definition["objective"]["target"] = obj
                        state.problem_definition["objective"]["description"] = obj_ko
                        save_session_state(project_id, state)
                        return {
                            "type": "problem_definition",
                            "text": (
                                f"목적함수를 **{obj_ko}**으로 변경했습니다.\n\n"
                                "**확인**을 입력하면 문제 정의가 확정됩니다."
                            ),
                            "data": {
                                "proposal": state.problem_definition,
                                "agent_status": "objective_modified",
                            },
                            "options": [
                                {"label": "확인", "action": "send", "message": "확인"},
                                {"label": "추가 수정", "action": "send", "message": "수정"},
                            ],
                        }

        # 기타
        return {
            "type": "problem_definition",
            "text": (
                "**확인**, **수정**, 또는 **다시 분석**을 입력해주세요.\n"
                "파라미터 수정은 파라미터명 = 값 형식으로 입력할 수 있습니다."
            ),
            "data": {"agent_status": "awaiting_response"},
            "options": [
                {"label": "확인", "action": "send", "message": "확인"},
                {"label": "수정", "action": "send", "message": "수정"},
                {"label": "다시 분석", "action": "send", "message": "다시 분석"},
            ],
        }


# ── 모듈 레벨 함수 ──
_skill_instance: Optional[ProblemDefinitionSkill] = None


def get_skill() -> ProblemDefinitionSkill:
    global _skill_instance
    if _skill_instance is None:
        _skill_instance = ProblemDefinitionSkill()
    return _skill_instance


async def skill_problem_definition(
    model, session: CrewSession, project_id: str,
    message: str, params: Dict
) -> Dict:
    skill = get_skill()
    return await skill.handle(session, project_id, message, params)
