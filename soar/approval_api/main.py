"""Approval API (FastAPI) — recibe respuestas de aprobacion, muta el Incident en Redis
y evalua la decision (two-person rule / conservative-wins, ADR-0006).

Endpoints:
- GET  /healthz           -> liveness + ping a Redis.
- POST /telegram/callback -> voto desde boton inline de Telegram.
- POST /voice/twiml       -> TwiML que enuncia el incidente y pide DTMF (Twilio).
- POST /voice/dtmf        -> voto desde DTMF de la llamada Twilio.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis
from fastapi import Depends, FastAPI, Form, Request, Response

from argos_contracts.enums import NotificationChannelType
from soar.approval_api.handlers import build_final_decision_if_ready, record_approval_response
from soar.approval_api.twiml import build_voice_gather_xml, dtmf_to_response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.redis = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    try:
        yield
    finally:
        await app.state.redis.aclose()


app = FastAPI(title="ARGOS Approval API", lifespan=lifespan)


async def get_redis(request: Request) -> redis.Redis:
    return request.app.state.redis


@app.get("/healthz")
async def healthz(r: redis.Redis = Depends(get_redis)) -> dict[str, Any]:
    return {"ok": True, "redis": await r.ping()}


@app.post("/telegram/callback")
async def telegram_callback(
    update: dict[str, Any], r: redis.Redis = Depends(get_redis)
) -> dict[str, Any]:
    callback = update.get("callback_query")
    if not callback:
        return {"ok": False, "error": "missing callback_query"}
    action, _, incident_id = (callback.get("data") or "").partition(":")
    if action not in ("approve", "reject") or not incident_id:
        return {"ok": False, "error": "bad callback_data"}
    user = callback.get("from", {})
    try:
        await record_approval_response(
            r,
            incident_id,
            email=f"telegram:{user.get('id')}",
            role="approver",
            decision=action,
            channel=NotificationChannelType.TELEGRAM,
        )
        await build_final_decision_if_ready(r, incident_id)
    except KeyError:
        return {"ok": False, "error": "unknown incident"}
    return {"ok": True}


@app.post("/voice/twiml")
async def voice_twiml(incident: str) -> Response:
    return Response(content=build_voice_gather_xml(incident), media_type="application/xml")


@app.post("/voice/dtmf")
async def voice_dtmf(
    incident: str,
    digits: str = Form(..., alias="Digits"),
    r: redis.Redis = Depends(get_redis),
) -> Response:
    decision = dtmf_to_response(digits)
    if decision is None:
        return Response(
            content="<Response><Say>Invalid input. Goodbye.</Say><Hangup/></Response>",
            media_type="application/xml",
        )
    try:
        await record_approval_response(
            r,
            incident,
            email=f"twilio:{incident}",
            role="approver",
            decision=decision,
            channel=NotificationChannelType.TWILIO_VOICE,
        )
        await build_final_decision_if_ready(r, incident)
    except KeyError:
        pass  # incidente desconocido: cerramos la llamada con cortesia igual
    return Response(
        content=f"<Response><Say>{decision} recorded. Goodbye.</Say><Hangup/></Response>",
        media_type="application/xml",
    )
