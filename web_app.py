from __future__ import annotations

"""
Simple web interface for ET_model, exposing HTTP APIs that correspond to
the main usage flows described in README.md:

- 预测新数据（离线单 session）：基于已训练好的任务级监督模型；
- 离线任务级浏览：读取 task 聚类结果与负荷映射并在网页中展示。

运行方式（在项目根目录）::

    # 安装 Flask（如未安装）
    #   python -m pip install flask
    #
    # 启动服务
    python web_app.py

默认监听 http://127.0.0.1:5000 ，在浏览器中打开即可使用。
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import subprocess
import sys
import json
from datetime import datetime
import threading

from flask import Flask, jsonify, request, send_from_directory

from predict_utils import predict_session
from offline_task_dashboard import load_task_records


BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_TASK_CLUSTER = BASE_DIR / "outputs_task_cluster"
OUTPUTS_SUPERVISED_TASK = BASE_DIR / "outputs_supervised_task"
UPDATE_LOG_PATH = BASE_DIR / "web_update_log.jsonl"
REALTIME_LOG_PATH = BASE_DIR / "realtime_predictions_task_supervised.jsonl"
MONITOR_SCRIPT = BASE_DIR / "realtime_session_monitor.py"

app = Flask(__name__, static_folder="web", static_url_path="/static")

# 全局变量：存储监控进程
_monitor_process: Optional[subprocess.Popen] = None
_monitor_lock = threading.Lock()


def _append_update_log(
    action: str,
    status: str,
    message: str,
    extra: Dict[str, Any] | None = None,
) -> None:
    """
    追加一条 JSON 行到 web_update_log.jsonl，便于在网页或命令行中查看历史更新记录。
    """
    entry: Dict[str, Any] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "status": status,
        "message": message,
    }
    if extra:
        entry.update(extra)
    try:
        with UPDATE_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # 日志写入失败不应影响主流程
        pass


def _run_script(
    cmd: List[str],
    action: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    在项目根目录下以子进程方式运行脚本，并记录到更新日志。
    """
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except Exception as e:  # noqa: BLE001
        msg = f"执行失败：{e}"
        _append_update_log(
            action,
            "error",
            msg,
            {"params": params},
        )
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(e),
            "message": msg,
        }

    ok = proc.returncode == 0
    msg = "执行成功" if ok else f"脚本返回非零退出码：{proc.returncode}"
    _append_update_log(
        action,
        "success" if ok else "error",
        msg,
        {
            "params": params,
            "returncode": proc.returncode,
        },
    )
    return {
        "ok": ok,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "message": msg,
    }


@app.route("/", methods=["GET"])
def index() -> Any:
    """Serve the main single-page web UI."""
    index_path = BASE_DIR / "web" / "index.html"
    if not index_path.exists():
        return "index.html not found. Please make sure web/index.html exists.", 404
    return send_from_directory(str(index_path.parent), index_path.name)


@app.route("/api/predict-session", methods=["POST"])
def api_predict_session() -> Any:
    """
    预测单个 session 内所有 task 的 cluster / 2D 坐标 / 相对负荷等级。

    对应 README 中“预测新数据（离线单 session）”一节。

    请求 JSON 示例::

        {
          "session_dir": "data/20260124_140152",
          "classifier_model": "outputs_supervised_task/model_svm.joblib",  # 可选
          "pca_model": "outputs_task_cluster/pca_model.joblib",             # 可选
          "features_template": "outputs_task_cluster/features.csv"         # 可选
        }
    """
    payload: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
    session_dir = payload.get("session_dir")
    if not session_dir:
        return jsonify({"error": "session_dir 字段必填"}), 400

    classifier_model = payload.get(
        "classifier_model", "outputs_supervised_task/model_svm.joblib"
    )
    pca_model = payload.get("pca_model", "outputs_task_cluster/pca_model.joblib")
    features_template = payload.get(
        "features_template", "outputs_task_cluster/features.csv"
    )

    try:
        results = predict_session(
            session_dir,
            classifier_model=classifier_model,
            pca_model=pca_model,
            features_template=features_template,
        )
    except Exception as e:  # noqa: BLE001
        return jsonify(
            {
                "error": str(e),
                "detail": type(e).__name__,
            }
        ), 500

    rows: List[Dict[str, Any]] = []
    for r in results:
        x, y = r.coordinates_2d
        rows.append(
            {
                "sample_key": r.sample_key,
                "session_id": r.session_id,
                "task_id": r.task_id,
                "predicted_cluster": r.predicted_cluster,
                "predicted_cluster_encoded": r.predicted_cluster_encoded,
                "coordinates_2d": {"x": float(x), "y": float(y)},
                "probabilities": r.probabilities,
                "relative_load_level": r.relative_load_level,
                "relative_load_label": r.relative_load_label,
            }
        )

    return jsonify({"session_dir": session_dir, "results": rows})


@app.route("/api/task-records", methods=["GET"])
def api_task_records() -> Any:
    """
    返回离线任务级聚类 + 负荷映射的记录列表。

    对应 README / WORKLOG 中“离线任务浏览面板”的数据源：
    - outputs_task_cluster/clusters.csv
    - outputs_task_cluster/cluster_load_mapping.csv
    """
    clusters_path = BASE_DIR / "outputs_task_cluster" / "clusters.csv"
    mapping_path = BASE_DIR / "outputs_task_cluster" / "cluster_load_mapping.csv"

    try:
        records = load_task_records(
            clusters_path=clusters_path,
            mapping_path=mapping_path,
        )
    except Exception as e:  # noqa: BLE001
        return jsonify(
            {
                "error": str(e),
                "detail": type(e).__name__,
            }
        ), 500

    rows: List[Dict[str, Any]] = [
        {
            "session": r.session,
            "task_id": r.task_id,
            "cluster": r.cluster,
            "level": r.level,
            "label": r.label,
        }
        for r in records
    ]
    return jsonify({"records": rows})


@app.route("/api/rebuild-task-pipeline", methods=["POST"])
def api_rebuild_task_pipeline() -> Any:
    """
    一键更新任务级 pipeline：
    1) 按 task 重新聚类（cluster_cognitive_data.py）；
    2) 基于聚类结果生成相对负荷映射（summarize_cluster_load.py）；
    3) 使用 task 级特征/标签重新训练监督模型（train_classifier.py）。

    该接口用于在网页中替代 README/WORKLOG 中的多条命令行操作，并在本地写入简单的更新日志。
    """
    payload: Dict[str, Any] = request.get_json(force=True, silent=True) or {}

    # 聚类参数（提供合理默认值，必要时可在前端暴露）
    data_root = str(payload.get("data_root", "data"))
    k = int(payload.get("k", 6))
    algo = str(payload.get("algo", "kmeans"))
    mapping_mode = str(payload.get("mapping_mode", "auto"))
    clf_algo = str(payload.get("classifier_algo", "svm"))

    OUTPUTS_TASK_CLUSTER.mkdir(parents=True, exist_ok=True)
    OUTPUTS_SUPERVISED_TASK.mkdir(parents=True, exist_ok=True)

    steps: List[Dict[str, Any]] = []

    # 1) 按 task 聚类
    cluster_cmd = [
        sys.executable,
        str(BASE_DIR / "cluster_cognitive_data.py"),
        "--data_root",
        data_root,
        "--unit",
        "task",
        "--k",
        str(k),
        "--algo",
        algo,
        "--out_dir",
        str(OUTPUTS_TASK_CLUSTER),
        "--feature_weights_json",
        str(BASE_DIR / "feature_weights_task.json"),
    ]
    cluster_result = _run_script(
        cluster_cmd,
        action="task_cluster",
        params={
            "data_root": data_root,
            "unit": "task",
            "k": k,
            "algo": algo,
            "out_dir": str(OUTPUTS_TASK_CLUSTER),
        },
    )
    steps.append({"name": "task_cluster", **cluster_result})
    if not cluster_result["ok"]:
        return jsonify(
            {
                "error": "任务级聚类失败",
                "steps": steps,
            }
        ), 500

    # 2) 生成 cluster → 负荷映射
    summarize_cmd = [
        sys.executable,
        str(BASE_DIR / "summarize_cluster_load.py"),
        "--features",
        str(OUTPUTS_TASK_CLUSTER / "features.csv"),
        "--clusters",
        str(OUTPUTS_TASK_CLUSTER / "clusters.csv"),
        "--out_dir",
        str(OUTPUTS_TASK_CLUSTER),
        "--mapping_mode",
        mapping_mode,
    ]
    summarize_result = _run_script(
        summarize_cmd,
        action="summarize_cluster_load",
        params={
            "features": str(OUTPUTS_TASK_CLUSTER / "features.csv"),
            "clusters": str(OUTPUTS_TASK_CLUSTER / "clusters.csv"),
            "out_dir": str(OUTPUTS_TASK_CLUSTER),
            "mapping_mode": mapping_mode,
        },
    )
    steps.append({"name": "summarize_cluster_load", **summarize_result})
    if not summarize_result["ok"]:
        return jsonify(
            {
                "error": "生成相对负荷映射失败",
                "steps": steps,
            }
        ), 500

    # 3) 重新训练监督模型（使用 task 级特征和聚类标签）
    train_cmd = [
        sys.executable,
        str(BASE_DIR / "train_classifier.py"),
        "--features",
        str(OUTPUTS_TASK_CLUSTER / "features.csv"),
        "--labels",
        str(OUTPUTS_TASK_CLUSTER / "clusters.csv"),
        "--out_dir",
        str(OUTPUTS_SUPERVISED_TASK),
        "--algo",
        clf_algo,
    ]
    train_result = _run_script(
        train_cmd,
        action="train_classifier",
        params={
            "features": str(OUTPUTS_TASK_CLUSTER / "features.csv"),
            "labels": str(OUTPUTS_TASK_CLUSTER / "clusters.csv"),
            "out_dir": str(OUTPUTS_SUPERVISED_TASK),
            "algo": clf_algo,
        },
    )
    steps.append({"name": "train_classifier", **train_result})
    if not train_result["ok"]:
        return jsonify(
            {
                "error": "监督模型训练失败",
                "steps": steps,
            }
        ), 500

    return jsonify(
        {
            "message": "任务级 pipeline 更新完成",
            "steps": steps,
        }
    )


@app.route("/api/update-log", methods=["GET"])
def api_update_log() -> Any:
    """
    读取最近的更新日志（默认最多 50 条），方便在网页上快速查看。
    """
    limit = 50
    try:
        limit = int(request.args.get("limit", limit))
    except Exception:
        limit = 50

    entries: List[Dict[str, Any]] = []
    if UPDATE_LOG_PATH.exists():
        try:
            lines = UPDATE_LOG_PATH.read_text(encoding="utf-8").splitlines()
            for line in lines[-limit:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
        except Exception:
            # 读取失败时返回空列表即可
            entries = []

    return jsonify({"entries": entries})


@app.route("/api/realtime-monitor/status", methods=["GET"])
def api_realtime_monitor_status() -> Any:
    """
    获取实时监控进程的状态。
    """
    global _monitor_process
    with _monitor_lock:
        is_running = _monitor_process is not None
        if is_running:
            # 检查进程是否还在运行
            if _monitor_process.poll() is not None:
                # 进程已结束
                is_running = False
                _monitor_process = None
        
        return jsonify({
            "running": is_running,
            "log_path": str(REALTIME_LOG_PATH),
        })


@app.route("/api/realtime-monitor/start", methods=["POST"])
def api_realtime_monitor_start() -> Any:
    """
    启动实时监控进程。
    """
    global _monitor_process
    
    payload: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
    watch_dirs = payload.get("watch_dirs", ["Cognitive/data/cognitive_study", "data"])
    interval = int(payload.get("interval", 10))
    
    with _monitor_lock:
        if _monitor_process is not None:
            # 检查进程是否还在运行
            if _monitor_process.poll() is None:
                return jsonify({"error": "监控进程已在运行中"}), 400
            else:
                # 进程已结束，清理引用
                _monitor_process = None
        
        if not MONITOR_SCRIPT.exists():
            return jsonify({"error": f"监控脚本不存在: {MONITOR_SCRIPT}"}), 404
        
        cmd = [
            sys.executable,
            str(MONITOR_SCRIPT),
            "--watch_dirs",
            *watch_dirs,
            "--interval",
            str(interval),
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
            _append_update_log(
                "realtime_monitor_start",
                "success",
                f"启动实时监控进程，监控目录: {', '.join(watch_dirs)}, 间隔: {interval}秒",
                {"watch_dirs": watch_dirs, "interval": interval},
            )
            return jsonify({
                "message": "实时监控已启动",
                "pid": proc.pid,
                "watch_dirs": watch_dirs,
                "interval": interval,
            })
        except Exception as e:  # noqa: BLE001
            _append_update_log(
                "realtime_monitor_start",
                "error",
                f"启动实时监控失败: {e}",
            )
            return jsonify({"error": f"启动失败: {e}"}), 500


@app.route("/api/realtime-monitor/stop", methods=["POST"])
def api_realtime_monitor_stop() -> Any:
    """
    停止实时监控进程。
    """
    global _monitor_process
    
    with _monitor_lock:
        if _monitor_process is None:
            return jsonify({"error": "监控进程未运行"}), 400
        
        try:
            _monitor_process.terminate()
            try:
                _monitor_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _monitor_process.kill()
                _monitor_process.wait()
            
            _monitor_process = None
            _append_update_log(
                "realtime_monitor_stop",
                "success",
                "实时监控进程已停止",
            )
            return jsonify({"message": "实时监控已停止"})
        except Exception as e:  # noqa: BLE001
            _monitor_process = None
            _append_update_log(
                "realtime_monitor_stop",
                "error",
                f"停止实时监控失败: {e}",
            )
            return jsonify({"error": f"停止失败: {e}"}), 500


@app.route("/api/realtime-predictions", methods=["GET"])
def api_realtime_predictions() -> Any:
    """
    读取实时预测数据（从 JSONL 文件）。
    
    支持 limit 参数限制返回的记录数（默认 50）。
    """
    limit = 50
    try:
        limit = int(request.args.get("limit", limit))
    except Exception:
        limit = 50
    
    records: List[Dict[str, Any]] = []
    if REALTIME_LOG_PATH.exists():
        try:
            lines = REALTIME_LOG_PATH.read_text(encoding="utf-8").splitlines()
            for line in lines[-limit:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    # 提取关键字段
                    record = {
                        "session_dir": obj.get("session_dir", ""),
                        "task_id": str(obj.get("task_id") or "__all__"),
                        "sample_key": str(obj.get("sample_key", "")),
                        "predicted_cluster": obj.get("predicted_cluster"),
                        "relative_load_level": int(obj.get("relative_load_level", -1)),
                        "relative_load_label": str(obj.get("relative_load_label", "")),
                        "coordinates_2d": obj.get("coordinates_2d", [0.0, 0.0]),
                        "probabilities": obj.get("probabilities", {}),
                    }
                    records.append(record)
                except Exception:
                    continue
        except Exception:
            # 读取失败时返回空列表即可
            records = []
    
    return jsonify({
        "records": records,
        "total": len(records),
    })


if __name__ == "__main__":
    # 默认仅监听本机，端口 5000
    app.run(host="127.0.0.1", port=5000, debug=True)

