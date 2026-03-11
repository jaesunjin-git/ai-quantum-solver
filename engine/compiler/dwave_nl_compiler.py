# engine/compiler/dwave_nl_compiler.py
# ============================================================
# D-Wave NL (Nonlinear Model / Stride) Compiler v2.0
# ============================================================
#
# dwave.optimization.Model을 사용하여 비선형 모델을 구성합니다.
# expression_parser + struct_builder 공유로 CP-SAT/CQM과 동일한
# 제약 처리 파이프라인을 사용합니다.
#
# v2.0 변경사항:
# - var_map에 NL 심볼(arr[idx]) 직접 저장 (expression_parser 호환)
# - expression_parser._eval_expr 경유 제약 적용
# - struct_builder fallback 지원
# ============================================================

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

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

            # ── 1. 변수 생성 (NL 심볼 직접 저장) ──
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

                    if vtype == "binary":
                        var_map[vid] = self._create_binary_array(model, vid, combos)
                    elif vtype == "integer":
                        var_map[vid] = self._create_integer_array(model, vid, combos, var_def)
                    else:
                        var_map[vid] = self._create_continuous_array(model, vid, combos, var_def)
                    total_vars += n

            logger.info(f"NL: created {total_vars} variables")

            # ── 2. BuildContext 구성 (expression_parser 공유) ──
            from engine.compiler.struct_builder import BuildContext

            ctx = BuildContext(
                var_map=var_map,
                param_map=param_map,
                set_map=set_map,
                model=model,
            )

            # ── 3. 제약조건 (expression_parser + struct_builder 활용) ──
            constraint_defs = math_model.get("constraints", [])
            soft_penalties: list = []  # (violation_expr, weight) for soft→penalty

            for con_def in constraint_defs:
                cname = con_def.get("name", con_def.get("id", "unknown"))
                category = con_def.get("category", "hard")

                if category == "soft":
                    # NL soft constraint → penalty 변환 시도
                    penalty_result = self._apply_soft_as_penalty(
                        model, con_def, ctx, var_map, soft_penalties
                    )
                    if penalty_result > 0:
                        total_constraints += penalty_result
                        constraint_info.append({
                            "name": cname, "category": "soft",
                            "count": penalty_result, "method": "penalty",
                        })
                        logger.info(f"NL soft '{cname}': {penalty_result} penalty terms added")
                    else:
                        warnings.append(
                            f"Soft constraint '{cname}': could not convert to penalty, skipped"
                        )
                        constraint_info.append({
                            "name": cname, "category": "soft",
                            "count": 0, "method": "skipped",
                        })
                    continue

                count = 0
                method = "none"

                # 경로 1: structured (lhs/rhs) → struct_builder
                has_lhs = con_def.get("lhs") is not None
                has_rhs = con_def.get("rhs") is not None
                if has_lhs and has_rhs:
                    try:
                        count = self._apply_structured_constraint(model, con_def, ctx)
                        if count > 0:
                            method = "structured"
                    except Exception as e:
                        logger.debug(f"NL structured '{cname}' failed: {e}")

                # 경로 2: expression → expression_parser
                if count == 0:
                    expr_str = con_def.get("expression", "").strip()
                    for_each_str = con_def.get("for_each", "")
                    if expr_str and any(op in expr_str for op in ["<=", ">=", "=="]):
                        try:
                            count = self._apply_expr_constraint(
                                model, expr_str, for_each_str, ctx, var_map
                            )
                            if count > 0:
                                method = "expression_parser"
                        except Exception as e:
                            logger.debug(f"NL expression '{cname}' failed: {e}")

                total_constraints += count
                constraint_info.append({
                    "name": cname, "category": category,
                    "count": count, "method": method,
                })
                logger.info(f"NL constraint '{cname}': {count} instances applied ({method})")

            logger.info(
                f"NL: {total_constraints} total constraints applied, "
                f"{len(soft_penalties)} soft penalty terms"
            )

            # ── 4. 목적함수 (+ soft penalty 합산) ──
            obj_def = math_model.get("objective", {})
            obj_parsed = self._parse_objective_with_penalties(
                model, obj_def, var_map, ctx, soft_penalties
            )
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

    # ── 변수 생성 헬퍼 (NL 심볼 직접 반환) ──

    def _create_scalar_var(self, model, vid: str, vtype: str, var_def: Dict):
        """단일 스칼라 변수 생성 — NL 심볼(arr[0]) 반환"""
        if vtype == "binary":
            arr = model.binary(1)
            return arr[0]
        elif vtype == "integer":
            lb = int(var_def.get("lower_bound", 0))
            ub = int(var_def.get("upper_bound", 100))
            arr = model.integer(1, lower_bound=lb, upper_bound=ub)
            return arr[0]
        else:
            lb = var_def.get("lower_bound", 0)
            ub = var_def.get("upper_bound", 1e6)
            if hasattr(model, 'continuous'):
                arr = model.continuous(1, lower_bound=float(lb), upper_bound=float(ub))
            else:
                logger.warning(f"NL continuous '{vid}': not supported, using integer")
                arr = model.integer(1, lower_bound=int(lb), upper_bound=int(ub))
            return arr[0]

    def _create_binary_array(self, model, vid: str, combos: List) -> Dict:
        """인덱싱된 바이너리 변수 배열 — key → arr[idx] 심볼"""
        n = len(combos)
        arr = model.binary(n)
        result = {}
        for idx, combo in enumerate(combos):
            key = tuple(combo) if len(combo) > 1 else combo[0]
            result[key] = arr[idx]
        return result

    def _create_integer_array(self, model, vid: str, combos: List, var_def: Dict) -> Dict:
        """인덱싱된 정수 변수 배열 — key → arr[idx] 심볼"""
        n = len(combos)
        lb = int(var_def.get("lower_bound", 0))
        ub = int(var_def.get("upper_bound", 100))
        arr = model.integer(n, lower_bound=lb, upper_bound=ub)
        result = {}
        for idx, combo in enumerate(combos):
            key = tuple(combo) if len(combo) > 1 else combo[0]
            result[key] = arr[idx]
        return result

    def _create_continuous_array(self, model, vid: str, combos: List, var_def: Dict) -> Dict:
        """인덱싱된 연속 변수 배열 — key → arr[idx] 심볼"""
        n = len(combos)
        lb = var_def.get("lower_bound", 0)
        ub = var_def.get("upper_bound", 1e6)
        if hasattr(model, 'continuous'):
            arr = model.continuous(n, lower_bound=float(lb), upper_bound=float(ub))
        else:
            logger.warning(f"NL continuous '{vid}': not supported, using integer")
            arr = model.integer(n, lower_bound=int(lb), upper_bound=int(ub))
        result = {}
        for idx, combo in enumerate(combos):
            key = tuple(combo) if len(combo) > 1 else combo[0]
            result[key] = arr[idx]
        return result

    # ── 인덱스 조합 생성 ──

    def _get_index_combos(
        self, indices: List, set_map: Dict, math_model: Dict
    ) -> List[List]:
        """변수 인덱스 조합 생성"""
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
                for s in math_model.get("sets", []):
                    if s.get("id") == set_name or s.get("name") == set_name:
                        size = s.get("size", 0)
                        vals = list(range(size))
                        break
            sets_list.append(vals)

        if not sets_list:
            return []

        import itertools
        return [list(combo) for combo in itertools.product(*sets_list)]

    # ── 제약조건 적용 ──

    def _apply_structured_constraint(self, model, con_def: Dict, ctx) -> int:
        """structured (lhs/rhs/operator) → struct_builder → NL add_constraint"""
        from engine.compiler.struct_builder import build_constraint

        tuples = build_constraint(con_def, ctx)
        count = 0
        for lhs_val, op, rhs_val in tuples:
            try:
                if op == "==":
                    model.add_constraint(lhs_val == rhs_val)
                elif op == "<=":
                    model.add_constraint(lhs_val <= rhs_val)
                elif op == ">=":
                    model.add_constraint(lhs_val >= rhs_val)
                count += 1
            except Exception as e:
                logger.debug(f"NL add_constraint failed: {e}")
        return count

    def _precompute_sum_cache(
        self, expr_str: str, for_each_str: str, ctx, var_map: Dict
    ) -> Dict[str, Any]:
        """sum(coeff[i] * x[i,j] for i in I) 패턴을 미리 j별로 계산하여 캐시.
        NL 심볼 연산을 바인딩마다 반복하지 않고 한 번만 수행."""
        cache = {}
        # sum(body for var in SET) 패턴 추출
        sum_pattern = re.compile(
            r'sum\((.+?)\s+for\s+(\w+)\s+in\s+(\w+)\)'
        )
        matches = list(sum_pattern.finditer(expr_str))
        if not matches:
            return cache

        from engine.compiler.expression_parser import _parse_for_each, _eval_expr

        # for_each 바인딩의 변수명 (보통 "j")
        fe_match = re.match(r'(\w+)\s+in\s+(\w+)', for_each_str.strip())
        if not fe_match:
            return cache

        outer_var = fe_match.group(1)  # "j"
        outer_set_name = fe_match.group(2)  # "J"
        outer_vals = ctx.get_set(outer_set_name)
        if not outer_vals:
            return cache

        for m in matches:
            body_str = m.group(1)  # "trip_duration[i] * x[i,j]"
            iter_var = m.group(2)  # "i"
            set_name = m.group(3)  # "I"
            set_vals = ctx.get_set(set_name)
            if not set_vals:
                continue

            sum_key = m.group(0)  # full match as cache key
            logger.debug(f"NL sum cache: precomputing '{sum_key}' for {len(outer_vals)} x {len(set_vals)}")

            # j별로 sum 계산
            j_sums = {}
            for j_val in outer_vals:
                result = None
                for i_val in set_vals:
                    binding = {outer_var: str(j_val), iter_var: str(i_val)}
                    term = _eval_expr(body_str, binding, ctx, var_map, None)
                    if result is None:
                        result = term
                    else:
                        result = result + term
                j_sums[str(j_val)] = result if result is not None else 0
            cache[sum_key] = j_sums
            logger.info(f"NL sum cache: '{sum_key}' precomputed for {len(outer_vals)} bindings")

        return cache

    def _apply_expr_constraint(
        self, model, expr_str: str, for_each_str: str,
        ctx, var_map: Dict
    ) -> int:
        """expression 문자열 → expression_parser → NL add_constraint"""
        import time as _time
        from engine.compiler.expression_parser import _parse_for_each, _eval_expr

        # expression에서 operator 추출
        op = None
        lhs_str = rhs_str = None
        for op_try in ['<=', '>=', '==']:
            if op_try in expr_str:
                parts = expr_str.split(op_try, 1)
                lhs_str = parts[0].strip()
                rhs_str = parts[1].strip()
                op = op_try
                break

        if not op:
            return 0

        # ", for all ..." 제거 (expression 끝에 붙어 있는 경우)
        for suffix_pattern in [r',\s*for\s+all\s+.*$', r',\s*for\s+.*$']:
            rhs_str = re.sub(suffix_pattern, '', rhs_str)

        # ── Fast-path: sum 패턴 사전 계산 ──
        t0 = _time.time()
        full_expr = f"{lhs_str} {op} {rhs_str}"
        sum_cache = self._precompute_sum_cache(full_expr, for_each_str, ctx, var_map)
        if sum_cache:
            logger.debug(f"NL sum cache built in {_time.time() - t0:.1f}s")

        bindings = _parse_for_each(for_each_str, ctx)
        count = 0

        # for_each 변수명 추출 (캐시 lookup용)
        fe_var = None
        if sum_cache:
            fe_match = re.match(r'(\w+)\s+in\s+(\w+)', for_each_str.strip())
            if fe_match:
                fe_var = fe_match.group(1)

        for binding in bindings:
            try:
                if sum_cache and fe_var and fe_var in binding:
                    # sum 캐시에서 현재 바인딩의 값을 꺼내서 var_map에 임시 주입
                    bind_val = str(binding[fe_var])
                    temp_var_map = dict(var_map)
                    local_lhs = lhs_str
                    local_rhs = rhs_str
                    for idx, (sum_key, val_map) in enumerate(sum_cache.items()):
                        cached_val = val_map.get(bind_val)
                        if cached_val is not None:
                            # sum(...)을 _sc{idx}[0]으로 치환 (indexed var lookup 경로)
                            ph = f"_sc{idx}"
                            local_lhs = local_lhs.replace(sum_key, f"{ph}[0]")
                            local_rhs = local_rhs.replace(sum_key, f"{ph}[0]")
                            temp_var_map[ph] = {0: cached_val, "0": cached_val}

                    lhs_val = _eval_expr(local_lhs, binding, ctx, temp_var_map, None)
                    rhs_val = _eval_expr(local_rhs, binding, ctx, temp_var_map, None)
                else:
                    lhs_val = _eval_expr(lhs_str, binding, ctx, var_map, None)
                    rhs_val = _eval_expr(rhs_str, binding, ctx, var_map, None)

                # 숫자 → model.constant() 변환 (NL 비교 연산에 필요)
                if isinstance(lhs_val, (int, float)) and isinstance(rhs_val, (int, float)):
                    # 양쪽 다 상수면 제약 의미 없음
                    continue
                if isinstance(rhs_val, (int, float)):
                    rhs_val = model.constant(rhs_val)
                if isinstance(lhs_val, (int, float)):
                    lhs_val = model.constant(lhs_val)

                if op == "==":
                    model.add_constraint(lhs_val == rhs_val)
                elif op == "<=":
                    model.add_constraint(lhs_val <= rhs_val)
                elif op == ">=":
                    model.add_constraint(lhs_val >= rhs_val)
                count += 1
            except Exception as e:
                if count == 0:
                    logger.debug(f"NL expr constraint binding failed: {e}")

        return count

    # ── Soft constraint → penalty 변환 ──

    def _apply_soft_as_penalty(
        self, model, con_def: Dict, ctx, var_map: Dict,
        soft_penalties: list,
    ) -> int:
        """soft constraint를 penalty term으로 변환.

        <= 제약: violation = max(0, lhs - rhs) → penalty에 추가
        >= 제약: violation = max(0, rhs - lhs) → penalty에 추가
        == 제약: violation = abs(lhs - rhs) → penalty에 추가 (max(lhs-rhs,0) + max(rhs-lhs,0))

        Returns: penalty term 수 (0이면 실패)
        """
        from dwave.optimization import maximum as nl_maximum
        from engine.compiler.expression_parser import _parse_for_each, _eval_expr

        cname = con_def.get("name", con_def.get("id", "unknown"))
        expr_str = con_def.get("expression", "").strip()
        for_each_str = con_def.get("for_each", "")

        if not expr_str:
            return 0

        # operator 추출
        op = None
        lhs_str = rhs_str = None
        for op_try in ['<=', '>=', '==']:
            if op_try in expr_str:
                parts = expr_str.split(op_try, 1)
                lhs_str = parts[0].strip()
                rhs_str = parts[1].strip()
                op = op_try
                break
        if not op:
            return 0

        # ", for all ..." 제거
        for suffix_pattern in [r',\s*for\s+all\s+.*$', r',\s*for\s+.*$']:
            rhs_str = re.sub(suffix_pattern, '', rhs_str)

        # soft weight 로딩 (constraints.yaml에서)
        weight = self._get_soft_weight(cname)

        bindings = _parse_for_each(for_each_str, ctx)
        count = 0

        for binding in bindings:
            try:
                lhs_val = _eval_expr(lhs_str, binding, ctx, var_map, None)
                rhs_val = _eval_expr(rhs_str, binding, ctx, var_map, None)

                # 양쪽 다 상수면 스킵
                if isinstance(lhs_val, (int, float)) and isinstance(rhs_val, (int, float)):
                    continue

                if isinstance(rhs_val, (int, float)):
                    rhs_val = model.constant(rhs_val)
                if isinstance(lhs_val, (int, float)):
                    lhs_val = model.constant(lhs_val)

                # violation 계산: max(0, diff) 형태
                zero = model.constant(0)
                if op == "<=":
                    # lhs <= rhs → violation = max(0, lhs - rhs)
                    violation = nl_maximum(lhs_val - rhs_val, zero)
                elif op == ">=":
                    # lhs >= rhs → violation = max(0, rhs - lhs)
                    violation = nl_maximum(rhs_val - lhs_val, zero)
                elif op == "==":
                    # |lhs - rhs| ≈ max(lhs-rhs, 0) + max(rhs-lhs, 0)
                    violation = nl_maximum(lhs_val - rhs_val, zero) + nl_maximum(rhs_val - lhs_val, zero)
                else:
                    continue

                soft_penalties.append((violation, weight))
                count += 1
            except Exception as e:
                if count == 0:
                    logger.debug(f"NL soft penalty '{cname}' binding failed: {e}")

        return count

    def _get_soft_weight(self, constraint_name: str) -> float:
        """constraints.yaml에서 soft constraint weight 로딩"""
        import os
        try:
            import yaml
        except ImportError:
            return 1.0
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        domains_dir = os.path.join(base, "knowledge", "domains")
        if not os.path.isdir(domains_dir):
            return 1.0
        for dname in os.listdir(domains_dir):
            cpath = os.path.join(domains_dir, dname, "constraints.yaml")
            if not os.path.isfile(cpath):
                continue
            try:
                with open(cpath, "r", encoding="utf-8") as f:
                    cdata = yaml.safe_load(f) or {}
                constraints = cdata.get("constraints") or {}
                if constraint_name in constraints:
                    cdef = constraints[constraint_name]
                    if isinstance(cdef, dict):
                        return float(cdef.get("weight", 1.0))
            except Exception:
                continue
        return 1.0

    # ── 목적함수 (+ soft penalty 합산) ──

    def _parse_objective_with_penalties(
        self, model, obj_def: Dict, var_map: Dict, ctx,
        soft_penalties: list,
    ) -> bool:
        """목적함수 파싱 + soft penalty 합산"""
        if not obj_def and not soft_penalties:
            return False

        direction = "minimize"
        if obj_def:
            direction = obj_def.get("direction", obj_def.get("type", "minimize")).lower()
            if direction not in ("minimize", "maximize"):
                direction = "minimize"

        # 기본 목적함수 파싱
        base_obj = self._parse_base_objective(model, obj_def, var_map, ctx)

        # soft penalty 합산
        penalty_total = None
        for violation_expr, weight in soft_penalties:
            term = violation_expr * model.constant(weight) if weight != 1.0 else violation_expr
            if penalty_total is None:
                penalty_total = term
            else:
                penalty_total = penalty_total + term

        if penalty_total is not None:
            logger.info(f"NL: {len(soft_penalties)} soft penalty terms added to objective")

        # 최종 목적함수 조합
        if base_obj is not None and penalty_total is not None:
            if direction == "maximize":
                model.minimize(-base_obj + penalty_total)
            else:
                model.minimize(base_obj + penalty_total)
            logger.info(f"NL Objective set: {direction} + soft penalties")
            return True
        elif base_obj is not None:
            if direction == "maximize":
                model.minimize(-base_obj)
            else:
                model.minimize(base_obj)
            logger.info(f"NL Objective set: {direction} (no penalties)")
            return True
        elif penalty_total is not None:
            model.minimize(penalty_total)
            logger.info(f"NL Objective set: minimize soft penalties only")
            return True

        return False

    def _parse_base_objective(self, model, obj_def: Dict, var_map: Dict, ctx):
        """기본 목적함수 파싱 — struct_builder → expression_parser fallback.
        Returns NL symbol or None."""
        if not obj_def:
            return None

        # 경로 1: struct_builder
        try:
            from engine.compiler.struct_builder import build_objective
            obj_type, obj_val = build_objective(obj_def, ctx)
            if obj_val is not None and not isinstance(obj_val, (int, float)):
                logger.info(f"NL base objective parsed (structured)")
                return obj_val
        except Exception as e:
            logger.debug(f"NL structured objective failed: {e}")

        # 경로 2: expression_parser
        expression = obj_def.get("expression", "")
        if expression:
            try:
                from engine.compiler.expression_parser import _eval_expr
                obj_val = _eval_expr(expression, {}, ctx, var_map, None)
                if obj_val is not None and not isinstance(obj_val, (int, float)):
                    logger.info(f"NL base objective parsed (expression)")
                    return obj_val
            except Exception as e:
                logger.debug(f"NL expression objective failed: {e}")

        # 경로 3: sum fallback
        terms = []
        for v in var_map.values():
            if isinstance(v, dict):
                terms.extend(v.values())
            else:
                terms.append(v)
        if terms:
            result = terms[0]
            for t in terms[1:]:
                result = result + t
            logger.info(f"NL base objective: sum fallback")
            return result

        return None

    # _set_sum_objective removed — merged into _parse_base_objective
