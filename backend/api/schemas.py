"""
Pydantic schemas for FastAPI request/response validation.
"""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr | None = None
    password: str = Field(..., min_length=6)


class UserOut(BaseModel):
    id: int
    username: str
    email: str | None
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserRoleUpdate(BaseModel):
    role: str = Field(..., pattern="^(user|admin)$", description="角色：user 或 admin")


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Prediction ────────────────────────────────────────────────────────────────

class PredictSessionRequest(BaseModel):
    session_dir: str
    classifier_model: str | None = None
    pca_model: str | None = None
    features_template: str | None = None


class PredictionResultItem(BaseModel):
    sample_key: str
    session_id: str
    task_id: str | None
    predicted_cluster: str
    predicted_cluster_encoded: int
    coordinates_2d: dict[str, float]
    probabilities: dict[str, float]
    relative_load_level: int
    relative_load_label: str


class PredictSessionResponse(BaseModel):
    session_dir: str
    results: list[PredictionResultItem]


# ── Task Records ───────────────────────────────────────────────────────────────

class TaskRecordOut(BaseModel):
    session: str
    task_id: str
    cluster: str
    level: str | None
    label: str | None

    class Config:
        from_attributes = True


class TaskRecordsResponse(BaseModel):
    records: list[TaskRecordOut]


# ── Pipeline ──────────────────────────────────────────────────────────────────

class PipelineRebuildRequest(BaseModel):
    data_root: str = "data"
    k: int = 6
    algo: str = "kmeans"
    mapping_mode: str = "auto"
    classifier_algo: str = "svm"


class PipelineStepResult(BaseModel):
    name: str
    ok: bool
    returncode: int | None
    stdout: str
    stderr: str
    message: str


class PipelineRebuildResponse(BaseModel):
    message: str
    steps: list[PipelineStepResult]


# ── Log ───────────────────────────────────────────────────────────────────────

class LogEntryOut(BaseModel):
    timestamp: str
    action: str
    status: str
    message: str | None
    extra: dict | None = None

    class Config:
        from_attributes = True


class LogResponse(BaseModel):
    entries: list[LogEntryOut]


# ── Realtime Monitor ──────────────────────────────────────────────────────────

class MonitorStatusResponse(BaseModel):
    running: bool
    log_path: str | None


class MonitorStartRequest(BaseModel):
    watch_dirs: list[str] = ["Cognitive/data/cognitive_study", "data"]
    interval: int = 10


class MonitorStartResponse(BaseModel):
    message: str
    pid: int
    watch_dirs: list[str]
    interval: int


class RealtimePredictionItem(BaseModel):
    session_dir: str
    task_id: str | None
    sample_key: str
    predicted_cluster: str | None
    relative_load_level: int
    relative_load_label: str
    coordinates_2d: list[float]
    probabilities: dict[str, float]


class RealtimePredictionsResponse(BaseModel):
    records: list[RealtimePredictionItem]
    total: int


# ── System ────────────────────────────────────────────────────────────────────

class SystemInfoResponse(BaseModel):
    python: str
    sklearn: str


# ── AI Advice ────────────────────────────────────────────────────────────────

class AIAdviceRequest(BaseModel):
    session_filter: str = ""
