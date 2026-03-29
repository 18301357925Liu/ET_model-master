import sqlite3, json

conn = sqlite3.connect('et_model.db')
session_filter = ""
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
print("Results:", [dict(r) for r in rows[:3]])
