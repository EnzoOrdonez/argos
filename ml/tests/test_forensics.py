from datetime import UTC, datetime

from argos_contracts.ml_score import MLFeatures, MLScore
from ml.forensics.snapshot import build_forensic_snapshot_record


def _score() -> MLScore:
    features = MLFeatures(
        file_write_rate=5.0,
        avg_entropy=7.9,
        extension_modification_ratio=0.95,
        crypto_api_calls=30,
        new_outbound_connections=5,
        cpu_burst_score=8.0,
        io_burst_score=10.0,
    )

    return MLScore(
        score_id="ml-test-001",
        timestamp=datetime.now(UTC),
        host_id="WIN-VICTIM-01",
        process_id=4321,
        process_name="unknown.exe",
        isolation_forest_score=0.90,
        one_class_svm_score=0.88,
        ensemble_score=0.89,
        features=features,
        model_version="iforest-v0.1-svm-v0.1",
    )


def test_build_forensic_snapshot_record(tmp_path):
    record = build_forensic_snapshot_record(
        _score(),
        storage_dir=tmp_path,
    )

    assert record.snapshot_id.startswith("snap-")
    assert record.host_id == "WIN-VICTIM-01"
    assert record.process_id == 4321
    assert record.process_name == "unknown.exe"
    assert record.trigger_score_id == "ml-test-001"
    assert record.ensemble_score == 0.89
    assert record.snapshot_type == "simulated-process-context"

    output_file = tmp_path / f"{record.snapshot_id}.json"
    assert output_file.exists()
