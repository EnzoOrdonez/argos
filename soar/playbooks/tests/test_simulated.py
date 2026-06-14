"""SimulatedExecutor: invariantes de ADR-0012 §2.4 con el executor demo-safe."""

from __future__ import annotations

from argos_contracts.enums import ActionType
from soar.playbooks.builders import build_isolation, build_snapshot, build_throttle
from soar.playbooks.simulated import SimulatedExecutor


def test_secuencia_throttle_snapshot_pre_aprobacion():
    """ADR-0006 Sit.B / ADR-0012 §2.2: throttle + snapshot disparan sin
    aprobación previa. No interviene ningún aprobador en esta secuencia."""
    executor = SimulatedExecutor()
    throttle = build_throttle("LIN-DB-01", action_id="act-001")
    snapshot = build_snapshot("LIN-DB-01", action_id="act-002")

    r1 = executor.run(throttle)
    r2 = executor.run(snapshot)

    assert r1.ok and r2.ok
    assert (ActionType.PROCESS_THROTTLE, "LIN-DB-01") in executor.applied
    assert (ActionType.DISK_SNAPSHOT, "LIN-DB-01") in executor.applied
    assert [op for op, _, _ in executor.history] == ["run", "run"]


def test_idempotencia_re_ejecutar_es_noop():
    executor = SimulatedExecutor()
    isolation = build_isolation("WIN-VICTIM-01", action_id="act-001")

    first = executor.run(isolation)
    second = executor.run(isolation)

    assert first.ok and second.ok
    assert "no-op" in second.detail
    assert len(executor.applied) == 1


def test_fail_soft_un_playbook_que_falla_no_lanza():
    executor = SimulatedExecutor(fail_on={ActionType.HOST_ISOLATION})
    result = executor.run(build_isolation("h", action_id="act-001"))
    assert result.status == "failed"
    assert not result.ok
    # El fallo no quedo registrado como aplicado.
    assert executor.applied == {}


def test_partial_inyectado():
    executor = SimulatedExecutor(partial_on={ActionType.PROCESS_THROTTLE})
    result = executor.run(build_throttle("h", action_id="act-001"))
    assert result.status == "partial"


def test_revert_de_isolation_remueve_el_estado():
    executor = SimulatedExecutor()
    isolation = build_isolation("h", action_id="act-001")
    executor.run(isolation)

    result = executor.revert(isolation)

    assert result.ok
    assert executor.applied == {}


def test_revert_de_snapshot_es_noop_documentado():
    executor = SimulatedExecutor()
    snapshot = build_snapshot("h", action_id="act-001")
    executor.run(snapshot)

    result = executor.revert(snapshot)

    assert result.ok
    assert "no-op" in result.detail
    # El snapshot queda registrado: no se "des-toma".
    assert (ActionType.DISK_SNAPSHOT, "h") in executor.applied


def test_revert_sin_aplicar_es_noop_success():
    executor = SimulatedExecutor()
    result = executor.revert(build_isolation("h", action_id="act-001"))
    assert result.ok
    assert "no-op" in result.detail


def test_fail_revert_inyectado():
    executor = SimulatedExecutor(fail_revert_on={ActionType.PROCESS_THROTTLE})
    throttle = build_throttle("h", action_id="act-001")
    executor.run(throttle)
    result = executor.revert(throttle)
    assert result.status == "failed"
