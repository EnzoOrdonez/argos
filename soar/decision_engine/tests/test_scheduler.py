"""Los tres relojes (ADR-0013 §7.6): deterministas, con sleep inyectado."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fakeredis import FakeAsyncRedis

from argos_contracts.enums import (
    ApproverStatus,
    Criticality,
    IncidentState,
    NotificationChannelType,
    Tier,
)
from argos_contracts.incident import ApproverState, FinalDecision, Incident
from argos_contracts.triage import HostInfo
from soar.approval_api.handlers import load_incident, save_incident
from soar.audit.logger import AuditLogger
from soar.audit.memory import MemorySink
from soar.decision_engine.scheduler import WindowScheduler
from soar.notifications.base import DispatchResult


class _InstantSleep:
    """Sleep falso: registra el delay pedido y resuelve al instante."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


class _FakeVoice:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def escalate_to_voice(self, incident: Incident) -> DispatchResult:
        self.calls.append(incident.incident_id)
        return DispatchResult(
            channel=NotificationChannelType.TWILIO_VOICE, success=True, latency_ms=5
        )


def _standard_host() -> HostInfo:
    return HostInfo(
        id="WIN-VICTIM-01", criticality=Criticality.STANDARD, ip="10.0.0.21", os="Win11"
    )


def _vote(decision: ApproverStatus, email: str) -> ApproverState:
    return ApproverState(
        email=email,
        role="approver",
        status=decision,
        responded_at=datetime.now(UTC),
        channel=NotificationChannelType.TELEGRAM,
    )


class _DecisionSpy:
    def __init__(self) -> None:
        self.incidents: list[Incident] = []

    async def __call__(self, incident: Incident) -> None:
        self.incidents.append(incident)


def _scheduler(
    r: FakeAsyncRedis,
    *,
    notifier: _FakeVoice | None = None,
    memory: MemorySink | None = None,
    spy: _DecisionSpy | None = None,
    sleep: _InstantSleep | None = None,
) -> WindowScheduler:
    return WindowScheduler(
        r,
        notifier=notifier,  # type: ignore[arg-type]  # duck-typed en tests
        audit=AuditLogger([memory]) if memory else None,
        on_decision=spy,
        sleep=sleep or _InstantSleep(),
        consolidation_seconds=60,
        t2_timeout_seconds=180,
    )


async def _drain(scheduler: WindowScheduler) -> None:
    await asyncio.gather(*scheduler._tasks)


# -- Reloj B: timeout T2 -----------------------------------------------------


async def test_t2_timeout_sin_votos_host_estandar_aplica_failsafe(make_incident):
    """ADR-0003 §T2: el atacante no gana por silencio."""
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T2, host=_standard_host())
    await save_incident(r, incident)
    memory, spy, sleep = MemorySink(), _DecisionSpy(), _InstantSleep()
    scheduler = _scheduler(r, memory=memory, spy=spy, sleep=sleep)

    await scheduler.start_t2_timeout(incident.incident_id)

    final = await load_incident(r, incident.incident_id)
    assert final.final_decision is not None
    assert final.final_decision.outcome == "EXECUTE_ISOLATION"
    assert final.final_decision.policy_applied == "timeout-escalation"
    assert final.state == IncidentState.PENDING_EXECUTION
    assert sleep.delays == [180]
    assert "decision_final" in memory.kinds()
    assert [i.incident_id for i in spy.incidents] == [incident.incident_id]


async def test_t2_timeout_production_critical_espera_sin_auto_execute(make_incident):
    """ADR-0006 Sit.B, caso 3 AM: four-eyes no se anula por timeout."""
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T2)  # host default: production-critical
    await save_incident(r, incident)
    memory, spy = MemorySink(), _DecisionSpy()
    scheduler = _scheduler(r, memory=memory, spy=spy)

    await scheduler.start_t2_timeout(incident.incident_id)

    final = await load_incident(r, incident.incident_id)
    assert final.final_decision is None
    assert final.state == IncidentState.AWAITING_APPROVAL
    assert memory.kinds() == ["timeout_wait"]
    assert spy.incidents == []


async def test_require_approval_blocks_t2_timeout_failsafe(make_incident):
    """Rail airtight (RF-4, Gate 2): con require_approval, el failsafe de timeout
    NO auto-aísla a un host estándar sin votos — a diferencia del comportamiento
    default (test_t2_timeout_sin_votos_host_estandar_aplica_failsafe), que sí cierra
    con EXECUTE_ISOLATION. Segundo camino de auto-ejecución sin humano, gateado."""
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T2, host=_standard_host())
    await save_incident(r, incident)
    memory, spy, sleep = MemorySink(), _DecisionSpy(), _InstantSleep()
    scheduler = WindowScheduler(
        r,
        audit=AuditLogger([memory]),
        on_decision=spy,
        sleep=sleep,
        require_approval=True,
    )

    await scheduler.start_t2_timeout(incident.incident_id)

    final = await load_incident(r, incident.incident_id)
    assert final.final_decision is None  # el rail bloqueó el failsafe
    assert final.state == IncidentState.AWAITING_APPROVAL
    assert memory.kinds() == ["timeout_wait"]
    assert spy.incidents == []
    assert sleep.delays == [180]


async def test_t2_timeout_con_decision_previa_no_hace_nada(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T2, host=_standard_host())
    incident.final_decision = FinalDecision(
        outcome="NO_ACTION", policy_applied="two-person-rule", rationale="reject previo"
    )
    await save_incident(r, incident)
    memory, spy = MemorySink(), _DecisionSpy()
    scheduler = _scheduler(r, memory=memory, spy=spy)

    await scheduler.start_t2_timeout(incident.incident_id)

    assert memory.kinds() == []
    assert spy.incidents == []


async def test_t2_timeout_con_votos_difiere_a_la_ventana(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T2, host=_standard_host())
    incident.approvers.append(_vote(ApproverStatus.APPROVED, "telegram:1"))
    await save_incident(r, incident)
    scheduler = _scheduler(r)

    await scheduler.start_t2_timeout(incident.incident_id)

    final = await load_incident(r, incident.incident_id)
    assert final.final_decision is None  # la ventana decide, no el timer


# -- Reloj A: ventana de consolidacion ---------------------------------------


async def test_primer_voto_puebla_ventana_y_cierra_con_reject(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T2, host=_standard_host())
    incident.approvers.append(_vote(ApproverStatus.REJECTED, "telegram:1"))
    await save_incident(r, incident)
    sleep = _InstantSleep()
    scheduler = _scheduler(r, sleep=sleep)

    started = await scheduler.ensure_consolidation_started(incident.incident_id)
    again = await scheduler.ensure_consolidation_started(incident.incident_id)
    await _drain(scheduler)

    assert started is True
    assert again is False  # idempotente: solo el primer voto agenda
    final = await load_incident(r, incident.incident_id)
    assert final.consolidation_window is not None
    assert final.consolidation_window.duration_seconds == 60
    assert final.consolidation_window.ended_at is not None
    assert final.consolidation_window.conflict_detected is False
    assert final.final_decision is not None
    assert final.final_decision.outcome == "NO_ACTION"
    assert final.final_decision.policy_applied == "conservative-wins"
    assert sleep.delays == [60]


async def test_ventana_con_conflicto_marca_conflict_y_gana_aislar(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T2, host=_standard_host())
    incident.approvers.append(_vote(ApproverStatus.REJECTED, "telegram:1"))
    incident.approvers.append(_vote(ApproverStatus.APPROVED, "telegram:2"))
    await save_incident(r, incident)
    scheduler = _scheduler(r)

    await scheduler.ensure_consolidation_started(incident.incident_id)
    await _drain(scheduler)

    final = await load_incident(r, incident.incident_id)
    assert final.consolidation_window is not None
    assert final.consolidation_window.conflict_detected is True
    assert final.final_decision is not None
    assert final.final_decision.outcome == "EXECUTE_ISOLATION"
    assert final.final_decision.policy_applied == "conservative-wins"


async def test_ventana_two_person_sin_quorum_sigue_esperando(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T1)  # host critico: two-person
    incident.approvers.append(_vote(ApproverStatus.APPROVED, "telegram:1"))
    await save_incident(r, incident)
    memory = MemorySink()
    scheduler = _scheduler(r, memory=memory)

    await scheduler.ensure_consolidation_started(incident.incident_id)
    await _drain(scheduler)

    final = await load_incident(r, incident.incident_id)
    assert final.final_decision is None  # 1 approve < quorum de 2 (Sit.B)
    assert final.state == IncidentState.AWAITING_APPROVAL
    assert "timeout_wait" in memory.kinds()


async def test_ensure_sin_votos_no_arranca_ventana(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T2, host=_standard_host())
    await save_incident(r, incident)
    scheduler = _scheduler(r)

    assert await scheduler.ensure_consolidation_started(incident.incident_id) is False
    final = await load_incident(r, incident.incident_id)
    assert final.consolidation_window is None


# -- Reloj C: escalacion por voz ---------------------------------------------


async def test_voz_escala_a_los_60s_sin_respuesta(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T2, host=_standard_host())
    await save_incident(r, incident)
    voice, memory, sleep = _FakeVoice(), MemorySink(), _InstantSleep()
    scheduler = _scheduler(r, notifier=voice, memory=memory, sleep=sleep)

    await scheduler.start_voice_escalation(incident.incident_id)

    assert voice.calls == [incident.incident_id]
    assert "voice_escalated" in memory.kinds()
    assert sleep.delays == [60]


async def test_voz_no_escala_si_ya_hubo_respuesta(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    incident = make_incident(tier=Tier.T2, host=_standard_host())
    incident.approvers.append(_vote(ApproverStatus.APPROVED, "telegram:1"))
    await save_incident(r, incident)
    voice = _FakeVoice()
    scheduler = _scheduler(r, notifier=voice)

    await scheduler.start_voice_escalation(incident.incident_id)

    assert voice.calls == []
