"""Approval API (FastAPI) — recibe respuestas de aprobacion, muta el Incident en Redis
y evalua la decision (two-person rule / conservative-wins, ADR-0006).

Endpoints:
- GET  /healthz           -> liveness + ping a Redis.
- POST /telegram/callback -> voto desde boton inline de Telegram.
- POST /voice/twiml       -> TwiML que enuncia el incidente y pide DTMF (Twilio).
- POST /voice/dtmf        -> voto desde DTMF de la llamada Twilio.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status

from argos_contracts.incident import Incident
from soar.approval_api.callback_state import (
    bind_twilio_call_from_request,
    callback_ttl_seconds_from_env,
    load_twilio_call,
)
from soar.approval_api.handlers import (
    acquire_twilio_effects,
    complete_twilio_effects,
    record_telegram_approval_atomically,
    record_twilio_approval_atomically,
    release_twilio_effects,
)
from soar.approval_api.jwt_signer import (
    ApprovalSigner,
    Decision,
    TokenInvalid,
)
from soar.approval_api.twiml import build_voice_gather_xml, dtmf_to_response
from soar.approval_api.webhook_auth import (
    TelegramWebhookAuth,
    TwilioWebhookAuth,
    WebhookAuthenticationError,
)
from soar.audit.logger import AuditLogger
from soar.audit.memory import MemorySink
from soar.decision_engine.containment import apply_decision
from soar.decision_engine.scheduler import WindowScheduler
from soar.playbooks.factory import make_executor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    executor = make_executor()
    app.state.redis = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    # Composicion Fase 3 (ADR-0013): audit fail-soft, executor conmutado por
    # ENVIRONMENT + ARGOS_EXECUTOR (selección explícita; ADR-0017) y los relojes.
    # Antes hardcodeaba SimulatedExecutor -> la ejecucion de la decision final por
    # voto nunca era real; ahora honra el env, igual que el daemon consumer (Fase 5a).
    app.state.audit = AuditLogger([MemorySink()])
    app.state.executor = executor
    app.state.scheduler = WindowScheduler(app.state.redis, audit=app.state.audit)
    # Approval providers are disabled unless all authenticity controls exist.
    app.state.signer = ApprovalSigner.from_env()
    app.state.telegram_auth = TelegramWebhookAuth.from_env()
    app.state.twilio_auth = TwilioWebhookAuth.from_env()
    app.state.callback_ttl_seconds = callback_ttl_seconds_from_env()
    try:
        yield
    finally:
        await app.state.redis.aclose()


app = FastAPI(title="ARGOS Approval API", lifespan=lifespan)


async def get_redis(request: Request) -> redis.Redis:
    return cast(redis.Redis, request.app.state.redis)


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
    provider_auth: TelegramWebhookAuth | None = getattr(
        request.app.state, "telegram_auth", None
    )
    signer: ApprovalSigner | None = getattr(request.app.state, "signer", None)
    if provider_auth is None or signer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram approvals are disabled",
        )
    try:
        user_id, chat_id = provider_auth.authenticate(
            request.headers.get("X-Telegram-Bot-Api-Secret-Token"), update
        )
    except WebhookAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
        ) from exc

    callback = update.get("callback_query")
    if not callback:
        return {"ok": False, "error": "missing callback_query"}
    raw_data = callback.get("data")
    if not isinstance(raw_data, str):
        return {"ok": False, "error": "bad callback_data"}
    parts = raw_data.split(":")
    if len(parts) > 3:
        return {"ok": False, "error": "bad callback_data"}
    action = parts[0] if parts else ""
    incident_id = parts[1] if len(parts) >= 2 else ""
    jti = parts[2] if len(parts) >= 3 else None
    if action not in ("approve", "reject") or not incident_id:
        return {"ok": False, "error": "bad callback_data"}
    decision = cast(Decision, action)

    # El JTI se valida y consume en la misma transaccion que persiste el voto.
    if jti is None:
        return {"ok": False, "error": "missing signed token"}

    email = f"telegram:{user_id}"
    subject = f"telegram-chat:{chat_id}"
    try:
        incident, recorded = await record_telegram_approval_atomically(
            r,
            signer=signer,
            jti=jti,
            incident_id=incident_id,
            subject=subject,
            email=email,
            decision=decision,
            ttl_seconds=signer.ttl_seconds,
        )
        if not recorded:
            return {"ok": False, "error": "unknown or replayed token"}
        await _after_vote(
            request.app, r, incident, email=email, decision=decision, channel="telegram"
        )
    except TokenInvalid:
        return {"ok": False, "error": "invalid signed token"}
    except PermissionError:
        return {"ok": False, "error": "unknown or replayed token"}
    except KeyError:
        return {"ok": False, "error": "unknown incident"}
    return {"ok": True}


async def _authenticated_twilio_call(
    incident: str,
    request: Request,
    r: redis.Redis,
    *,
    request_id: str | None = None,
) -> tuple[str, dict[str, str]]:
    provider_auth: TwilioWebhookAuth | None = getattr(
        request.app.state, "twilio_auth", None
    )
    if provider_auth is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Twilio approvals are disabled",
        )
    form_data = await request.form()
    form = {str(key): str(value) for key, value in form_data.multi_items()}
    try:
        call_sid = provider_auth.authenticate(
            request, form, request.headers.get("X-Twilio-Signature")
        )
    except WebhookAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
        ) from exc
    if request_id is not None:
        try:
            await bind_twilio_call_from_request(
                r,
                request_id=request_id,
                call_sid=call_sid,
                incident_id=incident,
                ttl_seconds=int(
                    getattr(request.app.state, "callback_ttl_seconds", 300)
                ),
            )
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            ) from exc
    bound_incident = await load_twilio_call(r, call_sid)
    if bound_incident is None or not hmac.compare_digest(bound_incident, incident):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
        )
    return call_sid, form


@app.post("/voice/twiml")
async def voice_twiml(
    incident: str,
    request: Request,
    request_id: str | None = None,
    r: redis.Redis = Depends(get_redis),
) -> Response:
    await _authenticated_twilio_call(
        incident, request, r, request_id=request_id
    )
    return Response(content=build_voice_gather_xml(incident), media_type="application/xml")


@app.post("/voice/dtmf")
async def voice_dtmf(
    incident: str,
    request: Request,
    r: redis.Redis = Depends(get_redis),
) -> Response:
    call_sid, form = await _authenticated_twilio_call(incident, request, r)
    digits = form.get("Digits", "")
    decision = dtmf_to_response(digits)
    if decision is None:
        return Response(
            content="<Response><Say>Invalid input. Goodbye.</Say><Hangup/></Response>",
            media_type="application/xml",
        )
    ttl_seconds = int(getattr(request.app.state, "callback_ttl_seconds", 300))
    email = f"twilio:{call_sid}"
    try:
        updated, _recorded = await record_twilio_approval_atomically(
            r,
            call_sid=call_sid,
            incident_id=incident,
            decision=decision,
            ttl_seconds=ttl_seconds,
        )
        effects_owner = await acquire_twilio_effects(
            r,
            call_sid=call_sid,
            incident_id=incident,
            ttl_seconds=ttl_seconds,
        )
        if effects_owner is None:
            return Response(
                content="<Response><Say>Response already recorded.</Say><Hangup/></Response>",
                media_type="application/xml",
            )
        try:
            await _after_vote(
                request.app,
                r,
                updated,
                email=email,
                decision=decision,
                channel="twilio_voice",
            )
        except Exception:
            await release_twilio_effects(
                r,
                call_sid=call_sid,
                incident_id=incident,
                owner=effects_owner,
                ttl_seconds=ttl_seconds,
            )
            raise
        await complete_twilio_effects(
            r,
            call_sid=call_sid,
            incident_id=incident,
            owner=effects_owner,
            ttl_seconds=ttl_seconds,
        )
    except (KeyError, PermissionError):
        return Response(
            content="<Response><Say>Response could not be recorded.</Say><Hangup/></Response>",
            media_type="application/xml",
        )
    return Response(
        content=f"<Response><Say>{decision} recorded. Goodbye.</Say><Hangup/></Response>",
        media_type="application/xml",
    )
