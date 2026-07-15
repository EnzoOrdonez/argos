"""ARGOS Layer 2 anomaly ensemble.

This module trains two unsupervised anomaly detectors:

- Isolation Forest
- One-Class SVM

Both models are trained with benign activity windows. At inference time, their
outputs are normalized into 0.0-1.0 anomaly scores and combined into one
ensemble score consumed by the SOAR tier logic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from argos_contracts.ml_score import MLFeatures, MLScore
from ml.models.vectorizer import features_to_matrix, features_to_vector


@dataclass(frozen=True)
class _Calibration:
    """Maps sklearn decision_function values into ARGOS anomaly scores."""

    threshold: float
    scale: float

    def to_anomaly_score(self, decision_value: float) -> float:
        """Return anomaly score from 0.0 to 1.0.

        In sklearn anomaly models, lower decision_function values usually mean
        more anomalous behavior. Therefore, scores below the learned threshold
        become higher anomaly scores.
        """
        x = (self.threshold - decision_value) / self.scale
        x = float(np.clip(x, -60.0, 60.0))
        return round(float(1.0 / (1.0 + np.exp(-x))), 4)


def _build_calibration(decision_values: np.ndarray) -> _Calibration:
    """Build calibration from benign decision values."""
    p05 = float(np.percentile(decision_values, 5))
    p50 = float(np.percentile(decision_values, 50))
    scale = max((p50 - p05) / 3.0, 1e-6)

    return _Calibration(threshold=p05, scale=scale)


class Layer2AnomalyEnsemble:
    """Isolation Forest + One-Class SVM ensemble for ransomware anomaly scoring."""

    def __init__(
        self,
        *,
        model_version: str = "iforest-v0.1-svm-v0.1",
        iforest_weight: float = 0.55,
        random_state: int = 42,
    ) -> None:
        if not 0.0 <= iforest_weight <= 1.0:
            raise ValueError("iforest_weight must be between 0.0 and 1.0")

        self.model_version = model_version
        self.iforest_weight = iforest_weight
        self.random_state = random_state

        self.iforest: Pipeline | None = None
        self.ocsvm: Pipeline | None = None
        self._iforest_calibration: _Calibration | None = None
        self._ocsvm_calibration: _Calibration | None = None

    def fit(self, benign_windows: Sequence[MLFeatures]) -> Layer2AnomalyEnsemble:
        """Train both anomaly detectors using benign activity windows."""
        x_train = features_to_matrix(benign_windows)

        self.iforest = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "model",
                    IsolationForest(
                        n_estimators=100,
                        contamination=0.05,
                        random_state=self.random_state,
                    ),
                ),
            ]
        )

        self.ocsvm = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "model",
                    OneClassSVM(
                        kernel="rbf",
                        gamma="scale",
                        nu=0.05,
                    ),
                ),
            ]
        )

        self.iforest.fit(x_train)
        self.ocsvm.fit(x_train)

        self._iforest_calibration = _build_calibration(
            self.iforest.decision_function(x_train)
        )
        self._ocsvm_calibration = _build_calibration(
            self.ocsvm.decision_function(x_train)
        )

        return self

    def predict_score(
        self,
        features: MLFeatures,
        *,
        host_id: str,
        process_id: int | None = None,
        process_name: str | None = None,
        score_id: str | None = None,
    ) -> MLScore:
        """Return a validated MLScore contract for one activity window."""
        if (
            self.iforest is None
            or self.ocsvm is None
            or self._iforest_calibration is None
            or self._ocsvm_calibration is None
        ):
            raise RuntimeError("The ensemble must be fitted before calling predict_score().")

        x_event = features_to_vector(features).reshape(1, -1)

        iforest_decision = float(self.iforest.decision_function(x_event)[0])
        ocsvm_decision = float(self.ocsvm.decision_function(x_event)[0])

        iforest_score = self._iforest_calibration.to_anomaly_score(iforest_decision)
        ocsvm_score = self._ocsvm_calibration.to_anomaly_score(ocsvm_decision)

        ensemble_score = round(
            (self.iforest_weight * iforest_score)
            + ((1.0 - self.iforest_weight) * ocsvm_score),
            4,
        )

        return MLScore(
            score_id=score_id or f"ml-{uuid4().hex[:12]}",
            timestamp=datetime.now(UTC),
            host_id=host_id,
            process_id=process_id,
            process_name=process_name,
            isolation_forest_score=iforest_score,
            one_class_svm_score=ocsvm_score,
            ensemble_score=ensemble_score,
            features=features,
            model_version=self.model_version,
        )
