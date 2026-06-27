"""Test del Camino B: MLScore → NormalizedAlert Layer 2 → events:normalized.

`importorskip` por si el chain de `ml.soar_adapter` algún día arrastra deps pesadas
([ml]); hoy es liviano (solo argos_contracts + soar)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fakeredis import FakeStrictRedis

pytest.importorskip("ml.soar_adapter")

from argos_contracts import Layer, MLFeatures, MLScore, NormalizedAlert
from bridge.ml_publisher import publish_ml_score
from soar.decision_engine.consumer import STREAM


def _score() -> MLScore:
    return MLScore(
        score_id="s1",
        timestamp=datetime(2026, 6, 27, 12, 0, 0, tzinfo=timezone.utc),
        host_id="WIN-VICTIM-01",
        process_id=4321,
        process_name="powershell.exe",
        isolation_forest_score=0.88,
        one_class_svm_score=0.92,
        ensemble_score=0.90,
        features=MLFeatures(
            file_write_rate=120.0,
            avg_entropy=7.9,
            extension_modification_ratio=0.8,
            crypto_api_calls=15,
            new_outbound_connections=2,
            cpu_burst_score=0.9,
            io_burst_score=0.85,
        ),
        model_version="iforest-v0.1-svm-v0.1",
    )


def test_publish_ml_score() -> None:
    r = FakeStrictRedis(decode_responses=True)
    entry_id = publish_ml_score(r, _score())
    assert entry_id is not None
    assert r.xlen(STREAM) == 1
    _entry_id, fields = r.xrange(STREAM)[0]
    alert = NormalizedAlert.model_validate_json(fields["payload"])
    assert alert.source_layer == Layer.LAYER_2
    assert alert.host_id == "WIN-VICTIM-01"
    assert alert.severity_score == 0.90
    assert alert.technique_mitre is None  # ML-only: sin técnica por defecto
