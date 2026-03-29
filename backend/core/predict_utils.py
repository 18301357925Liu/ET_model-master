from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .eyerunn_cluster.cognitive import extract_cognitive_features


# 兜底映射：当找不到 cluster_load_mapping.csv 时使用
# 对齐到 task 级 6 类模型的默认语义
_FALLBACK_CLUSTER_LOAD_MAPPING: dict[str, tuple[int, str]] = {
    "0": (2, "低负荷 / 轻量任务型"),
    "1": (2, "低负荷 / 轻量任务型"),
    "2": (3, "中高负荷 / 信息整合型"),
    "3": (4, "高负荷 / 持续专注解题型"),
    "4": (3, "中高负荷 / 信息整合型"),
    "5": (1, "极低负荷 / 轻松浏览型"),
}

DEFAULT_LOAD_LEVEL = 0
DEFAULT_LOAD_LABEL = "未知负荷"


def _load_cluster_load_mapping_csv(path: Path) -> dict[str, tuple[int, str]]:
    mapping: dict[str, tuple[int, str]] = {}
    if not path.exists():
        return mapping
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            c = str(row.get("cluster", "")).strip()
            if c == "":
                continue
            try:
                level = int(str(row.get("relative_load_level", "")).strip())
            except Exception:
                level = DEFAULT_LOAD_LEVEL
            label = str(row.get("relative_load_label", "")).strip()
            if label == "":
                label = DEFAULT_LOAD_LABEL
            mapping[c] = (level, label)
    return mapping


def get_relative_load_for_cluster(
    cluster: str | int,
    *,
    mapping: dict[str, tuple[int, str]] | None = None,
) -> tuple[int, str]:
    m = mapping or _FALLBACK_CLUSTER_LOAD_MAPPING
    return m.get(str(cluster), (DEFAULT_LOAD_LEVEL, DEFAULT_LOAD_LABEL))


@dataclass(frozen=True)
class PredictionResult:
    sample_key: str
    session_id: str
    task_id: str | None
    predicted_cluster: str
    predicted_cluster_encoded: int
    coordinates_2d: tuple[float, float]
    probabilities: dict[str, float]
    relative_load_level: int
    relative_load_label: str


class SessionPredictor:
    def __init__(
        self,
        classifier_model: str | Path,
        pca_model: str | Path,
        features_template: str | Path,
    ):
        self.classifier_model_path = Path(classifier_model)
        self.pca_model_path = Path(pca_model)
        self.features_template_path = Path(features_template)

        if not self.classifier_model_path.exists():
            raise FileNotFoundError(f"分类器模型不存在: {self.classifier_model_path}")
        if not self.pca_model_path.exists():
            raise FileNotFoundError(f"PCA 模型不存在: {self.pca_model_path}")
        if not self.features_template_path.exists():
            raise FileNotFoundError(f"特征模板不存在: {self.features_template_path}")

        self._clf_data: dict[str, Any] | None = None
        self._pca_data: dict[str, Any] | None = None
        self._feat_cols: list[str] | None = None
        self._cluster_load_mapping: dict[str, tuple[int, str]] | None = None

    def _ensure_loaded(self) -> None:
        if self._clf_data is None:
            self._clf_data = joblib.load(self.classifier_model_path)
        if self._pca_data is None:
            self._pca_data = joblib.load(self.pca_model_path)
        if self._feat_cols is None:
            model_cols = None
            try:
                model_cols = self._clf_data.get("feature_columns")
            except Exception:
                model_cols = None

            if isinstance(model_cols, list) and model_cols:
                self._feat_cols = [str(c) for c in model_cols]
            else:
                feats_template = pd.read_csv(self.features_template_path, index_col=0)
                self._feat_cols = [c for c in feats_template.columns if c != "sample_key"]

            try:
                feats_template = pd.read_csv(self.features_template_path, index_col=0)
                template_cols = [c for c in feats_template.columns if c != "sample_key"]
                if self._feat_cols and len(template_cols) != len(self._feat_cols):
                    print(
                        "[WARN] features_template 与分类器模型的训练特征维度不一致："
                        f"template={len(template_cols)} vs model={len(self._feat_cols)}。"
                        "将按模型训练列名对齐。"
                    )
            except Exception:
                pass

        if self._cluster_load_mapping is None:
            mapping_path = self.features_template_path.parent / "cluster_load_mapping.csv"
            loaded = _load_cluster_load_mapping_csv(mapping_path)
            self._cluster_load_mapping = loaded if loaded else _FALLBACK_CLUSTER_LOAD_MAPPING

    def _predict_from_features(
        self,
        feats_row: pd.DataFrame,
    ) -> tuple[str, PredictionResult]:
        assert len(feats_row) == 1
        sample_key = str(feats_row.index[0])

        if "::task=" in sample_key:
            session_id, task_part = sample_key.split("::task=", 1)
            task_id: str | None = task_part or None
        else:
            session_id = sample_key
            task_id = None

        feats_new_aligned = feats_row.reindex(columns=self._feat_cols, fill_value=np.nan)

        clf_model = self._clf_data["model"]
        label_encoder = self._clf_data["label_encoder"]

        cluster_pred = clf_model.predict(feats_new_aligned)[0]
        cluster_name = label_encoder.inverse_transform([cluster_pred])[0]

        if hasattr(clf_model, "predict_proba"):
            proba = clf_model.predict_proba(feats_new_aligned)[0]
            proba_dict = {label_encoder.inverse_transform([i])[0]: float(p) for i, p in enumerate(proba)}
        else:
            proba_dict = {}

        pca_pipeline = self._pca_data["pipeline"]
        pca_model = self._pca_data["pca"]

        feats_for_pca = feats_new_aligned
        expected_n = getattr(pca_pipeline, "n_features_in_", None)
        if expected_n is not None and feats_new_aligned.shape[1] != int(expected_n):
            default_prefixes = ("fix__", "blink__", "trans__", "task__")
            cols_subset = [c for c in feats_new_aligned.columns if c.startswith(default_prefixes)]
            if len(cols_subset) == int(expected_n):
                feats_for_pca = feats_new_aligned[cols_subset]
            else:
                feats_for_pca = None

        if feats_for_pca is None:
            x = float("nan")
            y = float("nan")
        else:
            X_processed = pca_pipeline.transform(feats_for_pca)
            coords_2d = pca_model.transform(X_processed)[0]
            x, y = float(coords_2d[0]), float(coords_2d[1])

        load_level, load_label = get_relative_load_for_cluster(
            cluster_name,
            mapping=self._cluster_load_mapping,
        )

        result = PredictionResult(
            sample_key=sample_key,
            session_id=session_id,
            task_id=task_id,
            predicted_cluster=str(cluster_name),
            predicted_cluster_encoded=int(cluster_pred),
            coordinates_2d=(x, y),
            probabilities=proba_dict,
            relative_load_level=load_level,
            relative_load_label=load_label,
        )
        return sample_key, result

    def predict(
        self,
        session_dir: str | Path,
    ) -> list[PredictionResult]:
        self._ensure_loaded()

        session_dir = Path(session_dir)
        if not session_dir.exists():
            raise FileNotFoundError(f"session 目录不存在: {session_dir}")

        feats_new = extract_cognitive_features(session_dir, unit="task")
        if feats_new.empty:
            raise ValueError("未能从该 session 提取到任何特征")

        results: list[PredictionResult] = []
        for idx in feats_new.index:
            feats_row = feats_new.loc[[idx]]
            _, r = self._predict_from_features(feats_row)
            results.append(r)
        return results


def predict_session(
    session_dir: str | Path,
    *,
    classifier_model: str | Path = "outputs_supervised_task/model_svm.joblib",
    pca_model: str | Path = "outputs_task_cluster/pca_model.joblib",
    features_template: str | Path = "outputs_task_cluster/features.csv",
) -> list[PredictionResult]:
    predictor = SessionPredictor(
        classifier_model=classifier_model,
        pca_model=pca_model,
        features_template=features_template,
    )
    return predictor.predict(session_dir)
