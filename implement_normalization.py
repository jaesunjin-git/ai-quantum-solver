import os, ast, json, textwrap

def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  OK: {path} ({os.path.getsize(path)} bytes)')

# ============================================================
# 1. prompts/data_normalization.yaml
# ============================================================
write_file('prompts/data_normalization.yaml', textwrap.dedent("""\
    # AI Quantum Solver - Data Normalization Prompt
    # Version: 1.0
    # Used by: DataNormalizationSkill

    version: "1.0"

    system_prompt: |
      You are a data transformation expert for optimization problems.
      Analyze the given problem definition and data structure,
      then generate mapping rules to create normalized tables
      that a mathematical model can directly use.

      You must respond in pure JSON only. No markdown, no explanation.

    rules:
      - "Each mapping must include confidence (0.0 to 1.0)."
      - "Do NOT guess values that are not in the data."
      - "For pivot-style data (station names as columns), suggest unpivot transform."
      - "For non-tabular block structures, suggest parse_blocks transform."
      - "If a mapping is uncertain, set confidence below 0.3."
      - "Time values should be converted to minutes from midnight."
      - "Use the confirmed problem definition to determine which tables are needed."

    output_schema: |
      {
        "mappings": [
          {
            "target_table": "trips | parameters | existing_duties",
            "source_file": "filename.xlsx",
            "source_sheet": "SheetName",
            "transform_type": "unpivot | direct | parse_blocks | extract_kv | from_confirmed",
            "confidence": 0.0,
            "reason": "explanation of why this mapping was chosen",
            "column_mapping": {
              "target_col": "source_col or transform rule"
            },
            "notes": "any additional transformation notes"
          }
        ]
      }

    required_tables:
      task_generation:
        trips:
          columns:
            - trip_id
            - direction
            - dep_station
            - arr_station
            - dep_time_min
            - arr_time_min
          description: "Trip list. Times in minutes from midnight."
          required: true
        parameters:
          columns:
            - param_name
            - value
            - unit
          description: "Constraint parameter values."
          required: true
        existing_duties:
          columns:
            - duty_id
            - trip_ids
            - start_time_min
            - end_time_min
            - duty_type
          description: "Existing DIA duties for comparison."
          required: false

      roster_assignment:
        duties:
          columns:
            - duty_id
            - start_time_min
            - end_time_min
            - duty_type
          description: "Duty list to assign to crew."
          required: true
        crew:
          columns:
            - crew_id
            - qualification
            - depot
          description: "Crew member information."
          required: true
        parameters:
          columns:
            - param_name
            - value
            - unit
          description: "Constraint parameter values."
          required: true

    confidence_threshold: 0.8

    confirmation_keywords:
      positive: ["confirm", "ok", "yes", "approve",
                  "확인", "네", "좋습니다", "승인", "진행"]
      modify: ["modify", "change", "adjust",
               "수정", "변경", "조정"]
      restart: ["restart", "reset", "다시",
                "재시작", "처음부터"]
"""))

print('=== File 1 created ===')

# ============================================================
# 2. domains/crew/skills/data_normalization.py
# ============================================================
write_file('domains/crew/skills/data_normalization.py', textwrap.dedent('''\
    from __future__ import annotations
    """
    domains/crew/skills/data_normalization.py

    Data Normalization Skill.

    confirmed_problem + 기존 분석 결과를 바탕으로
    LLM에게 매핑 규칙을 1회 요청하고,
    confidence 기준으로 자동 확정 / 사용자 확인 분류 후,
    확인된 규칙으로 실제 데이터 변환을 실행하여
    normalized/ 폴더에 저장한다.
    """

    import asyncio
    import json
    import logging
    import os
    import re
    from pathlib import Path
    from typing import Any, Dict, List, Optional

    import pandas as pd
    import yaml

    from domains.crew.session import CrewSession, save_session_state

    logger = logging.getLogger(__name__)

    _BASE = Path(__file__).resolve().parents[3]
    _UPLOAD_BASE = _BASE / "uploads"


    def _load_yaml(rel_path: str) -> dict:
        full = _BASE / rel_path
        if not full.exists():
            logger.warning(f"YAML not found: {full}")
            return {}
        with open(full, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


    class DataNormalizationSkill:

        def __init__(self):
            self.config = _load_yaml("prompts/data_normalization.yaml")
            self.confidence_threshold = self.config.get("confidence_threshold", 0.8)

        # ──────────────────────────────────────
        # public entry point
        # ──────────────────────────────────────
        async def handle(
            self, model, session: CrewSession, project_id: str,
            message: str, params: Dict
        ) -> Dict:
            state = session.state

            # 매핑 제안 후 사용자 응답 대기 중
            if state.normalization_mapping and not state.normalization_confirmed:
                return await self._handle_user_response(
                    model, session, project_id, message
                )

            # 첫 진입: LLM으로 매핑 생성
            mapping_result = await self._generate_mapping(model, state)

            if not mapping_result:
                return {
                    "type": "error",
                    "text": "데이터 매핑 생성에 실패했습니다. 다시 시도해주세요.",
                    "data": None,
                    "options": [
                        {"label": "재시도", "action": "send",
                         "message": "데이터 정규화 시작"},
                    ],
                }

            # confidence 기준으로 분류
            auto_confirmed = []
            needs_review = []
            for m in mapping_result.get("mappings", []):
                if m.get("confidence", 0) >= self.confidence_threshold:
                    auto_confirmed.append(m)
                else:
                    needs_review.append(m)

            # 세션에 저장
            state.normalization_mapping = {
                "auto_confirmed": auto_confirmed,
                "needs_review": needs_review,
                "all_mappings": mapping_result.get("mappings", []),
            }
            save_session_state(project_id, state)

            # needs_review가 없으면 바로 변환 실행
            if not needs_review:
                return await self._execute_normalization(
                    model, session, project_id
                )

            # 사용자 확인 필요
            response_text = self._format_mapping_result(
                auto_confirmed, needs_review
            )

            return {
                "type": "data_normalization",
                "text": response_text,
                "data": {
                    "view_mode": "normalization_mapping",
                    "mappings": {
                        "auto_confirmed": auto_confirmed,
                        "needs_review": needs_review,
                    },
                    "agent_status": "normalization_proposed",
                },
                "options": [
                    {"label": "확인", "action": "send", "message": "확인"},
                    {"label": "수정", "action": "send", "message": "수정"},
                ],
            }

        # ──────────────────────────────────────
        # LLM 매핑 생성 (1회 호출)
        # ──────────────────────────────────────
        async def _generate_mapping(self, model, state) -> Optional[dict]:
            confirmed = state.confirmed_problem or {}
            stage = confirmed.get("stage", "task_generation")

            # 필요한 테이블 목록
            required = self.config.get("required_tables", {}).get(stage, {})

            # 프롬프트 조립
            system = self.config.get("system_prompt", "")
            rules = self.config.get("rules", [])
            rules_text = "\\n".join(f"  {i+1}. {r}" for i, r in enumerate(rules))
            output_schema = self.config.get("output_schema", "{}")

            # confirmed_problem 요약
            problem_summary = json.dumps(confirmed, ensure_ascii=False, indent=2)

            # 데이터 구조 요약
            data_summary = state.csv_summary or "데이터 요약 없음"
            if len(data_summary) > 4000:
                data_summary = data_summary[:4000]

            # data_profile 요약
            profile_summary = ""
            if state.data_profile and isinstance(state.data_profile, dict):
                for sheet_key, info in state.data_profile.get("files", {}).items():
                    cols = info.get("columns", {})
                    col_names = list(cols.keys())[:20]
                    structure = info.get("structure", "tabular")
                    profile_summary += (
                        f"\\n[{sheet_key}] {info.get('rows', 0)} rows, "
                        f"structure={structure}, "
                        f"columns={col_names}"
                    )

            # 필요한 테이블 설명
            tables_desc = ""
            for table_name, table_info in required.items():
                cols = table_info.get("columns", [])
                desc = table_info.get("description", "")
                req = "필수" if table_info.get("required", True) else "선택"
                tables_desc += (
                    f"\\n  - {table_name} ({req}): {desc}"
                    f"\\n    columns: {cols}"
                )

            prompt = f"""{system}

    Rules:
    {rules_text}

    Output JSON Schema:
    {output_schema}

    [Confirmed Problem Definition]
    {problem_summary}

    [Required Normalized Tables]
    {tables_desc}

    [Data Structure Summary]
    {data_summary}

    [Data Profile]
    {profile_summary}

    Generate the mapping JSON now."""

            try:
                response = await asyncio.to_thread(
                    model.generate_content, prompt
                )
                text = response.text.strip()

                # JSON 추출
                json_match = re.search(r'\\{[\\s\\S]*\\}', text)
                if json_match:
                    return json.loads(json_match.group())
                return json.loads(text)

            except json.JSONDecodeError as e:
                logger.error(f"Mapping JSON parse error: {e}")
                logger.error(f"Raw response: {text[:500]}")
                return None
            except Exception as e:
                logger.error(f"Mapping generation failed: {e}", exc_info=True)
                return None

        # ──────────────────────────────────────
        # 사용자 응답 처리
        # ──────────────────────────────────────
        async def _handle_user_response(
            self, model, session: CrewSession, project_id: str, message: str
        ) -> Dict:
            state = session.state
            keywords = self.config.get("confirmation_keywords", {})
            msg_lower = message.strip().lower()

            positive = [k.lower() for k in keywords.get("positive", [])]
            modify = [k.lower() for k in keywords.get("modify", [])]
            restart = [k.lower() for k in keywords.get("restart", [])]

            # 확인 → 변환 실행
            if any(kw in msg_lower for kw in positive):
                return await self._execute_normalization(
                    model, session, project_id
                )

            # 수정 요청
            if any(kw in msg_lower for kw in modify):
                return {
                    "type": "data_normalization",
                    "text": (
                        "수정할 매핑을 알려주세요. 예시:\\n\\n"
                        "- trips의 source를 다른 시트로 변경\\n"
                        "- dep_station 컬럼을 출발역으로 매핑\\n"
                    ),
                    "data": {"agent_status": "modification_pending"},
                    "options": [],
                }

            # 재시작
            if any(kw in msg_lower for kw in restart):
                state.normalization_mapping = None
                state.normalization_confirmed = False
                state.data_normalized = False
                save_session_state(project_id, state)
                return {
                    "type": "info",
                    "text": "데이터 정규화를 초기화했습니다.",
                    "data": {"agent_status": "normalization_reset"},
                    "options": [
                        {"label": "정규화 재시작", "action": "send",
                         "message": "데이터 정규화 시작"},
                    ],
                }

            # 기타
            return {
                "type": "data_normalization",
                "text": (
                    "**확인**, **수정**, 또는 **다시**를 입력해주세요."
                ),
                "data": {"agent_status": "awaiting_response"},
                "options": [
                    {"label": "확인", "action": "send", "message": "확인"},
                    {"label": "수정", "action": "send", "message": "수정"},
                ],
            }

        # ──────────────────────────────────────
        # 변환 실행
        # ──────────────────────────────────────
        async def _execute_normalization(
            self, model, session: CrewSession, project_id: str
        ) -> Dict:
            state = session.state
            mapping = state.normalization_mapping
            if not mapping:
                return {
                    "type": "error",
                    "text": "매핑 정보가 없습니다.",
                    "data": None,
                    "options": [],
                }

            all_mappings = mapping.get("all_mappings", [])
            upload_dir = _UPLOAD_BASE / re.sub(r"[^a-zA-Z0-9_\\-]", "", str(project_id))
            norm_dir = upload_dir / "normalized"
            norm_dir.mkdir(parents=True, exist_ok=True)

            results = []
            errors = []

            for m in all_mappings:
                target = m.get("target_table", "")
                transform = m.get("transform_type", "")
                source_file = m.get("source_file", "")
                source_sheet = m.get("source_sheet", "")

                try:
                    if target == "trips" and transform == "unpivot":
                        df = await self._transform_unpivot_timetable(
                            upload_dir, source_file, source_sheet, m
                        )
                        if df is not None and len(df) > 0:
                            out_path = norm_dir / "trips.csv"
                            df.to_csv(str(out_path), index=False, encoding="utf-8")
                            results.append(f"trips.csv: {len(df)} rows")
                        else:
                            errors.append(f"trips: 변환 결과가 비어있습니다")

                    elif target == "trips" and transform == "direct":
                        df = await self._transform_direct(
                            upload_dir, source_file, source_sheet, m
                        )
                        if df is not None and len(df) > 0:
                            out_path = norm_dir / "trips.csv"
                            df.to_csv(str(out_path), index=False, encoding="utf-8")
                            results.append(f"trips.csv: {len(df)} rows")
                        else:
                            errors.append(f"trips: 변환 결과가 비어있습니다")

                    elif target == "parameters":
                        df = await self._transform_parameters(
                            state, upload_dir, source_file, source_sheet, m
                        )
                        if df is not None and len(df) > 0:
                            out_path = norm_dir / "parameters.csv"
                            df.to_csv(str(out_path), index=False, encoding="utf-8")
                            results.append(f"parameters.csv: {len(df)} rows")

                    elif target == "existing_duties":
                        df = await self._transform_parse_blocks(
                            upload_dir, source_file, source_sheet, m
                        )
                        if df is not None and len(df) > 0:
                            out_path = norm_dir / "existing_duties.csv"
                            df.to_csv(str(out_path), index=False, encoding="utf-8")
                            results.append(f"existing_duties.csv: {len(df)} rows")

                except Exception as e:
                    logger.error(f"Transform error [{target}]: {e}", exc_info=True)
                    errors.append(f"{target}: {str(e)}")

            # 결과 판단
            if results:
                state.normalization_confirmed = True
                state.data_normalized = True
                state.normalized_data_summary = {
                    "files": results,
                    "errors": errors,
                    "output_dir": str(norm_dir),
                }
                save_session_state(project_id, state)

                result_text = "**데이터 정규화가 완료되었습니다.**\\n\\n"
                result_text += "생성된 파일:\\n"
                for r in results:
                    result_text += f"- {r}\\n"
                if errors:
                    result_text += "\\n경고:\\n"
                    for e in errors:
                        result_text += f"- {e}\\n"
                result_text += "\\n다음 단계: 수학 모델 생성"

                return {
                    "type": "data_normalization",
                    "text": result_text,
                    "data": {
                        "view_mode": "normalization_complete",
                        "results": results,
                        "errors": errors,
                        "agent_status": "normalization_complete",
                    },
                    "options": [
                        {"label": "수학 모델 생성", "action": "send",
                         "message": "수학 모델 생성해줘"},
                    ],
                }
            else:
                return {
                    "type": "error",
                    "text": (
                        "데이터 변환에 실패했습니다.\\n\\n"
                        + "\\n".join(f"- {e}" for e in errors)
                    ),
                    "data": {"agent_status": "normalization_failed"},
                    "options": [
                        {"label": "재시도", "action": "send",
                         "message": "데이터 정규화 시작"},
                    ],
                }

        # ──────────────────────────────────────
        # 변환 함수들
        # ──────────────────────────────────────
        async def _transform_unpivot_timetable(
            self, upload_dir: Path, source_file: str,
            source_sheet: str, mapping: dict
        ) -> Optional[pd.DataFrame]:
            """피벗 형태 시간표를 행 기반 trips로 변환"""
            file_path = upload_dir / source_file
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return None

            df = pd.read_excel(str(file_path), sheet_name=source_sheet or 0)
            col_mapping = mapping.get("column_mapping", {})

            # 역명 컬럼과 메타 컬럼 분리
            meta_keywords = [
                "열번", "배차", "반복", "회차", "영업", "편도",
                "unnamed", "trip", "interval", "operation"
            ]

            meta_cols = []
            station_cols = []
            for col in df.columns:
                col_str = str(col).lower()
                if any(kw in col_str for kw in meta_keywords):
                    meta_cols.append(col)
                else:
                    station_cols.append(col)

            if not station_cols:
                logger.error("No station columns detected")
                return None

            # 상행/하행 분리 감지 (.1 suffix)
            base_stations = [c for c in station_cols if ".1" not in str(c)]
            rev_stations = [c for c in station_cols if ".1" in str(c)]

            trips = []
            trip_id = 1

            for idx, row in df.iterrows():
                # 상행 (base_stations)
                if base_stations:
                    times = []
                    for st in base_stations:
                        val = row.get(st)
                        if pd.notna(val):
                            minutes = self._to_minutes(val)
                            if minutes is not None:
                                times.append((str(st), minutes))

                    if len(times) >= 2:
                        trips.append({
                            "trip_id": trip_id,
                            "direction": "up",
                            "dep_station": times[0][0],
                            "arr_station": times[-1][0],
                            "dep_time_min": times[0][1],
                            "arr_time_min": times[-1][1],
                        })
                        trip_id += 1

                # 하행 (rev_stations)
                if rev_stations:
                    times = []
                    for st in rev_stations:
                        val = row.get(st)
                        if pd.notna(val):
                            minutes = self._to_minutes(val)
                            if minutes is not None:
                                clean_name = str(st).replace(".1", "")
                                times.append((clean_name, minutes))

                    if len(times) >= 2:
                        trips.append({
                            "trip_id": trip_id,
                            "direction": "down",
                            "dep_station": times[0][0],
                            "arr_station": times[-1][0],
                            "dep_time_min": times[0][1],
                            "arr_time_min": times[-1][1],
                        })
                        trip_id += 1

            return pd.DataFrame(trips) if trips else None

        async def _transform_direct(
            self, upload_dir: Path, source_file: str,
            source_sheet: str, mapping: dict
        ) -> Optional[pd.DataFrame]:
            """이미 정규형인 데이터를 컬럼 매핑만 적용"""
            file_path = upload_dir / source_file
            if not file_path.exists():
                return None

            ext = file_path.suffix.lower()
            if ext == ".csv":
                try:
                    df = pd.read_csv(str(file_path), encoding="utf-8")
                except UnicodeDecodeError:
                    df = pd.read_csv(str(file_path), encoding="cp949")
            else:
                df = pd.read_excel(str(file_path), sheet_name=source_sheet or 0)

            col_mapping = mapping.get("column_mapping", {})
            if col_mapping:
                reverse_map = {v: k for k, v in col_mapping.items() if isinstance(v, str)}
                df = df.rename(columns=reverse_map)

            return df

        async def _transform_parameters(
            self, state, upload_dir: Path, source_file: str,
            source_sheet: str, mapping: dict
        ) -> Optional[pd.DataFrame]:
            """confirmed_problem의 파라미터 + 데이터에서 보충"""
            confirmed = state.confirmed_problem or {}
            params = confirmed.get("parameters", {})

            rows = []
            for pname, pinfo in params.items():
                value = pinfo.get("value") if isinstance(pinfo, dict) else pinfo
                source = pinfo.get("source", "confirmed") if isinstance(pinfo, dict) else "confirmed"
                rows.append({
                    "param_name": pname,
                    "value": value,
                    "unit": "minutes",
                    "source": source,
                })

            return pd.DataFrame(rows) if rows else None

        async def _transform_parse_blocks(
            self, upload_dir: Path, source_file: str,
            source_sheet: str, mapping: dict
        ) -> Optional[pd.DataFrame]:
            """비정형 블록 구조의 DIA 파싱"""
            file_path = upload_dir / source_file
            if not file_path.exists():
                return None

            df = pd.read_excel(str(file_path), sheet_name=source_sheet or 0, header=None)

            # 빈 행으로 블록 분리
            duties = []
            current_duty = []
            duty_id = 1

            for idx, row in df.iterrows():
                if row.isna().all():
                    if current_duty:
                        parsed = self._parse_duty_block(duty_id, current_duty)
                        if parsed:
                            duties.append(parsed)
                            duty_id += 1
                        current_duty = []
                else:
                    current_duty.append(row)

            # 마지막 블록
            if current_duty:
                parsed = self._parse_duty_block(duty_id, current_duty)
                if parsed:
                    duties.append(parsed)

            return pd.DataFrame(duties) if duties else None

        def _parse_duty_block(self, duty_id: int, rows: list) -> Optional[dict]:
            """개별 DIA 블록을 파싱"""
            if not rows:
                return None

            times = []
            for row in rows:
                for val in row:
                    if pd.notna(val):
                        minutes = self._to_minutes(val)
                        if minutes is not None:
                            times.append(minutes)

            if len(times) >= 2:
                return {
                    "duty_id": f"D{duty_id:03d}",
                    "trip_ids": "",
                    "start_time_min": min(times),
                    "end_time_min": max(times),
                    "duty_type": "normal",
                }
            return None

        def _to_minutes(self, val) -> Optional[int]:
            """다양한 시간 형태를 자정 기준 분으로 변환"""
            import datetime
            if isinstance(val, datetime.time):
                return val.hour * 60 + val.minute
            if isinstance(val, datetime.datetime):
                return val.hour * 60 + val.minute
            if isinstance(val, (int, float)):
                v = float(val)
                if 0 <= v <= 1440:
                    return int(v)
                return None
            s = str(val).strip()
            m = re.match(r"^(\\d{1,2}):(\\d{2})(?::(\\d{2}))?$", s)
            if m:
                h, mi = int(m.group(1)), int(m.group(2))
                return h * 60 + mi
            return None

        # ──────────────────────────────────────
        # 응답 포맷팅
        # ──────────────────────────────────────
        def _format_mapping_result(
            self, auto_confirmed: list, needs_review: list
        ) -> str:
            lines = []
            lines.append("## 데이터 정규화 매핑 결과\\n")

            if auto_confirmed:
                lines.append("### 자동 매핑 완료 (확인 불필요)")
                for m in auto_confirmed:
                    target = m.get("target_table", "")
                    source = m.get("source_file", "")
                    sheet = m.get("source_sheet", "")
                    conf = m.get("confidence", 0)
                    reason = m.get("reason", "")
                    source_str = f"{source}:{sheet}" if sheet else source
                    lines.append(
                        f"- **{target}** <- {source_str} "
                        f"(확신도: {conf:.0%}) {reason}"
                    )
                lines.append("")

            if needs_review:
                lines.append("### 확인 필요")
                for m in needs_review:
                    target = m.get("target_table", "")
                    source = m.get("source_file", "")
                    sheet = m.get("source_sheet", "")
                    conf = m.get("confidence", 0)
                    reason = m.get("reason", "")
                    source_str = f"{source}:{sheet}" if sheet else source
                    lines.append(
                        f"- **{target}** <- {source_str} "
                        f"(확신도: {conf:.0%})"
                    )
                    lines.append(f"  사유: {reason}")
                lines.append("")

            lines.append("---")
            lines.append(
                "**확인**을 입력하면 변환을 실행합니다. "
                "**수정**을 입력하면 매핑을 조정할 수 있습니다."
            )

            return "\\n".join(lines)


    # ── 모듈 레벨 함수 ──
    _skill_instance: Optional[DataNormalizationSkill] = None


    def get_skill() -> DataNormalizationSkill:
        global _skill_instance
        if _skill_instance is None:
            _skill_instance = DataNormalizationSkill()
        return _skill_instance


    async def skill_data_normalization(
        model, session: CrewSession, project_id: str,
        message: str, params: Dict
    ) -> Dict:
        skill = get_skill()
        return await skill.handle(model, session, project_id, message, params)
'''))

print('=== File 2 created ===')

# ============================================================
# 3. session.py 패치
# ============================================================
with open('domains/crew/session.py', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# 필드 추가
new_fields = """
    # ── Data Normalization Phase ──
    normalization_mapping: Optional[Dict] = None
    normalization_confirmed: bool = False
    data_normalized: bool = False
    normalized_data_summary: Optional[Dict] = None
"""

if 'normalization_mapping' not in content:
    anchor = 'confirmed_problem: Optional[Dict] = None'
    if anchor in content:
        content = content.replace(anchor, anchor + '\n' + new_fields)
        changes += 1
        print('  session.py: normalization fields ADDED')

    # reset_from_analysis에 리셋 추가
    reset_addition = """
        self.normalization_mapping = None
        self.normalization_confirmed = False
        self.data_normalized = False
        self.normalized_data_summary = None"""

    if 'self.confirmed_problem = None' in content and 'normalization_mapping' not in content.split('reset_from_analysis')[1].split('def ')[0] if 'reset_from_analysis' in content else True:
        content = content.replace(
            '        self.confirmed_problem = None',
            '        self.confirmed_problem = None' + reset_addition,
            1
        )
        changes += 1
        print('  session.py: reset_from_analysis UPDATED')

    with open('domains/crew/session.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  session.py: {changes} changes ({os.path.getsize("domains/crew/session.py")} bytes)')
else:
    print('  session.py: SKIP (already has normalization fields)')

print('=== File 3 patched ===')

# ============================================================
# 4. agent.py 패치
# ============================================================
with open('domains/crew/agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# import 추가
if 'skill_data_normalization' not in content:
    content = content.replace(
        'from domains.crew.skills.problem_definition import skill_problem_definition',
        'from domains.crew.skills.problem_definition import skill_problem_definition\nfrom domains.crew.skills.data_normalization import skill_data_normalization'
    )
    changes += 1
    print('  agent.py: import added')

# 가드 추가: problem_defined + not data_normalized → DATA_NORMALIZATION
norm_guard = '''
            # ★ Phase2: 문제 정의 완료 but 데이터 미정규화 시
            if session.state.problem_defined and not session.state.data_normalized:
                logger.info(f"[{project_id}] Data not normalized — redirecting to DATA_NORMALIZATION")
                return await self._execute_skill(session, project_id, "DATA_NORMALIZATION", message, {})
'''

if 'data_normalized' not in content:
    # Phase1.5 가드 뒤에 삽입
    anchor = 'return await self._execute_skill(session, project_id, "PROBLEM_DEFINITION", message, {})'
    if anchor in content:
        content = content.replace(anchor, anchor + '\n' + norm_guard)
        changes += 1
        print('  agent.py: normalization guard added')

# handler 추가
if '"DATA_NORMALIZATION"' not in content.split('handlers = {')[1].split('}')[0] if 'handlers = {' in content else True:
    content = content.replace(
        '"PROBLEM_DEFINITION": lambda s, p, m, pr: skill_problem_definition(self.model, s, p, m, pr),',
        '"PROBLEM_DEFINITION": lambda s, p, m, pr: skill_problem_definition(self.model, s, p, m, pr),\n            "DATA_NORMALIZATION": lambda s, p, m, pr: skill_data_normalization(self.model, s, p, m, pr),'
    )
    changes += 1
    print('  agent.py: handler added')

# intent_to_tab 추가
if '"DATA_NORMALIZATION"' not in content.split('intent_to_tab')[1] if 'intent_to_tab' in content else True:
    content = content.replace(
        '"PROBLEM_DEFINITION": "analysis",',
        '"PROBLEM_DEFINITION": "analysis",\n            "DATA_NORMALIZATION": "analysis",'
    )
    changes += 1
    print('  agent.py: intent_to_tab updated')

# skill_name_map 추가
if 'DataNormalizationSkill' not in content:
    content = content.replace(
        '"ProblemDefinitionSkill": "PROBLEM_DEFINITION",',
        '"ProblemDefinitionSkill": "PROBLEM_DEFINITION",\n                "DataNormalizationSkill": "DATA_NORMALIZATION",'
    )
    changes += 1
    print('  agent.py: skill_name_map updated')

with open('domains/crew/agent.py', 'w', encoding='utf-8') as f:
    f.write(content)
print(f'  agent.py: {changes} changes ({os.path.getsize("domains/crew/agent.py")} bytes)')

print('=== File 4 patched ===')

# ============================================================
# 5. classifier.py 패치
# ============================================================
with open('domains/crew/classifier.py', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

if 'data_normalization' not in content:
    # defaults에 추가
    content = content.replace(
        '"problem_definition": ["문제 정의",',
        '"data_normalization": ["데이터 정규화", "정규화", "normalization", "데이터 변환", "매핑"],\n            "problem_definition": ["문제 정의",'
    )
    changes += 1

    # quick_classify에 추가
    content = content.replace(
        '        if any(kw in msg for kw in cls._keywords.get("problem_definition", [])):\n            return "PROBLEM_DEFINITION"',
        '        if any(kw in msg for kw in cls._keywords.get("data_normalization", [])):\n            return "DATA_NORMALIZATION"\n        if any(kw in msg for kw in cls._keywords.get("problem_definition", [])):\n            return "PROBLEM_DEFINITION"'
    )
    changes += 1

    # SKILL_TO_INTENT에 추가
    content = content.replace(
        '"ProblemDefinitionSkill": "PROBLEM_DEFINITION",',
        '"ProblemDefinitionSkill": "PROBLEM_DEFINITION",\n    "DataNormalizationSkill": "DATA_NORMALIZATION",'
    )
    changes += 1

    with open('domains/crew/classifier.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  classifier.py: {changes} changes ({os.path.getsize("domains/crew/classifier.py")} bytes)')
else:
    print('  classifier.py: SKIP (already has data_normalization)')

print('=== File 5 patched ===')

# ============================================================
# 6. core/models.py 패치
# ============================================================
with open('core/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'data_normalized' not in content:
    content = content.replace(
        '    confirmed_problem = Column(Text, nullable=True)',
        '    confirmed_problem = Column(Text, nullable=True)\n\n    # Data Normalization\n    data_normalized = Column(Boolean, default=False)\n    normalization_mapping = Column(Text, nullable=True)\n    normalized_data_summary = Column(Text, nullable=True)'
    )
    with open('core/models.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  models.py: columns added ({os.path.getsize("core/models.py")} bytes)')
else:
    print('  models.py: SKIP (already has data_normalized)')

print('=== File 6 patched ===')

# ============================================================
# 7. session.py save/load에 새 필드 추가
# ============================================================
with open('domains/crew/session.py', 'r', encoding='utf-8') as f:
    content = f.read()

save_addition = """
        # Data Normalization
        row.data_normalized = getattr(state, 'data_normalized', False)
        row.normalization_mapping = json.dumps(state.normalization_mapping, ensure_ascii=False) if state.normalization_mapping else None
        row.normalized_data_summary = json.dumps(state.normalized_data_summary, ensure_ascii=False) if state.normalized_data_summary else None
"""

load_addition = """
        # Data Normalization
        state.data_normalized = getattr(row, 'data_normalized', False) or False
        state.normalization_confirmed = state.data_normalized
        state.normalization_mapping = json.loads(row.normalization_mapping) if getattr(row, 'normalization_mapping', None) else None
        state.normalized_data_summary = json.loads(row.normalized_data_summary) if getattr(row, 'normalized_data_summary', None) else None
"""

if 'row.data_normalized' not in content:
    # save에 추가
    content = content.replace(
        '        row.confirmed_problem = json.dumps(state.confirmed_problem, ensure_ascii=False) if state.confirmed_problem else None',
        '        row.confirmed_problem = json.dumps(state.confirmed_problem, ensure_ascii=False) if state.confirmed_problem else None' + save_addition
    )
    # load에 추가
    content = content.replace(
        '        state.confirmed_problem = json.loads(row.confirmed_problem) if getattr(row, \'confirmed_problem\', None) else None',
        '        state.confirmed_problem = json.loads(row.confirmed_problem) if getattr(row, \'confirmed_problem\', None) else None' + load_addition
    )
    with open('domains/crew/session.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('  session.py: save/load UPDATED')
else:
    print('  session.py: save/load SKIP')

print('=== File 7 patched ===')

# ============================================================
# 8. Syntax check
# ============================================================
print('\n=== Syntax Check ===')
check_files = [
    'prompts/data_normalization.yaml',
    'domains/crew/skills/data_normalization.py',
    'domains/crew/session.py',
    'domains/crew/agent.py',
    'domains/crew/classifier.py',
    'core/models.py',
]

for f in check_files:
    if f.endswith('.yaml'):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                yaml.safe_load(fh)
            print(f'  PASS: {f}')
        except Exception as e:
            print(f'  FAIL: {f} - {e}')
    else:
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                ast.parse(fh.read())
            print(f'  PASS: {f}')
        except SyntaxError as e:
            print(f'  FAIL: {f} - line {e.lineno}: {e.msg}')
            with open(f, 'r', encoding='utf-8') as fh:
                lines = fh.readlines()
            for j in range(max(0, e.lineno-3), min(len(lines), e.lineno+3)):
                print(f'    {j+1:3d}| {lines[j].rstrip()}')

# ============================================================
# 9. DB migration
# ============================================================
print('\n=== DB Migration ===')
import sys
sys.path.insert(0, '.')
try:
    from core.database import engine
    from sqlalchemy import text, inspect

    insp = inspect(engine)
    columns = [c['name'] for c in insp.get_columns('session_states', schema='core')]

    new_cols = {
        'data_normalized': 'BOOLEAN DEFAULT FALSE',
        'normalization_mapping': 'TEXT',
        'normalized_data_summary': 'TEXT',
    }

    with engine.connect() as conn:
        for col_name, col_type in new_cols.items():
            if col_name not in columns:
                try:
                    conn.execute(text(f'ALTER TABLE core.session_states ADD COLUMN {col_name} {col_type}'))
                    conn.commit()
                    print(f'  ADDED: {col_name}')
                except Exception as e:
                    if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
                        print(f'  EXISTS: {col_name}')
                    else:
                        print(f'  ERROR: {col_name} - {e}')
            else:
                print(f'  EXISTS: {col_name}')
except Exception as e:
    print(f'  DB migration error: {e}')

print('\n=== All Done ===')