"""Contención al resolverse la decisión (ADR-0013 §2.7).

`apply_decision` materializa la `FinalDecision` del incidente vía el
`ResponseExecutor` (ADR-0012) y escribe `execution_status` + `executed_at`:

- EXECUTE_ISOLATION: corre isolation + kill, transiciona EXECUTING -> EXECUTED.
- NO_ACTION: revierte el throttle (y deja el snapshot, que no se "des-toma").
- REVERTED: revierte el isolation aplicado y transiciona a REVERTED.

Idempotente: si `execution_status` ya está escrito, no re-ejecuta. Fail-soft:
un playbook que falla queda como `failed`/`partial` en la decisión y en el
audit, nunca como excepción hacia el orquestador (ADR-0012 §2.4).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import redis.asyncio as redis

from argos_contracts.enums import ActionType, IncidentState
from argos_contracts.incident import Incident
from soar.approval_api.handlers import load_incident, save_incident
from soar.audit.logger import AuditLogger
from soar.playbooks.base import ExecutionResult, ResponseExecutor
from soar.playbooks.builders import build_isolation, build_kill

logger = logging.getLogger(__name__)

# Acciones protectoras pre-aprobacion que se revierten en NO_ACTION
# (el snapshot se conserva como evidencia; su revert es no-op igual).
_PROTECTIVE_REVERT_TYPES = (ActionType.PROCESS_THROTTLE,)


def _next_action_id(incident: Incident) -> str:
    return f"act-{len(incident.proposed_actions) + 1:03d}"


def _combined_status(results: list[ExecutionResult]) -> str:
    if all(r.status == "success" for r in results):
        return "success"
    if any(r.status in ("success", "partial") for r in results):
        return "partial"
    return "failed"


def _audit_result(
    audit: AuditLogger | None, incident_id: str, op: str, result: ExecutionResult
) -> None:
    if audit is None:
        return
    kind = "action_failed" if result.status == "failed" else f"action_{op}"
    audit.emit(
        kind,
        incident_id,
        action_id=result.action_id,
        status=result.status,
        detail=result.detail,
    )


async def apply_decision(
    r: redis.Redis,
    incident_id: str,
    *,
    executor: ResponseExecutor,
    audit: AuditLogger | None = None,
) -> Incident:
    """Ejecuta lo que la `FinalDecision` ordena. Idempotente y fail-soft."""
    incident = await load_incident(r, incident_id)
    decision = incident.final_decision
    if decision is None or decision.execution_status is not None:
        return incident

    now = datetime.now(UTC)

    if decision.outcome == "EXECUTE_ISOLATION":
        isolation = build_isolation(incident.host.id, action_id=_next_action_id(incident))
        incident.proposed_actions.append(isolation)
        kill = build_kill(incident.host.id, action_id=_next_action_id(incident))
        incident.proposed_actions.append(kill)
        incident.state = IncidentState.EXECUTING
        results = [executor.run(isolation), executor.run(kill)]
        for result in results:
            _audit_result(audit, incident_id, "executed", result)
        decision.execution_status = _combined_status(results)  # type: ignore[assignment]
        incident.state = IncidentState.EXECUTED

    elif decision.outcome == "NO_ACTION":
        results = []
        for action in incident.proposed_actions:
            if action.type in _PROTECTIVE_REVERT_TYPES:
                result = executor.revert(action)
                results.append(result)
                _audit_result(audit, incident_id, "reverted", result)
        decision.execution_status = (
            _combined_status(results) if results else "success"
        )  # type: ignore[assignment]
        # El estado (REJECTED) ya lo fijo quien escribio la decision.

    else:  # REVERTED: des-aislar (boton "Revert if false alarm", ADR-0003)
        results = []
        for action in incident.proposed_actions:
            if action.type == ActionType.HOST_ISOLATION:
                result = executor.revert(action)
                results.append(result)
                _audit_result(audit, incident_id, "reverted", result)
        decision.execution_status = (
            _combined_status(results) if results else "success"
        )  # type: ignore[assignment]
        incident.state = IncidentState.REVERTED

    decision.executed_at = now
    incident.updated_at = now
    await save_incident(r, incident)
    return incident
