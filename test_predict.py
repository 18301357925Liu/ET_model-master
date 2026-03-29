import sys, json, urllib.request, datetime
from pathlib import Path

BASE_DIR = Path(r"D:\Project_code\ET_model-master")
sys.path.insert(0, str(BASE_DIR))

secret = "dev-secret-key-change-in-production"
ef = BASE_DIR / ".env"
if ef.exists():
    for line in ef.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("JWT_SECRET_KEY="):
            secret = line.split("=", 1)[1].strip().strip('"')
            break

import jwt
token = jwt.encode(
    {"sub": "1", "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)},
    secret, algorithm="HS256"
)
print("Token OK")

req = urllib.request.Request(
    "http://127.0.0.1:5000/api/predict-session",
    data=json.dumps({"session_dir": "20260122_204327"}).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
        print("SUCCESS! Got", len(result.get("results", [])), "results")
        for r in result.get("results", []):
            print(" -", r.get("session_id"), r.get("predicted_cluster"), r.get("relative_load_label"))
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="replace")
    print(f"HTTP {e.code}:", body[:2000])
except Exception as e:
    print("Error:", type(e).__name__, str(e))
