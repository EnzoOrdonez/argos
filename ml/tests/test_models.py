from argos_contracts.ml_score import MLFeatures, MLScore
from ml.models.ensemble import Layer2AnomalyEnsemble
from ml.models.vectorizer import FEATURE_NAMES, features_to_matrix, features_to_vector


def _benign_windows(size: int = 80) -> list[MLFeatures]:
    rows = []

    for index in range(size):
        rows.append(
            MLFeatures(
                file_write_rate=0.01 + (index % 5) * 0.003,
                avg_entropy=3.2 + (index % 7) * 0.12,
                extension_modification_ratio=0.02 + (index % 4) * 0.01,
                crypto_api_calls=index % 2,
                new_outbound_connections=1 if index % 11 == 0 else 0,
                cpu_burst_score=(index % 4) * 0.1,
                io_burst_score=(index % 5) * 0.1,
            )
        )

    return rows


def _ransomware_like_window() -> MLFeatures:
    return MLFeatures(
        file_write_rate=5.0,
        avg_entropy=7.9,
        extension_modification_ratio=0.95,
        crypto_api_calls=30,
        new_outbound_connections=5,
        cpu_burst_score=8.0,
        io_burst_score=10.0,
    )


def test_features_to_vector_has_expected_shape():
    features = _ransomware_like_window()

    vector = features_to_vector(features)

    assert vector.shape == (len(FEATURE_NAMES),)


def test_features_to_matrix_has_expected_shape():
    rows = _benign_windows(size=10)

    matrix = features_to_matrix(rows)

    assert matrix.shape == (10, len(FEATURE_NAMES))


def test_layer2_ensemble_returns_valid_ml_score_for_anomalous_window():
    model = Layer2AnomalyEnsemble().fit(_benign_windows())

    score = model.predict_score(
        _ransomware_like_window(),
        host_id="WIN-VICTIM-01",
        process_id=4321,
        process_name="unknown.exe",
    )

    assert isinstance(score, MLScore)
    assert score.host_id == "WIN-VICTIM-01"
    assert score.process_id == 4321
    assert score.process_name == "unknown.exe"
    assert score.isolation_forest_score >= 0.0
    assert score.one_class_svm_score >= 0.0
    assert score.ensemble_score >= 0.74
    assert score.model_version == "iforest-v0.1-svm-v0.1"
    assert score.timestamp.tzinfo is not None


def test_layer2_ensemble_requires_fit_before_predict():
    model = Layer2AnomalyEnsemble()

    try:
        model.predict_score(_ransomware_like_window(), host_id="WIN-VICTIM-01")
    except RuntimeError as error:
        assert "must be fitted" in str(error)
    else:
        raise AssertionError("Expected RuntimeError when predicting before fit.")
