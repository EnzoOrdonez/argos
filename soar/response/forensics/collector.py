"""Lightweight forensic collector for ARGOS SOAR response.

This collector creates a structured evidence bundle for an incident.

It collects:
- MLScore
- Normalized alert, if provided
- SOAR decision metadata
- Process metadata
- Network connections
- Recently modified files from monitored directories
- Evidence manifest with SHA256 hashes

This module does not dump memory or image disks. It is a safe lightweight
forensic capture suitable for MVP and academic demonstration.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from argos_contracts.ml_score import MLScore
from soar.response.forensics.manifest import EvidenceManifest, build_manifest


@dataclass(frozen=True)
class ForensicCaptureResult:
    incident_id: str
    host_id: str
    evidence_dir: str
    manifest: EvidenceManifest


def _jsonable(value: Any) -> Any:
    """Convert Pydantic/dataclass/plain objects to JSON-friendly values."""
    if value is None:
        return None

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")

    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)

    return value


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_jsonable(payload), indent=2, default=str),
        encoding="utf-8",
    )


def _run_command(command: list[str], *, timeout: int = 5) -> dict[str, Any]:
    """Run a local forensic command with timeout and safe error capture."""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    except Exception as error:
        return {
            "command": command,
            "error": str(error),
        }


def collect_process_metadata(
    *,
    process_id: int | None,
    process_name: str | None,
) -> dict[str, Any]:
    """Collect lightweight process metadata.

    Windows uses PowerShell CIM.
    Linux uses /proc when available.
    """
    base: dict[str, Any] = {
        "process_id": process_id,
        "process_name": process_name,
        "platform": platform.system(),
        "captured_at": datetime.now(UTC).isoformat(),
    }

    if process_id is None:
        base["status"] = "process_id_not_available"
        return base

    system = platform.system().lower()

    if system == "windows":
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                f"Get-CimInstance Win32_Process -Filter \"ProcessId = {process_id}\" "
                "| Select-Object ProcessId,Name,ExecutablePath,CommandLine,ParentProcessId "
                "| ConvertTo-Json -Compress"
            ),
        ]

        base["windows_cim"] = _run_command(command)
        return base

    proc_dir = Path(f"/proc/{process_id}")

    if proc_dir.exists():
        base["proc_exists"] = True

        try:
            base["cmdline"] = (proc_dir / "cmdline").read_text(errors="ignore").replace(
                "\x00",
                " ",
            )
        except Exception as error:
            base["cmdline_error"] = str(error)

        try:
            base["status_text"] = (proc_dir / "status").read_text(errors="ignore")
        except Exception as error:
            base["status_error"] = str(error)

        try:
            base["exe"] = str((proc_dir / "exe").resolve())
        except Exception as error:
            base["exe_error"] = str(error)

    else:
        base["proc_exists"] = False

    return base


def collect_network_connections() -> dict[str, Any]:
    """Collect current network connection listing."""
    system = platform.system().lower()

    if system == "windows":
        return _run_command(["netstat", "-ano"])

    result = _run_command(["ss", "-tunap"])

    if "error" in result or result.get("returncode") not in {0, None}:
        return _run_command(["netstat", "-tunap"])

    return result


def collect_recent_files(
    *,
    monitored_dirs: list[str | Path],
    modified_within_minutes: int = 30,
    max_files: int = 100,
) -> list[dict[str, Any]]:
    """Collect metadata for recently modified files in monitored directories."""
    cutoff = datetime.now(UTC) - timedelta(minutes=modified_within_minutes)
    results: list[dict[str, Any]] = []

    for directory in monitored_dirs:
        root = Path(directory)

        if not root.exists():
            results.append(
                {
                    "path": str(root),
                    "error": "directory_not_found",
                }
            )
            continue

        for file_path in root.rglob("*"):
            if len(results) >= max_files:
                return results

            if not file_path.is_file():
                continue

            try:
                stat = file_path.stat()
                modified_at = datetime.fromtimestamp(stat.st_mtime, UTC)

                if modified_at < cutoff:
                    continue

                results.append(
                    {
                        "path": str(file_path),
                        "size_bytes": stat.st_size,
                        "modified_at": modified_at.isoformat(),
                    }
                )

            except Exception as error:
                results.append(
                    {
                        "path": str(file_path),
                        "error": str(error),
                    }
                )

    return results


def collect_forensic_bundle(
    *,
    incident_id: str,
    ml_score: MLScore,
    tier: str,
    normalized_alert: Any | None = None,
    decision_metadata: dict[str, Any] | None = None,
    monitored_dirs: list[str | Path] | None = None,
    output_root: str | Path = "evidence",
) -> ForensicCaptureResult:
    """Create a lightweight forensic evidence bundle for an ARGOS incident."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    host_id = ml_score.host_id

    evidence_dir = Path(output_root) / f"{incident_id}_{host_id}_{timestamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    _write_json(evidence_dir / "ml_score.json", ml_score)

    if normalized_alert is not None:
        _write_json(evidence_dir / "normalized_alert.json", normalized_alert)

    _write_json(
        evidence_dir / "soar_decision.json",
        {
            "incident_id": incident_id,
            "host_id": host_id,
            "tier": tier,
            "decision_metadata": decision_metadata or {},
            "captured_at": datetime.now(UTC).isoformat(),
        },
    )

    process_metadata = collect_process_metadata(
        process_id=ml_score.process_id,
        process_name=ml_score.process_name,
    )
    _write_json(evidence_dir / "process_metadata.json", process_metadata)

    network_connections = collect_network_connections()
    _write_json(evidence_dir / "network_connections.json", network_connections)

    recent_files = collect_recent_files(
        monitored_dirs=monitored_dirs or [Path.cwd()],
        modified_within_minutes=30,
        max_files=100,
    )
    _write_json(evidence_dir / "recent_files.json", recent_files)

    _write_json(
        evidence_dir / "host_metadata.json",
        {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "python_version": platform.python_version(),
            "working_directory": os.getcwd(),
            "captured_at": datetime.now(UTC).isoformat(),
        },
    )

    manifest = build_manifest(
        evidence_dir=evidence_dir,
        incident_id=incident_id,
        host_id=host_id,
        trigger="Layer 2 ML anomaly",
        tier=tier,
    )

    return ForensicCaptureResult(
        incident_id=incident_id,
        host_id=host_id,
        evidence_dir=str(evidence_dir),
        manifest=manifest,
    )
