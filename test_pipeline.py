"""Test pipeline rebuild by simulating what the FastAPI route does."""
import subprocess, sys, json
from pathlib import Path

BASE_DIR = Path(r"D:\Project_code\ET_model-master")

cmd = [
    sys.executable,
    str(BASE_DIR / "cluster_cognitive_data.py"),
    "--data_root", "uploads/1/data",
    "--unit", "task",
    "--k", "4",
    "--algo", "kmeans",
    "--out_dir", str(BASE_DIR / "outputs_task_cluster"),
    "--feature_weights_json", str(BASE_DIR / "feature_weights_task.json"),
]
print("Running:", " ".join(cmd))
proc = subprocess.run(
    cmd,
    cwd=str(BASE_DIR),
    capture_output=True,
    text=True,
    encoding="utf-8",
)
print("Return code:", proc.returncode)
print("STDOUT:", proc.stdout[:2000] if proc.stdout else "(empty)")
print("STDERR:", proc.stderr[:2000] if proc.stderr else "(empty)")
