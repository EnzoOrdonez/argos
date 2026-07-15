"""Lectura read-only de incidentes desde Redis (polling; el SOAR no expone pub/sub).

Espeja la convención de claves de ``soar/approval_api/handlers.py`` (``incident:{id}``)
sin importar ``soar``. El ``SCAN incident:*`` también matchea ``incident:counter:{fecha}``
(``soar/decision_engine/consumer.py``), así que filtramos por el patrón de id del
contrato. Fail-soft: un valor ausente o no parseable se saltea, nunca tumba la consola.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import redis
from pydantic import ValidationError

from argos_contracts.incident import Incident

_KEY_PREFIX = "incident:"
# Mismo patrón que Incident.incident_id en el contrato (INC-YYYY-MM-DD-NNN).
_INCIDENT_ID_RE = re.compile(r"^INC-\d{4}-\d{2}-\d{2}-\d{3}$")


def get_client(url: str) -> redis.Redis:
    """Cliente Redis sync (Streamlit no corre event loop).

    ``decode_responses=True`` para recibir str, igual que el SOAR.
    """
    return redis.Redis.from_url(url, decode_responses=True)


def incident_id_from_key(key: str) -> str | None:
    """Devuelve el id si la clave es de un incidente real, o None (p.ej. counter)."""
    if not key.startswith(_KEY_PREFIX):
        return None
    candidate = key[len(_KEY_PREFIX) :]
    return candidate if _INCIDENT_ID_RE.match(candidate) else None


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _sort_key(incident: Incident) -> tuple[int, datetime]:
    # Abiertos (sin final_decision) primero; dentro de cada grupo, más nuevo primero.
    is_open = 1 if incident.final_decision is None else 0
    return (is_open, _as_utc(incident.updated_at))


def load_one(client: redis.Redis, incident_id: str) -> Incident | None:
    """GET incident:{id} → Incident, o None si no existe / no valida."""
    raw = client.get(f"{_KEY_PREFIX}{incident_id}")
    if raw is None:
        return None
    try:
        return Incident.model_validate_json(raw)
    except ValidationError:
        return None


def enumerate_incidents(client: redis.Redis) -> list[Incident]:
    """Todos los incidentes parseables: abiertos primero, luego por updated_at desc.

    Filtra ``incident:counter:*`` y cualquier snapshot corrupto/parcial (fail-soft).
    """
    incidents: list[Incident] = []
    for key in client.scan_iter(match=f"{_KEY_PREFIX}*", count=100):
        if incident_id_from_key(key) is None:
            continue  # incident:counter:{fecha} u otra clave que no es un incidente
        raw = client.get(key)
        if raw is None:
            continue  # expiró entre el SCAN y el GET
        try:
            incidents.append(Incident.model_validate_json(raw))
        except ValidationError:
            continue  # snapshot inválido: no rompemos la consola
    incidents.sort(key=_sort_key, reverse=True)
    return incidents
