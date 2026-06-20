"""Adapter from ARGOS Layer 2 ML scores to SOAR-compatible signals.

The ML layer outputs MLScore contracts. The SOAR tier router consumes
NormalizedAlert-derived RoutingSignal objects.

This adapter bridges both parts without changing the shared contracts.
"""

from __future__ import annotations

from typing import Any

from argos_contracts.alert import NormalizedAlert
from argos_contracts.enums import Layer, Severity

from argos_contracts.ml_score import MLScore
from soar.decision_engine.tier_router import RoutingSignal


def severity_from_ml_score(score: float) -> Severity:
    """Map a 0.0-1.0 ML anomaly score to ARGOS severity labels."""
    if score >= 0.90:
        return Severity.CRITICAL
    if score >= 0.74:
        return Severity.HIGH
    if score >= 0.40:
        return Severity.MEDIUM
    return Severity.LOW


def ml_score_to_normalized_alert(
    score: MLScore,
    *,
    technique_mitre: str | None = None,
    extra_process_info: dict[str, Any] | None = None,
) -> NormalizedAlert:
    """Convert an MLScore into a Layer 2 NormalizedAlert.

    Important:
        For ML-only detections, technique_mitre should usually remain None.

        If we set technique_mitre="T1486", the SOAR router may classify the
        event as T0 because T1486 is an automatic high-impact ransomware
        technique. For a novel/uncertain ML-only anomaly, we want the score
        to drive the decision and usually produce T2 instead.
    """
    process_info: dict[str, Any] = {
        "process_id": score.process_id,
        "process_name": score.process_name,
        "isolation_forest_score": score.isolation_forest_score,
        "one_class_svm_score": score.one_class_svm_score,
        "ensemble_score": score.ensemble_score,
        "model_version": score.model_version,
        "features": score.features.model_dump(),
    }

    if extra_process_info:
        process_info.update(extra_process_info)

    return NormalizedAlert(
        alert_id=f"ml-alert-{score.score_id}",
        source_layer=Layer.LAYER_2,
        timestamp=score.timestamp,
        host_id=score.host_id,
        severity_score=score.ensemble_score,
        severity_label=severity_from_ml_score(score.ensemble_score),
        technique_mitre=technique_mitre,
        triggering_rule=score.model_version,
        process_info=process_info,
    )


def ml_score_to_routing_signal(
    score: MLScore,
    *,
    technique_mitre: str | None = None,
) -> RoutingSignal:
    """Convert an MLScore into a SOAR RoutingSignal for tier classification."""
    alert = ml_score_to_normalized_alert(score, technique_mitre=technique_mitre)

    return RoutingSignal(
        fired_layers=frozenset({Layer.LAYER_2}),
        technique_mitre=alert.technique_mitre,
        l2_score=alert.severity_score,
        host_id=alert.host_id,
        contributing_alert_ids=(alert.alert_id,),
    )