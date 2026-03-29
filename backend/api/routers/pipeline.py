"""
Pipeline router - /api/pipeline/rebuild
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db import crud
from backend.api.schemas import (
    PipelineRebuildRequest,
    PipelineRebuildResponse,
    PipelineStepResult,
)
from backend.config import BASE_DIR, OUTPUTS_TASK_CLUSTER, OUTPUTS_SUPERVISED_TASK


router = APIRouter()


def _run_script(
    cmd: list[str],
    action: str,
    params: dict,
    db: Session,
) -> dict:
    """Run a Python script as a subprocess and log the result."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except Exception as e:
        msg = f"执行失败：{e}"
        crud.append_update_log(db, action, "error", msg, {"params": params})
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(e),
            "message": msg,
        }

    ok = proc.returncode == 0
    msg = "执行成功" if ok else f"脚本返回非零退出码：{proc.returncode}"
    crud.append_update_log(
        db, action, "success" if ok else "error", msg,
        {"params": params, "returncode": proc.returncode},
    )
    return {
        "ok": ok,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "message": msg,
    }


@router.post("/rebuild", response_model=PipelineRebuildResponse)
def rebuild_pipeline(
    payload: PipelineRebuildRequest,
    db: Session = Depends(get_db),
):
    """
    One-click rebuild of the task-level pipeline:
    1. Task clustering (cluster_cognitive_data.py)
    2. Cluster-to-load mapping (summarize_cluster_load.py)
    3. Supervised model training (train_classifier.py)
    """
    OUTPUTS_TASK_CLUSTER.mkdir(parents=True, exist_ok=True)
    OUTPUTS_SUPERVISED_TASK.mkdir(parents=True, exist_ok=True)

    steps: list[PipelineStepResult] = []

    # 1) Task clustering
    cluster_cmd = [
        sys.executable,
        str(BASE_DIR / "cluster_cognitive_data.py"),
        "--data_root", payload.data_root,
        "--unit", "task",
        "--k", str(payload.k),
        "--algo", payload.algo,
        "--out_dir", str(OUTPUTS_TASK_CLUSTER),
        "--feature_weights_json", str(BASE_DIR / "feature_weights_task.json"),
    ]
    cluster_result = _run_script(
        cluster_cmd, "task_cluster",
        {"data_root": payload.data_root, "unit": "task", "k": payload.k, "algo": payload.algo},
        db,
    )
    steps.append(PipelineStepResult(name="task_cluster", **cluster_result))
    if not cluster_result["ok"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "任务级聚类失败",
                "steps": [s.model_dump() for s in steps],
            },
        )

    # 2) Cluster-to-load mapping
    summarize_cmd = [
        sys.executable,
        str(BASE_DIR / "summarize_cluster_load.py"),
        "--features", str(OUTPUTS_TASK_CLUSTER / "features.csv"),
        "--clusters", str(OUTPUTS_TASK_CLUSTER / "clusters.csv"),
        "--out_dir", str(OUTPUTS_TASK_CLUSTER),
        "--mapping_mode", payload.mapping_mode,
    ]
    summarize_result = _run_script(
        summarize_cmd, "summarize_cluster_load",
        {"features": str(OUTPUTS_TASK_CLUSTER / "features.csv"),
         "clusters": str(OUTPUTS_TASK_CLUSTER / "clusters.csv"),
         "mapping_mode": payload.mapping_mode},
        db,
    )
    steps.append(PipelineStepResult(name="summarize_cluster_load", **summarize_result))
    if not summarize_result["ok"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "生成相对负荷映射失败",
                "steps": [s.model_dump() for s in steps],
            },
        )

    # 3) Supervised model training
    train_cmd = [
        sys.executable,
        str(BASE_DIR / "train_classifier.py"),
        "--features", str(OUTPUTS_TASK_CLUSTER / "features.csv"),
        "--labels", str(OUTPUTS_TASK_CLUSTER / "clusters.csv"),
        "--out_dir", str(OUTPUTS_SUPERVISED_TASK),
        "--algo", payload.classifier_algo,
    ]
    train_result = _run_script(
        train_cmd, "train_classifier",
        {"features": str(OUTPUTS_TASK_CLUSTER / "features.csv"),
         "labels": str(OUTPUTS_TASK_CLUSTER / "clusters.csv"),
         "algo": payload.classifier_algo},
        db,
    )
    steps.append(PipelineStepResult(name="train_classifier", **train_result))
    if not train_result["ok"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "监督模型训练失败",
                "steps": [s.model_dump() for s in steps],
            },
        )

    return PipelineRebuildResponse(
        message="任务级 pipeline 更新完成",
        steps=steps,
    )
