"""PostgresAuditReader: mapeo de filas de audit_events y degradación limpia."""

from __future__ import annotations

from datetime import UTC, datetime

from console.api.audit import PostgresAuditReader

_TS = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)


class _FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows


class _FakeConn:
    def __init__(self, rows: list[tuple], *, fail: bool = False) -> None:
        self._rows = rows
        self._fail = fail
        self.last_sql: str | None = None
        self.last_params: tuple | None = None

    def execute(self, sql: str, params: tuple | None = None) -> _FakeCursor:
        if self._fail:
            raise RuntimeError("db down")
        self.last_sql = sql
        self.last_params = params
        return _FakeCursor(self._rows)


def test_timeline_maps_rows() -> None:
    conn = _FakeConn([
        (_TS, "incident_created", {"tier": "T2"}),
        (_TS, "tier_escalated", {"to_tier": "T0"}),
    ])
    reader = PostgresAuditReader(conn=conn)
    events = reader.timeline("INC-2026-06-29-001")
    assert events is not None
    assert [e["kind"] for e in events] == ["incident_created", "tier_escalated"]
    assert events[0]["ts"] == _TS.isoformat()
    assert events[0]["payload"] == {"tier": "T2"}
    # consulta acotada al incidente pedido, ordenada
    assert "audit_events" in conn.last_sql
    assert "ORDER BY ts, id" in conn.last_sql
    assert conn.last_params == ("INC-2026-06-29-001",)


def test_timeline_none_without_connection() -> None:
    # sin dsn ni conn -> deshabilitado
    assert PostgresAuditReader().timeline("INC-2026-06-29-001") is None


def test_timeline_none_on_db_error() -> None:
    reader = PostgresAuditReader(conn=_FakeConn([], fail=True))
    assert reader.timeline("INC-2026-06-29-001") is None  # fail-soft, no lanza


def test_non_dict_payload_defaults_empty() -> None:
    reader = PostgresAuditReader(conn=_FakeConn([(_TS, "poison_discarded", None)]))
    events = reader.timeline("INC-2026-06-29-001")
    assert events == [{"ts": _TS.isoformat(), "kind": "poison_discarded", "payload": {}}]
