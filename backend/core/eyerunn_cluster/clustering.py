from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, DBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import StandardScaler


Algo = Literal["kmeans", "agglo", "dbscan"]


@dataclass(frozen=True)
class ClusterResult:
    labels: np.ndarray
    embedding_2d: np.ndarray
    silhouette: float | None
    model: object
    pipeline: Pipeline


class FeatureWeighter(BaseEstimator, TransformerMixin):
    def __init__(self, weights: np.ndarray | None = None):
        self.weights = weights

    def fit(self, X: np.ndarray, y: object = None):  # noqa: ANN401
        if self.weights is None:
            self._weights_ = None
            return self
        w = np.asarray(self.weights, dtype="float64").reshape(-1)
        if X.ndim != 2:
            raise ValueError("X 必须为 2D 数组")
        if w.size != X.shape[1]:
            raise ValueError(f"weights 维度不匹配: weights={w.size}, n_features={X.shape[1]}")
        self._weights_ = w
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if self._weights_ is None:
            return X
        return X * self._weights_


def cluster_features(
    features: pd.DataFrame,
    *,
    algo: Algo = "kmeans",
    k: int = 4,
    dbscan_eps: float = 0.8,
    dbscan_min_samples: int = 5,
    random_state: int = 42,
    feature_weights: dict[str, float] | None = None,
) -> ClusterResult:
    if features.empty:
        raise ValueError("features 为空")

    feat_num = features.select_dtypes(include=["number", "bool"]).copy()
    if feat_num.empty:
        raise ValueError("features 中未找到任何数值列")

    X = feat_num.to_numpy(dtype="float64", copy=True)

    w_vec: np.ndarray | None = None
    if feature_weights:
        w_vec = np.ones(feat_num.shape[1], dtype="float64")
        for i, c in enumerate(feat_num.columns):
            if c in feature_weights:
                try:
                    w_vec[i] = float(feature_weights[c])
                except Exception:
                    w_vec[i] = 1.0

    pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
            ("weighter", FeatureWeighter(w_vec)),
        ]
    )
    Xs = pipe.fit_transform(X)

    if algo == "kmeans":
        model = KMeans(n_clusters=int(k), n_init="auto", random_state=random_state)
        labels = model.fit_predict(Xs)
    elif algo == "agglo":
        model = AgglomerativeClustering(n_clusters=int(k), linkage="ward")
        labels = model.fit_predict(Xs)
    elif algo == "dbscan":
        model = DBSCAN(eps=float(dbscan_eps), min_samples=int(dbscan_min_samples))
        labels = model.fit_predict(Xs)
    else:
        raise ValueError(f"未知 algo: {algo}")

    pca = PCA(n_components=2, random_state=random_state)
    emb = pca.fit_transform(Xs)

    sil: float | None = None
    try:
        uniq = sorted(set(int(x) for x in labels))
        n_clusters = len([u for u in uniq if u != -1])
        if n_clusters >= 2:
            sil = float(silhouette_score(Xs, labels))
    except Exception:
        sil = None

    return ClusterResult(labels=labels, embedding_2d=emb, silhouette=sil, model=model, pipeline=pipe)
