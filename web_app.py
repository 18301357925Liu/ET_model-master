"""
ET_model Flask Web Application
Multi-user cognitive load analysis platform with role-based access control.

Roles:
  - admin:   Full access — Pipeline rebuild, all logs
  - user:    Upload data, predict, browse tasks, realtime, AI advice

Data isolation: every user's data is stored under uploads/<user_id>/
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load .env first
load_dotenv(Path(__file__).parent / ".env")

from flask import (
    Flask,
    Response,
    jsonify,
    request,
    send_from_directory,
)
from flask_cors import CORS

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_BASE = BASE_DIR / "uploads"

# Global outputs (admin pipeline only)
OUTPUTS_TASK_CLUSTER = BASE_DIR / "outputs_task_cluster"
OUTPUTS_SUPERVISED_TASK = BASE_DIR / "outputs_supervised_task"
UPDATE_LOG_PATH = BASE_DIR / "web_update_log.jsonl"
REALTIME_LOG_PATH = BASE_DIR / "realtime_predictions_task_supervised.jsonl"
MONITOR_SCRIPT = BASE_DIR / "realtime_session_monitor.py"
DB_PATH = BASE_DIR / "et_model.db"

# ── JWT helpers (reuse backend auth utils) ────────────────────────────────────
sys.path.insert(0, str(BASE_DIR))
from backend.api.auth import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from backend.config import DASHSCOPE_API_KEY
from prompts import QWEN_SYSTEM_PROMPT, USER_MESSAGE_TEMPLATE, build_advice_context

# ── Database (SQLite via raw sqlite3 — avoids extra dependencies) ────────────
import sqlite3

DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    """Create all tables if they don't exist."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            hashed_password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    # Migration: add role column if it doesn't exist (from old is_admin schema)
    try:
        cur.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
        # Migrate existing is_admin=1 to role='admin'
        cur.execute("UPDATE users SET role = 'admin' WHERE is_admin = 1 AND role IS NULL")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

    cur.execute("""
        CREATE TABLE IF NOT EXISTS task_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session TEXT NOT NULL,
            task_id TEXT NOT NULL,
            cluster TEXT NOT NULL,
            level TEXT,
            label TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS prediction_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_dir TEXT NOT NULL,
            task_id TEXT,
            sample_key TEXT,
            predicted_cluster TEXT NOT NULL,
            relative_load_level INTEGER,
            relative_load_label TEXT,
            coord_x REAL,
            coord_y REAL,
            probabilities TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS log_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            extra TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS uploaded_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_name TEXT NOT NULL,
            session_path TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()


    conn.close()


init_database()

# ── App ────────────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="web", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB max upload
app.config["REQUEST_TIMEOUT"] = 300  # 5 min timeout for large uploads
CORS(app, supports_credentials=True)

# ── Auth helpers ───────────────────────────────────────────────────────────────


def get_current_user() -> Optional[Dict]:
    """Decode JWT from Authorization header. Returns dict with user info or None."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    payload = decode_access_token(token)
    if payload is None:
        return None
    user_id = payload.get("sub")
    if user_id is None:
        return None
    conn = get_db()
    cur = conn.execute(
        "SELECT id, username, email, role, is_active FROM users WHERE id = ?",
        (int(user_id),),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    if not row["is_active"]:
        return None
    return dict(row)


def require_auth(f):
    """Decorator: require valid JWT token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return jsonify({"error": "未登录或登录已过期"}), 401
        request._current_user = user
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    """Decorator: require admin role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return jsonify({"error": "未登录或登录已过期"}), 401
        if user.get("role") != "admin":
            return jsonify({"error": "需要管理员权限"}), 403
        request._current_user = user
        return f(*args, **kwargs)
    return decorated


def current_user() -> Dict:
    """Get the current user dict (must be called inside a require_auth route)."""
    return request._current_user


def user_dir(user_id: int) -> Path:
    """Per-user data directory."""
    d = UPLOAD_BASE / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_data_dir(user_id: int) -> Path:
    return user_dir(user_id) / "data"


def user_outputs_cluster(user_id: int) -> Path:
    return user_dir(user_id) / "outputs_task_cluster"


def user_outputs_model(user_id: int) -> Path:
    return user_dir(user_id) / "outputs_supervised_task"


# ── Append log helper ─────────────────────────────────────────────────────────


def _append_log(
    user_id: Optional[int],
    action: str,
    status: str,
    message: str,
    extra: Dict[str, Any] | None = None,
) -> None:
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user_id,
        "action": action,
        "status": status,
        "message": message,
    }
    if extra:
        entry["extra"] = extra
    try:
        with UPDATE_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # Also write to DB log_entries
    conn = get_db()
    conn.execute(
        "INSERT INTO log_entries (user_id, action, status, message, extra, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            user_id,
            action,
            status,
            message,
            json.dumps(extra) if extra else None,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


# ── Static file serving ────────────────────────────────────────────────────────


@app.route("/")
def index() -> Response:
    """Serve the SPA entry point."""
    index_path = BASE_DIR / "web" / "index.html"
    if not index_path.exists():
        return "index.html not found. Please make sure web/index.html exists.", 404
    return send_from_directory(str(index_path.parent), index_path.name)


# ── Auth ──────────────────────────────────────────────────────────────────────


@app.route("/api/auth/register", methods=["POST"])
def register() -> Response:
    """Register a new user account."""
    payload = request.get_json(force=True, silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    email = str(payload.get("email", "") or "").strip() or None

    if len(username) < 3 or len(username) > 64:
        return jsonify({"error": "用户名需要3-64个字符"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码至少6个字符"}), 400

    hashed = get_password_hash(password)
    now = datetime.now().isoformat()

    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, email, hashed_password, role, is_active, created_at) VALUES (?, ?, ?, 'user', 1, ?)",
            (username, email, hashed, now),
        )
        user_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "用户名已存在"}), 400
    conn.close()

    token = create_access_token(data={"sub": str(user_id)})
    _append_log(user_id, "register", "success", f"用户 {username} 注册成功")
    return jsonify({"access_token": token, "token_type": "bearer", "username": username}), 201


@app.route("/api/auth/login", methods=["POST"])
def login() -> Response:
    """Login and receive a JWT token."""
    payload = request.get_json(force=True, silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))

    conn = get_db()
    cur = conn.execute(
        "SELECT id, username, hashed_password, role, is_active FROM users WHERE username = ?",
        (username,),
    )
    row = cur.fetchone()
    conn.close()

    if row is None or not verify_password(password, row["hashed_password"]):
        return jsonify({"error": "用户名或密码错误"}), 401

    if not row["is_active"]:
        return jsonify({"error": "账号已被禁用"}), 403

    user_id = row["id"]
    token = create_access_token(data={"sub": str(user_id)})
    _append_log(user_id, "login", "success", f"用户 {username} 登录")
    return jsonify({
        "access_token": token,
        "token_type": "bearer",
        "username": row["username"],
        "role": row["role"],
        "is_admin": row["role"] == "admin",
    })


@app.route("/api/auth/me", methods=["GET"])
@require_auth
def me() -> Response:
    """Get current user info."""
    user = current_user()
    return jsonify({
        "id": user["id"],
        "username": user["username"],
        "email": user.get("email"),
        "role": user.get("role", "user"),
        "is_admin": user.get("role") == "admin",
        "is_active": bool(user["is_active"]),
    })


# ── User Management (Admin Only) ──────────────────────────────────────────────


@app.route("/api/admin/users", methods=["GET"])
@require_admin
def list_all_users() -> Response:
    """List all users (admin only)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, email, role, is_active, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return jsonify({"users": [dict(r) for r in rows]})


@app.route("/api/admin/users/<int:user_id>/role", methods=["PATCH"])
@require_admin
def update_user_role(user_id: int) -> Response:
    """Update user role (admin only)."""
    payload = request.get_json(force=True) or {}
    new_role = payload.get("role", "")
    if new_role not in ("user", "admin"):
        return jsonify({"error": "角色必须是 user 或 admin"}), 400

    conn = get_db()
    cur = conn.execute(
        "UPDATE users SET role = ? WHERE id = ?",
        (new_role, user_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "用户不存在"}), 404

    user = conn.execute(
        "SELECT id, username, email, role, is_active, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return jsonify(dict(user))


@app.route("/api/admin/users/<int:user_id>/status", methods=["PATCH"])
@require_admin
def update_user_status(user_id: int) -> Response:
    """Enable/disable user (admin only)."""
    payload = request.get_json(force=True) or {}
    is_active = bool(payload.get("is_active", True))

    conn = get_db()
    cur = conn.execute(
        "UPDATE users SET is_active = ? WHERE id = ?",
        (is_active, user_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "用户不存在"}), 404

    user = conn.execute(
        "SELECT id, username, email, role, is_active, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return jsonify(dict(user))


# ── File Upload ────────────────────────────────────────────────────────────────


@app.route("/api/upload/sessions", methods=["GET"])
@require_auth
def list_sessions() -> Response:
    """List all uploaded sessions for the current user."""
    user = current_user()
    conn = get_db()
    rows = conn.execute(
        "SELECT id, session_name, session_path, created_at FROM uploaded_sessions WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    conn.close()
    return jsonify({"sessions": [dict(r) for r in rows]})


def _discover_sessions_from_zip(
    zf: zipfile.ZipFile,
    user_data: Path,
    uid: int,
) -> list[dict]:
    """
    Extract zip and discover all valid session folders inside.
    A valid session folder contains the expected 6 CSV + 1 JSON files.
    Returns list of dicts with session_name and session_path.
    """
    SESSION_REQUIRED_FILES = {
        "fixations.csv",
        "gaze_data.csv",
        "blinks.csv",
        "events.csv",
        "aoi_transitions.csv",
        "session_meta.json",
    }
    _TASK_FILE_ALTERNATIVES = {"tasks.csv", "task_events.csv"}

    found_sessions = []
    # zip may contain flat files or nested folders; group by top-level folder
    folder_contents: dict[str, set[str]] = {}
    for name in zf.namelist():
        name_clean = name.strip("/")
        if not name_clean:
            continue
        # Determine top-level folder
        if "/" in name_clean:
            top = name_clean.split("/", 1)[0]
        elif "\\" in name_clean:
            top = name_clean.split("\\", 1)[0]
        else:
            top = ""  # flat file, skip
        if not top or top.startswith("."):
            continue
        if top not in folder_contents:
            folder_contents[top] = set()
        # Track only relevant files
        subpath = name_clean[len(top):].lstrip("/")
        if subpath:
            folder_contents[top].add(subpath)

    now = datetime.now().isoformat()
    for folder_name, files in folder_contents.items():
        # Check if this folder looks like a valid session
        # A valid session must have all required files, plus either tasks.csv or task_events.csv
        present = {f for f in files if not any(f.startswith(".") or f.startswith("_") for _ in [1])}
        required_missing = SESSION_REQUIRED_FILES - present
        has_task_file = bool(_TASK_FILE_ALTERNATIVES & present)
        if required_missing or not has_task_file:
            # Not a complete session folder — skip silently
            continue
        session_name = folder_name
        session_path = user_data / session_name

        # Extract only this folder
        for zip_name in zf.namelist():
            clean = zip_name.strip("/")
            if not clean.startswith(folder_name + "/") and clean != folder_name:
                continue
            dest = user_data / clean
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not clean.endswith("/"):
                dest.write_bytes(zf.read(zip_name))

        found_sessions.append({
            "session_name": session_name,
            "session_path": str(session_path),
            "created_at": now,
        })
    return found_sessions


@app.route("/api/upload/session", methods=["POST"])
@require_auth
def upload_session() -> Response:
    """
    Upload a session data package.
    Accepts:
      - multipart/form-data with a zip file in field 'file' (field 'session_name' optional)
      - application/json with base64-encoded zip in 'zip_base64' and 'session_name'
    The zip may contain one or multiple session folders (each with 6 CSV + 1 JSON).
    All valid sessions found will be registered automatically.
    """
    user = current_user()
    uid = user["id"]

    # ── Handle multipart upload ──────────────────────────────────────────────
    if request.content_type and "multipart/form-data" in request.content_type:
        if "file" not in request.files:
            return jsonify({"error": "未提供文件"}), 400

        uploaded_file = request.files["file"]
        if uploaded_file.filename == "":
            return jsonify({"error": "文件名为空"}), 400

        tmp_zip = BASE_DIR / f"tmp_{uid}_{datetime.now().timestamp()}.zip"
        uploaded_file.save(str(tmp_zip))

    # ── Handle JSON base64 upload ────────────────────────────────────────────
    elif request.is_json:
        payload = request.get_json(force=True)
        zip_b64 = payload.get("zip_base64", "")

        if not zip_b64:
            return jsonify({"error": "未提供 zip_base64"}), 400

        import base64
        tmp_zip = BASE_DIR / f"tmp_{uid}_{datetime.now().timestamp()}.zip"
        try:
            with open(tmp_zip, "wb") as f:
                f.write(base64.b64decode(zip_b64))
        except Exception as e:
            return jsonify({"error": f"zip_base64 解码失败: {e}"}), 400

    else:
        return jsonify({"error": "不支持的 Content-Type"}), 400

    user_data = user_data_dir(uid)
    user_data.mkdir(parents=True, exist_ok=True)

    # ── Extract zip and discover sessions ────────────────────────────────────
    try:
        with zipfile.ZipFile(str(tmp_zip), "r") as zf:
            # Security check
            for name in zf.namelist():
                if ".." in name or name.startswith("/"):
                    raise ValueError("Zip contains unsafe paths")
            sessions = _discover_sessions_from_zip(zf, user_data, uid)
    except zipfile.BadZipFile:
        tmp_zip.unlink(missing_ok=True)
        return jsonify({"error": "无效的 zip 文件，请确认文件格式正确"}), 400
    except ValueError as e:
        tmp_zip.unlink(missing_ok=True)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        tmp_zip.unlink(missing_ok=True)
        return jsonify({"error": f"解压失败: {e}"}), 500
    finally:
        if tmp_zip.exists():
            tmp_zip.unlink(missing_ok=True)

    if not sessions:
        return jsonify({"error": "zip 包中未找到有效的 session 文件夹（需要包含 fixations.csv、gaze_data.csv、blinks.csv、events.csv、aoi_transitions.csv、task_events.csv、session_meta.json）"}), 400

    # ── Save records ─────────────────────────────────────────────────────────
    conn = get_db()
    registered = []
    for s in sessions:
        conn.execute(
            "DELETE FROM uploaded_sessions WHERE user_id = ? AND session_name = ?",
            (uid, s["session_name"]),
        )
        conn.execute(
            "INSERT INTO uploaded_sessions (user_id, session_name, session_path, created_at) VALUES (?, ?, ?, ?)",
            (uid, s["session_name"], s["session_path"], s["created_at"]),
        )
        registered.append(s["session_name"])
    conn.commit()
    conn.close()

    _append_log(uid, "upload_session", "success", f"上传 session: {', '.join(registered)}")
    return jsonify({
        "message": f"上传成功，共 {len(registered)} 个 session",
        "sessions": registered,
    })


@app.route("/api/upload/sessions/<session_name>", methods=["DELETE"])
@require_auth
def delete_session(session_name: str) -> Response:
    """Delete an uploaded session for the current user."""
    user = current_user()
    uid = user["id"]

    conn = get_db()
    row = conn.execute(
        "SELECT id, session_path FROM uploaded_sessions WHERE user_id = ? AND session_name = ?",
        (uid, session_name),
    ).fetchone()
    if row is None:
        conn.close()
        return jsonify({"error": "Session 不存在"}), 404

    session_path = Path(row["session_path"])
    if session_path.exists():
        shutil.rmtree(str(session_path))

    conn.execute("DELETE FROM uploaded_sessions WHERE id = ?", (row["id"],))
    conn.execute("DELETE FROM prediction_records WHERE user_id = ? AND session_dir LIKE ?", (uid, f"%{session_name}%"))
    conn.commit()
    conn.close()

    _append_log(uid, "delete_session", "success", f"删除 session: {session_name}")
    return jsonify({"message": "删除成功"})


# ── Pipeline (admin only) ───────────────────────────────────────────────────────


@app.route("/api/pipeline/rebuild", methods=["POST"])
@require_admin
def rebuild_pipeline() -> Response:
    """
    Admin: rebuild global task-level pipeline.
    All users share the same global outputs (admin maintains the shared model).
    """
    payload = request.get_json(force=True, silent=True) or {}

    data_root = str(payload.get("data_root", "data"))
    k = int(payload.get("k", 6))
    algo = str(payload.get("algo", "kmeans"))
    mapping_mode = str(payload.get("mapping_mode", "auto"))
    clf_algo = str(payload.get("classifier_algo", "svm"))

    OUTPUTS_TASK_CLUSTER.mkdir(parents=True, exist_ok=True)
    OUTPUTS_SUPERVISED_TASK.mkdir(parents=True, exist_ok=True)

    steps: List[Dict] = []

    # Step 1: clustering
    cmd1 = [
        sys.executable,
        str(BASE_DIR / "cluster_cognitive_data.py"),
        "--data_root", data_root,
        "--unit", "task",
        "--k", str(k),
        "--algo", algo,
        "--out_dir", str(OUTPUTS_TASK_CLUSTER),
        "--feature_weights_json", str(BASE_DIR / "feature_weights_task.json"),
    ]
    r1 = _run_script(cmd1, "task_cluster", {"data_root": data_root, "k": k, "algo": algo}, None)
    steps.append({"name": "task_cluster", **r1})
    if not r1["ok"]:
        return jsonify({"error": "聚类失败", "steps": steps}), 500

    # Step 2: load mapping
    cmd2 = [
        sys.executable,
        str(BASE_DIR / "summarize_cluster_load.py"),
        "--features", str(OUTPUTS_TASK_CLUSTER / "features.csv"),
        "--clusters", str(OUTPUTS_TASK_CLUSTER / "clusters.csv"),
        "--out_dir", str(OUTPUTS_TASK_CLUSTER),
        "--mapping_mode", mapping_mode,
    ]
    r2 = _run_script(cmd2, "summarize_cluster_load", {"mapping_mode": mapping_mode}, None)
    steps.append({"name": "summarize_cluster_load", **r2})
    if not r2["ok"]:
        return jsonify({"error": "生成负荷映射失败", "steps": steps}), 500

    # Step 3: train model
    cmd3 = [
        sys.executable,
        str(BASE_DIR / "train_classifier.py"),
        "--features", str(OUTPUTS_TASK_CLUSTER / "features.csv"),
        "--labels", str(OUTPUTS_TASK_CLUSTER / "clusters.csv"),
        "--out_dir", str(OUTPUTS_SUPERVISED_TASK),
        "--algo", clf_algo,
    ]
    r3 = _run_script(cmd3, "train_classifier", {"algo": clf_algo}, None)
    steps.append({"name": "train_classifier", **r3})
    if not r3["ok"]:
        return jsonify({"error": "模型训练失败", "steps": steps}), 500

    _append_log(None, "pipeline_rebuild", "success", "全局 pipeline 更新完成")
    return jsonify({"message": "Pipeline 更新完成", "steps": steps})


# ── User-level pipeline (each user builds their own model from their data) ──────


@app.route("/api/pipeline/user-rebuild", methods=["POST"])
@require_auth
def user_pipeline_rebuild() -> Response:
    """
    User: build a personal pipeline using their own uploaded data.
    Each user gets their own model.
    """
    user = current_user()
    uid = user["id"]

    payload = request.get_json(force=True, silent=True) or {}
    session_names = payload.get("session_names", [])
    k = int(payload.get("k", 6))
    algo = str(payload.get("algo", "kmeans"))
    mapping_mode = str(payload.get("mapping_mode", "auto"))
    clf_algo = str(payload.get("classifier_algo", "svm"))

    uc = user_outputs_cluster(uid)
    um = user_outputs_model(uid)
    ud = user_data_dir(uid)
    uc.mkdir(parents=True, exist_ok=True)
    um.mkdir(parents=True, exist_ok=True)

    steps: List[Dict] = []

    # Filter data_root based on selected sessions
    # If session_names provided, create a temp symlink or copy structure
    if session_names:
        # Use only selected sessions for clustering
        data_root = str(ud)
    else:
        data_root = str(ud)

    # Step 1: clustering
    cmd1 = [
        sys.executable,
        str(BASE_DIR / "cluster_cognitive_data.py"),
        "--data_root", data_root,
        "--unit", "task",
        "--k", str(k),
        "--algo", algo,
        "--out_dir", str(uc),
        "--feature_weights_json", str(BASE_DIR / "feature_weights_task.json"),
    ]
    r1 = _run_script(cmd1, "user_task_cluster", {"data_root": data_root, "k": k, "algo": algo}, uid)
    steps.append({"name": "task_cluster", **r1})
    if not r1["ok"]:
        return jsonify({"error": "聚类失败", "steps": steps}), 500

    # Step 2: load mapping
    cmd2 = [
        sys.executable,
        str(BASE_DIR / "summarize_cluster_load.py"),
        "--features", str(uc / "features.csv"),
        "--clusters", str(uc / "clusters.csv"),
        "--out_dir", str(uc),
        "--mapping_mode", mapping_mode,
    ]
    r2 = _run_script(cmd2, "summarize_cluster_load", {"mapping_mode": mapping_mode}, uid)
    steps.append({"name": "summarize_cluster_load", **r2})
    if not r2["ok"]:
        return jsonify({"error": "生成负荷映射失败", "steps": steps}), 500

    # Step 3: train model
    cmd3 = [
        sys.executable,
        str(BASE_DIR / "train_classifier.py"),
        "--features", str(uc / "features.csv"),
        "--labels", str(uc / "clusters.csv"),
        "--out_dir", str(um),
        "--algo", clf_algo,
    ]
    r3 = _run_script(cmd3, "user_train_classifier", {"algo": clf_algo}, uid)
    steps.append({"name": "train_classifier", **r3})
    if not r3["ok"]:
        return jsonify({"error": "模型训练失败", "steps": steps}), 500

    _append_log(uid, "user_pipeline_rebuild", "success", "个人 pipeline 更新完成")
    return jsonify({"message": "个人 pipeline 更新完成", "steps": steps})


# ── Predict ───────────────────────────────────────────────────────────────────


@app.route("/api/predict-session", methods=["POST"])
@require_auth
def predict_session() -> Response:
    """
    Predict a single session. Works for both global model (admin) and user model.
    The session must be in the user's uploaded sessions list.
    """
    user = current_user()
    uid = user["id"]

    payload = request.get_json(force=True, silent=True) or {}
    session_dir = str(payload.get("session_dir", "")).strip()

    if not session_dir:
        return jsonify({"error": "session_dir 必填"}), 400

    # Verify session belongs to user
    conn = get_db()
    row = conn.execute(
        "SELECT session_path FROM uploaded_sessions WHERE user_id = ? AND session_name = ?",
        (uid, session_dir),
    ).fetchone()
    conn.close()

    if row is None:
        return jsonify({"error": "Session 不存在或无权访问"}), 404

    session_path = row["session_path"]  # 使用数据库中的完整路径

    # Determine model paths:
    # Priority: user model > global model
    user_clf = user_outputs_model(uid) / "model_svm.joblib"
    user_pca = user_outputs_cluster(uid) / "pca_model.joblib"
    user_feat = user_outputs_cluster(uid) / "features.csv"

    clf_model = str(user_clf) if user_clf.exists() else str(OUTPUTS_SUPERVISED_TASK / "model_svm.joblib")
    pca_model = str(user_pca) if user_pca.exists() else str(OUTPUTS_TASK_CLUSTER / "pca_model.joblib")
    feat_tpl = str(user_feat) if user_feat.exists() else str(OUTPUTS_TASK_CLUSTER / "features.csv")

    try:
        from predict_utils import predict_session as _predict
        results = _predict(
            session_path,
            classifier_model=clf_model,
            pca_model=pca_model,
            features_template=feat_tpl,
        )
    except Exception as e:
        return jsonify({"error": str(e), "detail": type(e).__name__}), 500

    rows = []
    now = datetime.now().isoformat()
    for r in results:
        x, y = r.coordinates_2d
        rows.append({
            "sample_key": r.sample_key,
            "session_id": r.session_id,
            "task_id": r.task_id,
            "predicted_cluster": r.predicted_cluster,
            "predicted_cluster_encoded": r.predicted_cluster_encoded,
            "coordinates_2d": {"x": float(x), "y": float(y)},
            "probabilities": r.probabilities,
            "relative_load_level": r.relative_load_level,
            "relative_load_label": r.relative_load_label,
        })

        # Save to DB
        conn2 = get_db()
        conn2.execute(
            """INSERT INTO prediction_records
               (user_id, session_dir, task_id, sample_key, predicted_cluster,
                relative_load_level, relative_load_label, coord_x, coord_y,
                probabilities, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uid, session_dir, r.task_id, r.sample_key, r.predicted_cluster,
                r.relative_load_level, r.relative_load_label,
                float(x) if x == x else None,
                float(y) if y == y else None,
                json.dumps(r.probabilities),
                now,
            ),
        )
        conn2.commit()
        conn2.close()

    return jsonify({"session_dir": session_dir, "results": rows})


# ── Task Records ───────────────────────────────────────────────────────────────


@app.route("/api/task-records", methods=["GET"])
@require_auth
def task_records() -> Response:
    """Get task records (global pipeline output, shared across all users)."""
    session_filter = request.args.get("session", "").strip()

    conn = get_db()
    if session_filter:
        rows = conn.execute(
            """SELECT session, task_id, cluster, level, label FROM task_records
               WHERE session LIKE ? ORDER BY created_at DESC LIMIT 200""",
            (f"%{session_filter}%",),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT session, task_id, cluster, level, label FROM task_records ORDER BY created_at DESC LIMIT 200",
        ).fetchall()
    conn.close()

    return jsonify({"records": [dict(r) for r in rows]})


# ── Realtime Monitor ──────────────────────────────────────────────────────────


@app.route("/api/realtime/monitor/status", methods=["GET"])
@require_auth
def realtime_status() -> Response:
    uid = current_user()["id"]
    return jsonify({
        "running": False,
        "log_path": str(REALTIME_LOG_PATH),
        "user_id": uid,
    })


@app.route("/api/realtime/predictions", methods=["GET"])
@require_auth
def realtime_predictions() -> Response:
    """Get realtime predictions for the current user."""
    user = current_user()
    uid = user["id"]
    limit = int(request.args.get("limit", 50))

    conn = get_db()
    rows = conn.execute(
        """SELECT session_dir, task_id, sample_key, predicted_cluster,
                  relative_load_level, relative_load_label, coord_x, coord_y, probabilities, created_at
           FROM prediction_records
           WHERE user_id = ?
           ORDER BY created_at DESC LIMIT ?""",
        (uid, limit),
    ).fetchall()
    conn.close()

    records = []
    for r in rows:
        prob = {}
        try:
            prob = json.loads(r["probabilities"] or "{}")
        except Exception:
            pass
        records.append({
            "session_dir": r["session_dir"],
            "task_id": r["task_id"] or "",
            "sample_key": r["sample_key"] or "",
            "predicted_cluster": r["predicted_cluster"],
            "relative_load_level": r["relative_load_level"] or 0,
            "relative_load_label": r["relative_load_label"] or "",
            "coordinates_2d": [r["coord_x"] or 0.0, r["coord_y"] or 0.0],
            "probabilities": prob,
        })

    return jsonify({"records": records, "total": len(records)})


# ── Logs ───────────────────────────────────────────────────────────────────────


@app.route("/api/system/logs", methods=["GET"])
@require_admin
def system_logs() -> Response:
    """Admin: all system logs."""
    limit = int(request.args.get("limit", 50))
    entries = _read_log_file(UPDATE_LOG_PATH, limit)
    return jsonify({"entries": entries})


@app.route("/api/user/logs", methods=["GET"])
@require_auth
def user_logs() -> Response:
    """User: only their own logs."""
    user = current_user()
    uid = user["id"]
    conn = get_db()
    rows = conn.execute(
        "SELECT action, status, message, extra, created_at FROM log_entries WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
        (uid,),
    ).fetchall()
    conn.close()
    entries = [
        {
            "action": r["action"],
            "status": r["status"],
            "message": r["message"],
            "extra": json.loads(r["extra"]) if r["extra"] else None,
            "timestamp": r["created_at"],
        }
        for r in rows
    ]
    return jsonify({"entries": entries})


# ── System Info ───────────────────────────────────────────────────────────────


@app.route("/api/system/info", methods=["GET"])
def system_info() -> Response:
    """Public system info (no auth required)."""
    import platform, sklearn
    return jsonify({
        "python": platform.python_version(),
        "sklearn": sklearn.__version__,
    })


# ── AI Advice ─────────────────────────────────────────────────────────────────


@app.route("/api/ai/advice", methods=["POST"])
@require_auth
def ai_advice() -> Response:
    """Streaming AI learning advice via Qwen DashScope."""
    if not DASHSCOPE_API_KEY:
        return jsonify({"error": "后端未配置 DASHSCOPE_API_KEY"}), 400

    payload = request.get_json(force=True, silent=True) or {}
    session_filter = str(payload.get("session_filter", "")).strip()
    user = current_user()
    uid = user["id"]

    # Build context from user's prediction records
    conn = get_db()
    rows = conn.execute(
        """SELECT session_dir, task_id, predicted_cluster, relative_load_level, relative_load_label
           FROM prediction_records WHERE user_id = ? LIMIT 200""",
        (uid,),
    ).fetchall()
    conn.close()

    raw_records = [dict(r) for r in rows]
    context = build_advice_context(raw_records, session_filter)
    user_message = USER_MESSAGE_TEMPLATE.format(context=context)

    def generate():
        import requests as _req, re as _re
        headers = {
            "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
            "Content-Type": "application/json",
        }
        payload_req = {
            "model": "qwen-max",
            "messages": [
                {"role": "system", "content": QWEN_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            resp = _req.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers=headers, json=payload_req, timeout=(10, 60), stream=True,
            )
        except _req.exceptions.Timeout:
            yield "data: [TIMEOUT]\n\n"
            return
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
            return

        if resp.status_code != 200:
            yield f"data: [HTTP {resp.status_code}] {resp.text[:200]}\n\n"
            return

        for line in resp.iter_lines():
            if not line:
                continue
            lt = line.decode("utf-8", errors="replace")
            if lt.startswith(":"):
                continue
            m = _re.match(r"data:\s*(.+)", lt)
            if m:
                yield f"data: {m.group(1)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Internal helpers ───────────────────────────────────────────────────────────


def _run_script(
    cmd: List[str],
    action: str,
    params: Dict[str, Any],
    uid: int | None,
) -> Dict[str, Any]:
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
        _append_log(uid, action, "error", msg, params)
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(e), "message": msg}

    ok = proc.returncode == 0
    msg = "执行成功" if ok else f"脚本返回非零退出码：{proc.returncode}"
    _append_log(uid, action, "success" if ok else "error", msg, {**params, "returncode": proc.returncode})
    return {
        "ok": ok,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "message": msg,
    }


def _read_log_file(path: Path, limit: int) -> List[Dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    return entries


# ── Run ───────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("Starting ET_model Multi-user Platform...")
    print(f"Database: {DB_PATH}")
    print(f"Upload base: {UPLOAD_BASE}")
    print("Open http://127.0.0.1:5000 in your browser")
    # Use threaded=True for concurrent request handling; disable reloader to avoid upload issues
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True, use_reloader=False)
