"""PostgresSink: mapea AuditEvent -> audit_incidents/audit_responses y es fail-soft
(nunca lanza desde emit, ni con la DB caída ni sin conexión)."""

from __future__ import annotations

import socket
import threading
import time
from datetime import UTC, datetime

import pytest

from soar.audit.base import AuditEvent
from soar.audit.logger import AuditLogger
from soar.audit.postgres import PostgresSink

_TS = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)


class _FakeCursor:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeConn:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.cursors: list[_FakeCursor] = []
        self.close_calls = 0
        self._fail = fail

    def execute(self, sql: str, params: dict | None = None):
        if self._fail:
            raise RuntimeError("db down")
        self.calls.append((sql, params or {}))
        cursor = _FakeCursor()
        self.cursors.append(cursor)
        return cursor

    def close(self) -> None:
        self.close_calls += 1


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


def test_constructor_defers_connection() -> None:
    calls: list[tuple[str, dict]] = []

    def connect(dsn: str, **kwargs):
        calls.append((dsn, kwargs))
        return _FakeConn()

    PostgresSink(
        "postgresql://audit.invalid/argos",
        connection_factory=connect,
    )

    assert calls == []


def test_first_emit_connects_with_bounded_timeout() -> None:
    conn = _FakeConn()
    calls: list[tuple[str, dict]] = []

    def connect(dsn: str, **kwargs):
        calls.append((dsn, kwargs))
        return conn

    sink = PostgresSink(
        "postgresql://audit.invalid/argos",
        connection_factory=connect,
    )

    sink.emit(_event("alert_correlated", "INC-2026-06-29-001", alert_id="x"))

    assert calls == [
        (
            "postgresql://audit.invalid/argos",
            {"autocommit": True, "connect_timeout": 5},
        )
    ]
    assert len(conn.calls) == 1


def test_emit_closes_cursor_and_close_is_idempotent() -> None:
    conn = _FakeConn()
    sink = PostgresSink(conn=conn)

    sink.emit(_event("alert_correlated", "INC-2026-06-29-001", alert_id="x"))
    sink.close()
    sink.close()

    assert len(conn.cursors) == 1
    assert conn.cursors[0].closed is True
    assert conn.close_calls == 1


def test_database_error_is_sanitized_but_event_loss_is_visible(caplog: pytest.LogCaptureFixture) -> None:
    sensitive_detail = "sensitive-driver-detail-do-not-log"
    conn = _FakeConn(fail=True)
    conn.execute = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError(sensitive_detail)
    )
    sink = PostgresSink(conn=conn)

    sink.emit(_event("incident_created", "INC-2026-06-29-001"))

    assert sensitive_detail not in caplog.text
    assert "INC-2026-06-29-001/incident_created" in caplog.text


def test_connection_timeout_is_configurable_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("ARGOS_AUDIT_SQL_CONNECT_TIMEOUT_SECONDS", "2")
    calls: list[dict] = []

    def connect(_dsn: str, **kwargs):
        calls.append(kwargs)
        return _FakeConn()

    sink = PostgresSink("postgresql://audit.invalid/argos", connection_factory=connect)
    sink.emit(_event("alert_correlated", "INC-2026-06-29-001"))

    assert calls == [{"autocommit": True, "connect_timeout": 2}]


def test_audit_logger_closes_owned_postgres_sink() -> None:
    conn = _FakeConn()
    audit = AuditLogger([PostgresSink(conn=conn)])

    audit.close()

    assert conn.close_calls == 1


def test_write_failure_reconnects_on_next_event_without_replaying_failed_event() -> None:
    broken = _FakeConn(fail=True)
    recovered = _FakeConn()
    connections = iter([broken, recovered])

    def connect(_dsn: str, **_kwargs):
        return next(connections)

    sink = PostgresSink("postgresql://audit.invalid/argos", connection_factory=connect)

    sink.emit(_event("alert_correlated", "INC-FAILED", alert_id="lost"))
    sink.emit(_event("alert_correlated", "INC-RECOVERED", alert_id="stored"))

    assert broken.close_calls == 1
    assert len(recovered.calls) == 1
    assert recovered.calls[0][1]["id"] == "INC-RECOVERED"


def test_explicit_timeout_outside_safe_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="between 1 and 60"):
        PostgresSink(
            "postgresql://audit.invalid/argos",
            connection_factory=lambda *_args, **_kwargs: _FakeConn(),
            connect_timeout_seconds=61,
        )


@pytest.mark.parametrize("raw", ["", "slow", "0", "61"])
def test_invalid_timeout_environment_is_rejected(monkeypatch, raw: str) -> None:
    monkeypatch.setenv("ARGOS_AUDIT_SQL_CONNECT_TIMEOUT_SECONDS", raw)

    with pytest.raises(ValueError, match="ARGOS_AUDIT_SQL_CONNECT_TIMEOUT_SECONDS"):
        PostgresSink("postgresql://audit.invalid/argos")


def test_transient_connection_failure_retries_on_next_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    recovered = _FakeConn()
    attempts = 0

    def connect(_dsn: str, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("sensitive-driver-detail-do-not-log")
        return recovered

    sink = PostgresSink("postgresql://audit.invalid/argos", connection_factory=connect)

    sink.emit(_event("alert_correlated", "INC-FAILED"))
    sink.emit(_event("alert_correlated", "INC-RECOVERED"))

    assert attempts == 2
    assert len(recovered.calls) == 1
    assert "INC-FAILED/alert_correlated" in caplog.text
    assert "sensitive-driver-detail-do-not-log" not in caplog.text


def test_slow_server_connection_is_bounded_by_timeout() -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    accepted = threading.Event()

    def hold_connection() -> None:
        conn, _address = server.accept()
        accepted.set()
        time.sleep(4)
        conn.close()
        server.close()

    threading.Thread(target=hold_connection, daemon=True).start()
    sink = PostgresSink(
        f"postgresql://argos@127.0.0.1:{port}/argos",
        connect_timeout_seconds=1,
    )

    started = time.monotonic()
    connected = sink.connect()
    elapsed = time.monotonic() - started

    assert accepted.wait(1)
    assert connected is False
    assert elapsed < 4
