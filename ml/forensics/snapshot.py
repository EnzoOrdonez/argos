"""Safe forensic snapshot simulation for ARGOS Layer 2.

This module does not collect real memory, disk images, or sensitive files.
It only creates a structured evidence record for demo and testing purposes.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
import json

from argos_contracts.ml_score import MLScore


@dataclass(frozen=True)
class ForensicSnapshotRecord:
    snapshot_id: str
    created_at: str
    host_id: str
    process_id: int | None
    process_name: str | None
    trigger_score_id: str
    ensemble_score: float
    snapshot_type: str
    storage_path: str


def build_forensic_snapshot_record(
    score: MLScore,
    *,
    storage_dir: str | Path = "ml/data/forensics",
    snapshot_type: str = "simulated-process-context",
) -> ForensicSnapshotRecord:
    """Create and persist a safe simulated forensic snapshot record."""
    storage_path = Path(storage_dir)
    storage_path.mkdir(parents=True, exist_ok=True)

    snapshot_id = f"snap-{uuid4().hex[:12]}"
    output_file = storage_path / f"{snapshot_id}.json"

    record = ForensicSnapshotRecord(
        snapshot_id=snapshot_id,
        created_at=datetime.now(UTC).isoformat(),
        host_id=score.host_id,
        process_id=score.process_id,
        process_name=score.process_name,
        trigger_score_id=score.score_id,
        ensemble_score=score.ensemble_score,
        snapshot_type=snapshot_type,
        storage_path=str(output_file),
    )

    output_file.write_text(
        json.dumps(asdict(record), indent=2),
        encoding="utf-8",
    )

    return record