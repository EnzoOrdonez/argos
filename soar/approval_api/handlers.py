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

from datetime import datetime, timezone
from typing import Literal

import redis.asyncio as redis

from argos_contracts.enums import (
    ApproverStatus,
    Criticality,
    IncidentState,
    NotificationChannelType,
)
from argos_contracts.incident import ApproverState, FinalDecision, Incident

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
    if incident.final_decision is not None:
        return incident

    status = _DECISION_STATUS[decision]
    now = datetime.now(timezone.utc)

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

    await save_incident(r, incident)
    return incident


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
    if incident.final_decision is not None:
        return incident
    decision = _evaluate(incident)
    if decision is None:
        return incident
    incident.final_decision = decision
    incident.state = (
        IncidentState.PENDING_EXECUTION
        if decision.outcome == "EXECUTE_ISOLATION"
        else IncidentState.REJECTED
    )
    incident.updated_at = datetime.now(timezone.utc)
    await save_incident(r, incident)
    return incident
