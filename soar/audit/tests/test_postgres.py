"""PostgresSink: mapea AuditEvent -> audit_incidents/audit_responses y es fail-soft
(nunca lanza desde emit, ni con la DB caída ni sin conexión)."""

from __future__ import annotations

from datetime import UTC, datetime

from soar.audit.base import AuditEvent
from soar.audit.postgres import PostgresSink

_TS = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)


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


def _find(conn: _FakeConn, needle: str) -> tuple[str, dict]:
    """Primer call cuyo SQL contiene `needle` (cada emit escribe audit_events + su agregado)."""
    for sql, params in conn.calls:
        if needle in sql:
            return sql, params
    raise AssertionError(f"ningún SQL contiene {needle!r}; calls={[c[0] for c in conn.calls]}")


def test_incident_created_inserts_with_contract_values() -> None:
    conn = _FakeConn()
    sink = PostgresSink(conn=conn)
    sink.emit(_event("incident_created", "INC-2026-06-29-001",
                      tier="T2", host="WIN-WS-07", criticality="standard", technique="T1083"))
    # audit_events (genérico) + audit_incidents (agregado)
    assert len(conn.calls) == 2
    sql, params = _find(conn, "INSERT INTO argos_audit.audit_incidents")
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
    _sql, params = _find(conn, "UPDATE argos_audit.audit_incidents")
    assert params["out"] == "EXECUTE_ISOLATION"
    assert params["pol"] == "conservative-wins"
    assert params["state"] == "executed"   # EXECUTE_ISOLATION -> executed


def test_approval_response_inserts_vote() -> None:
    conn = _FakeConn()
    PostgresSink(conn=conn).emit(
        _event("approval_response", "INC-2026-06-29-001", email="telegram:enzo", decision="reject")
    )
    _sql, params = _find(conn, "INSERT INTO argos_audit.audit_responses")
    assert params["email"] == "telegram:enzo"
    assert params["status"] == "rejected"   # reject -> rejected


def test_every_kind_persisted_to_audit_events() -> None:
    """Todo evento va a audit_events (fuente del timeline), tenga o no agregado."""
    conn = _FakeConn()
    PostgresSink(conn=conn).emit(
        _event("incident_created", "INC-2026-06-29-001",
               tier="T2", host="h", criticality="standard", technique="T1083")
    )
    _sql, params = _find(conn, "INSERT INTO argos_audit.audit_events")
    assert params["kind"] == "incident_created"
    assert params["id"] == "INC-2026-06-29-001"
    assert '"tier": "T2"' in params["payload"]  # payload serializado a json


def test_kind_sin_agregado_igual_va_a_audit_events() -> None:
    """Un kind sin handler _on_* (antes se descartaba) ahora sí queda en audit_events."""
    conn = _FakeConn()
    PostgresSink(conn=conn).emit(_event("alert_correlated", "INC-2026-06-29-001", alert_id="x"))
    assert len(conn.calls) == 1  # solo audit_events (no hay agregado para alert_correlated)
    sql, params = conn.calls[0]
    assert "INSERT INTO argos_audit.audit_events" in sql
    assert params["kind"] == "alert_correlated"


def test_failsoft_on_db_error() -> None:
    sink = PostgresSink(conn=_FakeConn(fail=True))
    # no debe lanzar aunque la DB falle
    sink.emit(_event("incident_created", "INC-2026-06-29-001",
                      tier="T0", host="h", criticality="standard", technique=None))


def test_no_connection_is_noop() -> None:
    sink = PostgresSink()  # sin dsn ni conn
    sink.emit(_event("incident_created", "INC-2026-06-29-001",
                     tier="T0", host="h", criticality="standard", technique=None))
