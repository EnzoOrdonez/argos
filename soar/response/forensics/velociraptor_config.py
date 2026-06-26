"""Configuration helpers for ARGOS + Velociraptor integration.

This module resolves ARGOS host identifiers into Velociraptor client IDs.

ARGOS works with host_id values such as:

    WIN-VICTIM-01

Velociraptor works with client IDs such as:

    C.1234567890abcdef

The mapping is stored in a local JSON file that should not be committed to Git.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VelociraptorIntegrationConfig:
    """Configuration needed to call Velociraptor from ARGOS."""

    api_config_path: str = "config/api.config.yaml"
    host_map_path: str = "config/velociraptor_hosts.json"
    output_root: str = "evidence"


def load_host_map(path: str | Path) -> dict[str, str]:
    """Load ARGOS host_id to Velociraptor client_id mapping.

    Expected JSON format:

        {
          "WIN-VICTIM-01": "C.1234567890abcdef"
        }
    """
    host_map_path = Path(path)

    if not host_map_path.exists():
        raise FileNotFoundError(f"Velociraptor host map not found: {host_map_path}")

    raw_data = json.loads(host_map_path.read_text(encoding="utf-8"))

    if not isinstance(raw_data, dict):
        raise ValueError("Velociraptor host map must be a JSON object")

    host_map: dict[str, str] = {}

    for host_id, client_id in raw_data.items():
        host_id_text = str(host_id).strip()
        client_id_text = str(client_id).strip()

        if not host_id_text:
            raise ValueError("host_id cannot be empty")

        if not client_id_text:
            raise ValueError(f"client_id cannot be empty for host_id={host_id_text}")

        host_map[host_id_text] = client_id_text

    return host_map


def resolve_client_id(host_id: str, host_map: dict[str, str]) -> str:
    """Resolve ARGOS host_id into Velociraptor client_id."""
    normalized_host_id = host_id.strip()

    try:
        return host_map[normalized_host_id]
    except KeyError as error:
        raise ValueError(
            f"No Velociraptor client_id mapped for host_id={normalized_host_id}"
        ) from error