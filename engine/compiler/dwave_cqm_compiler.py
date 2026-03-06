# engine/compiler/dwave_cqm_compiler.py
# ============================================================
# D-Wave CQM Compiler v2.0
# struct_builder 연동 - OR-Tools와 동일한 구조화된 제약 처리
# ============================================================

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

from .base import BaseCompiler, CompileResult, DataBinder

logger = logging.getLogger(__name__)


class DWaveCQMCompiler(BaseCompiler):
    """수학 모델 IR을 D-Wave CQM으로 변환 (struct_builder 활용)"""

    def compile(self, math_model: Dict, bound_data: Any, **kwargs) -> CompileResult:
        try:
            import dimod

            cqm = dimod.ConstrainedQuadraticModel()
            var_map: Dict[str, Any] = {}
            total_vars = 0
            total_constraints = 0
            warnings = []

            # ── bound_data에서 세트/파라미터 추출 ──
            # bound_data = {"sets": {I: [...], ...}, "parameters": {name: val, ...}, "set_sizes": {...}}
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
                    var_map[vid] = self._create_var(dimod, vid, vtype, var_def)
                    total_vars += 1
                else:
                    combos = self._get_index_combos(indices, set_map, math_model)
                    var_map[vid] = {}
                    for combo in combos:
                        key = tuple(combo)
                        name = f"{vid}_{'_'.join(str(c) for c in combo)}"
                        var_map[vid][key] = self._create_var(dimod, name, vtype, var_def)
                        total_vars += 1

            logger.info(f"CQM: created {total_vars} variables")

            # ── 2. BuildContext 구성 (struct_builder 공유) ──
            from engine.compiler.struct_builder import BuildContext

            ctx = BuildContext(
                var_map=var_map,
                param_map=param_map,
                set_map=set_map,
            )

            # ── 3. 제약조건 (struct_builder 활용) ──
            from engine.compiler.struct_builder import build_constraint

            for con_def in math_model.get("constraints", []):
                cid = con_def.get("id") or con_def.get("name", "unknown")
                category = con_def.get("category", "hard")
                weight = con_def.get("weight")
                op = con_def.get("operator", "==")

                has_lhs = con_def.get("lhs") is not None
                has_rhs = con_def.get("rhs") is not None

                if has_lhs and has_rhs:
                    # overlap_pairs가 있으면 고속 경로 사용
                    if "_overlap_pairs" in con_def and con_def["_overlap_pairs"]:
                        fast_count = self._fast_add_overlap_constraints(cqm, var_map, con_def, set_map, param_map)
                        if fast_count > 0:
                            total_constraints += fast_count
                            logger.info(f"Constraint '{cid}': {fast_count} instances (fast-path)")
                            continue

                    # 구조화된 제약 -> build_constraint로 dimod 표현식 생성
                    try:
                        tuples = build_constraint(con_def, ctx)
                        added = 0
                        for idx, (lhs_val, op_str, rhs_val) in enumerate(tuples):
                            label = f"{cid}_{idx}"
                            try:
                                self._add_cqm_constraint(
                                    cqm, lhs_val, op_str, rhs_val,
                                    label, category, weight
                                )
                                added += 1
                            except Exception as e:
                                if added == 0 and idx < 3:
                                    logger.warning(f"CQM constraint {label} failed: {e}")

                        if added > 0:
                            total_constraints += added
                            logger.info(f"Constraint '{cid}': {added} instances (structured)")
                        else:
                            warnings.append(f"Constraint {cid}: 0 instances from structured parse")

                    except Exception as e:
                        logger.warning(f"Constraint '{cid}' structured parse failed: {e}")
                        warnings.append(f"Constraint {cid}: structured parse error")
                else:
                    # 레거시 expression 파싱 (폴백)
                    count = self._parse_constraint_legacy(cqm, var_map, con_def, set_map, param_map)
                    if count > 0:
                        total_constraints += count
                        logger.info(f"Constraint '{cid}': {count} instances (legacy)")
                    else:
                        warnings.append(f"Constraint {cid}: could not parse")

            logger.info(f"CQM: created {total_constraints} constraints")

            # ── 4. 목적함수 ──
            obj = math_model.get("objective", {})
            obj_parsed = self._parse_objective(cqm, var_map, obj, ctx)
            if not obj_parsed:
                warnings.append("Objective: could not parse, using default minimize sum")
                self._set_default_objective(cqm, var_map)

            return CompileResult(
                success=True,
                solver_model=cqm,
                solver_type="cqm",
                variable_count=total_vars,
                constraint_count=total_constraints,
                variable_map=var_map,
                warnings=warnings,
                metadata={"model_type": "CQM", "engine": "D-Wave"},
            )

        except ImportError as e:
            return CompileResult(
                success=False,
                error=f"dimod package not installed: {e}. Run: pip install dwave-ocean-sdk"
            )
        except Exception as e:
            logger.error(f"CQM compilation failed: {e}", exc_info=True)
            return CompileResult(success=False, error=str(e))

    # ── 변수 생성 ──

    def _create_var(self, dimod, name: str, vtype: str, var_def: Dict):
        if vtype == "binary":
            return dimod.Binary(name)
        elif vtype == "integer":
            lb = int(var_def.get("lower_bound") or 0)
            ub = int(var_def.get("upper_bound") or 1000000)
            return dimod.Integer(name, lower_bound=lb, upper_bound=ub)
        else:
            lb = float(var_def.get("lower_bound") or 0)
            ub = float(var_def.get("upper_bound") or 1e7)
            return dimod.Real(name, lower_bound=lb, upper_bound=ub)

    def _get_index_combos(self, indices: List[str], set_map: Dict, math_model: Dict) -> List[List]:
        """인덱스 조합 계산"""
        sets_in_order = []
        for idx_name in indices:
            vals = set_map.get(idx_name, [])
            if not vals:
                # 모델 정의에서 set 크기 조회
                for s_def in math_model.get("sets", []):
                    if s_def.get("id") == idx_name:
                        size = s_def.get("size", 0)
                        if size > 0:
                            vals = list(range(1, size + 1))
                        break
            sets_in_order.append(vals)

        if not sets_in_order or any(len(s) == 0 for s in sets_in_order):
            return []

        # 카르테시안 프로덕트
        from itertools import product
        return [list(combo) for combo in product(*sets_in_order)]

    # ── CQM 제약 추가 ──

    def _add_cqm_constraint(self, cqm, lhs, op: str, rhs, label: str, category: str, weight=None):
        """dimod 표현식으로 CQM 제약 추가"""
        is_soft = (category == "soft") and weight

        # dimod는 lhs - rhs 형태로 제약을 표현해야 타입 충돌이 없음
        # lhs <= rhs  ->  cqm.add_constraint(lhs - rhs <= 0)
        # lhs >= rhs  ->  cqm.add_constraint(rhs - lhs <= 0)
        # lhs == rhs  ->  cqm.add_constraint(lhs - rhs == 0)
        try:
            diff = lhs - rhs
        except TypeError:
            # 타입 불일치 시 숫자를 명시적으로 처리
            if isinstance(rhs, (int, float)):
                diff = lhs - rhs
            elif isinstance(lhs, (int, float)):
                diff = lhs - rhs
            else:
                raise ValueError(f"unexpected data format")

        if op in ("<=", "le"):
            constraint_expr = diff <= 0
        elif op in (">=", "ge"):
            constraint_expr = diff >= 0
        elif op in ("==", "eq", "="):
            constraint_expr = diff == 0
        else:
            constraint_expr = diff <= 0

        if is_soft:
            cqm.add_constraint(constraint_expr, label=label, weight=float(weight))
        else:
            cqm.add_constraint(constraint_expr, label=label)

    # ── 고속 경로: overlap pairs (time_compatibility) ──

    def _fast_add_overlap_constraints(self, cqm, var_map, con_def, set_map, param_map=None, max_constraints=56000) -> int:
        """
        y[i,d] + y[j,d] <= 1 패턴을 eval_node 없이 직접 생성.
        D-Wave CQM 한도(100K)를 초과하지 않도록 겹침 강도 기반 필터링 적용.
        """
        pairs = con_def.get("_overlap_pairs", [])
        if not pairs:
            return 0

        y_vars = var_map.get("y", {})
        if not isinstance(y_vars, dict) or not y_vars:
            return 0

        D_vals = set_map.get("D", [])
        if not D_vals:
            return 0

        cid = con_def.get("id") or con_def.get("name", "overlap")

        # 제약 수가 한도를 초과하면 겹침 강도 기반 필터링
        total_possible = len(pairs) * len(D_vals)
        if total_possible > max_constraints and param_map:
            dep_times = param_map.get("trip_dep_time", [])
            arr_times = param_map.get("trip_arr_time", [])
            I_vals = set_map.get("I", [])

            if dep_times and arr_times and I_vals:
                id_to_idx = {v: i for i, v in enumerate(I_vals)}
                scored_pairs = []
                for pair in pairs:
                    i_id = int(pair[0]) if isinstance(pair[0], str) else pair[0]
                    j_id = int(pair[1]) if isinstance(pair[1], str) else pair[1]
                    i_idx = id_to_idx.get(i_id)
                    j_idx = id_to_idx.get(j_id)
                    if i_idx is not None and j_idx is not None:
                        overlap = min(arr_times[i_idx], arr_times[j_idx]) - max(dep_times[i_idx], dep_times[j_idx])
                        scored_pairs.append((overlap, pair))

                scored_pairs.sort(key=lambda x: x[0], reverse=True)
                max_pairs = max_constraints // len(D_vals)
                filtered_pairs = [p for _, p in scored_pairs[:max_pairs]]
                min_overlap = scored_pairs[min(max_pairs-1, len(scored_pairs)-1)][0] if scored_pairs else 0

                logger.info(
                    f"CQM overlap filter: {len(pairs)} -> {len(filtered_pairs)} pairs "
                    f"(min_overlap={min_overlap:.0f}min, limit={max_constraints})"
                )
                pairs = filtered_pairs

        count = 0
        for pi, pair in enumerate(pairs):
            i_val = int(pair[0]) if isinstance(pair[0], str) else pair[0]
            j_val = int(pair[1]) if isinstance(pair[1], str) else pair[1]

            for d_val in D_vals:
                d_int = int(d_val) if isinstance(d_val, str) else d_val
                yi = y_vars.get((i_val, d_int))
                yj = y_vars.get((j_val, d_int))

                if yi is not None and yj is not None:
                    cqm.add_constraint(yi + yj <= 1, label=f"{cid}_{count}")
                    count += 1

        logger.info(f"CQM fast-path: {len(pairs)} pairs x {len(D_vals)} D = {count} constraints")
        return count

    # ── 목적함수 ──

    def _parse_objective(self, cqm, var_map: Dict, obj_def: Dict, ctx) -> bool:
        """구조화된 목적함수 파싱"""
        from engine.compiler.struct_builder import build_objective

        obj_type, obj_val = build_objective(obj_def, ctx)

        if obj_val is not None:
            try:
                if obj_type == "minimize":
                    cqm.set_objective(obj_val)
                else:
                    cqm.set_objective(-obj_val)
                logger.info(f"CQM Objective set: {obj_type} (structured)")
                return True
            except Exception as e:
                logger.warning(f"CQM structured objective failed: {e}")

        # 폴백: expression 파싱
        expr_str = obj_def.get("expression", "")
        if expr_str:
            return self._parse_objective_from_expr(cqm, var_map, obj_def, ctx)

        return False

    def _parse_objective_from_expr(self, cqm, var_map, obj_def, ctx) -> bool:
        """expression 문자열에서 목적함수 파싱"""
        expr_str = obj_def.get("expression", "")
        obj_type = obj_def.get("type", "minimize")

        # sum(u[d] for d in D) 패턴
        m = re.match(r'sum\((\w+)\[(\w+)\]\s+for\s+(\w+)\s+in\s+(\w+)\)', expr_str)
        if m:
            var_name, idx_var, loop_var, set_name = m.groups()
            v = var_map.get(var_name)
            if isinstance(v, dict) and v:
                total = sum(v.values())
                if obj_type == "maximize":
                    total = -total
                cqm.set_objective(total)
                logger.info(f"CQM Objective from expression: {expr_str}")
                return True

        return False

    def _set_default_objective(self, cqm, var_map):
        """기본 목적함수: 모든 변수 합 최소화"""
        all_vars = []
        for v in var_map.values():
            if isinstance(v, dict):
                all_vars.extend(v.values())
            else:
                all_vars.append(v)
        if all_vars:
            cqm.set_objective(sum(all_vars))

    # ── 레거시 제약 파서 (폴백) ──

    def _parse_constraint_legacy(self, cqm, var_map, con_def, set_map, param_map) -> int:
        """레거시 expression 기반 파싱"""
        expr = con_def.get("expression", "").strip()
        cid = con_def.get("id") or con_def.get("name", "unknown")
        category = con_def.get("category", "hard")
        weight = con_def.get("weight")
        count = 0

        if "sum" in expr and ("== 1" in expr or "= 1" in expr):
            for vid, vars_dict in var_map.items():
                if isinstance(vars_dict, dict) and vars_dict:
                    first_key = next(iter(vars_dict))
                    if len(first_key) >= 2:
                        groups = {}
                        for key, var in vars_dict.items():
                            groups.setdefault(key[0], []).append(var)
                        for gk, gvars in groups.items():
                            label = f"{cid}_{gk}"
                            if category == "soft" and weight:
                                cqm.add_constraint(sum(gvars) == 1, label=label, weight=float(weight))
                            else:
                                cqm.add_constraint(sum(gvars) == 1, label=label)
                            count += 1
                        break

        elif "sum" in expr and "<=" in expr:
            nums = re.findall(r'<=\s*(\d+)', expr)
            ub = int(nums[0]) if nums else 10
            for vid, vars_dict in var_map.items():
                if isinstance(vars_dict, dict) and vars_dict:
                    first_key = next(iter(vars_dict))
                    if len(first_key) >= 2:
                        groups = {}
                        for key, var in vars_dict.items():
                            groups.setdefault(key[-1], []).append(var)
                        for gk, gvars in groups.items():
                            label = f"{cid}_{gk}"
                            cqm.add_constraint(sum(gvars) <= ub, label=label)
                            count += 1
                        break

        return count
