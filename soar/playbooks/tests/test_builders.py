"""Builders puros de ProposedAction (ADR-0012 §2.5)."""

from __future__ import annotations

import pytest

from argos_contracts.enums import ActionType
from soar.playbooks.builders import (
    build_block_ip,
    build_isolation,
    build_kill,
    build_snapshot,
    build_throttle,
)


def test_builders_arman_los_cuatro_tipos_del_catalogo():
    throttle = build_throttle("LIN-DB-01", action_id="act-001")
    snapshot = build_snapshot("LIN-DB-01", action_id="act-002")
    isolation = build_isolation("LIN-DB-01", action_id="act-003")
    kill = build_kill("LIN-DB-01", action_id="act-004", pid=4242)

    assert throttle.type == ActionType.PROCESS_THROTTLE
    assert snapshot.type == ActionType.DISK_SNAPSHOT
    assert isolation.type == ActionType.HOST_ISOLATION
    assert kill.type == ActionType.PROCESS_KILL
    assert [a.id for a in (throttle, snapshot, isolation, kill)] == [
        "act-001",
        "act-002",
        "act-003",
        "act-004",
    ]
    assert all(a.target == "LIN-DB-01" for a in (throttle, snapshot, isolation, kill))


def test_reversible_true_en_los_cuatro_para_no_activar_two_person_por_accion():
    # ADR-0012 §7.3: requires_two_person() solo se activa por criticidad del host.
    actions = [
        build_throttle("h", action_id="act-001"),
        build_snapshot("h", action_id="act-002"),
        build_isolation("h", action_id="act-003"),
        build_kill("h", action_id="act-004"),
    ]
    assert all(a.reversible for a in actions)


def test_throttle_lee_parametros_del_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THROTTLE_CPU_PERCENT_LIMIT", "25")
    monkeypatch.setenv("THROTTLE_IO_PRIORITY", "best-effort")
    action = build_throttle("WIN-VICTIM-01", action_id="act-001", pid=1234)
    assert action.parameters["cpu_percent_limit"] == 25
    assert action.parameters["io_priority"] == "best-effort"
    assert action.parameters["pid"] == 1234


def test_throttle_defaults_sin_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("THROTTLE_CPU_PERCENT_LIMIT", raising=False)
    monkeypatch.delenv("THROTTLE_IO_PRIORITY", raising=False)
    action = build_throttle("WIN-VICTIM-01", action_id="act-001")
    assert action.parameters == {"cpu_percent_limit": 10, "io_priority": "idle"}


def test_build_block_ip_lleva_la_srcip_en_parameters():
    action = build_block_ip("web-prod-01", action_id="act-001", src_ip="203.0.113.7")
    assert action.type == ActionType.BLOCK_IP
    assert action.target == "web-prod-01"  # target = host; la IP va en parameters
    assert action.parameters == {"src_ip": "203.0.113.7"}
    assert action.reversible is True  # se des-dropea la regla
