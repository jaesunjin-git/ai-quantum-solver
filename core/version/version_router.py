# core/version/version_router.py — Version Management API
#
# Provides:
#   - CRUD for dataset/model/run versions (existing)
#   - Timeline API: unified linear version history (new)
#   - Compare API: side-by-side version diff (new)

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database import SessionLocal
from core.models import DatasetVersionDB, ModelVersionDB, RunResultDB
from core.version.dataset_service import get_dataset_versions
from core.version.model_service import get_model_versions, get_model_version
from core.version.run_service import get_run_results, get_run_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Versions"])


# ── Existing CRUD endpoints ─────────────────────────────────────────

@router.get("/{project_id}/versions/datasets")
def list_dataset_versions(project_id: int):
    return get_dataset_versions(project_id)


@router.get("/{project_id}/versions/models")
def list_model_versions(project_id: int):
    return get_model_versions(project_id)


@router.get("/{project_id}/versions/models/{model_version_id}")
def detail_model_version(project_id: int, model_version_id: int):
    result = get_model_version(model_version_id)
    if not result:
        raise HTTPException(status_code=404, detail="Model version not found")
    return result


@router.get("/{project_id}/versions/runs")
def list_run_results(project_id: int, model_version_id: int = None):
    return get_run_results(project_id, model_version_id)


@router.get("/{project_id}/versions/runs/{run_id}")
def detail_run_result(project_id: int, run_id: int):
    result = get_run_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run result not found")
    return result


# ── Timeline API ─────────────────────────────────────────────────────

@router.get("/{project_id}/versions/timeline")
def get_version_timeline(project_id: int):
    """Unified linear version timeline.

    Joins Dataset → Model → Run into a flat timeline ordered by time.
    Each entry represents a user-visible "version" of the optimization.

    Returns:
        list of timeline entries, each with:
          - version_label: "v1", "v2", ...
          - dataset_version, model_version, run info
          - objective_value, status, solver_name
          - created_at
          - changes: what changed from previous version
    """
    db = SessionLocal()
    try:
        runs = (
            db.query(RunResultDB)
            .filter(RunResultDB.project_id == project_id)
            .order_by(RunResultDB.created_at.asc())
            .all()
        )

        # Also include model versions without runs
        models_with_runs = {r.model_version_id for r in runs if r.model_version_id}
        all_models = (
            db.query(ModelVersionDB)
            .filter(ModelVersionDB.project_id == project_id)
            .order_by(ModelVersionDB.created_at.asc())
            .all()
        )

        timeline = []
        idx = 0
        prev_entry = None

        # Build entries from runs (primary timeline anchor)
        for run in runs:
            idx += 1
            model = None
            dataset = None

            if run.model_version_id:
                model = db.query(ModelVersionDB).filter(
                    ModelVersionDB.id == run.model_version_id
                ).first()
            if model and model.dataset_version_id:
                dataset = db.query(DatasetVersionDB).filter(
                    DatasetVersionDB.id == model.dataset_version_id
                ).first()

            entry = {
                "version_label": f"v{idx}",
                "version_index": idx,
                "run_id": run.id,
                "model_version_id": run.model_version_id,
                "dataset_version_id": dataset.id if dataset else None,
                "solver_id": run.solver_id,
                "solver_name": run.solver_name,
                "status": run.status,
                "objective_value": run.objective_value,
                "compile_time_sec": run.compile_time_sec,
                "execute_time_sec": run.execute_time_sec,
                "model_version": model.version if model else None,
                "dataset_version": dataset.version if dataset else None,
                "variable_count": model.variable_count if model else None,
                "constraint_count": model.constraint_count if model else None,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "changes": [],
            }

            # Detect what changed from previous version
            if prev_entry:
                if entry["dataset_version_id"] != prev_entry["dataset_version_id"]:
                    entry["changes"].append("dataset_changed")
                if entry["model_version_id"] != prev_entry["model_version_id"]:
                    entry["changes"].append("model_changed")
                if entry["solver_id"] != prev_entry["solver_id"]:
                    entry["changes"].append("solver_changed")

            prev_entry = entry
            timeline.append(entry)

        # Append model-only entries (confirmed but never executed)
        for model in all_models:
            if model.id not in models_with_runs:
                idx += 1
                dataset = None
                if model.dataset_version_id:
                    dataset = db.query(DatasetVersionDB).filter(
                        DatasetVersionDB.id == model.dataset_version_id
                    ).first()

                timeline.append({
                    "version_label": f"v{idx}",
                    "version_index": idx,
                    "run_id": None,
                    "model_version_id": model.id,
                    "dataset_version_id": dataset.id if dataset else None,
                    "solver_id": None,
                    "solver_name": None,
                    "status": "model_confirmed",
                    "objective_value": None,
                    "compile_time_sec": None,
                    "execute_time_sec": None,
                    "model_version": model.version,
                    "dataset_version": dataset.version if dataset else None,
                    "variable_count": model.variable_count,
                    "constraint_count": model.constraint_count,
                    "created_at": model.created_at.isoformat() if model.created_at else None,
                    "changes": ["model_confirmed_only"],
                })

        return {
            "project_id": project_id,
            "total_versions": len(timeline),
            "timeline": timeline,
        }
    finally:
        db.close()


# ── Compare API ──────────────────────────────────────────────────────

@router.get("/{project_id}/versions/compare")
def compare_versions(
    project_id: int,
    run_id_a: int = Query(..., description="First run ID"),
    run_id_b: int = Query(..., description="Second run ID"),
):
    """Side-by-side comparison of two solver runs.

    Compares:
      - Solver info (id, name, status)
      - Objective values
      - KPI metrics (from result_json.interpreted_result.kpi)
      - Parameter differences (from model_json)
      - Constraint counts
      - Timing
    """
    db = SessionLocal()
    try:
        run_a = db.query(RunResultDB).filter(
            RunResultDB.id == run_id_a,
            RunResultDB.project_id == project_id,
        ).first()
        run_b = db.query(RunResultDB).filter(
            RunResultDB.id == run_id_b,
            RunResultDB.project_id == project_id,
        ).first()

        if not run_a or not run_b:
            raise HTTPException(status_code=404, detail="Run not found")

        def _extract_run_summary(run: RunResultDB) -> dict:
            result = json.loads(run.result_json) if run.result_json else {}
            interpreted = result.get("interpreted_result", {})
            kpi = interpreted.get("kpi", {})

            model = None
            params = {}
            if run.model_version_id:
                model = db.query(ModelVersionDB).filter(
                    ModelVersionDB.id == run.model_version_id
                ).first()
                if model and model.model_json:
                    model_data = json.loads(model.model_json)
                    for p in model_data.get("parameters", []):
                        pid = p.get("id") or p.get("name", "")
                        val = p.get("value") or p.get("default_value")
                        if val is not None:
                            params[pid] = val

            return {
                "run_id": run.id,
                "solver_id": run.solver_id,
                "solver_name": run.solver_name,
                "status": run.status,
                "objective_value": run.objective_value,
                "compile_time_sec": run.compile_time_sec,
                "execute_time_sec": run.execute_time_sec,
                "model_version_id": run.model_version_id,
                "model_version": model.version if model else None,
                "variable_count": model.variable_count if model else None,
                "constraint_count": model.constraint_count if model else None,
                "kpi": kpi,
                "parameters": params,
                "created_at": run.created_at.isoformat() if run.created_at else None,
            }

        summary_a = _extract_run_summary(run_a)
        summary_b = _extract_run_summary(run_b)

        # Calculate diffs
        kpi_diff = {}
        all_kpi_keys = set(summary_a["kpi"].keys()) | set(summary_b["kpi"].keys())
        for k in all_kpi_keys:
            va = summary_a["kpi"].get(k)
            vb = summary_b["kpi"].get(k)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                kpi_diff[k] = {
                    "a": va, "b": vb,
                    "delta": round(vb - va, 4),
                    "direction": "improved" if vb < va else "degraded" if vb > va else "same",
                }
            else:
                kpi_diff[k] = {"a": va, "b": vb, "delta": None, "direction": "unknown"}

        param_diff = {}
        all_param_keys = set(summary_a["parameters"].keys()) | set(summary_b["parameters"].keys())
        for k in all_param_keys:
            va = summary_a["parameters"].get(k)
            vb = summary_b["parameters"].get(k)
            if va != vb:
                param_diff[k] = {"a": va, "b": vb}

        return {
            "project_id": project_id,
            "a": summary_a,
            "b": summary_b,
            "kpi_diff": kpi_diff,
            "param_diff": param_diff,
            "solver_changed": summary_a["solver_id"] != summary_b["solver_id"],
            "model_changed": summary_a["model_version_id"] != summary_b["model_version_id"],
        }
    finally:
        db.close()
