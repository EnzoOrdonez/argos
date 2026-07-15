"""Manifest generation for ARGOS forensic evidence bundles."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from soar.response.forensics.hashing import sha256_file


@dataclass(frozen=True)
class EvidenceArtifact:
    name: str
    path: str
    sha256: str


@dataclass(frozen=True)
class EvidenceManifest:
    evidence_id: str
    incident_id: str
    host_id: str
    created_at: str
    trigger: str
    tier: str
    artifacts: list[EvidenceArtifact]


def build_manifest(
    *,
    evidence_dir: str | Path,
    incident_id: str,
    host_id: str,
    trigger: str,
    tier: str,
) -> EvidenceManifest:
    """Build and persist a manifest.json for all files in an evidence directory."""
    evidence_path = Path(evidence_dir)

    artifacts: list[EvidenceArtifact] = []

    for file_path in sorted(evidence_path.iterdir()):
        if not file_path.is_file():
            continue

        if file_path.name == "manifest.json":
            continue

        artifacts.append(
            EvidenceArtifact(
                name=file_path.name,
                path=str(file_path),
                sha256=sha256_file(file_path),
            )
        )

    manifest = EvidenceManifest(
        evidence_id=f"ev-{uuid4().hex[:12]}",
        incident_id=incident_id,
        host_id=host_id,
        created_at=datetime.now(UTC).isoformat(),
        trigger=trigger,
        tier=tier,
        artifacts=artifacts,
    )

    manifest_file = evidence_path / "manifest.json"
    manifest_file.write_text(
        json.dumps(asdict(manifest), indent=2),
        encoding="utf-8",
    )

    return manifest
