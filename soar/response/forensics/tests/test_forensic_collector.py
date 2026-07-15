from datetime import UTC, datetime

from argos_contracts.ml_score import MLFeatures, MLScore
from soar.response.forensics.collector import collect_forensic_bundle


def _ml_score() -> MLScore:
    return MLScore(
        score_id="ml-test-001",
        timestamp=datetime.now(UTC),
        host_id="WIN-VICTIM-01",
        process_id=None,
        process_name="unknown.exe",
        isolation_forest_score=0.90,
        one_class_svm_score=0.88,
        ensemble_score=0.89,
        features=MLFeatures(
            file_write_rate=5.0,
            avg_entropy=7.9,
            extension_modification_ratio=0.95,
            crypto_api_calls=30,
            new_outbound_connections=5,
            cpu_burst_score=8.0,
            io_burst_score=10.0,
        ),
        model_version="iforest-v0.1-svm-v0.1",
    )


def test_collect_forensic_bundle_creates_expected_files(tmp_path):
    monitored_dir = tmp_path / "monitored"
    monitored_dir.mkdir()
    sample_file = monitored_dir / "recent.txt"
    sample_file.write_text("sample", encoding="utf-8")

    result = collect_forensic_bundle(
        incident_id="INC-TEST-001",
        ml_score=_ml_score(),
        tier="T2",
        monitored_dirs=[monitored_dir],
        output_root=tmp_path / "evidence",
    )

    evidence_dir = tmp_path / "evidence"
    created_dirs = list(evidence_dir.iterdir())

    assert len(created_dirs) == 1

    bundle_dir = created_dirs[0]

    assert bundle_dir.exists()
    assert (bundle_dir / "ml_score.json").exists()
    assert (bundle_dir / "soar_decision.json").exists()
    assert (bundle_dir / "process_metadata.json").exists()
    assert (bundle_dir / "network_connections.json").exists()
    assert (bundle_dir / "recent_files.json").exists()
    assert (bundle_dir / "host_metadata.json").exists()
    assert (bundle_dir / "manifest.json").exists()

    assert result.incident_id == "INC-TEST-001"
    assert result.host_id == "WIN-VICTIM-01"
    assert result.manifest.incident_id == "INC-TEST-001"
    assert len(result.manifest.artifacts) >= 5
