"""PostgresSink: mapea AuditEvent -> audit_incidents/audit_responses y es fail-soft
(nunca lanza desde emit, ni con la DB caída ni sin conexión)."""

from __future__ import annotations

from datetime import datetime, timezone

from soar.audit.base import AuditEvent
from soar.audit.postgres import PostgresSink

_TS = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


class _FakeConn:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._fail = fail

    def execute(self, sql: str, params: dict | None = None):
        if self._fail:
            raise RuntimeError("db down")
        self.calls.append((sql, params or {}))


def _event(kind: str, incident_id: str, **payload) -> AuditEvent:
    return AuditEvent(ts=_TS, kind=kind, incident_id=incident_id, payload=payload)


def test_incident_created_inserts_with_contract_values() -> None:
    conn = _FakeConn()
    sink = PostgresSink(conn=conn)
    sink.emit(_event("incident_created", "INC-2026-06-29-001",
                      tier="T2", host="WIN-WS-07", criticality="standard", technique="T1083"))
    assert len(conn.calls) == 1
    sql, params = conn.calls[0]
    assert "INSERT INTO argos_audit.audit_incidents" in sql
    assert "ON CONFLICT (incident_id) DO NOTHING" in sql
    assert params["tier"] == "T2"
    assert params["crit"] == "standard"
    assert params["tech"] == "T1083"


def test_decision_final_updates_outcome_and_state() -> None:
    conn = _FakeConn()
    PostgresSink(conn=conn).emit(
        _event("decision_final", "INC-2026-06-29-001",
               outcome="EXECUTE_ISOLATION", policy="conservative-wins", rationale="2A/1R")
    )
    sql, params = conn.calls[0]
    assert "UPDATE argos_audit.audit_incidents" in sql
    assert params["out"] == "EXECUTE_ISOLATION"
    assert params["pol"] == "conservative-wins"
    assert params["state"] == "executed"   # EXECUTE_ISOLATION -> executed


def test_approval_response_inserts_vote() -> None:
    conn = _FakeConn()
    PostgresSink(conn=conn).emit(
        _event("approval_response", "INC-2026-06-29-001", email="telegram:enzo", decision="reject")
    )
    sql, params = conn.calls[0]
    assert "INSERT INTO argos_audit.audit_responses" in sql
    assert params["email"] == "telegram:enzo"
    assert params["status"] == "rejected"   # reject -> rejected


def test_unmapped_kind_is_ignored() -> None:
    conn = _FakeConn()
    PostgresSink(conn=conn).emit(_event("alert_correlated", "INC-2026-06-29-001", alert_id="x"))
    assert conn.calls == []                 # sin handler -> no escribe


def test_failsoft_on_db_error() -> None:
    sink = PostgresSink(conn=_FakeConn(fail=True))
    # no debe lanzar aunque la DB falle
    sink.emit(_event("incident_created", "INC-2026-06-29-001",
                      tier="T0", host="h", criticality="standard", technique=None))


def test_no_connection_is_noop() -> None:
    sink = PostgresSink()  # sin dsn ni conn
    sink.emit(_event("incident_created", "INC-2026-06-29-001",
                     tier="T0", host="h", criticality="standard", technique=None))
