"""
System info router - /api/system/info
"""
from __future__ import annotations

import platform

import sklearn

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db import crud
from backend.api.schemas import SystemInfoResponse, LogResponse, LogEntryOut


router = APIRouter()


@router.get("/info", response_model=SystemInfoResponse)
def get_system_info():
    """Return Python / sklearn version info."""
    return SystemInfoResponse(
        python=platform.python_version(),
        sklearn=sklearn.__version__,
    )


@router.get("/logs", response_model=LogResponse)
def get_logs(limit: int = 50, db: Session = Depends(get_db)):
    """Return recent log entries from the database."""
    entries = crud.get_log_entries(db, limit=limit)
    return LogResponse(
        entries=[
            LogEntryOut(
                timestamp=e.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                action=e.action,
                status=e.status,
                message=e.message,
                extra=e.extra,
            )
            for e in entries
        ]
    )
