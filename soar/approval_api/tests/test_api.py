"""Tests de los endpoints FastAPI (ASGITransport + fakeredis, sin red ni Redis real)."""

from __future__ import annotations

import httpx
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport

from argos_contracts.enums import ApproverStatus
from argos_contracts.incident import Incident
from soar.approval_api.handlers import save_incident
from soar.approval_api.main import app, get_redis


@pytest_asyncio.fixture
async def api():
    fake = FakeAsyncRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake
    app.dependency_overrides.clear()


async def test_healthz_ok(api):
    client, _ = api
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "redis": True}


async def test_telegram_callback_records_vote(api, make_incident):
    client, fake = api
    inc = make_incident()
    await save_incident(fake, inc)
    update = {"callback_query": {"data": f"approve:{inc.incident_id}", "from": {"id": 42}}}
    r = await client.post("/telegram/callback", json=update)
    assert r.json() == {"ok": True}
    stored = Incident.model_validate_json(await fake.get(f"incident:{inc.incident_id}"))
    assert len(stored.approvers) == 1
    assert stored.approvers[0].email == "telegram:42"
    assert stored.approvers[0].status == ApproverStatus.APPROVED


async def test_telegram_callback_bad_data(api):
    client, _ = api
    r = await client.post("/telegram/callback", json={"callback_query": {"data": "nope"}})
    assert r.json()["ok"] is False


async def test_telegram_callback_unknown_incident(api):
    client, _ = api
    update = {"callback_query": {"data": "approve:INC-2026-05-30-777", "from": {"id": 1}}}
    r = await client.post("/telegram/callback", json=update)
    assert r.json() == {"ok": False, "error": "unknown incident"}


async def test_voice_twiml_returns_xml(api):
    client, _ = api
    r = await client.post("/voice/twiml?incident=INC-2026-05-30-001")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    assert "INC-2026-05-30-001" in r.text and "<Gather" in r.text


async def test_voice_dtmf_records_vote(api, make_incident):
    client, fake = api
    inc = make_incident()
    await save_incident(fake, inc)
    r = await client.post(f"/voice/dtmf?incident={inc.incident_id}", data={"Digits": "1"})
    assert "approve recorded" in r.text
    stored = Incident.model_validate_json(await fake.get(f"incident:{inc.incident_id}"))
    assert stored.approvers[0].status == ApproverStatus.APPROVED


async def test_voice_dtmf_invalid_digit(api):
    client, _ = api
    r = await client.post("/voice/dtmf?incident=INC-2026-05-30-001", data={"Digits": "9"})
    assert "Invalid input" in r.text


async def test_telegram_callback_missing_callback_query(api):
    client, _ = api
    r = await client.post("/telegram/callback", json={})
    assert r.json() == {"ok": False, "error": "missing callback_query"}


async def test_voice_dtmf_unknown_incident_is_graceful(api):
    client, _ = api
    r = await client.post("/voice/dtmf?incident=INC-2026-05-30-777", data={"Digits": "1"})
    assert "approve recorded" in r.text  # KeyError contenido, la llamada cierra ok
