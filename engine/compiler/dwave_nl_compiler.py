# engine/compiler/dwave_nl_compiler.py
# ============================================================
# D-Wave NL (Nonlinear Model / Stride) Compiler
# ============================================================
#
# dwave.optimization.Model을 사용하여 비선형 모델을 구성합니다.
# 순열, 부분집합 등 네이티브 변수 타입 지원.
# 최대 200만 변수/제약조건 지원 (CQM의 20배).
#
# 주요 특성:
# - 순열(List) 변수: 근무조 할당 등 순열 문제에 최적
# - 부분집합(SetVariable): 선택 문제에 적합
# - 비선형 목적함수 지원
# - 연속 변수 + 선형 상호작용 지원 (2025~ 추가)
# ============================================================

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from .base import BaseCompiler, CompileResult

logger = logging.getLogger(__name__)


class DWaveNLCompiler(BaseCompiler):
    """수학 모델 IR을 D-Wave NL(Nonlinear) 모델로 변환"""

    def compile(self, math_model: Dict, bound_data: Any, **kwargs) -> CompileResult:
        try:
            from dwave.optimization import Model as NLModel
        except ImportError:
            return CompileResult(
                success=False,
                error="dwave-optimization not installed. Run: pip install dwave-optimization",
            )

        try:
            model = NLModel()
            var_map: Dict[str, Any] = {}
            total_vars = 0
            total_constraints = 0
            warnings: List[str] = []
            constraint_info: List[Dict] = []

            # ── bound_data에서 세트/파라미터 추출 ──
            if isinstance(bound_data, dict):
                set_map = bound_data.get("sets", {})
                param_map = bound_data.get("parameters", {})
            else:
                set_map = getattr(bound_data, "set_map", {})
                param_map = getattr(bound_data, "param_map", {})

            # ── 1. 변수 생성 ──
            for var_def in math_model.get("variables", []):
                vid = var_def.get("id", "")
                vtype = var_def.get("type", "binary").lower()
                indices = var_def.get("indices", [])

                if not indices:
                    var_map[vid] = self._create_scalar_var(model, vid, vtype, var_def)
                    total_vars += 1
                else:
                    combos = self._get_index_combos(indices, set_map, math_model)
                    n = len(combos)
                    if n == 0:
                        warnings.append(f"Variable {vid}: no index combinations generated")
                        continue

                    # NL 모델에서는 indexed 변수를 List 또는 Binary 배열로 생성
                    if vtype == "binary":
                        # Binary 배열: 각 조합에 대한 0/1 결정
                        var_map[vid] = self._create_binary_array(model, vid, combos)
                        total_vars += n
                    elif vtype == "integer":
                        var_map[vid] = self._create_integer_array(
                            model, vid, combos, var_def
                        )
                        total_vars += n
                    else:
                        # 연속 변수 등
                        var_map[vid] = self._create_continuous_array(
                            model, vid, combos, var_def
                        )
                        total_vars += n

            logger.info(f"NL: created {total_vars} variables")

            # ── 2. 제약조건 ──
            constraint_defs = math_model.get("constraints", [])
            for con_def in constraint_defs:
                cname = con_def.get("name", con_def.get("id", "unknown"))
                category = con_def.get("category", "hard")

                if category == "soft":
                    # NL 모델에서 soft constraint는 목적함수 페널티로 처리
                    warnings.append(
                        f"Soft constraint '{cname}': NL model does not natively "
                        f"support soft constraints, will be added as penalty"
                    )
                    constraint_info.append({
                        "name": cname, "category": "soft",
                        "count": 0, "method": "penalty_deferred",
                    })
                    continue

                try:
                    count = self._apply_constraint(model, con_def, var_map, set_map, param_map)
                    total_constraints += count
                    constraint_info.append({
                        "name": cname, "category": category,
                        "count": count, "method": "nl_native",
                    })
                    logger.info(f"NL constraint '{cname}': {count} instances applied")
                except Exception as e:
                    warnings.append(f"Constraint '{cname}': {e}")
                    constraint_info.append({
                        "name": cname, "category": category,
                        "count": 0, "method": "failed",
                    })
                    logger.warning(f"NL constraint '{cname}' failed: {e}")

            logger.info(f"NL: {total_constraints} constraints applied")

            # ── 3. 목적함수 ──
            obj_def = math_model.get("objective", {})
            obj_parsed = self._parse_objective(model, obj_def, var_map, set_map, param_map)
            if not obj_parsed:
                warnings.append("Objective: could not parse for NL model")

            return CompileResult(
                success=True,
                solver_model=model,
                solver_type="nl",
                variable_count=total_vars,
                constraint_count=total_constraints,
                variable_map=var_map,
                warnings=warnings,
                metadata={
                    "model_type": "NL/Stride",
                    "engine": "dwave_optimization",
                    "constraint_info": constraint_info,
                },
            )

        except Exception as e:
            logger.error(f"NL compilation failed: {e}", exc_info=True)
            return CompileResult(
                success=False,
                error=f"NL compilation error: {str(e)}",
            )

    # ── 변수 생성 헬퍼 ──

    def _create_scalar_var(self, model, vid: str, vtype: str, var_def: Dict):
        """단일 스칼라 변수 생성"""
        if vtype == "binary":
            return model.binary(1)
        elif vtype == "integer":
            lb = int(var_def.get("lower_bound", 0))
            ub = int(var_def.get("upper_bound", 100))
            return model.integer(1, lower_bound=lb, upper_bound=ub)
        else:
            # continuous — dwave-optimization 버전에 따라 지원 여부 다름
            lb = var_def.get("lower_bound", 0)
            ub = var_def.get("upper_bound", 1e6)
            if hasattr(model, 'continuous'):
                return model.continuous(1, lower_bound=float(lb), upper_bound=float(ub))
            logger.warning(f"NL continuous variable '{vid}': not supported, using integer approximation")
            return model.integer(1, lower_bound=int(lb), upper_bound=int(ub))

    def _create_binary_array(self, model, vid: str, combos: List) -> Dict:
        """인덱싱된 바이너리 변수 배열 생성"""
        n = len(combos)
        arr = model.binary(n)
        result = {}
        for idx, combo in enumerate(combos):
            key = tuple(combo) if len(combo) > 1 else combo[0]
            result[key] = (arr, idx)
        return result

    def _create_integer_array(self, model, vid: str, combos: List, var_def: Dict) -> Dict:
        """인덱싱된 정수 변수 배열 생성"""
        n = len(combos)
        lb = int(var_def.get("lower_bound", 0))
        ub = int(var_def.get("upper_bound", 100))
        arr = model.integer(n, lower_bound=lb, upper_bound=ub)
        result = {}
        for idx, combo in enumerate(combos):
            key = tuple(combo) if len(combo) > 1 else combo[0]
            result[key] = (arr, idx)
        return result

    def _create_continuous_array(self, model, vid: str, combos: List, var_def: Dict) -> Dict:
        """인덱싱된 연속 변수 배열 생성"""
        n = len(combos)
        lb = var_def.get("lower_bound", 0)
        ub = var_def.get("upper_bound", 1e6)
        if hasattr(model, 'continuous'):
            arr = model.continuous(n, lower_bound=float(lb), upper_bound=float(ub))
        else:
            logger.warning(f"NL continuous array '{vid}': not supported, using integer approximation")
            arr = model.integer(n, lower_bound=int(lb), upper_bound=int(ub))
        result = {}
        for idx, combo in enumerate(combos):
            key = tuple(combo) if len(combo) > 1 else combo[0]
            result[key] = (arr, idx)
        return result

    # ── 인덱스 조합 생성 ──

    def _get_index_combos(
        self, indices: List, set_map: Dict, math_model: Dict
    ) -> List[List]:
        """변수 인덱스 조합 생성 (CQM 컴파일러와 동일 로직)"""
        sets_list = []
        for idx_def in indices:
            if isinstance(idx_def, str):
                set_name = idx_def
            elif isinstance(idx_def, dict):
                set_name = idx_def.get("set", idx_def.get("name", ""))
            else:
                continue
            vals = set_map.get(set_name, [])
            if not vals:
                # sets 정의에서 찾기
                for s in math_model.get("sets", []):
                    if s.get("id") == set_name or s.get("name") == set_name:
                        size = s.get("size", 0)
                        vals = list(range(size))
                        break
            sets_list.append(vals)

        if not sets_list:
            return []

        # 카르테시안 곱
        import itertools
        return [list(combo) for combo in itertools.product(*sets_list)]

    # ── 제약조건 적용 ──

    def _apply_constraint(
        self, model, con_def: Dict, var_map: Dict, set_map: Dict, param_map: Dict
    ) -> int:
        """
        NL 모델에 제약조건을 적용한다.
        NL의 제약 추가는 model.add_constraint() 대신
        불등식/등식을 model.constant() + 비교 연산으로 추가.

        현재 지원 패턴:
        - sum == constant (할당 제약)
        - sum <= constant (용량 제약)
        - sum >= constant (커버리지 제약)
        """
        expression = con_def.get("expression", "").strip()
        operator = con_def.get("operator", "==")
        for_each = con_def.get("for_each", "")
        count = 0

        # expression 기반 처리
        if expression:
            count = self._apply_expression_constraint(
                model, expression, operator, for_each,
                var_map, set_map, param_map
            )

        # structured (lhs/rhs) 처리
        elif con_def.get("lhs") is not None and con_def.get("rhs") is not None:
            count = self._apply_structured_constraint(
                model, con_def, var_map, set_map, param_map
            )

        return count

    def _apply_expression_constraint(
        self, model, expression: str, operator: str, for_each: str,
        var_map: Dict, set_map: Dict, param_map: Dict
    ) -> int:
        """expression 문자열 기반 제약 적용 (기본 패턴)"""
        import re

        # sum(x[i,j] for i in I) == 1 for j in J 패턴
        sum_match = re.match(
            r'sum\((\w+)\[([^\]]+)\]\s+for\s+(\w+)\s+in\s+(\w+)\)\s*(==|<=|>=)\s*(\w+)',
            expression
        )
        if not sum_match:
            return 0

        var_id = sum_match.group(1)
        idx_expr = sum_match.group(2)
        iter_var = sum_match.group(3)
        iter_set = sum_match.group(4)
        op = sum_match.group(5)
        rhs_str = sum_match.group(6)

        # RHS 값 파싱
        try:
            rhs_val = int(rhs_str)
        except ValueError:
            rhs_val = param_map.get(rhs_str, 1)
            if not isinstance(rhs_val, (int, float)):
                rhs_val = 1

        var_data = var_map.get(var_id)
        if var_data is None or not isinstance(var_data, dict):
            return 0

        # for_each 파싱
        outer_set_vals = [None]  # 기본: 외부 루프 없음
        if for_each:
            fe_match = re.match(r'(\w+)\s+in\s+(\w+)', for_each)
            if fe_match:
                outer_var = fe_match.group(1)
                outer_set = fe_match.group(2)
                outer_set_vals = set_map.get(outer_set, [])

        count = 0
        iter_vals = set_map.get(iter_set, [])

        for outer_val in outer_set_vals:
            # 해당 외부 값에 대한 합계 구성
            terms = []
            for iv in iter_vals:
                if outer_val is not None:
                    key = (iv, outer_val) if iter_var < for_each.split()[0] else (outer_val, iv)
                else:
                    key = iv

                entry = var_data.get(key)
                if entry is not None:
                    arr, idx = entry
                    terms.append(arr[idx])

            if not terms:
                continue

            # 합계 구성
            lhs = terms[0]
            for t in terms[1:]:
                lhs = lhs + t

            rhs_const = model.constant(rhs_val)

            # 제약 추가
            if op == "==":
                model.add_constraint(lhs == rhs_const)
            elif op == "<=":
                model.add_constraint(lhs <= rhs_const)
            elif op == ">=":
                model.add_constraint(lhs >= rhs_const)

            count += 1

        return count

    def _apply_structured_constraint(
        self, model, con_def: Dict, var_map: Dict, set_map: Dict, param_map: Dict
    ) -> int:
        """structured (lhs/rhs/operator) 기반 제약 적용"""
        from engine.compiler.struct_builder import BuildContext, build_constraint

        ctx = BuildContext(
            var_map=var_map,
            param_map=param_map,
            set_map=set_map,
            model=model,
        )

        try:
            results = build_constraint(con_def, ctx)
            count = 0
            for lhs_val, op, rhs_val in results:
                if op == "==":
                    model.add_constraint(lhs_val == rhs_val)
                elif op == "<=":
                    model.add_constraint(lhs_val <= rhs_val)
                elif op == ">=":
                    model.add_constraint(lhs_val >= rhs_val)
                count += 1
            return count
        except Exception as e:
            logger.warning(f"NL structured constraint failed: {e}")
            return 0

    # ── 목적함수 ──

    def _parse_objective(
        self, model, obj_def: Dict, var_map: Dict, set_map: Dict, param_map: Dict
    ) -> bool:
        """목적함수 파싱 및 설정"""
        if not obj_def:
            return False

        direction = obj_def.get("direction", "minimize").lower()
        expression = obj_def.get("expression", "")

        if not expression:
            return False

        try:
            # 간단한 sum 패턴: sum(c[i,j] * x[i,j] for i in I for j in J)
            # 복잡한 표현식은 struct_builder 활용
            obj_expr = self._build_objective_expression(
                model, expression, var_map, set_map, param_map
            )
            if obj_expr is not None:
                if direction == "maximize":
                    model.minimize(-obj_expr)  # NL은 minimize만 지원
                else:
                    model.minimize(obj_expr)
                return True
        except Exception as e:
            logger.warning(f"NL objective parsing failed: {e}")

        return False

    def _build_objective_expression(
        self, model, expression: str, var_map: Dict, set_map: Dict, param_map: Dict
    ):
        """목적함수 표현식 구성"""
        import re

        # sum(x[i,j] for i in I for j in J) 패턴
        sum_match = re.match(
            r'sum\((\w+)\[([^\]]+)\]\s+for\s+(.+)\)',
            expression
        )
        if sum_match:
            var_id = sum_match.group(1)
            var_data = var_map.get(var_id)
            if var_data and isinstance(var_data, dict):
                terms = []
                for key, entry in var_data.items():
                    if isinstance(entry, tuple):
                        arr, idx = entry
                        terms.append(arr[idx])
                if terms:
                    result = terms[0]
                    for t in terms[1:]:
                        result = result + t
                    return result

        # 단일 변수 참조
        for vid, var_data in var_map.items():
            if vid in expression and isinstance(var_data, dict):
                terms = []
                for key, entry in var_data.items():
                    if isinstance(entry, tuple):
                        arr, idx = entry
                        terms.append(arr[idx])
                if terms:
                    result = terms[0]
                    for t in terms[1:]:
                        result = result + t
                    return result

        return None
