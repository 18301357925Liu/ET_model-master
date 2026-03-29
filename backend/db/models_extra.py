"""
SQLAlchemy ORM models for task records, prediction records, and log entries.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from backend.db.database import Base


class TaskRecord(Base):
    __tablename__ = "task_records"

    id = Column(Integer, primary_key=True, index=True)
    session = Column(String(128), index=True, nullable=False)
    task_id = Column(String(64), index=True, nullable=False)
    cluster = Column(String(32), index=True, nullable=False)
    level = Column(String(16), nullable=True)
    label = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PredictionRecord(Base):
    __tablename__ = "prediction_records"

    id = Column(Integer, primary_key=True, index=True)
    session_dir = Column(String(512), index=True, nullable=False)
    task_id = Column(String(64), nullable=True)
    sample_key = Column(String(256), nullable=True)
    predicted_cluster = Column(String(32), index=True, nullable=False)
    relative_load_level = Column(Integer, nullable=True)
    relative_load_label = Column(String(128), nullable=True)
    coord_x = Column(Float, nullable=True)
    coord_y = Column(Float, nullable=True)
    probabilities = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(64), index=True, nullable=False)
    status = Column(String(16), nullable=False)
    message = Column(Text, nullable=True)
    extra = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
