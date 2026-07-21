"""Persistencia + evaluacion de decisiones del HITL.

§2.6: record_approval_response — registra/actualiza el voto de un aprobador en Redis.
§2.7: requires_two_person + _evaluate + build_final_decision_if_ready — decide.

Politicas (ADR-0006 §"Reglas concretas"):
- Two-person rule (Situacion A irreversibles / Situacion B host production-critical,
  ADR-0006 + override ADR-0003): requiere DOS aprobaciones; UN SOLO rechazo cancela.
- Conservative-wins (acciones reversibles, no criticas): en contencion conservative =
  AISLAR. Cualquier approve gana -> EXECUTE_ISOLATION, sin importar cuantos rejects.
  El caso solo-reject y el timeout se resuelven al cierre de la ventana de 60s (§2.8),
  porque un approve posterior aun puede voltear un solo-reject hacia EXECUTE.

Adaptado a argos_contracts v1.1.0: FinalDecision usa los Literals reales
(outcome EXECUTE_ISOLATION|NO_ACTION|REVERTED; policy two-person-rule|conservative-wins|
...) + rationale obligatorio. ApproverState usa email+role y responded_at datetime.
NO los valores inventados del manual (outcome="execute"/"block", *_count, float).
"""

from __future__ import annotations

import hmac
import json
import secrets
import time
from datetime import UTC, datetime
from typing import Any, Literal, cast

import redis.asyncio as redis
from redis.exceptions import WatchError

from argos_contracts.enums import (
    ApproverStatus,
    Criticality,
    IncidentState,
    NotificationChannelType,
)
from argos_contracts.incident import ApproverState, FinalDecision, Incident
from soar.approval_api.callback_state import (
    TELEGRAM_TOKEN_KEY,
    TELEGRAM_VOTE_KEY,
    TWILIO_CALL_KEY,
    TWILIO_VOTE_KEY,
)
from soar.approval_api.jwt_signer import ApprovalSigner

Decision = Literal["approve", "reject"]

_DECISION_STATUS: dict[Decision, ApproverStatus] = {
    "approve": ApproverStatus.APPROVED,
    "reject": ApproverStatus.REJECTED,
}

# Two-person rule: aprobaciones necesarias (ADR-0006 Situacion A/B).
QUORUM_APPROVALS = 2


def _key(incident_id: str) -> str:
    return f"incident:{incident_id}"


async def load_incident(r: redis.Redis, incident_id: str) -> Incident:
    raw = await r.get(_key(incident_id))
    if raw is None:
        raise KeyError(f"incident {incident_id} not in Redis")
    return Incident.model_validate_json(raw)


async def save_incident(r: redis.Redis, incident: Incident) -> None:
    await r.set(_key(incident.incident_id), incident.model_dump_json())


async def record_approval_response(
    r: redis.Redis,
    incident_id: str,
    *,
    email: str,
    role: str,
    decision: Decision,
    channel: NotificationChannelType,
) -> Incident:
    """Registra el voto de un aprobador. Idempotente por email: re-votar actualiza.

    Si el incidente ya tiene final_decision, ignora el voto tardio (no muta).
    """
    incident = await load_incident(r, incident_id)
    _apply_approval_response(
        incident,
        email=email,
        role=role,
        decision=decision,
        channel=channel,
    )
    await save_incident(r, incident)
    return incident


def _apply_approval_response(
    incident: Incident,
    *,
    email: str,
    role: str,
    decision: Decision,
    channel: NotificationChannelType,
) -> None:
    if incident.final_decision is not None:
        return
    status = _DECISION_STATUS[decision]
    now = datetime.now(UTC)
    for approver in incident.approvers:
        if approver.email == email:
            approver.status = status
            approver.responded_at = now
            approver.channel = channel
            break
    else:
        incident.approvers.append(
            ApproverState(
                email=email, role=role, status=status, responded_at=now, channel=channel
            )
        )


def requires_two_person(incident: Incident) -> bool:
    """ADR-0006 Situacion B (host production-critical) o A (accion irreversible)."""
    if incident.host.criticality == Criticality.PRODUCTION_CRITICAL:
        return True
    return any(not action.reversible for action in incident.proposed_actions)


def _counts(incident: Incident) -> tuple[int, int]:
    approved = sum(a.status == ApproverStatus.APPROVED for a in incident.approvers)
    rejected = sum(a.status == ApproverStatus.REJECTED for a in incident.approvers)
    return approved, rejected


def _evaluate(incident: Incident) -> FinalDecision | None:
    """Decision durante la ventana. None = aun sin decision (seguir esperando)."""
    approved, rejected = _counts(incident)

    if requires_two_person(incident):
        if rejected >= 1:
            return FinalDecision(
                outcome="NO_ACTION",
                policy_applied="two-person-rule",
                rationale=f"two-person-rule: reject cancela ({approved}A/{rejected}R)",
            )
        if approved >= QUORUM_APPROVALS:
            return FinalDecision(
                outcome="EXECUTE_ISOLATION",
                policy_applied="two-person-rule",
                rationale=f"two-person-rule: {approved} aprobaciones (quorum)",
            )
        return None

    # conservative-wins (reversible, no critico): cualquier approve gana -> aislar.
    if approved >= 1:
        return FinalDecision(
            outcome="EXECUTE_ISOLATION",
            policy_applied="conservative-wins",
            rationale=f"conservative-wins: aislar gana ({approved}A/{rejected}R)",
        )
    return None


async def build_final_decision_if_ready(r: redis.Redis, incident_id: str) -> Incident:
    """Si hay decision posible AHORA, la fija en el Incident y transiciona el estado."""
    incident = await load_incident(r, incident_id)
    if _finalize_if_ready(incident):
        await save_incident(r, incident)
    return incident


def _finalize_if_ready(incident: Incident) -> bool:
    if incident.final_decision is not None:
        return False
    decision = _evaluate(incident)
    if decision is None:
        return False
    incident.final_decision = decision
    incident.state = (
        IncidentState.PENDING_EXECUTION
        if decision.outcome == "EXECUTE_ISOLATION"
        else IncidentState.REJECTED
    )
    incident.updated_at = datetime.now(UTC)
    return True


def _decode_vote_receipt(raw: Any, incident_id: str) -> dict[str, Any]:
    try:
        receipt = json.loads(cast(str, raw))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("invalid Twilio vote receipt") from exc
    if (
        receipt.get("version") != 1
        or receipt.get("status") != "recorded"
        or receipt.get("incident_id") != incident_id
        or receipt.get("decision") not in ("approve", "reject")
        or receipt.get("effects_status") not in ("pending", "processing", "completed")
    ):
        raise RuntimeError("conflicting Twilio vote receipt")
    return cast(dict[str, Any], receipt)


def _decode_telegram_vote_receipt(
    raw: Any,
    *,
    incident_id: str,
    decision: Decision,
    subject: str,
) -> None:
    try:
        receipt = json.loads(cast(str, raw))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("invalid Telegram vote receipt") from exc
    if (
        receipt.get("version") != 1
        or receipt.get("status") != "recorded"
        or receipt.get("incident_id") != incident_id
        or receipt.get("decision") != decision
        or receipt.get("subject") != subject
    ):
        raise RuntimeError("conflicting Telegram vote receipt")


async def record_telegram_approval_atomically(
    r: redis.Redis,
    *,
    signer: ApprovalSigner,
    jti: str,
    incident_id: str,
    decision: Decision,
    subject: str,
    email: str,
    ttl_seconds: int,
) -> tuple[Incident, bool]:
    """Validate and commit a Telegram vote without consuming its JTI early.

    Incident mutation, durable receipt, and token deletion share one Redis
    transaction. A transient failure before commit leaves the token retryable;
    an exact confirmed replay returns ``recorded=False``.
    """
    token_key = TELEGRAM_TOKEN_KEY.format(jti=jti)
    vote_key = TELEGRAM_VOTE_KEY.format(jti=jti)
    incident_key = _key(incident_id)

    while True:
        async with r.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(token_key, vote_key, incident_key)
                existing_receipt = await pipe.get(vote_key)
                raw_incident = await pipe.get(incident_key)
                if raw_incident is None:
                    raise KeyError(f"incident {incident_id} not in Redis")
                incident = Incident.model_validate_json(raw_incident)
                if existing_receipt is not None:
                    _decode_telegram_vote_receipt(
                        existing_receipt,
                        incident_id=incident_id,
                        decision=decision,
                        subject=subject,
                    )
                    return incident, False

                token = await pipe.get(token_key)
                if token is None:
                    # Another watched transaction may have committed between
                    # the first receipt read and this token read. Its atomic
                    # commit deletes the token and creates the receipt.
                    committed_receipt = await pipe.get(vote_key)
                    if committed_receipt is not None:
                        _decode_telegram_vote_receipt(
                            committed_receipt,
                            incident_id=incident_id,
                            decision=decision,
                            subject=subject,
                        )
                        latest_incident = await pipe.get(incident_key)
                        if latest_incident is None:
                            raise KeyError(f"incident {incident_id} not in Redis")
                        return Incident.model_validate_json(latest_incident), False
                    raise PermissionError("unknown or replayed token")
                signer.verify_approval(
                    cast(str, token),
                    expected_incident=incident_id,
                    expected_decision=decision,
                    expected_subject=subject,
                )
                _apply_approval_response(
                    incident,
                    email=email,
                    role="approver",
                    decision=decision,
                    channel=NotificationChannelType.TELEGRAM,
                )
                _finalize_if_ready(incident)
                receipt = json.dumps(
                    {
                        "version": 1,
                        "status": "recorded",
                        "incident_id": incident_id,
                        "decision": decision,
                        "subject": subject,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
                pipe.multi()  # type: ignore[no-untyped-call]
                pipe.set(incident_key, incident.model_dump_json())
                pipe.set(vote_key, receipt, ex=ttl_seconds, nx=True)
                pipe.delete(token_key)
                results = await pipe.execute()
                if results[1] and results[2] == 1:
                    return incident, True
            except WatchError:
                continue


async def record_twilio_approval_atomically(
    r: redis.Redis,
    *,
    call_sid: str,
    incident_id: str,
    decision: Decision,
    ttl_seconds: int,
) -> tuple[Incident, bool]:
    """Atomically persist Incident mutation and a durable single-use receipt.

    Returns (incident, True) for the first committed vote and
    (incident, False) for an exact replay. Conflicting or corrupt receipts fail
    closed. WATCH retries preserve concurrent unrelated Incident updates.
    """
    incident_key = _key(incident_id)
    call_key = TWILIO_CALL_KEY.format(call_sid=call_sid)
    vote_key = TWILIO_VOTE_KEY.format(call_sid=call_sid)
    email = f"twilio:{call_sid}"
    receipt = json.dumps(
        {
            "version": 1,
            "status": "recorded",
            "incident_id": incident_id,
            "decision": decision,
            "effects_status": "pending",
        },
        separators=(",", ":"),
        sort_keys=True,
    )

    while True:
        async with r.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(call_key, vote_key, incident_key)
                bound_incident = await pipe.get(call_key)
                if bound_incident is None or not hmac.compare_digest(
                    cast(str, bound_incident), incident_id
                ):
                    raise PermissionError("CallSid is not bound to the incident")

                raw_incident = await pipe.get(incident_key)
                if raw_incident is None:
                    raise KeyError(f"incident {incident_id} not in Redis")
                incident = Incident.model_validate_json(raw_incident)

                existing_receipt = await pipe.get(vote_key)
                if existing_receipt is not None:
                    _decode_vote_receipt(existing_receipt, incident_id)
                    return incident, False

                _apply_approval_response(
                    incident,
                    email=email,
                    role="approver",
                    decision=decision,
                    channel=NotificationChannelType.TWILIO_VOICE,
                )
                _finalize_if_ready(incident)
                pipe.multi()  # type: ignore[no-untyped-call]
                pipe.set(incident_key, incident.model_dump_json())
                pipe.set(vote_key, receipt, ex=ttl_seconds, nx=True)
                results = await pipe.execute()
                if results[1]:
                    return incident, True
            except WatchError:
                continue


async def acquire_twilio_effects(
    r: redis.Redis,
    *,
    call_sid: str,
    incident_id: str,
    ttl_seconds: int,
) -> str | None:
    vote_key = TWILIO_VOTE_KEY.format(call_sid=call_sid)
    owner = secrets.token_urlsafe(18)
    while True:
        async with r.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(vote_key)
                raw = await pipe.get(vote_key)
                if raw is None:
                    raise RuntimeError("missing Twilio vote receipt")
                receipt = _decode_vote_receipt(raw, incident_id)
                if receipt["effects_status"] == "completed":
                    return None
                if (
                    receipt["effects_status"] == "processing"
                    and float(receipt.get("lease_expires_at", 0)) > time.time()
                ):
                    return None
                receipt["effects_status"] = "processing"
                receipt["owner"] = owner
                receipt["lease_expires_at"] = time.time() + min(30, ttl_seconds)
                pipe.multi()  # type: ignore[no-untyped-call]
                pipe.set(
                    vote_key,
                    json.dumps(receipt, separators=(",", ":"), sort_keys=True),
                    ex=ttl_seconds,
                    xx=True,
                )
                results = await pipe.execute()
                if results[0]:
                    return owner
            except WatchError:
                continue


async def complete_twilio_effects(
    r: redis.Redis,
    *,
    call_sid: str,
    incident_id: str,
    owner: str,
    ttl_seconds: int,
) -> None:
    await _transition_twilio_effects(
        r,
        call_sid=call_sid,
        incident_id=incident_id,
        owner=owner,
        ttl_seconds=ttl_seconds,
        target="completed",
    )


async def release_twilio_effects(
    r: redis.Redis,
    *,
    call_sid: str,
    incident_id: str,
    owner: str,
    ttl_seconds: int,
) -> None:
    await _transition_twilio_effects(
        r,
        call_sid=call_sid,
        incident_id=incident_id,
        owner=owner,
        ttl_seconds=ttl_seconds,
        target="pending",
    )


async def _transition_twilio_effects(
    r: redis.Redis,
    *,
    call_sid: str,
    incident_id: str,
    owner: str,
    ttl_seconds: int,
    target: Literal["pending", "completed"],
) -> None:
    vote_key = TWILIO_VOTE_KEY.format(call_sid=call_sid)
    while True:
        async with r.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(vote_key)
                raw = await pipe.get(vote_key)
                if raw is None:
                    raise RuntimeError("missing Twilio vote receipt")
                receipt = _decode_vote_receipt(raw, incident_id)
                if receipt["effects_status"] == "completed":
                    return
                if receipt["effects_status"] != "processing" or not hmac.compare_digest(
                    str(receipt.get("owner", "")), owner
                ):
                    raise RuntimeError("Twilio effects lease ownership mismatch")
                receipt["effects_status"] = target
                receipt.pop("owner", None)
                receipt.pop("lease_expires_at", None)
                pipe.multi()  # type: ignore[no-untyped-call]
                pipe.set(
                    vote_key,
                    json.dumps(receipt, separators=(",", ":"), sort_keys=True),
                    ex=ttl_seconds,
                    xx=True,
                )
                results = await pipe.execute()
                if results[0]:
                    return
            except WatchError:
                continue
