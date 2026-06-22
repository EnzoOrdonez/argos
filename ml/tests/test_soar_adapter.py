from datetime import UTC, datetime

from argos_contracts.enums import Layer, Severity, Tier
from argos_contracts.ml_score import MLFeatures, MLScore

from ml.soar_adapter import (
    ml_score_to_normalized_alert,
    ml_score_to_routing_signal,
    severity_from_ml_score,
)
from soar.decision_engine.tier_router import route


def _features() -> MLFeatures:
    return MLFeatures(
        file_write_rate=5.0,
        avg_entropy=7.9,
        extension_modification_ratio=0.95,
        crypto_api_calls=30,
        new_outbound_connections=5,
        cpu_burst_score=8.0,
        io_burst_score=10.0,
    )


def _score(ensemble_score: float) -> MLScore:
    return MLScore(
        score_id="ml-test-001",
        timestamp=datetime.now(UTC),
        host_id="WIN-VICTIM-01",
        process_id=4321,
        process_name="unknown.exe",
        isolation_forest_score=ensemble_score,
        one_class_svm_score=ensemble_score,
        ensemble_score=ensemble_score,
        features=_features(),
        model_version="iforest-v0.1-svm-v0.1",
    )


def test_severity_from_ml_score():
    assert severity_from_ml_score(0.95) == Severity.CRITICAL
    assert severity_from_ml_score(0.74) == Severity.HIGH
    assert severity_from_ml_score(0.50) == Severity.MEDIUM
    assert severity_from_ml_score(0.20) == Severity.LOW


def test_ml_score_to_normalized_alert():
    score = _score(0.82)

    alert = ml_score_to_normalized_alert(score)

    assert alert.alert_id == "ml-alert-ml-test-001"
    assert alert.source_layer == Layer.LAYER_2
    assert alert.host_id == "WIN-VICTIM-01"
    assert alert.severity_score == 0.82
    assert alert.severity_label == Severity.HIGH
    assert alert.technique_mitre is None
    assert alert.triggering_rule == "iforest-v0.1-svm-v0.1"
    assert alert.process_info["ensemble_score"] == 0.82
    assert alert.process_info["process_name"] == "unknown.exe"


def test_ml_score_routes_to_t2_when_score_is_high_enough():
    signal = ml_score_to_routing_signal(_score(0.82))

    assert route(signal) == Tier.T2


def test_ml_score_routes_to_t3_when_score_is_low():
    signal = ml_score_to_routing_signal(_score(0.50))

    assert route(signal) == Tier.T3


def test_ml_score_with_auto_t0_mitre_technique_routes_to_t0():
    signal = ml_score_to_routing_signal(_score(0.50), technique_mitre="T1486")

    assert route(signal) == Tier.T0