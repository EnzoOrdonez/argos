"""Ablation study helpers for ARGOS Layer 2."""

from __future__ import annotations

from dataclasses import dataclass

from ml.evaluation.metrics import DetectionMetrics, evaluate_binary_detection


@dataclass(frozen=True)
class AblationResult:
    """Evaluation result for one system configuration."""

    configuration_name: str
    description: str
    metrics: DetectionMetrics


def run_ablation_study(
    y_true: list[int],
    scores_by_configuration: dict[str, list[float]],
    *,
    threshold: float = 0.74,
) -> list[AblationResult]:
    """Compare several detection configurations.

    Example configurations:
        - rules_only
        - ml_only
        - canary_only
        - rules_plus_ml
        - full_argos
    """
    if not scores_by_configuration:
        raise ValueError("At least one configuration is required")

    descriptions = {
        "rules_only": "Only signature/rule-based detection.",
        "ml_only": "Only Layer 2 anomaly detection.",
        "canary_only": "Only canary/deception detection.",
        "rules_plus_ml": "Rules and ML anomaly detection combined.",
        "full_argos": "Rules, ML, canary and triage combined.",
    }

    results: list[AblationResult] = []

    for configuration_name, y_score in scores_by_configuration.items():
        metrics = evaluate_binary_detection(
            y_true,
            y_score,
            threshold=threshold,
        )

        results.append(
            AblationResult(
                configuration_name=configuration_name,
                description=descriptions.get(
                    configuration_name,
                    "Custom detection configuration.",
                ),
                metrics=metrics,
            )
        )

    return results