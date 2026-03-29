"""
FastAPI main application - entry point for the backend API.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend/ is on path
_backend_root = Path(__file__).resolve().parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db.database import init_db
from backend.api.routers import auth, predictions, pipeline, realtime, system, tasks, ai_advice
from backend.config import BASE_DIR


# ── Init database ─────────────────────────────────────────────────────────────

init_db()


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ET_model API",
    description="Cognitive Load Prediction API - Eye Tracking ML Model",
    version="1.0.0",
)


# ── CORS ───────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Register routers ───────────────────────────────────────────────────────────

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(predictions.router, prefix="/api", tags=["Predictions"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["Pipeline"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(realtime.router, prefix="/api/realtime", tags=["Realtime"])
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(ai_advice.router, prefix="/api/ai", tags=["AI Advice"])


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/")
def root():
    return {
        "message": "ET_model API is running.",
        "docs": "/docs",
        "health": "/health",
    }
