from argos_contracts.ml_score import MLFeatures
from ml.features.entropy import shannon_entropy
from ml.features.extractor import extract_ml_features


def test_entropy_empty_input_returns_zero():
    assert shannon_entropy(b"") == 0.0
    assert shannon_entropy(None) == 0.0


def test_entropy_low_for_repeated_bytes():
    entropy = shannon_entropy(b"aaaaaaaaaaaaaaaaaaaa")
    assert entropy == 0.0


def test_entropy_higher_for_varied_bytes():
    entropy = shannon_entropy(bytes(range(256)))
    assert entropy > 7.0


def test_extract_ml_features_from_synthetic_ransomware_like_window():
    events = [
        {
            "event_type": "file_write",
            "action": "write",
            "file_path": "C:/Users/victim/Documents/report.docx.locked",
            "bytes_sample": bytes(range(256)),
            "cpu_percent": 80,
            "io_ops": 300,
        },
        {
            "event_type": "file_write",
            "action": "write",
            "file_path": "C:/Users/victim/Documents/payroll.xlsx.locked",
            "bytes_sample": bytes(range(255, -1, -1)),
            "cpu_percent": 85,
            "io_ops": 320,
        },
        {
            "event_type": "crypto_api",
            "dll_name": "bcrypt.dll",
            "api_name": "BCryptEncrypt",
            "cpu_percent": 90,
            "io_ops": 350,
        },
        {
            "event_type": "network_outbound",
            "direction": "outbound",
            "destination_ip": "8.8.8.8",
            "cpu_percent": 70,
            "io_ops": 250,
        },
    ]

    features = extract_ml_features(
        events,
        window_seconds=60,
        cpu_baseline_mean=10,
        cpu_baseline_std=10,
        io_baseline_mean=50,
        io_baseline_std=50,
    )

    assert isinstance(features, MLFeatures)
    assert features.file_write_rate == 0.0333
    assert features.avg_entropy > 7.0
    assert features.extension_modification_ratio == 0.5
    assert features.crypto_api_calls == 1
    assert features.new_outbound_connections == 1
    assert features.cpu_burst_score > 0
    assert features.io_burst_score > 0


def test_extract_ml_features_from_empty_window():
    features = extract_ml_features([])

    assert features.file_write_rate == 0.0
    assert features.avg_entropy == 0.0
    assert features.extension_modification_ratio == 0.0
    assert features.crypto_api_calls == 0
    assert features.new_outbound_connections == 0
    assert features.cpu_burst_score == 0.0
    assert features.io_burst_score == 0.0
