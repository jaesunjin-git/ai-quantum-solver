from __future__ import annotations
"""
domains/crew/skills/problem_definition.py

Problem Definition Skill.

기존 분석 결과(csv_summary, data_facts, data_profile, analysis_report)를 읽고,
도메인 지식(knowledge/domains/railway.yaml)을 참조하여
문제 유형, 목적함수, 제약조건, 파라미터를 확정한다.

입력: session.state의 기존 분석 결과
출력: session.state.confirmed_problem
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        self.prompt_config = _load_yaml("prompts/problem_definition.yaml")
        self._domain_cache: Dict[str, dict] = {}

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
        problem_type = self._determine_problem_type(state, domain_yaml)
        objective = self._determine_objective(problem_type, domain_yaml)
        constraints = self._determine_constraints(problem_type, domain_yaml)
        parameters = self._collect_parameters(state, domain_yaml)

        proposal = {
            "stage": problem_type.get("stage", "task_generation"),
            "variant": problem_type.get("variant"),
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
    # 1. 도메인 YAML 로드
    # ──────────────────────────────────────
    def _load_domain_yaml(self, state) -> dict:
        domain = state.detected_domain or "generic"
        domain_map = {"crew": "railway", "railway": "railway"}
        domain_key = domain_map.get(domain, domain)

        path = _BASE / "knowledge" / "domains" / f"{domain_key}.yaml"
        if not path.exists():
            # fallback: domains 폴더에서 첫 번째 yaml
            domains_dir = _BASE / "knowledge" / "domains"
            if domains_dir.exists():
                for f in domains_dir.glob("*.yaml"):
                    path = f
                    break
        return self._get_cached_yaml(str(path))

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
    # 2. 문제 유형 결정
    # ──────────────────────────────────────
    def _determine_problem_type(self, state, domain_yaml: dict) -> dict:
        result = {"stage": "task_generation", "variant": None, "confidence": 0.5}

        # data_facts에서 단서 추출
        facts = state.data_facts or {}
        sheet_info = facts.get("sheet_info", {})
        all_columns = facts.get("all_columns", {})

        # 힌트 수집
        has_timetable = False
        has_existing_duty = False
        has_crew_info = False
        station_count = 0

        for sheet_key, columns in all_columns.items():
            col_text = " ".join(str(c).lower() for c in columns)

            if any(kw in col_text for kw in ["열번", "배차", "departure", "arrival", "출발", "도착"]):
                has_timetable = True
            if any(kw in col_text for kw in ["dia", "듀티", "duty", "교번"]):
                has_existing_duty = True
            if any(kw in col_text for kw in ["승무원", "기관사", "인원", "crew", "driver"]):
                has_crew_info = True

        # data_profile에서 구조 단서
        if state.data_profile and isinstance(state.data_profile, dict):
            for sheet_key, info in state.data_profile.get("files", {}).items():
                if info.get("structure") == "non_tabular_block":
                    has_existing_duty = True

        # 문제 유형 결정
        if has_timetable:
            result["stage"] = "task_generation"
            result["confidence"] = 0.8
            if has_existing_duty:
                result["confidence"] = 0.9

        # variant 결정 (도메인 YAML 참조)
        variants = domain_yaml.get("problem_variants", {}).get("duty_generation", {})
        # 기본: single_line_bidirectional
        result["variant"] = "single_line_bidirectional"

        # station 수로 보정
        for sheet_key, columns in all_columns.items():
            station_cols = [c for c in columns if not any(
                kw in str(c).lower() for kw in
                ["열번", "배차", "반복", "회차", "영업", "편도", "unnamed"]
            )]
            if len(station_cols) > station_count:
                station_count = len(station_cols)

        if station_count >= 6:
            # 많은 역이 컬럼으로 있으면 단일노선 양방향 가능성 높음
            result["variant"] = "single_line_bidirectional"

        return result

    # ──────────────────────────────────────
    # 3. 목적함수 결정
    # ──────────────────────────────────────
    def _determine_objective(self, problem_type: dict, domain_yaml: dict) -> dict:
        stage = problem_type.get("stage", "task_generation")
        variant = problem_type.get("variant")

        # 도메인 YAML에서 variant별 목적함수 후보 가져오기
        variant_info = (
            domain_yaml
            .get("problem_variants", {})
            .get("duty_generation", {})
            .get(variant, {})
        )
        example_objectives = variant_info.get("example_objectives", [])

        # taxonomy에서 stage별 기본 목적함수
        stage_info = self.taxonomy.get("stages", {}).get(stage, {})
        typical_objectives = stage_info.get("typical_objectives", [])

        # 기본 목적함수 선택
        primary = "min_duties"
        if example_objectives:
            primary = example_objectives[0]
        elif typical_objectives:
            primary = typical_objectives[0]

        # 목적함수명 → 설명 매핑
        obj_descriptions = {
            "min_duties": "듀티 수 최소화",
            "minimize total number of duties": "듀티 수 최소화",
            "minimize total deadhead time": "공차회송 시간 최소화",
            "minimize total work time": "총 근무시간 최소화",
            "min_total_cost": "총 비용 최소화",
            "min_deadhead": "공차회송 최소화",
            "min_cost": "비용 최소화",
        }

        primary_clean = primary.lower().strip()
        description = obj_descriptions.get(primary_clean, primary)
        for key, desc in obj_descriptions.items():
            if key in primary_clean:
                description = desc
                break

        alternatives = []
        all_objs = example_objectives or typical_objectives
        for obj in all_objs[1:3]:
            obj_clean = obj.lower().strip()
            alt_desc = obj_descriptions.get(obj_clean, obj)
            for key, desc in obj_descriptions.items():
                if key in obj_clean:
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

        # 데이터에서 추출 시도
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
        extracted = {}
        if not state.data_facts:
            return extracted

        all_columns = state.data_facts.get("all_columns", {})

        param_keywords = {
            "max_work_minutes": ["최대근무", "max_work", "총근무시간", "근로시간"],
            "max_driving_minutes": ["최대승무", "max_driv", "승무시간"],
            "min_break_minutes": ["휴식", "break", "식사"],
            "prep_time_minutes": ["준비", "prep", "출근", "인수"],
            "cleanup_time_minutes": ["정리", "cleanup", "퇴근", "인계"],
            "night_rest_minutes": ["야간", "night", "숙박", "주박"],
        }

        for sheet_key, columns in all_columns.items():
            for param_name in required_params:
                if param_name in extracted:
                    continue
                keywords = param_keywords.get(param_name, [])
                if not keywords:
                    continue
                for col in columns:
                    col_l = str(col).lower()
                    if any(kw.lower() in col_l for kw in keywords):
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

        variant_info = (
            domain_yaml
            .get("problem_variants", {})
            .get("duty_generation", {})
            .get(variant, {})
        )
        variant_ko = variant_info.get("name_ko", variant)

        lines.append("### 1. 문제 유형")
        lines.append(f"- **단계**: {stage_ko}")
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
                    "- 목적함수를 총 근무시간 최소화로 변경\n"
                    "- max_work_minutes = 600\n"
                    "- 공차회송 최소화 제약 제거\n"
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
        param_pattern = re.compile(r"(\w+)\s*[=:]\s*(\d+(?:\.\d+)?)")
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

        # 목적함수 변경 요청 감지
        if state.problem_definition:
            obj_keywords = {
                "듀티 수 최소화": {"target": "min_duties", "description": "듀티 수 최소화"},
                "근무시간 최소화": {"target": "min_total_work_time", "description": "총 근무시간 최소화"},
                "공차회송 최소화": {"target": "min_deadhead", "description": "공차회송 시간 최소화"},
                "비용 최소화": {"target": "min_cost", "description": "총 비용 최소화"},
            }
            for keyword, obj_update in obj_keywords.items():
                if keyword in message:
                    state.problem_definition["objective"]["target"] = obj_update["target"]
                    state.problem_definition["objective"]["description"] = obj_update["description"]
                    save_session_state(project_id, state)
                    return {
                        "type": "problem_definition",
                        "text": (
                            f"목적함수를 **{obj_update['description']}**으로 변경했습니다.\n\n"
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
