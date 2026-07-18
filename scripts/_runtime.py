"""Helpers de runtime compartidos por los scripts (viven FUERA de soar/).

`make_executor()` vive ahora en `soar.playbooks.factory` (para que el daemon consumer
`python -m soar.decision_engine` lo use sin importar de scripts/); se re-exporta acá
para no romper los imports existentes de los scripts (`from _runtime import make_executor`).

`latest_incident_id()` deriva el último incidente del día desde el contador, para el
flag `--latest` de `live_approve.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import redis.asyncio as redis

from soar.playbooks.factory import make_executor

__all__ = ["latest_incident_id", "make_executor"]


async def latest_incident_id(r: redis.Redis) -> str | None:
    """Último incidente del día (INC-YYYY-MM-DD-NNN) según el contador, o None."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    sequence = int(await r.get(f"incident:counter:{today}") or 0)
    if sequence <= 0:
        return None
    return f"INC-{today}-{sequence:03d}"
