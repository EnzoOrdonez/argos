"""Lectura read-only de incidentes desde Redis para la consola web.

Mirror de la lógica ya probada en `ui/streamlit_app/lib/incident_loader.py`: `SCAN
incident:*` filtrando `incident:counter:*` (que también matchea), parse con el
contrato, fail-soft. Cliente `redis.Redis` sync (FastAPI sync endpoints).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import redis
from pydantic import ValidationError

from argos_contracts.incident import Incident

_KEY_PREFIX = "incident:"
_INCIDENT_ID_RE = re.compile(r"^INC-\d{4}-\d{2}-\d{2}-\d{3}$")


def get_client(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, decode_responses=True)


def incident_id_from_key(key: str) -> str | None:
    if not key.startswith(_KEY_PREFIX):
        return None
    candidate = key[len(_KEY_PREFIX) :]
    return candidate if _INCIDENT_ID_RE.match(candidate) else None


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def list_incidents(client: redis.Redis) -> list[Incident]:
    """Todos los incidentes parseables: abiertos primero, luego por updated_at desc."""
    incidents: list[Incident] = []
    for key in client.scan_iter(match=f"{_KEY_PREFIX}*", count=100):
        if incident_id_from_key(key) is None:
            continue  # incident:counter:{fecha} u otra clave que no es incidente
        raw = client.get(key)
        if raw is None:
            continue
        try:
            incidents.append(Incident.model_validate_json(raw))
        except ValidationError:
            continue  # snapshot inválido: fail-soft
    incidents.sort(
        key=lambda inc: (1 if inc.final_decision is None else 0, _as_utc(inc.updated_at)),
        reverse=True,
    )
    return incidents


def get_incident(client: redis.Redis, incident_id: str) -> Incident | None:
    raw = client.get(f"{_KEY_PREFIX}{incident_id}")
    if raw is None:
        return None
    try:
        return Incident.model_validate_json(raw)
    except ValidationError:
        return None
