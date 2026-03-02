"""
engine/gates/gate2_model_validate.py
────────────────────────────────────
Gate 2: 수학 모델 유효성 검증

LLM이 생성한 수학 모델 JSON을 실제 데이터와 대조하여 검증한다.
LLM 호출 없이 규칙 기반으로 동작한다.

검증 항목:
  1. Set 바인딩 — source_file/source_column이 실제 데이터에 존재하는가
  2. Parameter 바인딩 — 모델이 참조하는 파라미터가 데이터에 매핑 가능한가
  3. 제약 구조 — operator가 비교 연산자인가, 변수/파라미터가 정의되어 있는가
  4. 변수 수 재계산 — 실제 set 크기 기반으로 정확한 변수 수 산출
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

VALID_OPERATORS = {"==", "<=", ">=", "<", ">", "!="}


def run(math_model: Dict,
        data_profile: Optional[Dict] = None,
        dataframes: Optional[Dict] = None) -> Dict[str, Any]:
    """
    메인 검증 함수.

    Args:
        math_model: LLM이 생성한 수학 모델 JSON
        data_profile: Gate 1이 생성한 프로파일 (옵션)
        dataframes: DataBinder._dataframes (옵션, set 크기 계산용)

    Returns:
        {
            "valid": bool,
            "errors": [...],        # 치명적 오류 (모델 재생성 필요)
            "warnings": [...],      # 경고 (진행 가능하지만 주의)
            "corrections": {...},   # 자동 교정된 항목
            "actual_variable_count": int,
            "actual_set_sizes": {set_id: int},
        }
    """
    errors: List[str] = []
    warnings: List[str] = []
    corrections: Dict[str, Any] = {}
    set_sizes: Dict[str, int] = {}

    sets = math_model.get("sets", [])
    variables = math_model.get("variables", [])
    constraints = math_model.get("constraints", [])
    parameters = math_model.get("parameters", [])
    metadata = math_model.get("metadata", {})

    # ── 1. Set 검증 ──
    set_ids = set()
    for s in sets:
        sid = s.get("id", "")
        set_ids.add(sid)
        size = _validate_set(s, data_profile, dataframes)
        set_sizes[sid] = size

        if size == 0:
            errors.append(
                f"Set '{sid}': 크기를 결정할 수 없음 "
                f"(source_file={s.get('source_file')}, "
                f"source_column={s.get('source_column')}, "
                f"source_type={s.get('source_type')})"
            )
        elif size < 0:
            errors.append(f"Set '{sid}': 유효하지 않은 크기 ({size})")

    # ── 2. Variable 검증 ──
    var_ids = set()
    actual_var_count = 0
    for v in variables:
        vid = v.get("id", "")
        var_ids.add(vid)
        indices = v.get("indices", [])

        # 인덱스가 정의된 set을 참조하는지
        for idx in indices:
            if idx not in set_ids:
                errors.append(f"Variable '{vid}': 인덱스 '{idx}'가 정의된 set에 없음")

        # 변수 수 계산
        if not indices:
            actual_var_count += 1
        else:
            product = 1
            for idx in indices:
                product *= set_sizes.get(idx, 0)
            if product > 0:
                actual_var_count += product
            else:
                warnings.append(f"Variable '{vid}': set 크기 미확인으로 변수 수 계산 불가")

    # LLM 추정치와 비교
    llm_estimate = metadata.get("estimated_variable_count", 0)
    if llm_estimate > 0 and actual_var_count > 0:
        ratio = abs(actual_var_count - llm_estimate) / max(llm_estimate, 1)
        if ratio > 0.5:
            corrections["estimated_variable_count"] = {
                "old": llm_estimate,
                "new": actual_var_count,
                "reason": f"실제 set 크기 기반 재계산 (차이 {ratio:.0%})"
            }
            # 모델 내 metadata도 교정
            metadata["estimated_variable_count"] = actual_var_count
            warnings.append(
                f"변수 수 교정: LLM 추정 {llm_estimate} → 실제 {actual_var_count}"
            )

    # ── 3. Parameter 검증 ──
    param_names = {p.get("name", p.get("id", "")) for p in parameters}
    if data_profile:
        available_columns = set()
        for sheet_info in data_profile.get("files", {}).values():
            for col_name in sheet_info.get("columns", {}):
                available_columns.add(col_name)

        for p in parameters:
            pname = p.get("name", p.get("id", ""))
            source_file = p.get("source_file", "")
            source_column = p.get("source_column", "")

            if source_column and source_column not in available_columns:
                # 유사 이름 매칭 시도
                matched = _fuzzy_match_column(source_column, available_columns)
                if matched:
                    warnings.append(
                        f"Parameter '{pname}': '{source_column}' → '{matched}'로 유사 매칭"
                    )
                else:
                    warnings.append(
                        f"Parameter '{pname}': source_column '{source_column}'이 "
                        f"데이터에 없음 (바인딩 시 None 가능성)"
                    )

    # 비정형 시트를 source로 참조하는지 체크
    if data_profile:
        non_tabular = set(data_profile.get("summary", {}).get("non_tabular_sheets", []))
        for p in parameters:
            source_file = p.get("source_file", "")
            for nt_sheet in non_tabular:
                if source_file and source_file in nt_sheet:
                    warnings.append(
                        f"Parameter '{p.get('name', '')}': "
                        f"비정형 블록 시트 '{nt_sheet}'를 참조 — 파싱 오류 가능성"
                    )

    # ── 4. Constraint 검증 ──
    for c in constraints:
        cname = c.get("name", "unknown")
        op = c.get("operator", "")

        # operator 검증
        if op not in VALID_OPERATORS:
            errors.append(
                f"Constraint '{cname}': operator '{op}'는 비교 연산자가 아님 "
                f"(허용: {VALID_OPERATORS})"
            )

        # lhs/rhs에서 참조하는 변수/파라미터 검증
        lhs = c.get("lhs", {})
        rhs = c.get("rhs", {})
        for side_name, side in [("lhs", lhs), ("rhs", rhs)]:
            _check_node_refs(side, cname, side_name, var_ids, param_names, warnings)

        # for_each에서 참조하는 set 검증
        for_each = c.get("for_each", "")
        if for_each:
            referenced_sets = re.findall(r"in\s+(\w+)", for_each)
            for rs in referenced_sets:
                if rs not in set_ids:
                    errors.append(
                        f"Constraint '{cname}': for_each에서 '{rs}' set을 참조하지만 정의되지 않음"
                    )

    # ── 5. 결과 요약 ──
    is_valid = len(errors) == 0

    result = {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "corrections": corrections,
        "actual_variable_count": actual_var_count,
        "actual_set_sizes": set_sizes,
    }

    logger.info(
        f"Gate2: valid={is_valid}, errors={len(errors)}, "
        f"warnings={len(warnings)}, corrections={len(corrections)}, "
        f"actual_vars={actual_var_count}"
    )

    return result


def _validate_set(set_def: Dict,
                  data_profile: Optional[Dict],
                  dataframes: Optional[Dict]) -> int:
    """Set 크기를 결정"""
    # 1. source_type: "range"
    if set_def.get("source_type") == "range":
        size = set_def.get("size", 0)
        if size > 0:
            return size

    # 2. elements가 있으면
    elements = set_def.get("elements", [])
    if elements:
        return len(elements)

    # 3. source_type: "explicit" + values
    values = set_def.get("values", [])
    if values:
        return len(values)

    # 4. source_file + source_column — dataframes에서 직접 계산
    source_file = set_def.get("source_file", "")
    source_col = set_def.get("source_column", "")
    if source_file and source_col and dataframes:
        for key, df in dataframes.items():
            if source_file in key or key.startswith(source_file):
                if source_col in df.columns:
                    return int(df[source_col].dropna().nunique())
                # 대소문자 무시 매칭
                for col in df.columns:
                    if col.strip().lower() == source_col.strip().lower():
                        return int(df[col].dropna().nunique())

    # 5. data_profile에서 추정
    if data_profile and source_file and source_col:
        for sheet_key, sheet_info in data_profile.get("files", {}).items():
            if source_file in sheet_key:
                col_info = sheet_info.get("columns", {}).get(source_col, {})
                if col_info:
                    return col_info.get("unique_count", 0)

    return 0


def _check_node_refs(node: Any, cname: str, side: str,
                     var_ids: set, param_names: set,
                     warnings: List[str]):
    """노드에서 참조하는 변수/파라미터가 정의되어 있는지 재귀 검사"""
    if not isinstance(node, dict):
        return

    # var 참조
    if "var" in node:
        var_ref = node["var"] if isinstance(node["var"], str) else node["var"].get("name", "")
        if var_ref and var_ref not in var_ids:
            warnings.append(
                f"Constraint '{cname}' {side}: variable '{var_ref}' 미정의"
            )

    # param 참조
    if "param" in node:
        param_ref = node["param"] if isinstance(node["param"], str) else node["param"].get("name", "")
        if param_ref and param_ref not in param_names:
            warnings.append(
                f"Constraint '{cname}' {side}: parameter '{param_ref}' 미정의"
            )

    # sum 노드 내부
    if "sum" in node:
        sum_node = node["sum"]
        if isinstance(sum_node, dict):
            if "coeff" in sum_node and sum_node["coeff"]:
                _check_node_refs(sum_node["coeff"], cname, side, var_ids, param_names, warnings)

    # subtract, add, multiply 노드
    for op_key in ["subtract", "add", "multiply"]:
        if op_key in node:
            sub = node[op_key]
            if isinstance(sub, list):
                for item in sub:
                    _check_node_refs(item, cname, side, var_ids, param_names, warnings)
            elif isinstance(sub, dict):
                _check_node_refs(sub, cname, side, var_ids, param_names, warnings)


def _fuzzy_match_column(target: str, available: set) -> Optional[str]:
    """유사 컬럼명 매칭"""
    target_low = target.strip().lower()
    for col in available:
        if col.strip().lower() == target_low:
            return col
    # 부분 매칭
    for col in available:
        if target_low in col.strip().lower() or col.strip().lower() in target_low:
            return col
    return None


def to_text_summary(result: Dict) -> str:
    """Gate 2 결과를 읽기 쉬운 텍스트로 변환"""
    lines = [f"[모델 검증 결과] valid={result['valid']}"]
    lines.append(f"실제 변수 수: {result['actual_variable_count']}")
    lines.append(f"Set 크기: {result['actual_set_sizes']}")

    if result["errors"]:
        lines.append(f"\n❌ 오류 ({len(result['errors'])}개):")
        for e in result["errors"]:
            lines.append(f"  - {e}")

    if result["warnings"]:
        lines.append(f"\n⚠ 경고 ({len(result['warnings'])}개):")
        for w in result["warnings"]:
            lines.append(f"  - {w}")

    if result["corrections"]:
        lines.append(f"\n🔧 자동 교정 ({len(result['corrections'])}개):")
        for key, val in result["corrections"].items():
            lines.append(f"  - {key}: {val['old']} → {val['new']} ({val['reason']})")

    return "\n".join(lines)
