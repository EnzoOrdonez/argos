"""Consumer + correlación (ADR-0013 §2.1-2.4 con review §7): DoD de Fase 3."""

from __future__ import annotations

from datetime import UTC, datetime

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
from argos_contracts.incident import Incident
from argos_contracts.triage import TriageResponse
from soar.audit.logger import AuditLogger
from soar.audit.memory import MemorySink
from soar.decision_engine.consumer import GROUP, STREAM, SOARConsumer, build_signal
from soar.execution.journal import MemoryExecutionStore, ResponseExecutionJournal
from soar.inventory import HOST_INVENTORY, resolve_host
from soar.playbooks.simulated import SimulatedExecutor


class _FakeNotifier:
    def __init__(self) -> None:
        self.dispatched: list[tuple[str, Tier]] = []

    def dispatch_for_tier(self, incident: Incident) -> list[object]:
        self.dispatched.append((incident.incident_id, incident.tier))
        return []


class _FakeScheduler:
    def __init__(self) -> None:
        self.t2_started: list[str] = []
        self.voice_started: list[str] = []

    def start_t2_timeout(self, incident_id: str) -> None:
        self.t2_started.append(incident_id)

    def start_voice_escalation(self, incident_id: str) -> None:
        self.voice_started.append(incident_id)


class _FakeTriage:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch(self, incident: Incident, fired_layers: frozenset[Layer]):
        self.calls.append(incident.incident_id)
        return TriageResponse(
            incident_id=incident.incident_id,
            tecnica_mitre="T1486",
            confianza=0.9,
            severidad=Severity.HIGH,
            runbook_aplicable="NIST SP 800-61r3, Containment",
            accion_recomendada="Aislar el host tras validar el patron de acceso.",
            llm_backend="fake",
            generated_at=datetime.now(UTC),
        )


class _Clock:
    def __init__(self, dt: datetime) -> None:
        self.dt = dt

    def __call__(self) -> datetime:
        return self.dt


def _alert(
    layer: Layer,
    *,
    host: str = "WIN-VICTIM-01",
    score: float = 0.85,
    severity: Severity = Severity.HIGH,
    technique: str | None = "T1078",
    alert_id: str = "alert-001",
) -> NormalizedAlert:
    return NormalizedAlert(
        alert_id=alert_id,
        source_layer=layer,
        timestamp=datetime.now(UTC),
        host_id=host,
        severity_score=score,
        severity_label=severity,
        technique_mitre=technique,
    )


def _consumer(
    r: FakeAsyncRedis,
    *,
    executor: SimulatedExecutor | None = None,
    notifier: _FakeNotifier | None = None,
    scheduler: _FakeScheduler | None = None,
    memory: MemorySink | None = None,
    triage: _FakeTriage | None = None,
    clock: _Clock | None = None,
) -> SOARConsumer:
    return SOARConsumer(
        r,
        executor=executor or SimulatedExecutor(),
        journal=ResponseExecutionJournal(MemoryExecutionStore()),
        notifier=notifier,  # type: ignore[arg-type]
        scheduler=scheduler,  # type: ignore[arg-type]
        audit=AuditLogger([memory]) if memory else None,
        triage=triage,  # type: ignore[arg-type]
        now_fn=clock,
    )


# -- inventario (§7.4) ---------------------------------------------------------


def test_inventario_resuelve_criticidad_por_host_id():
    assert resolve_host("LIN-VICTIM-01").criticality == Criticality.PRODUCTION_CRITICAL
    assert resolve_host("LIN-DB-01").criticality == Criticality.PRODUCTION_CRITICAL
    assert resolve_host("WIN-VICTIM-01").criticality == Criticality.STANDARD


def test_inventario_host_desconocido_cae_a_standard():
    host = resolve_host("HOST-NUEVO", ip="10.0.0.99")
    assert host.criticality == Criticality.STANDARD
    assert host.ip == "10.0.0.99"


def test_inventario_devuelve_copias():
    first = resolve_host("LIN-VICTIM-01")
    first.criticality = Criticality.STANDARD
    assert HOST_INVENTORY["LIN-VICTIM-01"].criticality == Criticality.PRODUCTION_CRITICAL
    assert resolve_host("LIN-VICTIM-01").criticality == Criticality.PRODUCTION_CRITICAL


# -- casos del DoD -------------------------------------------------------------


async def test_alerta_unica_l1_experimental_es_t3_solo_notifica():
    r = FakeAsyncRedis(decode_responses=True)
    notifier, scheduler = _FakeNotifier(), _FakeScheduler()
    consumer = _consumer(r, notifier=notifier, scheduler=scheduler)

    incident = await consumer.handle_alert(
        _alert(Layer.LAYER_1, score=0.4, severity=Severity.MEDIUM)
    )

    assert incident.tier == Tier.T3
    assert incident.state == IncidentState.RECEIVED
    assert incident.proposed_actions == []
    assert [t for _, t in notifier.dispatched] == [Tier.T3]
    assert scheduler.t2_started == []


async def test_t2_estandar_espera_con_throttle_snapshot_y_relojes():
    r = FakeAsyncRedis(decode_responses=True)
    executor, notifier, scheduler = SimulatedExecutor(), _FakeNotifier(), _FakeScheduler()
    consumer = _consumer(r, executor=executor, notifier=notifier, scheduler=scheduler)

    incident = await consumer.handle_alert(_alert(Layer.LAYER_1))  # HIGH -> T2

    assert incident.tier == Tier.T2
    assert incident.state == IncidentState.AWAITING_APPROVAL
    types = [a.type for a in incident.proposed_actions]
    assert types == [ActionType.PROCESS_THROTTLE, ActionType.DISK_SNAPSHOT]
    assert (ActionType.PROCESS_THROTTLE, "WIN-VICTIM-01") in executor.applied
    assert scheduler.t2_started == [incident.incident_id]
    assert scheduler.voice_started == [incident.incident_id]


async def test_corroboracion_de_2_capas_escala_tier_y_renotifica():
    """T3 (L1 experimental) + L2 dentro de la ventana -> T2 con re-notificación."""
    r = FakeAsyncRedis(decode_responses=True)
    executor, notifier, scheduler, memory = (
        SimulatedExecutor(),
        _FakeNotifier(),
        _FakeScheduler(),
        MemorySink(),
    )
    consumer = _consumer(
        r, executor=executor, notifier=notifier, scheduler=scheduler, memory=memory
    )

    first = await consumer.handle_alert(
        _alert(Layer.LAYER_1, score=0.4, severity=Severity.MEDIUM, alert_id="a-1")
    )
    second = await consumer.handle_alert(
        _alert(Layer.LAYER_2, score=0.5, severity=Severity.MEDIUM, alert_id="a-2")
    )

    assert first.incident_id == second.incident_id  # mismo incidente, no duplicado
    assert first.tier == Tier.T3
    assert second.tier == Tier.T2  # noisy-OR(0.4, 0.5) = 0.7 < 0.8 -> T2
    assert "tier_escalated" in memory.kinds()
    assert [t for _, t in notifier.dispatched] == [Tier.T3, Tier.T2]
    assert second.state == IncidentState.AWAITING_APPROVAL
    assert scheduler.t2_started == [second.incident_id]


async def test_fast_path_canary_va_directo_a_t0_sin_esperar_ventana():
    r = FakeAsyncRedis(decode_responses=True)
    executor, notifier, memory = SimulatedExecutor(), _FakeNotifier(), MemorySink()
    consumer = _consumer(r, executor=executor, notifier=notifier, memory=memory)

    incident = await consumer.handle_alert(
        _alert(Layer.LAYER_3, score=0.97, severity=Severity.CRITICAL, technique=None)
    )

    assert incident.tier == Tier.T0
    assert incident.state == IncidentState.EXECUTED
    assert incident.final_decision is not None
    assert incident.final_decision.outcome == "EXECUTE_ISOLATION"
    assert incident.final_decision.policy_applied == "auto-execute"
    assert (ActionType.HOST_ISOLATION, "WIN-VICTIM-01") in executor.applied
    assert [t for _, t in notifier.dispatched] == [Tier.T0]  # post-facto


async def test_tecnica_auto_t0_fast_path_uc06():
    r = FakeAsyncRedis(decode_responses=True)
    consumer = _consumer(r, notifier=_FakeNotifier())
    incident = await consumer.handle_alert(
        _alert(Layer.LAYER_1, host="EDGE-FW-01", technique="T1498")
    )
    assert incident.tier == Tier.T0
    assert incident.state == IncidentState.EXECUTED


async def test_alerta_post_decision_solo_se_anexa_al_audit():
    r = FakeAsyncRedis(decode_responses=True)
    executor, memory = SimulatedExecutor(), MemorySink()
    consumer = _consumer(r, executor=executor, memory=memory)

    decided = await consumer.handle_alert(
        _alert(Layer.LAYER_3, score=0.97, alert_id="a-1", technique=None)
    )
    actions_before = len(decided.proposed_actions)
    late = await consumer.handle_alert(
        _alert(Layer.LAYER_1, alert_id="a-2")  # llega en la rafaga de 5s
    )

    assert late.incident_id == decided.incident_id
    assert "alert_correlated" in memory.kinds()
    assert len(late.proposed_actions) == actions_before  # sin re-ejecutar


async def test_ids_con_patron_inc_y_contador_que_resetea_por_dia():
    r = FakeAsyncRedis(decode_responses=True)
    clock = _Clock(datetime(2026, 6, 10, 12, 0, tzinfo=UTC))
    consumer = _consumer(r, clock=clock)

    one = await consumer.handle_alert(
        _alert(Layer.LAYER_1, host="HOST-A", score=0.4, severity=Severity.MEDIUM)
    )
    two = await consumer.handle_alert(
        _alert(Layer.LAYER_1, host="HOST-B", score=0.4, severity=Severity.MEDIUM)
    )
    clock.dt = datetime(2026, 6, 11, 0, 5, tzinfo=UTC)
    three = await consumer.handle_alert(
        _alert(Layer.LAYER_1, host="HOST-C", score=0.4, severity=Severity.MEDIUM)
    )

    assert one.incident_id == "INC-2026-06-10-001"
    assert two.incident_id == "INC-2026-06-10-002"
    assert three.incident_id == "INC-2026-06-11-001"  # contador nuevo por dia


async def test_production_critical_activa_two_person_y_hook_llm_uc04():
    """UC-04: L1+L2 corroboradas (T1) sobre el host DB -> two-person + LLM."""
    r = FakeAsyncRedis(decode_responses=True)
    executor, scheduler, triage = SimulatedExecutor(), _FakeScheduler(), _FakeTriage()
    consumer = _consumer(r, executor=executor, scheduler=scheduler, triage=triage)

    await consumer.handle_alert(
        _alert(Layer.LAYER_1, host="LIN-VICTIM-01", score=0.85, alert_id="a-1")
    )
    incident = await consumer.handle_alert(
        _alert(Layer.LAYER_2, host="LIN-VICTIM-01", score=0.9, alert_id="a-2")
    )

    assert incident.tier == Tier.T1  # noisy-OR(0.85, 0.9) = 0.985 >= 0.80
    assert incident.host.criticality == Criticality.PRODUCTION_CRITICAL
    assert incident.state == IncidentState.AWAITING_APPROVAL  # NO auto-execute
    assert incident.final_decision is None
    assert (ActionType.PROCESS_THROTTLE, "LIN-VICTIM-01") in executor.applied
    assert (ActionType.DISK_SNAPSHOT, "LIN-VICTIM-01") in executor.applied
    assert incident.llm_analysis is not None  # gate T2 ∪ two-person (§7.5)
    assert triage.calls  # el hook se llamo


async def test_entrada_defectuosa_queda_sin_ack_y_no_tumba_el_loop():
    r = FakeAsyncRedis(decode_responses=True)
    memory = MemorySink()
    consumer = _consumer(r, memory=memory)
    await r.xadd(STREAM, {"payload": "esto no es json"})

    await consumer.run(once=True, block_ms=10)  # no lanza

    pending = await r.xpending(STREAM, GROUP)
    assert pending["pending"] == 1  # sin ACK: se reintenta

    # Reintentos 2 y 3: a la tercera entrega se descarta con audit (§7.7).
    entries = await r.xrange(STREAM)
    entry_id, fields = entries[0]
    await consumer._handle_entry(entry_id, fields)
    await consumer._handle_entry(entry_id, fields)

    pending = await r.xpending(STREAM, GROUP)
    assert pending["pending"] == 0
    assert "poison_discarded" in memory.kinds()


async def test_loop_procesa_entries_validos_y_ackea():
    r = FakeAsyncRedis(decode_responses=True)
    notifier = _FakeNotifier()
    consumer = _consumer(r, notifier=notifier)
    alert = _alert(Layer.LAYER_1, score=0.4, severity=Severity.MEDIUM)
    await r.xadd(STREAM, {"payload": alert.model_dump_json()})

    await consumer.run(once=True, block_ms=10)

    pending = await r.xpending(STREAM, GROUP)
    assert pending["pending"] == 0
    assert len(notifier.dispatched) == 1


def test_build_signal_funde_capas_con_noisy_or():
    a1 = _alert(Layer.LAYER_1, score=0.85, alert_id="a-1")
    a2 = _alert(Layer.LAYER_2, score=0.9, alert_id="a-2")
    signal = build_signal([a1, a2], "WIN-VICTIM-01")
    assert signal.fired_layers == frozenset({Layer.LAYER_1, Layer.LAYER_2})
    assert signal.corroboration_confidence is not None
    assert abs(signal.corroboration_confidence - 0.985) < 1e-9
    assert signal.contributing_alert_ids == ("a-1", "a-2")


# -- Safety rail explícito (RF-4, Gate 1: consumer._act) ----------------------


async def test_require_approval_rail_blocks_t0_auto_execute():
    """Con require_approval=True, un T0 (canary) que la matemática de tiers
    auto-ejecutaría (cf. test_fast_path_canary_va_directo_a_t0) queda esperando
    aprobación humana. El rail es un control explícito, no emergente del tier."""
    r = FakeAsyncRedis(decode_responses=True)
    executor, notifier, scheduler = SimulatedExecutor(), _FakeNotifier(), _FakeScheduler()
    consumer = SOARConsumer(
        r,
        executor=executor,
        journal=ResponseExecutionJournal(MemoryExecutionStore()),
        notifier=notifier,
        scheduler=scheduler,
        require_approval=True,
    )

    incident = await consumer.handle_alert(
        _alert(Layer.LAYER_3, score=0.97, severity=Severity.CRITICAL, technique=None)
    )

    assert incident.tier == Tier.T0  # la matemática de tiers no cambia
    assert incident.state == IncidentState.AWAITING_APPROVAL  # el rail forzó la espera
    assert incident.final_decision is None  # NO auto-ejecutó
    # las acciones protectoras pre-aprobación (throttle) igual corren
    assert (ActionType.PROCESS_THROTTLE, "WIN-VICTIM-01") in executor.applied
    assert scheduler.t2_started == [incident.incident_id]


async def test_require_approval_rail_blocks_t1_auto_execute():
    """Gate 1 cubre T1 también: L1+L2 corroborado (noisy-OR ≥ 0.80) en host
    estándar daría T1 auto-execute; con el rail queda AWAITING_APPROVAL."""
    r = FakeAsyncRedis(decode_responses=True)
    executor, notifier, scheduler = SimulatedExecutor(), _FakeNotifier(), _FakeScheduler()
    consumer = SOARConsumer(
        r,
        executor=executor,
        journal=ResponseExecutionJournal(MemoryExecutionStore()),
        notifier=notifier,
        scheduler=scheduler,
        require_approval=True,
    )

    await consumer.handle_alert(
        _alert(Layer.LAYER_1, score=0.85, severity=Severity.HIGH, alert_id="l1")
    )
    incident = await consumer.handle_alert(
        _alert(Layer.LAYER_2, score=0.9, severity=Severity.HIGH, alert_id="l2")
    )

    assert incident.tier == Tier.T1  # corroboración fuerte
    assert incident.state == IncidentState.AWAITING_APPROVAL
    assert incident.final_decision is None  # el rail bloqueó el auto-execute de T1
