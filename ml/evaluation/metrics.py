"""Evaluation metrics for ARGOS Layer 2 ML detection."""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score


@dataclass(frozen=True)
class DetectionMetrics:
    """Binary detection metrics for ransomware anomaly detection."""

    threshold: float
    precision: float
    recall: float
    f1: float
    accuracy: float
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int


def predict_labels(scores: list[float], *, threshold: float) -> list[int]:
    """Convert anomaly scores into binary labels.

    Args:
        scores: Anomaly scores from 0.0 to 1.0.
        threshold: Decision threshold.

    Returns:
        1 means ransomware/anomaly, 0 means benign.
    """
    return [1 if score >= threshold else 0 for score in scores]


def evaluate_binary_detection(
    y_true: list[int],
    y_score: list[float],
    *,
    threshold: float = 0.74,
) -> DetectionMetrics:
    """Evaluate binary anomaly detection at one threshold."""
    if len(y_true) != len(y_score):
        raise ValueError("y_true and y_score must have the same length")

    if not y_true:
        raise ValueError("At least one labeled example is required")

    y_pred = predict_labels(y_score, threshold=threshold)

    true_positives = sum(1 for yt, yp in zip(y_true, y_pred, strict=False) if yt == 1 and yp == 1)
    false_positives = sum(1 for yt, yp in zip(y_true, y_pred, strict=False) if yt == 0 and yp == 1)
    true_negatives = sum(1 for yt, yp in zip(y_true, y_pred, strict=False) if yt == 0 and yp == 0)
    false_negatives = sum(1 for yt, yp in zip(y_true, y_pred, strict=False) if yt == 1 and yp == 0)

    return DetectionMetrics(
        threshold=threshold,
        precision=round(precision_score(y_true, y_pred, zero_division=0), 4),
        recall=round(recall_score(y_true, y_pred, zero_division=0), 4),
        f1=round(f1_score(y_true, y_pred, zero_division=0), 4),
        accuracy=round(accuracy_score(y_true, y_pred), 4),
        true_positives=true_positives,
        false_positives=false_positives,
        true_negatives=true_negatives,
        false_negatives=false_negatives,
    )


def sweep_thresholds(
    y_true: list[int],
    y_score: list[float],
    *,
    thresholds: list[float] | None = None,
) -> list[DetectionMetrics]:
    """Evaluate several thresholds for calibration."""
    if thresholds is None:
        thresholds = [0.40, 0.50, 0.60, 0.70, 0.74, 0.80, 0.90]

    return [
        evaluate_binary_detection(y_true, y_score, threshold=threshold)
        for threshold in thresholds
    ]


def best_threshold_by_f1(results: list[DetectionMetrics]) -> DetectionMetrics:
    """Return the threshold configuration with the best F1-score."""
    if not results:
        raise ValueError("At least one DetectionMetrics result is required")

    return max(results, key=lambda item: item.f1)
