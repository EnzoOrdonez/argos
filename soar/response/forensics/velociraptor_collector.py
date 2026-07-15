"""Velociraptor forensic collection adapter for ARGOS SOAR.

This module prepares and optionally executes Velociraptor forensic collections.

For MVP safety, the demo should run with dry_run=True first. In dry-run mode,
ARGOS only builds the Velociraptor request and stores the metadata in evidence/.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from soar.response.forensics.manifest import build_manifest
from soar.response.forensics.velociraptor_config import load_host_map, resolve_client_id

DEFAULT_RANSOMWARE_TRIAGE_ARTIFACTS = [
    "Generic.Client.Info",
    "Windows.System.Pslist",
    "Windows.Network.Netstat",
    "Windows.EventLogs.Evtx",
]


@dataclass(frozen=True)
class VelociraptorCollectionRequest:
    """Collection request prepared by ARGOS for Velociraptor."""

    incident_id: str
    host_id: str
    client_id: str
    artifacts: list[str]
    query: str
    dry_run: bool
    created_at: str


@dataclass(frozen=True)
class VelociraptorCollectionResult:
    """Result metadata for a Velociraptor collection request."""

    incident_id: str
    host_id: str
    client_id: str
    artifacts: list[str]
    status: str
    output_dir: str
    request_path: str
    command_result_path: str
    collected_at: str


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


def build_collect_client_query(
    *,
    client_id: str,
    artifacts: list[str],
) -> str:
    """Build the VQL query used to schedule a Velociraptor client collection.

    The query uses collect_client() to ask Velociraptor to collect selected
    artifacts from one endpoint.
    """
    artifact_list = ", ".join(f"'{artifact}'" for artifact in artifacts)

    return (
        "SELECT collect_client("
        f"client_id='{client_id}', "
        f"artifacts=[{artifact_list}], "
        "env=dict()"
        ") AS collection"
    )


def _run_velociraptor_query(
    *,
    velociraptor_binary: str,
    api_config_path: str,
    query: str,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Run a Velociraptor API query through the Velociraptor CLI."""
    command = [
        velociraptor_binary,
        "--api_config",
        api_config_path,
        "query",
        query,
        "--format",
        "jsonl",
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "status": "success" if completed.returncode == 0 else "failed",
        }

    except Exception as error:
        return {
            "command": command,
            "status": "error",
            "error": str(error),
        }


def collect_with_velociraptor(
    *,
    incident_id: str,
    host_id: str,
    host_map_path: str | Path = "config/velociraptor_hosts.json",
    api_config_path: str | Path = "config/api.config.yaml",
    velociraptor_binary: str = "velociraptor",
    output_root: str | Path = "evidence",
    artifacts: list[str] | None = None,
    dry_run: bool = True,
) -> VelociraptorCollectionResult:
    """Prepare or execute a Velociraptor forensic collection.

    In dry_run=True mode, no external Velociraptor command is executed.
    This is useful for tests and demos without touching the Velociraptor server.
    """
    selected_artifacts = artifacts or DEFAULT_RANSOMWARE_TRIAGE_ARTIFACTS

    host_map = load_host_map(host_map_path)
    client_id = resolve_client_id(host_id, host_map)

    output_dir = Path(output_root) / incident_id / "velociraptor"
    output_dir.mkdir(parents=True, exist_ok=True)

    query = build_collect_client_query(
        client_id=client_id,
        artifacts=selected_artifacts,
    )

    request = VelociraptorCollectionRequest(
        incident_id=incident_id,
        host_id=host_id,
        client_id=client_id,
        artifacts=selected_artifacts,
        query=query,
        dry_run=dry_run,
        created_at=datetime.now(UTC).isoformat(),
    )

    request_path = output_dir / "velociraptor_request.json"
    _write_json(request_path, asdict(request))

    if dry_run:
        command_result = {
            "status": "dry_run",
            "message": "Velociraptor query was built but not executed.",
            "query": query,
        }
    else:
        command_result = _run_velociraptor_query(
            velociraptor_binary=velociraptor_binary,
            api_config_path=str(api_config_path),
            query=query,
        )

    command_result_path = output_dir / "velociraptor_command_result.json"
    _write_json(command_result_path, command_result)

    status = str(command_result.get("status", "unknown"))

    result = VelociraptorCollectionResult(
        incident_id=incident_id,
        host_id=host_id,
        client_id=client_id,
        artifacts=selected_artifacts,
        status=status,
        output_dir=str(output_dir),
        request_path=str(request_path),
        command_result_path=str(command_result_path),
        collected_at=datetime.now(UTC).isoformat(),
    )

    _write_json(
        output_dir / "velociraptor_collection_result.json",
        asdict(result),
    )

    build_manifest(
        evidence_dir=output_dir,
        incident_id=incident_id,
        host_id=host_id,
        trigger="Velociraptor forensic collection",
        tier="T2",
    )

    return result
