"""
Predictions router - /api/predict-session
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db import crud
from backend.api.schemas import PredictSessionRequest, PredictSessionResponse, PredictionResultItem
from backend.config import DEFAULT_CLF_MODEL, DEFAULT_PCA_MODEL, DEFAULT_FEATURES_TEMPLATE


router = APIRouter()


@router.post("/predict-session", response_model=PredictSessionResponse)
def predict_session(
    payload: PredictSessionRequest,
    db: Session = Depends(get_db),
):
    """
    Predict cluster / 2D coordinates / relative load level for all tasks
    in a single session directory.
    """
    from backend.core import SessionPredictor

    session_dir = payload.session_dir
    if not session_dir:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_dir is required",
        )

    clf_model = payload.classifier_model or DEFAULT_CLF_MODEL
    pca_model = payload.pca_model or DEFAULT_PCA_MODEL
    features_template = payload.features_template or DEFAULT_FEATURES_TEMPLATE

    try:
        predictor = SessionPredictor(
            classifier_model=clf_model,
            pca_model=pca_model,
            features_template=features_template,
        )
        results = predictor.predict(session_dir)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {e}",
        )

    rows: list[PredictionResultItem] = []
    for r in results:
        x, y = r.coordinates_2d
        item = PredictionResultItem(
            sample_key=r.sample_key,
            session_id=r.session_id,
            task_id=r.task_id,
            predicted_cluster=r.predicted_cluster,
            predicted_cluster_encoded=r.predicted_cluster_encoded,
            coordinates_2d={"x": float(x), "y": float(y)},
            probabilities=r.probabilities,
            relative_load_level=r.relative_load_level,
            relative_load_label=r.relative_load_label,
        )
        rows.append(item)

        # Save to DB
        try:
            crud.create_prediction_record(
                db=db,
                session_dir=session_dir,
                task_id=r.task_id,
                sample_key=r.sample_key,
                predicted_cluster=r.predicted_cluster,
                relative_load_level=r.relative_load_level,
                relative_load_label=r.relative_load_label,
                coord_x=float(x) if x == x else None,  # nan check
                coord_y=float(y) if y == y else None,
                probabilities=r.probabilities,
            )
        except Exception:
            # DB write failure should not break the API response
            pass

    return PredictSessionResponse(session_dir=session_dir, results=rows)
