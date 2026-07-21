"""Twilio webhook authenticity, CallSid binding, and replay tests."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport
from twilio.request_validator import RequestValidator

from argos_contracts.incident import Incident
from soar.approval_api.callback_state import TWILIO_CALL_KEY, TWILIO_REQUEST_KEY
from soar.approval_api.handlers import save_incident
from soar.approval_api.main import app, get_redis
from soar.approval_api.webhook_auth import TwilioWebhookAuth

AUTH_TOKEN = "twilio-test-auth-token"
BASE_URL = "http://test"
CALL_SID = "CA" + "a" * 32


class FailOnceTransactionRedis(FakeAsyncRedis):
    fail_next_transaction = False
    fail_after_commit = False

    def pipeline(self, *args, **kwargs):
        pipeline = super().pipeline(*args, **kwargs)
        execute = pipeline.execute

        async def execute_with_failure(*execute_args, **execute_kwargs):
            if not self.fail_next_transaction:
                return await execute(*execute_args, **execute_kwargs)
            self.fail_next_transaction = False
            if self.fail_after_commit:
                await execute(*execute_args, **execute_kwargs)
            raise ConnectionError("injected Redis transaction failure")

        pipeline.execute = execute_with_failure
        return pipeline


class FailOnceScheduler:
    calls = 0

    async def ensure_consolidation_started(self, incident_id: str) -> None:
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("injected scheduler failure")


@pytest_asyncio.fixture
async def twilio_api():
    fake = FakeAsyncRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake
    app.state.twilio_auth = TwilioWebhookAuth(
        auth_token=AUTH_TOKEN, public_base_url=BASE_URL
    )
    app.state.callback_ttl_seconds = 300
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        yield client, fake
    app.dependency_overrides.clear()
    del app.state.twilio_auth


def _signature(path: str, form: dict[str, str]) -> str:
    return RequestValidator(AUTH_TOKEN).compute_signature(f"{BASE_URL}{path}", form)


async def _bind(fake: FakeAsyncRedis, incident_id: str) -> None:
    await fake.set(
        TWILIO_CALL_KEY.format(call_sid=CALL_SID), incident_id, ex=300
    )


async def test_twiml_requires_valid_signature_and_call_binding(twilio_api):
    client, fake = twilio_api
    incident_id = "INC-2026-05-30-001"
    path = f"/voice/twiml?incident={incident_id}"
    form = {"CallSid": CALL_SID}
    await _bind(fake, incident_id)

    rejected = await client.post(path, data=form)
    accepted = await client.post(
        path, data=form, headers={"X-Twilio-Signature": _signature(path, form)}
    )

    assert rejected.status_code == 403
    assert accepted.status_code == 200
    assert "<Gather" in accepted.text


async def test_twiml_binding_failure_preserves_request_for_valid_retry():
    fake = FailOnceTransactionRedis(decode_responses=True)
    request_id = "r" * 32
    incident_id = "INC-2026-05-30-001"
    await fake.set(
        TWILIO_REQUEST_KEY.format(request_id=request_id),
        incident_id,
        ex=300,
    )
    app.dependency_overrides[get_redis] = lambda: fake
    app.state.twilio_auth = TwilioWebhookAuth(
        auth_token=AUTH_TOKEN, public_base_url=BASE_URL
    )
    app.state.callback_ttl_seconds = 300
    path = f"/voice/twiml?incident={incident_id}&request_id={request_id}"
    form = {"CallSid": CALL_SID}
    headers = {"X-Twilio-Signature": _signature(path, form)}
    transport = ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url=BASE_URL
        ) as client:
            fake.fail_next_transaction = True
            with pytest.raises(ConnectionError):
                await client.post(path, data=form, headers=headers)

            assert await fake.get(
                TWILIO_REQUEST_KEY.format(request_id=request_id)
            ) == incident_id
            assert await fake.get(
                TWILIO_CALL_KEY.format(call_sid=CALL_SID)
            ) is None
            retry = await client.post(path, data=form, headers=headers)
    finally:
        app.dependency_overrides.clear()
        del app.state.twilio_auth

    assert retry.status_code == 200
    assert "<Gather" in retry.text
    assert await fake.get(
        TWILIO_CALL_KEY.format(call_sid=CALL_SID)
    ) == incident_id
    assert await fake.get(
        TWILIO_REQUEST_KEY.format(request_id=request_id)
    ) is None


async def test_dtmf_records_once_for_bound_call(twilio_api, make_incident):
    client, fake = twilio_api
    incident = make_incident()
    await save_incident(fake, incident)
    await _bind(fake, incident.incident_id)
    path = f"/voice/dtmf?incident={incident.incident_id}"
    form = {"CallSid": CALL_SID, "Digits": "1"}
    headers = {"X-Twilio-Signature": _signature(path, form)}

    first = await client.post(path, data=form, headers=headers)
    second = await client.post(path, data=form, headers=headers)

    assert "approve recorded" in first.text
    assert "already recorded" in second.text
    stored = Incident.model_validate_json(
        await fake.get(f"incident:{incident.incident_id}")
    )
    assert [approver.email for approver in stored.approvers] == [
        f"twilio:{CALL_SID}"
    ]


async def test_two_concurrent_callbacks_mutate_incident_once(twilio_api, make_incident):
    client, fake = twilio_api
    incident = make_incident()
    await save_incident(fake, incident)
    await _bind(fake, incident.incident_id)
    path = f"/voice/dtmf?incident={incident.incident_id}"
    form = {"CallSid": CALL_SID, "Digits": "1"}
    headers = {"X-Twilio-Signature": _signature(path, form)}

    first, second = await asyncio.gather(
        client.post(path, data=form, headers=headers),
        client.post(path, data=form, headers=headers),
    )

    responses = [first.text, second.text]
    assert sum("approve recorded" in text for text in responses) == 1
    assert sum("already recorded" in text for text in responses) == 1
    stored = Incident.model_validate_json(
        await fake.get(f"incident:{incident.incident_id}")
    )
    assert [approver.email for approver in stored.approvers] == [
        f"twilio:{CALL_SID}"
    ]


async def test_dtmf_rejects_tampered_incident(twilio_api, make_incident):
    client, fake = twilio_api
    incident = make_incident()
    await save_incident(fake, incident)
    await _bind(fake, incident.incident_id)
    path = "/voice/dtmf?incident=INC-2026-05-30-999"
    form = {"CallSid": CALL_SID, "Digits": "1"}

    response = await client.post(
        path, data=form, headers={"X-Twilio-Signature": _signature(path, form)}
    )

    assert response.status_code == 403
    stored = Incident.model_validate_json(
        await fake.get(f"incident:{incident.incident_id}")
    )
    assert stored.approvers == []


async def test_canonical_url_does_not_trust_host_header(twilio_api):
    client, fake = twilio_api
    incident_id = "INC-2026-05-30-001"
    path = f"/voice/twiml?incident={incident_id}"
    form = {"CallSid": CALL_SID}
    await _bind(fake, incident_id)

    response = await client.post(
        path,
        data=form,
        headers={
            "Host": "attacker.invalid",
            "X-Twilio-Signature": _signature(path, form),
        },
    )

    assert response.status_code == 200


async def test_retry_records_vote_after_failure_following_claim(make_incident):
    fake = FailOnceTransactionRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake
    app.state.twilio_auth = TwilioWebhookAuth(
        auth_token=AUTH_TOKEN, public_base_url=BASE_URL
    )
    app.state.callback_ttl_seconds = 300
    incident = make_incident()
    await save_incident(fake, incident)
    await _bind(fake, incident.incident_id)
    path = f"/voice/dtmf?incident={incident.incident_id}"
    form = {"CallSid": CALL_SID, "Digits": "1"}
    headers = {"X-Twilio-Signature": _signature(path, form)}
    transport = ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url=BASE_URL
        ) as client:
            fake.fail_next_transaction = True
            with pytest.raises(ConnectionError):
                await client.post(path, data=form, headers=headers)

            failed_state = Incident.model_validate_json(
                await fake.get(f"incident:{incident.incident_id}")
            )
            assert failed_state.approvers == []
            assert await fake.get(
                f"approval:twilio:vote:{CALL_SID}"
            ) is None
            retry = await client.post(path, data=form, headers=headers)
    finally:
        app.dependency_overrides.clear()
        del app.state.twilio_auth

    assert "approve recorded" in retry.text
    stored = Incident.model_validate_json(
        await fake.get(f"incident:{incident.incident_id}")
    )
    assert [approver.email for approver in stored.approvers] == [
        f"twilio:{CALL_SID}"
    ]


async def test_retry_after_ambiguous_commit_does_not_mutate_twice(make_incident):
    fake = FailOnceTransactionRedis(decode_responses=True)
    fake.fail_after_commit = True
    app.dependency_overrides[get_redis] = lambda: fake
    app.state.twilio_auth = TwilioWebhookAuth(
        auth_token=AUTH_TOKEN, public_base_url=BASE_URL
    )
    app.state.callback_ttl_seconds = 300
    incident = make_incident()
    await save_incident(fake, incident)
    await _bind(fake, incident.incident_id)
    path = f"/voice/dtmf?incident={incident.incident_id}"
    form = {"CallSid": CALL_SID, "Digits": "1"}
    headers = {"X-Twilio-Signature": _signature(path, form)}
    transport = ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url=BASE_URL
        ) as client:
            fake.fail_next_transaction = True
            with pytest.raises(ConnectionError):
                await client.post(path, data=form, headers=headers)

            retry = await client.post(path, data=form, headers=headers)
    finally:
        app.dependency_overrides.clear()
        del app.state.twilio_auth

    assert "approve recorded" in retry.text
    stored = Incident.model_validate_json(
        await fake.get(f"incident:{incident.incident_id}")
    )
    assert [approver.email for approver in stored.approvers] == [
        f"twilio:{CALL_SID}"
    ]


async def test_effect_failure_is_retryable_without_second_mutation(make_incident):
    fake = FakeAsyncRedis(decode_responses=True)
    scheduler = FailOnceScheduler()
    app.dependency_overrides[get_redis] = lambda: fake
    app.state.twilio_auth = TwilioWebhookAuth(
        auth_token=AUTH_TOKEN, public_base_url=BASE_URL
    )
    app.state.callback_ttl_seconds = 300
    app.state.scheduler = scheduler
    incident = make_incident()
    await save_incident(fake, incident)
    await _bind(fake, incident.incident_id)
    path = f"/voice/dtmf?incident={incident.incident_id}"
    form = {"CallSid": CALL_SID, "Digits": "1"}
    headers = {"X-Twilio-Signature": _signature(path, form)}
    transport = ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url=BASE_URL
        ) as client:
            with pytest.raises(ConnectionError):
                await client.post(path, data=form, headers=headers)

            retry = await client.post(path, data=form, headers=headers)
            replay = await client.post(path, data=form, headers=headers)
    finally:
        app.dependency_overrides.clear()
        del app.state.twilio_auth
        del app.state.scheduler

    assert "approve recorded" in retry.text
    assert "already recorded" in replay.text
    assert scheduler.calls == 2
    stored = Incident.model_validate_json(
        await fake.get(f"incident:{incident.incident_id}")
    )
    assert [approver.email for approver in stored.approvers] == [
        f"twilio:{CALL_SID}"
    ]
