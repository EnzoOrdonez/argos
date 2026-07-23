"""Stable identity propagated from the journal to external executors."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

Operation = Literal["run", "revert"]


@dataclass(frozen=True)
class ExecutionIdentity:
    incident_id: str
    action_id: str
    operation: Operation

    def __post_init__(self) -> None:
        if not self.incident_id.strip() or not self.action_id.strip():
            raise ValueError("execution identity components must be non-empty")
        if self.operation not in ("run", "revert"):
            raise ValueError("execution identity operation is invalid")

    @property
    def execution_id(self) -> str:
        canonical = json.dumps(
            [self.incident_id, self.action_id, self.operation],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"argos-v1-{digest}"

    def as_payload(self) -> dict[str, str]:
        return {
            "execution_id": self.execution_id,
            "incident_id": self.incident_id,
            "action_id": self.action_id,
            "operation": self.operation,
        }
