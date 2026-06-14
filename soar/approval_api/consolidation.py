"""Ventana de consolidacion T2 de 60 segundos (§2.8, ADR-0006 + ADR-0003).

Al cierre de la ventana se marcan como TIMEOUT los aprobadores que no respondieron y
se resuelve la decision segun la politica del incidente:

- two-person (host production-critical / accion irreversible): ADR-0006 Situacion B ->
  NO hay auto-execute por timeout; se espera al 2do aprobador indefinidamente con el
  throttle activo. No se fija final_decision (el incidente sigue AWAITING_APPROVAL).
- conservative-wins (reversible estandar):
    * algun reject (y ningun approve) -> NO_ACTION (rechazo humano explicito).
    * nadie respondio (todo timeout) -> EXECUTE_ISOLATION / timeout-escalation
      (failsafe ADR-0003: el T2 sin respuesta auto-aisla; throttle + snapshot ya
      acotaron el dano durante la espera).

Esto corrige el manual, que finalizaba SIEMPRE con outcome="block"/"no_quorum_timeout"
(valores inexistentes en v1.1.0) violando ADR-0003 (timeout estandar = auto-execute) y
ADR-0006 Situacion B (production-critical no auto-ejecuta por timeout).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import redis.asyncio as redis

from argos_contracts.enums import ApproverStatus, IncidentState
from argos_contracts.incident import FinalDecision, Incident
from soar.approval_api.handlers import (
    _counts,
    _evaluate,
    load_incident,
    requires_two_person,
    save_incident,
)

WINDOW_SECONDS = 60


def finalize_after_window(incident: Incident) -> FinalDecision | None:
    """Decision al cierre de la ventana (con pendientes ya marcados TIMEOUT).

    Devuelve None SOLO para two-person sin resolver (ADR-0006 Situacion B: espera, no
    auto-execute). En conservative-wins siempre resuelve (NO_ACTION o failsafe execute).
    """
    decision = _evaluate(incident)
    if decision is not None:
        return decision

    if requires_two_person(incident):
        return None  # ADR-0006 Situacion B: esperar al 2do aprobador, sin auto-execute.

    approved, rejected = _counts(incident)
    if rejected >= 1:
        return FinalDecision(
            outcome="NO_ACTION",
            policy_applied="conservative-wins",
            rationale=f"conservative-wins: todos reject ({approved}A/{rejected}R)",
        )
    return FinalDecision(
        outcome="EXECUTE_ISOLATION",
        policy_applied="timeout-escalation",
        rationale="timeout-escalation: T2 sin respuesta, failsafe aislar",
    )


async def close_window(r: redis.Redis, incident_id: str) -> Incident:
    """Marca pendientes como TIMEOUT y resuelve la decision (idempotente)."""
    incident = await load_incident(r, incident_id)
    if incident.final_decision is not None:
        return incident

    now = datetime.now(timezone.utc)
    for approver in incident.approvers:
        if approver.status == ApproverStatus.PENDING:
            approver.status = ApproverStatus.TIMEOUT
            approver.responded_at = now

    decision = finalize_after_window(incident)
    incident.updated_at = now
    if decision is None:
        # two-person sin resolver: persistir los timeouts y seguir esperando.
        await save_incident(r, incident)
        return incident

    incident.final_decision = decision
    incident.state = (
        IncidentState.PENDING_EXECUTION
        if decision.outcome == "EXECUTE_ISOLATION"
        else IncidentState.REJECTED
    )
    await save_incident(r, incident)
    return incident


async def consolidation_task(
    r: redis.Redis, incident_id: str, *, window_seconds: int = WINDOW_SECONDS
) -> None:
    """Background task: espera la ventana y cierra. Se lanza al crear un incidente T2."""
    await asyncio.sleep(window_seconds)
    await close_window(r, incident_id)
