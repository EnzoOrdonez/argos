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
from console.api import main, store


def _incident(
    incident_id: str = "INC-2026-06-27-001", final: FinalDecision | None = None
) -> Incident:
    now = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
    return Incident(
        incident_id=incident_id,
        created_at=now,
        updated_at=now,
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
