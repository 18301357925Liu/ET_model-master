"""
Realtime monitor router - /api/realtime/*
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db import crud
from backend.api.schemas import (
    MonitorStatusResponse,
    MonitorStartRequest,
    MonitorStartResponse,
    RealtimePredictionItem,
    RealtimePredictionsResponse,
)
from backend.config import BASE_DIR, MONITOR_SCRIPT, OUTPUTS_TASK_CLUSTER


router = APIRouter()

# Global state for the monitor subprocess (process-safe)
_monitor_process: subprocess.Popen | None = None
_monitor_lock = threading.Lock()


def _check_monitor_alive() -> bool:
    """Check if the monitor subprocess is still running."""
    global _monitor_process
    if _monitor_process is None:
        return False
    if _monitor_process.poll() is not None:
        _monitor_process = None
        return False
    return True


def _read_realtime_predictions_from_jsonl(
    limit: int = 50,
) -> list[RealtimePredictionItem]:
    """
    Read realtime predictions from the JSONL file.
    Falls back to DB if file is missing.
    """
    REALTIME_LOG_PATH = OUTPUTS_TASK_CLUSTER.parent / "realtime_predictions_task_supervised.jsonl"
    records: list[RealtimePredictionItem] = []
    if not REALTIME_LOG_PATH.exists():
        return records
    try:
        lines = REALTIME_LOG_PATH.read_text(encoding="utf-8").splitlines()
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                record = RealtimePredictionItem(
                    session_dir=obj.get("session_dir", ""),
                    task_id=str(obj.get("task_id") or "__all__"),
                    sample_key=str(obj.get("sample_key", "")),
                    predicted_cluster=obj.get("predicted_cluster"),
                    relative_load_level=int(obj.get("relative_load_level", -1)),
                    relative_load_label=str(obj.get("relative_load_label", "")),
                    coordinates_2d=obj.get("coordinates_2d", [0.0, 0.0]),
                    probabilities=obj.get("probabilities", {}),
                )
                records.append(record)
            except Exception:
                continue
    except Exception:
        pass
    return records


@router.get("/monitor/status", response_model=MonitorStatusResponse)
def get_monitor_status():
    running = _check_monitor_alive()
    REALTIME_LOG_PATH = OUTPUTS_TASK_CLUSTER.parent / "realtime_predictions_task_supervised.jsonl"
    return MonitorStatusResponse(
        running=running,
        log_path=str(REALTIME_LOG_PATH) if running else None,
    )


@router.post("/monitor/start", response_model=MonitorStartResponse)
def start_monitor(payload: MonitorStartRequest):
    global _monitor_process
    with _monitor_lock:
        if _check_monitor_alive():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="监控进程已在运行中",
            )
        if not MONITOR_SCRIPT.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"监控脚本不存在: {MONITOR_SCRIPT}",
            )
        cmd = [
            sys.executable,
            str(MONITOR_SCRIPT),
            "--watch_dirs",
            *payload.watch_dirs,
            "--interval",
            str(payload.interval),
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(BASE_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            _monitor_process = proc
            return MonitorStartResponse(
                message="实时监控已启动",
                pid=proc.pid,
                watch_dirs=payload.watch_dirs,
                interval=payload.interval,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"启动失败: {e}",
            )


@router.post("/monitor/stop")
def stop_monitor():
    global _monitor_process
    with _monitor_lock:
        if not _check_monitor_alive():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="监控进程未运行",
            )
        try:
            _monitor_process.terminate()  # type: ignore
            try:
                _monitor_process.wait(timeout=5)  # type: ignore
            except subprocess.TimeoutExpired:
                _monitor_process.kill()  # type: ignore
                _monitor_process.wait()  # type: ignore
            _monitor_process = None
            return {"message": "实时监控已停止"}
        except Exception as e:
            _monitor_process = None
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"停止失败: {e}",
            )


@router.get("/predictions", response_model=RealtimePredictionsResponse)
def get_realtime_predictions(limit: int = 50):
    records = _read_realtime_predictions_from_jsonl(limit=limit)
    return RealtimePredictionsResponse(
        records=records,
        total=len(records),
    )
