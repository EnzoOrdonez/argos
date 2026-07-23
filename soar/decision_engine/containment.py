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

import asyncio
import logging
from datetime import UTC, datetime

import redis.asyncio as redis

from argos_contracts.enums import ActionType, IncidentState
from argos_contracts.incident import Incident, ProposedAction
from soar.approval_api.handlers import load_incident, save_incident
from soar.audit.logger import AuditLogger
from soar.execution.journal import Operation, ResponseExecutionJournal
from soar.playbooks.base import ExecutionResult, ResponseExecutor, ResultStatus
from soar.playbooks.builders import build_block_ip, build_isolation, build_kill

logger = logging.getLogger(__name__)

# Acciones protectoras pre-aprobacion que se revierten en NO_ACTION
# (el snapshot se conserva como evidencia; su revert es no-op igual).
_PROTECTIVE_REVERT_TYPES = (ActionType.PROCESS_THROTTLE,)

# Acciones de contencion que un REVERTED des-hace (aislar/bloquear son reversibles).
_CONTAINMENT_REVERT_TYPES = (ActionType.HOST_ISOLATION, ActionType.BLOCK_IP)


def _next_action_id(incident: Incident) -> str:
    return f"act-{len(incident.proposed_actions) + 1:03d}"


def _attacker_ip(incident: Incident) -> str | None:
    """IP de origen del atacante si la alerta la trae (`network_info.src_ip`).

    La pobló el bridge desde `data.srcip` de la alerta Wazuh. Presente en vectores
    con IP de origen (fuerza bruta SSH); ausente en los basados en host/proceso."""
    src_ip = (incident.alert.network_info or {}).get("src_ip")
    return str(src_ip) if src_ip else None


def _combined_status(results: list[ExecutionResult]) -> ResultStatus:
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


async def _execute_effect(
    journal: ResponseExecutionJournal,
    executor: ResponseExecutor,
    incident_id: str,
    action: ProposedAction,
    operation: Operation,
) -> ExecutionResult:
    effect = executor.run if operation == "run" else executor.revert
    return await asyncio.to_thread(
        journal.execute,
        incident_id,
        action,
        operation=operation,
        actor="decision-engine",
        effect=lambda: effect(action),
    )


async def apply_decision(
    r: redis.Redis,
    incident_id: str,
    *,
    executor: ResponseExecutor,
    journal: ResponseExecutionJournal,
    audit: AuditLogger | None = None,
) -> Incident:
    """Ejecuta lo que la `FinalDecision` ordena. Idempotente y fail-soft."""
    incident = await load_incident(r, incident_id)
    decision = incident.final_decision
    if decision is None or decision.execution_status is not None:
        return incident

    now = datetime.now(UTC)

    if decision.outcome == "EXECUTE_ISOLATION":
        attacker_ip = _attacker_ip(incident)
        if attacker_ip is not None:
            # Vector con IP de origen (brute-force SSH): contencion quirurgica.
            # Se dropea SOLO al atacante; el host sigue operativo (no se aisla ni
            # se mata proceso: el ofensor es remoto, no hay pid local).
            block = build_block_ip(
                incident.host.id, action_id=_next_action_id(incident), src_ip=attacker_ip
            )
            incident.proposed_actions.append(block)
            incident.state = IncidentState.EXECUTING
            results = [
                await _execute_effect(journal, executor, incident_id, block, "run")
            ]
        else:
            # Sin IP de origen: contencion por host (aislar + matar proceso).
            isolation = build_isolation(incident.host.id, action_id=_next_action_id(incident))
            incident.proposed_actions.append(isolation)
            kill = build_kill(incident.host.id, action_id=_next_action_id(incident))
            incident.proposed_actions.append(kill)
            incident.state = IncidentState.EXECUTING
            results = [
                await _execute_effect(journal, executor, incident_id, isolation, "run"),
                await _execute_effect(journal, executor, incident_id, kill, "run"),
            ]
        for result in results:
            _audit_result(audit, incident_id, "executed", result)
        decision.execution_status = _combined_status(results)
        incident.state = IncidentState.EXECUTED

    elif decision.outcome == "NO_ACTION":
        results = []
        for action in incident.proposed_actions:
            if action.type in _PROTECTIVE_REVERT_TYPES:
                result = await _execute_effect(
                    journal, executor, incident_id, action, "revert"
                )
                results.append(result)
                _audit_result(audit, incident_id, "reverted", result)
        decision.execution_status = (
            _combined_status(results) if results else "success"
        )
        # El estado (REJECTED) ya lo fijo quien escribio la decision.

    else:  # REVERTED: des-aislar / des-bloquear (boton "Revert if false alarm", ADR-0003)
        results = []
        for action in incident.proposed_actions:
            if action.type in _CONTAINMENT_REVERT_TYPES:
                result = await _execute_effect(
                    journal, executor, incident_id, action, "revert"
                )
                results.append(result)
                _audit_result(audit, incident_id, "reverted", result)
        decision.execution_status = (
            _combined_status(results) if results else "success"
        )
        incident.state = IncidentState.REVERTED

    decision.executed_at = now
    incident.updated_at = now
    await save_incident(r, incident)
    return incident
