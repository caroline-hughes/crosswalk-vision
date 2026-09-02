from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import joblib
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .features import feature_names, rows_to_matrix

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "priority_ranker.joblib"


def _build_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced")),
        ]
    )


@dataclass
class LearnedPriorityScorer:
    include_311: bool = True
    pipeline: Pipeline | None = None
    feature_names_: list[str] | None = None
    label_definition: str = "pedestrian_crash_nearby"

    def __post_init__(self) -> None:
        if self.pipeline is None:
            self.pipeline = _build_pipeline()
        if self.feature_names_ is None:
            self.feature_names_ = feature_names(include_311=self.include_311)

    def fit(self, rows: Sequence[Mapping[str, object]]) -> "LearnedPriorityScorer":
        if not rows:
            raise ValueError("cannot train a ranker on zero rows")
        X = rows_to_matrix(rows, include_311=self.include_311)
        y = np.array([int(row.get("label") or 0) for row in rows], dtype=int)
        if np.unique(y).size < 2:
            # Constant-label folds still need a defined scorer; emit the constant.
            self.pipeline = _ConstantProba(float(y[0]))
        else:
            self.pipeline = _build_pipeline()
            self.pipeline.fit(X, y)
        self.feature_names_ = feature_names(include_311=self.include_311)
        return self

    def predict_scores(self, rows: Sequence[Mapping[str, object]]) -> np.ndarray:
        if not rows:
            return np.zeros(0, dtype=float)
        if self.pipeline is None:
            raise ValueError("scorer has no fitted pipeline")
        X = rows_to_matrix(rows, include_311=self.include_311)
        return _positive_class_scores(self.pipeline, X)

    def save(self, path: Path | None = None) -> Path:
        destination = Path(path) if path is not None else DEFAULT_MODEL_PATH
        destination.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "include_311": self.include_311,
                "label_definition": self.label_definition,
                "feature_names": self.feature_names_,
                "pipeline": self.pipeline,
            },
            destination,
        )
        return destination

    @classmethod
    def load(cls, path: Path | None = None) -> "LearnedPriorityScorer":
        source = Path(path) if path is not None else DEFAULT_MODEL_PATH
        payload = joblib.load(source)
        return cls(
            include_311=bool(payload.get("include_311", True)),
            pipeline=payload["pipeline"],
            feature_names_=list(payload.get("feature_names") or []),
            label_definition=str(payload.get("label_definition") or "pedestrian_crash_nearby"),
        )


class _ConstantProba:
    def __init__(self, value: float) -> None:
        self.value = value
        self.classes_ = np.array([0, 1] if value in (0.0, 1.0) else [value])

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        positive = np.full((len(X),), self.value, dtype=float)
        return np.column_stack([1.0 - positive, positive])


def _positive_class_scores(model: object, X: np.ndarray) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        proba = np.asarray(model.predict_proba(X), dtype=float)
        classes = getattr(model, "classes_", None)
        if classes is None and hasattr(model, "named_steps"):
            classes = getattr(model.named_steps.get("clf"), "classes_", None)
        if classes is None:
            return proba[:, -1]
        classes = list(classes)
        if 1 in classes:
            return proba[:, classes.index(1)]
        if len(classes) == 1:
            constant = float(classes[0])
            return np.full(len(X), constant, dtype=float)
        return proba[:, -1]
    if hasattr(model, "decision_function"):
        raw = np.asarray(model.decision_function(X), dtype=float)
        return 1.0 / (1.0 + np.exp(-raw))
    raise TypeError("fitted model cannot produce ranking scores")
