"""Contención al resolverse la decisión (ADR-0013 §2.7): los tres outcomes."""

from __future__ import annotations

from fakeredis import FakeAsyncRedis

from argos_contracts.enums import ActionType, Criticality, IncidentState, Tier
from argos_contracts.incident import FinalDecision
from argos_contracts.triage import HostInfo
from soar.approval_api.handlers import save_incident
from soar.audit.logger import AuditLogger
from soar.audit.memory import MemorySink
from soar.decision_engine.containment import apply_decision
from soar.playbooks.builders import build_snapshot, build_throttle
from soar.playbooks.simulated import SimulatedExecutor


def _standard_host() -> HostInfo:
    return HostInfo(
        id="WIN-VICTIM-01", criticality=Criticality.STANDARD, ip="10.0.0.21", os="Win11"
    )


def _decision(outcome: str) -> FinalDecision:
    return FinalDecision(
        outcome=outcome,  # type: ignore[arg-type]
        policy_applied="auto-execute",
        rationale="test",
    )


async def test_execute_isolation_corre_isolation_y_kill(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T1, host=_standard_host())
    incident.final_decision = _decision("EXECUTE_ISOLATION")
    await save_incident(r, incident)
    executor, memory = SimulatedExecutor(), MemorySink()

    result = await apply_decision(
        r, incident.incident_id, executor=executor, audit=AuditLogger([memory])
    )

    assert result.state == IncidentState.EXECUTED
    assert result.final_decision is not None
    assert result.final_decision.execution_status == "success"
    assert result.final_decision.executed_at is not None
    assert (ActionType.HOST_ISOLATION, "WIN-VICTIM-01") in executor.applied
    assert (ActionType.PROCESS_KILL, "WIN-VICTIM-01") in executor.applied
    assert memory.kinds() == ["action_executed", "action_executed"]


async def test_apply_decision_es_idempotente(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T1, host=_standard_host())
    incident.final_decision = _decision("EXECUTE_ISOLATION")
    await save_incident(r, incident)
    executor = SimulatedExecutor()

    first = await apply_decision(r, incident.incident_id, executor=executor)
    second = await apply_decision(r, incident.incident_id, executor=executor)

    assert len(first.proposed_actions) == 2
    assert len(second.proposed_actions) == 2  # no duplica acciones
    assert len(executor.history) == 2  # no re-ejecuta


async def test_fallo_parcial_queda_como_partial_sin_lanzar(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T1, host=_standard_host())
    incident.final_decision = _decision("EXECUTE_ISOLATION")
    await save_incident(r, incident)
    executor = SimulatedExecutor(fail_on={ActionType.HOST_ISOLATION})

    result = await apply_decision(r, incident.incident_id, executor=executor)

    assert result.final_decision is not None
    assert result.final_decision.execution_status == "partial"  # kill si entro


async def test_fallo_total_queda_como_failed(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T1, host=_standard_host())
    incident.final_decision = _decision("EXECUTE_ISOLATION")
    await save_incident(r, incident)
    executor = SimulatedExecutor(
        fail_on={ActionType.HOST_ISOLATION, ActionType.PROCESS_KILL}
    )

    result = await apply_decision(r, incident.incident_id, executor=executor)

    assert result.final_decision is not None
    assert result.final_decision.execution_status == "failed"


async def test_no_action_revierte_el_throttle_y_conserva_snapshot(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    executor, memory = SimulatedExecutor(), MemorySink()
    throttle = build_throttle("LIN-DB-01", action_id="act-001")
    snapshot = build_snapshot("LIN-DB-01", action_id="act-002")
    executor.run(throttle)
    executor.run(snapshot)
    incident = make_incident(tier=Tier.T2, proposed_actions=[throttle, snapshot])
    incident.final_decision = FinalDecision(
        outcome="NO_ACTION", policy_applied="two-person-rule", rationale="reject"
    )
    await save_incident(r, incident)

    result = await apply_decision(
        r, incident.incident_id, executor=executor, audit=AuditLogger([memory])
    )

    assert result.final_decision is not None
    assert result.final_decision.execution_status == "success"
    assert (ActionType.PROCESS_THROTTLE, "LIN-DB-01") not in executor.applied
    assert (ActionType.DISK_SNAPSHOT, "LIN-DB-01") in executor.applied  # evidencia
    assert "action_reverted" in memory.kinds()


async def test_reverted_des_aisla_y_transiciona(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    executor = SimulatedExecutor()
    from soar.playbooks.builders import build_isolation

    isolation = build_isolation("WIN-VICTIM-01", action_id="act-001")
    executor.run(isolation)
    incident = make_incident(
        tier=Tier.T0, host=_standard_host(), proposed_actions=[isolation]
    )
    incident.final_decision = FinalDecision(
        outcome="REVERTED", policy_applied="auto-execute", rationale="falsa alarma"
    )
    await save_incident(r, incident)

    result = await apply_decision(r, incident.incident_id, executor=executor)

    assert result.state == IncidentState.REVERTED
    assert (ActionType.HOST_ISOLATION, "WIN-VICTIM-01") not in executor.applied


async def test_sin_decision_no_hace_nada(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T2)
    await save_incident(r, incident)
    executor = SimulatedExecutor()

    result = await apply_decision(r, incident.incident_id, executor=executor)

    assert result.final_decision is None
    assert executor.history == []
