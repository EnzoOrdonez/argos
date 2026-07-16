"""Consola web ARGOS (P4) — FastAPI read-only + sirve el SPA estático.

`GET /api/incidents`, `GET /api/incidents/{id}`, `GET /health`. Lee `incident:{id}` del
mismo Redis que el SOAR (read-only: las aprobaciones siguen por Telegram / trigger local).
La Streamlit (`ui/`) queda como fallback. Fail-soft: si Redis no está, 503 (el front degrada).

    REDIS_URL=redis://localhost:6379/0 uvicorn console.api.main:app --port 8080
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from argos_contracts.alert import NormalizedAlert
from argos_contracts.incident import Incident
from console.api import audit, store
from console.api.auth import require_auth

_STATIC = Path(__file__).resolve().parent.parent / "static"


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


app = FastAPI(title="ARGOS Console (read-only)")


@app.get("/health")
async def health() -> dict[str, Any]:
    try:
        client = store.get_client(_redis_url())
        return {"ok": True, "redis": bool(client.ping())}
    except Exception:  # health nunca debe fallar duro
        return {"ok": True, "redis": False}


@app.get("/api/incidents", response_model=list[Incident], dependencies=[Depends(require_auth)])
async def list_incidents() -> list[Incident]:
    try:
        client = store.get_client(_redis_url())
        return store.list_incidents(client)
    except Exception as exc:  # Redis caído -> 503, el front degrada
        raise HTTPException(status_code=503, detail=f"Redis no disponible: {exc}") from exc


@app.get(
    "/api/incidents/{incident_id}",
    response_model=Incident,
    dependencies=[Depends(require_auth)],
)
async def get_incident(incident_id: str) -> Incident:
    try:
        client = store.get_client(_redis_url())
        incident = store.get_incident(client, incident_id)
    except Exception as exc:  # Redis caído -> 503
        raise HTTPException(status_code=503, detail=f"Redis no disponible: {exc}") from exc
    if incident is None:
        raise HTTPException(status_code=404, detail="incidente no encontrado")
    return incident


@app.get(
    "/api/incidents/{incident_id}/alerts",
    response_model=list[NormalizedAlert],
    dependencies=[Depends(require_auth)],
)
async def burst_alerts(incident_id: str) -> list[NormalizedAlert]:
    """Ráfaga multi-capa correlacionada (Redis `corr:alerts:{id}`). [] si expiró (TTL)."""
    try:
        client = store.get_client(_redis_url())
        return store.list_burst_alerts(client, incident_id)
    except Exception as exc:  # Redis caído -> 503, coherente con /api/incidents
        raise HTTPException(status_code=503, detail=f"Redis no disponible: {exc}") from exc


@app.get("/api/incidents/{incident_id}/audit", dependencies=[Depends(require_auth)])
async def audit_timeline(incident_id: str) -> dict[str, Any]:
    """Timeline evento-por-evento desde Postgres. Subsistema opcional: nunca 503.

    `{"available": false}` si el audit SQL no está configurado (la consola sigue
    100% funcional solo con Redis); `{"available": true, "events": [...]}` si sí.
    """
    events = audit.get_reader().timeline(incident_id)
    if events is None:
        return {"available": False, "events": []}
    return {"available": True, "events": events}


@app.get("/", dependencies=[Depends(require_auth)])
async def index() -> FileResponse:
    # Gateado para que el navegador muestre el diálogo Basic al cargar la consola;
    # una vez autenticado, el fetch del SPA a /api/* lleva las credenciales.
    return FileResponse(str(_STATIC / "index.html"))


app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
