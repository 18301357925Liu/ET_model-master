"""
CRUD operations for the ET_model database.
"""
from __future__ import annotations

from datetime import datetime
from typing import Generator

from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.db.models import User
from backend.db.models_extra import TaskRecord, PredictionRecord, LogEntry


# ── User CRUD ─────────────────────────────────────────────────────────────────

def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, username: str, email: str | None, hashed_password: str, role: str = "user") -> User:
    user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user_role(db: Session, user_id: int, new_role: str) -> User | None:
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.role = new_role
        db.commit()
        db.refresh(user)
    return user


def update_user_status(db: Session, user_id: int, is_active: bool) -> User | None:
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_active = is_active
        db.commit()
        db.refresh(user)
    return user


def list_all_users(db: Session) -> list[User]:
    return db.query(User).order_by(User.created_at.desc()).all()


# ── TaskRecord CRUD ────────────────────────────────────────────────────────────

def get_task_records(
    db: Session,
    session: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[TaskRecord]:
    q = db.query(TaskRecord)
    if session:
        q = q.filter(TaskRecord.session == session)
    return q.order_by(TaskRecord.created_at.desc()).offset(skip).limit(limit).all()


def upsert_task_records(db: Session, records: list[dict]) -> int:
    """
    Bulk upsert task records from pipeline output.
    Clears existing records and inserts new ones.
    """
    db.query(TaskRecord).delete()
    for r in records:
        db.add(TaskRecord(**r))
    db.commit()
    return len(records)


def get_task_records_count(db: Session) -> int:
    return db.query(TaskRecord).count()


# ── PredictionRecord CRUD ─────────────────────────────────────────────────────

def create_prediction_record(
    db: Session,
    session_dir: str,
    task_id: str | None,
    sample_key: str | None,
    predicted_cluster: str,
    relative_load_level: int | None,
    relative_load_label: str | None,
    coord_x: float | None,
    coord_y: float | None,
    probabilities: dict | None,
) -> PredictionRecord:
    record = PredictionRecord(
        session_dir=session_dir,
        task_id=task_id,
        sample_key=sample_key,
        predicted_cluster=predicted_cluster,
        relative_load_level=relative_load_level,
        relative_load_label=relative_load_label,
        coord_x=coord_x,
        coord_y=coord_y,
        probabilities=probabilities,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_realtime_predictions(
    db: Session,
    limit: int = 50,
) -> list[PredictionRecord]:
    return db.query(PredictionRecord).order_by(
        PredictionRecord.created_at.desc()
    ).limit(limit).all()


def get_predictions_by_session(
    db: Session,
    session_dir: str,
) -> list[PredictionRecord]:
    return db.query(PredictionRecord).filter(
        PredictionRecord.session_dir == session_dir
    ).all()


# ── LogEntry CRUD ────────────────────────────────────────────────────────────

def create_log_entry(
    db: Session,
    action: str,
    status: str,
    message: str | None,
    extra: dict | None,
) -> LogEntry:
    entry = LogEntry(
        action=action,
        status=status,
        message=message,
        extra=extra,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def append_update_log(
    db: Session,
    action: str,
    status: str,
    message: str,
    extra: dict | None = None,
) -> LogEntry:
    """Append a new log entry to the log_entries table."""
    return create_log_entry(db, action, status, message, extra)


def get_log_entries(
    db: Session,
    limit: int = 50,
) -> list[LogEntry]:
    return db.query(LogEntry).order_by(
        LogEntry.created_at.desc()
    ).limit(limit).all()
