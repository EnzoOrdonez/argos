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
from argos_contracts.incident import Incident
from soar.approval_api.handlers import build_final_decision_if_ready, record_approval_response
from soar.approval_api.twiml import build_voice_gather_xml, dtmf_to_response
from soar.audit.logger import AuditLogger
from soar.audit.memory import MemorySink
from soar.decision_engine.containment import apply_decision
from soar.decision_engine.scheduler import WindowScheduler
from soar.playbooks.simulated import SimulatedExecutor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.redis = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    # Composicion Fase 3 (ADR-0013): audit fail-soft, executor simulado por
    # defecto (el real se conmuta en la integracion con el lab) y los relojes.
    app.state.audit = AuditLogger([MemorySink()])
    app.state.executor = SimulatedExecutor()
    app.state.scheduler = WindowScheduler(app.state.redis, audit=app.state.audit)
    try:
        yield
    finally:
        await app.state.redis.aclose()


app = FastAPI(title="ARGOS Approval API", lifespan=lifespan)


async def get_redis(request: Request) -> redis.Redis:
    return request.app.state.redis


async def _after_vote(
    app: FastAPI,
    r: redis.Redis,
    incident: Incident,
    *,
    email: str,
    decision: str,
    channel: str,
) -> None:
    """Wiring Fase 3 tras cada voto (ADR-0013 §2.6/§2.7): audita la respuesta,
    arranca la ventana de consolidacion con el PRIMER voto (ADR-0006) y, si la
    decision quedo fija, ejecuta la contencion. Todos los colaboradores son
    opcionales (getattr) para que el API degrade a Fase 2 sin ellos."""
    audit: AuditLogger | None = getattr(app.state, "audit", None)
    if audit is not None:
        audit.emit(
            "approval_response",
            incident.incident_id,
            email=email,
            decision=decision,
            channel=channel,
        )
    scheduler: WindowScheduler | None = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        await scheduler.ensure_consolidation_started(incident.incident_id)
    executor = getattr(app.state, "executor", None)
    if (
        executor is not None
        and incident.final_decision is not None
        and incident.final_decision.execution_status is None
    ):
        if audit is not None:
            audit.emit(
                "decision_final",
                incident.incident_id,
                outcome=incident.final_decision.outcome,
                policy=incident.final_decision.policy_applied,
                rationale=incident.final_decision.rationale,
            )
        await apply_decision(r, incident.incident_id, executor=executor, audit=audit)


@app.get("/healthz")
async def healthz(r: redis.Redis = Depends(get_redis)) -> dict[str, Any]:
    return {"ok": True, "redis": await r.ping()}


@app.post("/telegram/callback")
async def telegram_callback(
    update: dict[str, Any], request: Request, r: redis.Redis = Depends(get_redis)
) -> dict[str, Any]:
    callback = update.get("callback_query")
    if not callback:
        return {"ok": False, "error": "missing callback_query"}
    action, _, incident_id = (callback.get("data") or "").partition(":")
    if action not in ("approve", "reject") or not incident_id:
        return {"ok": False, "error": "bad callback_data"}
    user = callback.get("from", {})
    email = f"telegram:{user.get('id')}"
    try:
        await record_approval_response(
            r,
            incident_id,
            email=email,
            role="approver",
            decision=action,
            channel=NotificationChannelType.TELEGRAM,
        )
        incident = await build_final_decision_if_ready(r, incident_id)
        await _after_vote(
            request.app, r, incident, email=email, decision=action, channel="telegram"
        )
    except KeyError:
        return {"ok": False, "error": "unknown incident"}
    return {"ok": True}


@app.post("/voice/twiml")
async def voice_twiml(incident: str) -> Response:
    return Response(content=build_voice_gather_xml(incident), media_type="application/xml")


@app.post("/voice/dtmf")
async def voice_dtmf(
    incident: str,
    request: Request,
    digits: str = Form(..., alias="Digits"),
    r: redis.Redis = Depends(get_redis),
) -> Response:
    decision = dtmf_to_response(digits)
    if decision is None:
        return Response(
            content="<Response><Say>Invalid input. Goodbye.</Say><Hangup/></Response>",
            media_type="application/xml",
        )
    email = f"twilio:{incident}"
    try:
        await record_approval_response(
            r,
            incident,
            email=email,
            role="approver",
            decision=decision,
            channel=NotificationChannelType.TWILIO_VOICE,
        )
        updated = await build_final_decision_if_ready(r, incident)
        await _after_vote(
            request.app,
            r,
            updated,
            email=email,
            decision=decision,
            channel="twilio_voice",
        )
    except KeyError:
        pass  # incidente desconocido: cerramos la llamada con cortesia igual
    return Response(
        content=f"<Response><Say>{decision} recorded. Goodbye.</Say><Hangup/></Response>",
        media_type="application/xml",
    )
