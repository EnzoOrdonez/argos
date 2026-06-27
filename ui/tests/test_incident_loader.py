"""Tests del loader de Redis (fakeredis sync). Foco: la trampa del counter key."""

from __future__ import annotations

import fakeredis
import pytest
from streamlit_app.lib import incident_loader

from argos_contracts.incident import FinalDecision


@pytest.fixture
def client() -> fakeredis.FakeStrictRedis:
    return fakeredis.FakeStrictRedis(decode_responses=True)


def test_incident_id_from_key() -> None:
    assert (
        incident_loader.incident_id_from_key("incident:INC-2026-06-24-001")
        == "INC-2026-06-24-001"
    )
    # incident:counter:{fecha} también matchea SCAN incident:* pero NO es incidente.
    assert incident_loader.incident_id_from_key("incident:counter:2026-06-24") is None
    assert incident_loader.incident_id_from_key("corr:open:LIN-DB-01") is None


def test_enumerate_filters_counter_key(client, make_incident) -> None:
    incident = make_incident()
    client.set(f"incident:{incident.incident_id}", incident.model_dump_json())
    client.set("incident:counter:2026-06-24", "5")  # la trampa

    result = incident_loader.enumerate_incidents(client)

    assert [i.incident_id for i in result] == [incident.incident_id]


def test_enumerate_skips_unparseable(client, make_incident) -> None:
    incident = make_incident()
    client.set(f"incident:{incident.incident_id}", incident.model_dump_json())
    client.set("incident:INC-2026-06-24-999", "{ not valid json")  # snapshot corrupto

    result = incident_loader.enumerate_incidents(client)

    assert [i.incident_id for i in result] == [incident.incident_id]


def test_enumerate_orders_open_before_settled(client, make_incident) -> None:
    open_inc = make_incident(incident_id="INC-2026-06-24-002")
    settled = make_incident(
        incident_id="INC-2026-06-24-001",
        final_decision=FinalDecision(
            outcome="NO_ACTION", policy_applied="two-person-rule", rationale="x"
        ),
    )
    client.set(f"incident:{open_inc.incident_id}", open_inc.model_dump_json())
    client.set(f"incident:{settled.incident_id}", settled.model_dump_json())

    result = incident_loader.enumerate_incidents(client)

    assert [i.incident_id for i in result] == [
        open_inc.incident_id,
        settled.incident_id,
    ]


def test_load_one_roundtrip(client, make_incident) -> None:
    incident = make_incident()
    client.set(f"incident:{incident.incident_id}", incident.model_dump_json())

    loaded = incident_loader.load_one(client, incident.incident_id)

    assert loaded is not None
    assert loaded.incident_id == incident.incident_id
    assert loaded.tier == incident.tier


def test_load_one_missing(client) -> None:
    assert incident_loader.load_one(client, "INC-2026-06-24-404") is None
