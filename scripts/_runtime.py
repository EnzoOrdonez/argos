"""Helpers de runtime compartidos por los scripts (viven FUERA de soar/).

`make_executor()` conmuta el executor por la env `ARGOS_EXECUTOR` (ADR-0015 §2.1)
sin tocar soar/. Default `simulated` para que el camino del demo quede idéntico;
`wazuh` usa el active-response real. Fail-soft: si falta la config de Wazuh,
degrada a simulated con warning (nunca crashea, invariante demo-safe).

`latest_incident_id()` deriva el último incidente del día desde el contador, para
el flag `--latest` de `live_approve.py`.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import redis.asyncio as redis

from soar.playbooks.base import ResponseExecutor

logger = logging.getLogger(__name__)


def make_executor() -> ResponseExecutor:
    """SimulatedExecutor por defecto; WazuhActiveResponseExecutor con
    `ARGOS_EXECUTOR=wazuh`. Degrada a simulated si el real no se puede construir."""
    mode = os.environ.get("ARGOS_EXECUTOR", "simulated").strip().lower()
    if mode == "wazuh":
        try:
            from soar.playbooks.wazuh import WazuhActiveResponseExecutor

            return WazuhActiveResponseExecutor()
        except KeyError as exc:  # falta WAZUH_API_URL/USER/PASSWORD en el entorno
            logger.warning(
                "ARGOS_EXECUTOR=wazuh pero falta %s en el entorno; uso simulated", exc
            )
        except Exception as exc:  # cualquier fallo construyendo el real -> degradar
            logger.warning(
                "no pude crear WazuhActiveResponseExecutor (%s); uso simulated", exc
            )
    elif mode != "simulated":
        logger.warning("ARGOS_EXECUTOR=%r desconocido; uso simulated", mode)

    from soar.playbooks.simulated import SimulatedExecutor

    return SimulatedExecutor()


async def latest_incident_id(r: redis.Redis) -> str | None:
    """Último incidente del día (INC-YYYY-MM-DD-NNN) según el contador, o None."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sequence = int(await r.get(f"incident:counter:{today}") or 0)
    if sequence <= 0:
        return None
    return f"INC-{today}-{sequence:03d}"
