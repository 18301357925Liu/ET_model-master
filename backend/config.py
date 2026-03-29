"""
Configuration management - loads from .env file.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# Base directory (project root)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from project root
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


def get_setting(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


# ── Paths ────────────────────────────────────────────────────────────────────

DATA_ROOT = BASE_DIR / "data"
OUTPUTS_TASK_CLUSTER = BASE_DIR / "outputs_task_cluster"
OUTPUTS_SUPERVISED_TASK = BASE_DIR / "outputs_supervised_task"
MONITOR_SCRIPT = BASE_DIR / "realtime_session_monitor.py"

# SQLite database path (one file, travels with the program)
_db_path = str(BASE_DIR / "et_model.db").replace("\\", "/")
DATABASE_URL = f"sqlite:///{_db_path}"

# ── Model defaults ────────────────────────────────────────────────────────────

DEFAULT_CLF_MODEL = str(OUTPUTS_SUPERVISED_TASK / "model_svm.joblib")
DEFAULT_PCA_MODEL = str(OUTPUTS_TASK_CLUSTER / "pca_model.joblib")
DEFAULT_FEATURES_TEMPLATE = str(OUTPUTS_TASK_CLUSTER / "features.csv")

# ── DashScope ─────────────────────────────────────────────────────────────────

DASHSCOPE_API_KEY = get_setting("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_MODEL = get_setting("DASHSCOPE_MODEL", "qwen-max")
