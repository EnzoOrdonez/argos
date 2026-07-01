"""uc03 (CENTERPIECE) — split-brain ML-only T2 -> conservative-wins.

Verifica el desenlace completo del escenario que el injector arma por el camino de
cierre de ventana (`drive_window_scenario`): T2 (ML sola, score 0.74), throttle +
snapshot proactivos PRE-aprobacion, 2 approve / 1 reject / 1 timeout, y resolucion
conservative-wins con `conflict_detected` + el aprobador no-votante marcado TIMEOUT.
fakeredis, sin lab. Usa la logica real de soar (finalize_after_window/_evaluate)."""

from __future__ import annotations

import demo_injector
from fakeredis import FakeAsyncRedis

from argos_contracts.enums import (
    ActionType,
    ApproverStatus,
    Criticality,
    IncidentState,
    Tier,
)
from soar.approval_api.handlers import load_incident


async def _run_uc03() -> tuple:
    r = FakeAsyncRedis(decode_responses=True)
    consumer, executor, scheduler, audit, _ = demo_injector.build_runtime(
        r, live=False, fast_window=True
    )
    scenario = demo_injector._scenarios()["uc03"]
    incident_id = await demo_injector.inject_scenario(r, scenario, consumer)
    await demo_injector.drive_window_scenario(
        r, incident_id, scenario, scheduler=scheduler, executor=executor, audit=audit
    )
    incident = await load_incident(r, incident_id)
    return incident, executor


async def test_uc03_routes_t2_ml_alone_standard_host() -> None:
    incident, _ = await _run_uc03()
    assert incident.tier == Tier.T2                       # ML sola, score 0.74
    assert incident.host.criticality == Criticality.STANDARD  # -> conservative-wins


async def test_uc03_proactive_throttle_and_snapshot_before_approval() -> None:
    incident, _ = await _run_uc03()
    types = [a.type for a in incident.proposed_actions]
    assert ActionType.PROCESS_THROTTLE in types          # acota dano durante la espera
    assert ActionType.DISK_SNAPSHOT in types             # preserva estado forense


async def test_uc03_split_brain_resolves_conservative_wins() -> None:
    incident, executor = await _run_uc03()
    assert incident.state == IncidentState.EXECUTED
    assert incident.final_decision is not None
    assert incident.final_decision.outcome == "EXECUTE_ISOLATION"
    assert incident.final_decision.policy_applied == "conservative-wins"
    assert incident.final_decision.execution_status == "success"
    # contencion ejecutada (isolation + kill) sobre el executor simulado
    assert any(op == "run" for op, _, _ in executor.history)


async def test_uc03_conflict_detected_and_timeout_marked() -> None:
    incident, _ = await _run_uc03()
    assert incident.consolidation_window is not None
    assert incident.consolidation_window.conflict_detected is True   # split-brain
    by_email = {a.email: a for a in incident.approvers}
    assert by_email["telegram:enzo"].status == ApproverStatus.REJECTED
    assert by_email["telegram:p2"].status == ApproverStatus.APPROVED
    assert by_email["telegram:p3"].status == ApproverStatus.APPROVED
    # el aprobador que no respondio quedo TIMEOUT al cerrar la ventana
    assert by_email["telegram:p4"].status == ApproverStatus.TIMEOUT
