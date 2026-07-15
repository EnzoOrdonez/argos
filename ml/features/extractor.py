"""Feature extraction for ARGOS Layer 2.

This module converts a 60-second process activity window into the MLFeatures
contract consumed by the Layer 2 anomaly models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from argos_contracts.ml_score import MLFeatures
from ml.features.entropy import shannon_entropy

CRYPTO_DLL_KEYWORDS = {
    "bcrypt.dll",
    "crypt32.dll",
    "advapi32.dll",
    "ncrypt.dll",
    "libcrypto",
    "openssl",
}


def _is_file_write_event(event: dict[str, Any]) -> bool:
    event_type = str(event.get("event_type", "")).lower()
    action = str(event.get("action", "")).lower()

    return event_type in {"file_write", "file_modify"} or action in {
        "write",
        "modify",
        "rename",
    }


def _is_crypto_event(event: dict[str, Any]) -> bool:
    event_type = str(event.get("event_type", "")).lower()
    dll_name = str(event.get("dll_name", "")).lower()
    api_name = str(event.get("api_name", "")).lower()

    if event_type == "crypto_api":
        return True

    combined = f"{dll_name} {api_name}"
    return any(keyword in combined for keyword in CRYPTO_DLL_KEYWORDS)


def _is_outbound_connection(event: dict[str, Any]) -> bool:
    event_type = str(event.get("event_type", "")).lower()
    direction = str(event.get("direction", "")).lower()

    return event_type in {"network_outbound", "connection"} and direction in {
        "outbound",
        "egress",
        "",
    }


def _safe_average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _zscore(value: float, mean: float, std: float) -> float:
    if std <= 0:
        return 0.0
    return max(0.0, (value - mean) / std)


def extract_ml_features(
    events: list[dict[str, Any]],
    *,
    window_seconds: float = 60.0,
    cpu_baseline_mean: float = 10.0,
    cpu_baseline_std: float = 5.0,
    io_baseline_mean: float = 50.0,
    io_baseline_std: float = 25.0,
) -> MLFeatures:
    """Extract MLFeatures from process events.

    The expected input is a list of synthetic or normalized events belonging
    to the same host/process inside a 60-second window.

    Args:
        events: List of event dictionaries.
        window_seconds: Size of the analysis window.
        cpu_baseline_mean: Normal CPU mean used for burst scoring.
        cpu_baseline_std: Normal CPU standard deviation.
        io_baseline_mean: Normal I/O mean used for burst scoring.
        io_baseline_std: Normal I/O standard deviation.

    Returns:
        A validated MLFeatures object.
    """
    if window_seconds <= 0:
        raise ValueError("window_seconds must be greater than zero")

    file_write_events = [event for event in events if _is_file_write_event(event)]

    entropy_values: list[float] = []
    modified_extensions: set[str] = set()

    for event in file_write_events:
        sample = event.get("bytes_sample")
        entropy_values.append(shannon_entropy(sample))

        file_path = event.get("file_path")
        if file_path:
            extension = Path(str(file_path)).suffix.lower()
            if extension:
                modified_extensions.add(extension)

    total_files_modified = len(file_write_events)
    extension_modification_ratio = (
        len(modified_extensions) / total_files_modified if total_files_modified else 0.0
    )

    crypto_api_calls = sum(1 for event in events if _is_crypto_event(event))
    new_outbound_connections = sum(1 for event in events if _is_outbound_connection(event))

    cpu_values = [
        float(event["cpu_percent"])
        for event in events
        if event.get("cpu_percent") is not None
    ]
    io_values = [
        float(event["io_ops"])
        for event in events
        if event.get("io_ops") is not None
    ]

    avg_cpu = _safe_average(cpu_values)
    avg_io = _safe_average(io_values)

    return MLFeatures(
        file_write_rate=round(total_files_modified / window_seconds, 4),
        avg_entropy=round(_safe_average(entropy_values), 4),
        extension_modification_ratio=round(extension_modification_ratio, 4),
        crypto_api_calls=crypto_api_calls,
        new_outbound_connections=new_outbound_connections,
        cpu_burst_score=round(_zscore(avg_cpu, cpu_baseline_mean, cpu_baseline_std), 4),
        io_burst_score=round(_zscore(avg_io, io_baseline_mean, io_baseline_std), 4),
    )
