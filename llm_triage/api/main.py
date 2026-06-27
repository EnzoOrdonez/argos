"""Servicio FastAPI del LLM Triage real (Layer 4, ADR-0001). `POST /triage` + `GET /health`.

Reemplaza a `scripts/triage_stub.py` para corridas reales (el stub queda como fallback
demo, igual que `SimulatedExecutor`). El SOAR ya postea acá vía `triage_hook.TriageClient`.
Ante cualquier fallo del backend → 502; el hook del SOAR lo absorbe a None (R-2: el LLM
nunca bloquea la contención).

    uvicorn llm_triage.api.main:app --port 8002   # LLM_TRIAGE_PORT
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException

from argos_contracts.triage import AlertContext, TriageResponse
from llm_triage.llm_client.factory import get_llm_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.client = get_llm_client()
    yield


app = FastAPI(title="ARGOS LLM Triage (Layer 4)", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    client = getattr(app.state, "client", None)
    return {"ok": True, "backend": getattr(client, "backend_id", None)}


@app.post("/triage")
async def triage(context: AlertContext) -> TriageResponse:
    try:
        return await app.state.client.analyze(context)
    except Exception as exc:
        logger.warning("triage falló para %s: %s", context.incident_id, exc)
        raise HTTPException(status_code=502, detail="triage backend unavailable") from exc
