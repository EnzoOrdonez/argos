"""Tests de la API read-only de la consola (fakeredis + ASGITransport)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakeredis import FakeStrictRedis
from httpx import ASGITransport, AsyncClient

from argos_contracts.alert import NormalizedAlert
from argos_contracts.enums import (
    ActionType,
    Criticality,
    IncidentState,
    Layer,
    Severity,
    Tier,
)
from argos_contracts.incident import FinalDecision, Incident, ProposedAction
from argos_contracts.triage import HostInfo
from console.api import audit, main, store


def _incident(
    incident_id: str = "INC-2026-06-27-001",
    final: FinalDecision | None = None,
    updated: datetime | None = None,
) -> Incident:
    now = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
    return Incident(
        incident_id=incident_id,
        created_at=now,
        updated_at=updated or now,
        tier=Tier.T2,
        state=IncidentState.AWAITING_APPROVAL,
        host=HostInfo(
            id="LIN-VICTIM-01",
            criticality=Criticality.PRODUCTION_CRITICAL,
            ip="10.0.0.22",
            os="Debian",
        ),
        alert=NormalizedAlert(
            alert_id="a", source_layer=Layer.LAYER_1, timestamp=now, host_id="LIN-VICTIM-01",
            severity_score=0.9, severity_label=Severity.HIGH, technique_mitre="T1190",
        ),
        proposed_actions=[
            ProposedAction(
                id="act-1", type=ActionType.HOST_ISOLATION, target="LIN-VICTIM-01", reversible=True
            )
        ],
        final_decision=final,
    )


def _burst_alert(alert_id: str, technique: str = "T1486") -> NormalizedAlert:
    now = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
    return NormalizedAlert(
        alert_id=alert_id, source_layer=Layer.LAYER_2, timestamp=now, host_id="LIN-VICTIM-01",
        severity_score=0.8, severity_label=Severity.HIGH, technique_mitre=technique,
    )


@pytest.fixture
def fake(monkeypatch) -> FakeStrictRedis:
    redis = FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(store, "get_client", lambda url: redis)
    return redis


async def _get(path: str):
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_list_incidents_filters_counter(fake) -> None:
    inc = _incident()
    fake.set(f"incident:{inc.incident_id}", inc.model_dump_json())
    fake.set("incident:counter:2026-06-27", "5")  # la trampa: no es un incidente
    resp = await _get("/api/incidents")
    assert resp.status_code == 200
    assert [i["incident_id"] for i in resp.json()] == [inc.incident_id]


async def test_get_incident_ok_and_404(fake) -> None:
    inc = _incident()
    fake.set(f"incident:{inc.incident_id}", inc.model_dump_json())
    ok = await _get(f"/api/incidents/{inc.incident_id}")
    assert ok.status_code == 200
    assert ok.json()["host"]["id"] == "LIN-VICTIM-01"
    missing = await _get("/api/incidents/INC-2026-06-27-404")
    assert missing.status_code == 404


async def test_health(fake) -> None:
    resp = await _get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


async def test_index_served(fake) -> None:
    resp = await _get("/")
    assert resp.status_code == 200
    assert "ARGOS" in resp.text


async def test_list_503_when_redis_down(monkeypatch) -> None:
    def _boom(url):
        raise ConnectionError("redis caído")

    monkeypatch.setattr(store, "get_client", _boom)
    resp = await _get("/api/incidents")
    assert resp.status_code == 503


async def test_list_skips_invalid_snapshot(fake) -> None:
    inc = _incident()
    fake.set(f"incident:{inc.incident_id}", inc.model_dump_json())
    fake.set("incident:INC-2026-06-27-002", "{no soy un incidente valido")  # ValidationError
    resp = await _get("/api/incidents")
    assert resp.status_code == 200
    assert [i["incident_id"] for i in resp.json()] == [inc.incident_id]  # el inválido se salta


async def test_list_sort_open_first_then_updated_desc(fake) -> None:
    t = lambda h: datetime(2026, 6, 27, h, 0, 0, tzinfo=UTC)  # noqa: E731
    final = FinalDecision(
        outcome="EXECUTE_ISOLATION", policy_applied="auto-execute",
        rationale="x", executed_at=t(9), execution_status="success",
    )
    open_new = _incident("INC-2026-06-27-001", updated=t(10))
    open_old = _incident("INC-2026-06-27-002", updated=t(8))
    closed = _incident("INC-2026-06-27-003", final=final, updated=t(11))
    for inc in (open_old, closed, open_new):
        fake.set(f"incident:{inc.incident_id}", inc.model_dump_json())
    resp = await _get("/api/incidents")
    ids = [i["incident_id"] for i in resp.json()]
    # abiertos primero (más nuevo antes), luego los cerrados
    assert ids == ["INC-2026-06-27-001", "INC-2026-06-27-002", "INC-2026-06-27-003"]


async def test_burst_alerts_parses_and_skips_invalid(fake) -> None:
    fake.rpush("corr:alerts:INC-2026-06-27-001", _burst_alert("al-1").model_dump_json())
    fake.rpush("corr:alerts:INC-2026-06-27-001", "{basura")  # inválido -> se salta
    fake.rpush("corr:alerts:INC-2026-06-27-001", _burst_alert("al-2").model_dump_json())
    resp = await _get("/api/incidents/INC-2026-06-27-001/alerts")
    assert resp.status_code == 200
    assert [a["alert_id"] for a in resp.json()] == ["al-1", "al-2"]


async def test_burst_empty_when_no_key(fake) -> None:
    resp = await _get("/api/incidents/INC-2026-06-27-999/alerts")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_audit_available_true(monkeypatch, fake) -> None:
    class _FakeReader:
        def timeline(self, incident_id):
            return [{"ts": "2026-06-27T12:00:00+00:00", "kind": "incident_created", "payload": {}}]

    monkeypatch.setattr(audit, "get_reader", lambda: _FakeReader())
    resp = await _get("/api/incidents/INC-2026-06-27-001/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["events"][0]["kind"] == "incident_created"


async def test_audit_available_false_when_reader_disabled(monkeypatch, fake) -> None:
    class _DisabledReader:
        def timeline(self, incident_id):
            return None

    monkeypatch.setattr(audit, "get_reader", lambda: _DisabledReader())
    resp = await _get("/api/incidents/INC-2026-06-27-001/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["events"] == []


# -- Autenticación HTTP Basic (RF-7/HU-6) -------------------------------------


async def _get_auth(path: str, *, auth=None):
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, auth=auth)


async def test_api_requires_basic_auth_when_configured(fake, monkeypatch) -> None:
    monkeypatch.setenv("CONSOLE_BASIC_USER", "admin")
    monkeypatch.setenv("CONSOLE_BASIC_PASS", "s3cr3t")
    # sin credenciales → 401 con reto Basic
    unauth = await _get_auth("/api/incidents")
    assert unauth.status_code == 401
    assert unauth.headers["www-authenticate"].lower().startswith("basic")
    # credenciales incorrectas → 401
    bad = await _get_auth("/api/incidents", auth=("admin", "wrong"))
    assert bad.status_code == 401
    # credenciales correctas → 200
    inc = _incident()
    fake.set(f"incident:{inc.incident_id}", inc.model_dump_json())
    ok = await _get_auth("/api/incidents", auth=("admin", "s3cr3t"))
    assert ok.status_code == 200


async def test_index_gated_but_health_open_when_auth_configured(fake, monkeypatch) -> None:
    monkeypatch.setenv("CONSOLE_BASIC_USER", "admin")
    monkeypatch.setenv("CONSOLE_BASIC_PASS", "s3cr3t")
    assert (await _get_auth("/")).status_code == 401  # / gateado → diálogo Basic
    assert (await _get_auth("/health")).status_code == 200  # liveness siempre abierto


async def test_api_open_when_auth_not_configured(fake, monkeypatch) -> None:
    monkeypatch.delenv("CONSOLE_BASIC_USER", raising=False)
    monkeypatch.delenv("CONSOLE_BASIC_PASS", raising=False)
    inc = _incident()
    fake.set(f"incident:{inc.incident_id}", inc.model_dump_json())
    # sin credencial configurada: auth deshabilitada (dev localhost) → 200
    assert (await _get_auth("/api/incidents")).status_code == 200
