"""
AI Advice router - /api/ai/advice (SSE streaming)
"""
from __future__ import annotations

import re
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.config import (
    BASE_DIR,
    OUTPUTS_TASK_CLUSTER,
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    DASHSCOPE_MODEL,
)
from backend.api.schemas import AIAdviceRequest


router = APIRouter()


def _load_task_records_from_csv() -> list[dict]:
    """Load task records from pipeline CSV output for AI context."""
    import sys

    project_root = str(BASE_DIR)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from offline_task_dashboard import load_task_records

    clusters_path = OUTPUTS_TASK_CLUSTER / "clusters.csv"
    mapping_path = OUTPUTS_TASK_CLUSTER / "cluster_load_mapping.csv"

    try:
        records = load_task_records(clusters_path=clusters_path, mapping_path=mapping_path)
    except Exception:
        return []

    return [
        {"session": r.session, "task_id": r.task_id,
         "cluster": r.cluster, "level": r.level, "label": r.label}
        for r in records
    ]


def _stream_ai_advice(session_filter: str = ""):
    """
    Generator function for SSE streaming from Qwen DashScope.
    Yields SSE-formatted chunks.
    """
    from backend.core.prompts import (
        QWEN_SYSTEM_PROMPT,
        USER_MESSAGE_TEMPLATE,
        build_advice_context,
    )

    # Load API key from config
    api_key = DASHSCOPE_API_KEY
    if not api_key:
        yield "data: [ERROR] 后端未配置 DASHSCOPE_API_KEY 环境变量\n\n"
        return

    # Load task records
    raw_records = _load_task_records_from_csv()
    context = build_advice_context(raw_records, session_filter)
    user_message = USER_MESSAGE_TEMPLATE.format(context=context)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload_req = {
        "model": DASHSCOPE_MODEL,
        "messages": [
            {"role": "system", "content": QWEN_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    try:
        resp = requests.post(
            f"{DASHSCOPE_BASE_URL}/chat/completions",
            headers=headers,
            json=payload_req,
            timeout=(10, 60),
            stream=True,
        )
    except requests.exceptions.Timeout:
        yield "data: [TIMEOUT]\n\n"
        return
    except Exception as e:
        yield f"data: [ERROR] {str(e)}\n\n"
        return

    if resp.status_code != 200:
        body = resp.text
        yield f"data: [HTTP {resp.status_code}] {body}\n\n"
        return

    # Parse SSE stream
    for line in resp.iter_lines():
        if not line:
            continue
        line_text = line.decode("utf-8", errors="replace")
        if line_text.startswith(":"):
            continue
        m = re.match(r"data:\s*(.+)", line_text)
        if m:
            raw = m.group(1)
            yield f"data: {raw}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/advice")
def ai_advice(payload: AIAdviceRequest):
    """
    Streaming SSE endpoint for AI learning advice from Qwen DashScope.
    Frontend uses ReadableStream / EventSource to consume the response.
    """
    api_key = DASHSCOPE_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="后端未配置 DASHSCOPE_API_KEY 环境变量",
        )

    return StreamingResponse(
        _stream_ai_advice(session_filter=payload.session_filter),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
