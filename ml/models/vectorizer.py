"""Vectorization utilities for ARGOS Layer 2 ML models."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from argos_contracts.ml_score import MLFeatures

FEATURE_NAMES = (
    "file_write_rate",
    "avg_entropy",
    "extension_modification_ratio",
    "crypto_api_calls",
    "new_outbound_connections",
    "cpu_burst_score",
    "io_burst_score",
)


def features_to_vector(features: MLFeatures) -> np.ndarray:
    """Convert one MLFeatures object into a numeric vector."""
    return np.array(
        [float(getattr(features, feature_name)) for feature_name in FEATURE_NAMES],
        dtype=float,
    )


def features_to_matrix(rows: Sequence[MLFeatures]) -> np.ndarray:
    """Convert multiple MLFeatures objects into a 2D matrix."""
    if not rows:
        raise ValueError("At least one MLFeatures row is required")

    return np.vstack([features_to_vector(row) for row in rows])
