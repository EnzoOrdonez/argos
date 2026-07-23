"""Fase 1 — modo live: `--live` deja el incidente esperando aprobación y
`live_approve.cast_vote` castea votos reales reusando los handlers del SOAR.
fakeredis, sin lab. El camino simulado de `demo_injector` queda cubierto por su
smoke `--in-process` (se corre aparte)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import _runtime
import demo_injector
import live_approve
import pytest
from fakeredis import FakeAsyncRedis

from argos_contracts.alert import NormalizedAlert
from argos_contracts.enums import (
    ActionType,
    Criticality,
    IncidentState,
    Layer,
    Severity,
    Tier,
)
from argos_contracts.incident import Incident, ProposedAction
from argos_contracts.triage import HostInfo
from soar.approval_api.handlers import load_incident, save_incident
from soar.audit.logger import AuditLogger
from soar.audit.memory import MemorySink
from soar.decision_engine.scheduler import WindowScheduler
from soar.execution.journal import MemoryExecutionStore, ResponseExecutionJournal
from soar.playbooks.factory import ExecutorConfigurationError
from soar.playbooks.simulated import SimulatedExecutor
from soar.playbooks.wazuh import WazuhActiveResponseExecutor


@pytest.fixture(autouse=True)
def explicit_test_executor(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ARGOS_EXECUTOR", "simulated")


async def _instant_sleep(_seconds: float) -> None:
    return None


def _journal() -> ResponseExecutionJournal:
    return ResponseExecutionJournal(MemoryExecutionStore())


def _fast_scheduler(r: FakeAsyncRedis) -> WindowScheduler:
    """Scheduler con sleep instantáneo y ventana 0s: cierra la ventana sin dormir."""
    return WindowScheduler(
        r,
        audit=AuditLogger([MemorySink()]),
        sleep=_instant_sleep,
        consolidation_seconds=0,
    )


async def _awaiting_uc04(r: FakeAsyncRedis) -> str:
    """Inyecta uc04 en modo live (sin votos) y devuelve el incident_id en espera."""
    consumer, _, scheduler, _, _ = demo_injector.build_runtime(
        r, live=True, executor=SimulatedExecutor(), journal=_journal()
    )
    incident_id = await demo_injector.inject_scenario(
        r, demo_injector._scenarios()["uc04"], consumer
    )
    for task in list(scheduler._tasks):
        task.cancel()
    return incident_id


# -- `--live` deja el incidente esperando (sin votos, sin decisión) ------------

async def test_live_injection_leaves_incident_awaiting() -> None:
    r = FakeAsyncRedis(decode_responses=True)
    incident_id = await _awaiting_uc04(r)
    incident = await load_incident(r, incident_id)
    assert incident.state == IncidentState.AWAITING_APPROVAL
    assert incident.approvers == []
    assert incident.final_decision is None


# -- two-person: 2 approve -> EXECUTE_ISOLATION --------------------------------

async def test_cast_vote_two_person_two_approvals_execute() -> None:
    r = FakeAsyncRedis(decode_responses=True)
    incident_id = await _awaiting_uc04(r)
    executor = SimulatedExecutor()
    audit = AuditLogger([MemorySink()])
    scheduler = _fast_scheduler(r)

    await live_approve.cast_vote(
        r, incident_id, email="telegram:a", role="approver",
        decision="approve", executor=executor, journal=_journal(),
        scheduler=scheduler, audit=audit, wait=False,
    )
    incident = await live_approve.cast_vote(
        r, incident_id, email="telegram:b", role="approver",
        decision="approve", executor=executor, journal=_journal(),
        scheduler=scheduler, audit=audit, wait=False,
    )

    assert incident.final_decision is not None
    assert incident.final_decision.outcome == "EXECUTE_ISOLATION"
    assert incident.final_decision.policy_applied == "two-person-rule"
    assert any(op == "run" for op, _, _ in executor.history)  # se ejecutó contención


# -- two-person: 1 reject -> NO_ACTION (cancela de inmediato) ------------------

async def test_cast_vote_two_person_reject_cancels() -> None:
    r = FakeAsyncRedis(decode_responses=True)
    incident_id = await _awaiting_uc04(r)
    executor = SimulatedExecutor()

    incident = await live_approve.cast_vote(
        r, incident_id, email="telegram:a", role="approver",
        decision="reject", executor=executor, journal=_journal(), scheduler=_fast_scheduler(r),
        audit=AuditLogger([MemorySink()]), wait=False,
    )

    assert incident.final_decision is not None
    assert incident.final_decision.outcome == "NO_ACTION"
    assert incident.final_decision.policy_applied == "two-person-rule"


# -- conservative-wins solo-reject: se fija al cerrar la ventana ---------------

def _conservative_incident() -> Incident:
    now = datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC)
    return Incident(
        incident_id="INC-2026-06-26-900",
        created_at=now,
        updated_at=now,
        tier=Tier.T2,
        state=IncidentState.AWAITING_APPROVAL,
        host=HostInfo(
            id="WIN-VICTIM-01", criticality=Criticality.STANDARD, ip="10.0.0.5", os="Win10"
        ),
        alert=NormalizedAlert(
            alert_id="cw-1", source_layer=Layer.LAYER_1, timestamp=now,
            host_id="WIN-VICTIM-01", severity_score=0.6, severity_label=Severity.MEDIUM,
            technique_mitre="T1486",
        ),
        proposed_actions=[
            ProposedAction(
                id="act-1", type=ActionType.HOST_ISOLATION, target="WIN-VICTIM-01", reversible=True
            )
        ],
    )


async def test_cast_vote_conservative_reject_waits_window() -> None:
    r = FakeAsyncRedis(decode_responses=True)
    incident = _conservative_incident()
    await save_incident(r, incident)

    result = await live_approve.cast_vote(
        r, incident.incident_id, email="local:op", role="approver",
        decision="reject", executor=SimulatedExecutor(), journal=_journal(),
        scheduler=_fast_scheduler(r),
        audit=AuditLogger([MemorySink()]), wait=True,
    )

    assert result.final_decision is not None  # no cuelga: la ventana resolvió
    assert result.final_decision.outcome == "NO_ACTION"
    assert result.final_decision.policy_applied == "conservative-wins"


# -- make_executor() valida ENVIRONMENT + ARGOS_EXECUTOR (fail-closed) ---------

def test_make_executor_without_mode_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("ARGOS_EXECUTOR", raising=False)
    with pytest.raises(ExecutorConfigurationError):
        _runtime.make_executor()


def test_make_executor_wazuh_without_config_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ARGOS_EXECUTOR", "wazuh")
    for key in ("WAZUH_API_URL", "WAZUH_API_USER", "WAZUH_API_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ExecutorConfigurationError):
        _runtime.make_executor()


def test_make_executor_wazuh_with_config(monkeypatch) -> None:
    monkeypatch.setenv("ARGOS_EXECUTOR", "wazuh")
    monkeypatch.setenv("WAZUH_API_URL", "https://wazuh.lab:55000")
    monkeypatch.setenv("WAZUH_API_USER", "argos")
    monkeypatch.setenv("WAZUH_API_PASSWORD", "secret")
    assert isinstance(_runtime.make_executor(), WazuhActiveResponseExecutor)


def test_make_executor_unknown_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ARGOS_EXECUTOR", "bogus")
    with pytest.raises(ExecutorConfigurationError):
        _runtime.make_executor()


async def test_live_approve_validates_executor_before_opening_redis(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ARGOS_EXECUTOR", "simulated")

    def must_not_open_redis(*_args, **_kwargs):
        raise AssertionError("Redis opened before executor validation")

    monkeypatch.setattr(live_approve.aioredis, "from_url", must_not_open_redis)
    with pytest.raises(ExecutorConfigurationError):
        await live_approve.run(SimpleNamespace(redis_url="redis://must-not-open"))


def test_live_demo_validates_executor_before_postgres(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ARGOS_EXECUTOR", "simulated")
    monkeypatch.setenv("ARGOS_AUDIT_SQL_DSN", "postgresql://unused")

    def must_not_initialize(_dsn: str) -> None:
        raise AssertionError("PostgresSink initialized before executor validation")

    monkeypatch.setattr("soar.audit.postgres.PostgresSink", must_not_initialize)
    with pytest.raises(ExecutorConfigurationError):
        demo_injector.build_runtime(object(), live=True)
