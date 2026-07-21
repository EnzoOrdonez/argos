from __future__ import annotations

import asyncio
import os
import secrets

import pytest
import redis.asyncio as redis_async

from soar.approval_api.callback_state import (
    TELEGRAM_TOKEN_KEY,
    TELEGRAM_VOTE_KEY,
    TWILIO_CALL_KEY,
    TWILIO_REQUEST_KEY,
    TWILIO_VOTE_KEY,
    RedisCallbackStateSink,
    bind_twilio_call_from_request,
    load_twilio_call,
)
from soar.approval_api.handlers import (
    acquire_twilio_effects,
    complete_twilio_effects,
    record_telegram_approval_atomically,
    record_twilio_approval_atomically,
    save_incident,
)
from soar.approval_api.jwt_signer import ApprovalSigner


@pytest.mark.skipif(
    not os.environ.get("ARGOS_TEST_REDIS_URL"),
    reason="set ARGOS_TEST_REDIS_URL to an isolated disposable Redis",
)
async def test_real_redis_callback_state_is_atomic_and_ttl_bound(
    make_incident,
) -> None:
    redis_url = os.environ["ARGOS_TEST_REDIS_URL"]
    suffix = secrets.token_hex(16)
    call_sid = f"CA{suffix}"
    call_key = TWILIO_CALL_KEY.format(call_sid=call_sid)
    vote_key = TWILIO_VOTE_KEY.format(call_sid=call_sid)
    incident = make_incident()
    incident_key = f"incident:{incident.incident_id}"
    client = redis_async.Redis.from_url(redis_url, decode_responses=True)
    sink = RedisCallbackStateSink(redis_url)

    try:
        await save_incident(client, incident)
        signer = ApprovalSigner(
            "redis-integration-secret-0123456789abcdef"  # pragma: allowlist secret
        )
        token, jti = signer.sign_approval(
            incident.incident_id, "telegram-chat:999", "approve"
        )
        token_key = TELEGRAM_TOKEN_KEY.format(jti=jti)
        telegram_vote_key = TELEGRAM_VOTE_KEY.format(jti=jti)
        sink.store_telegram_token(jti, token, 30)
        telegram_votes = await asyncio.gather(
            record_telegram_approval_atomically(
                client,
                signer=signer,
                jti=jti,
                incident_id=incident.incident_id,
                decision="approve",
                subject="telegram-chat:999",
                email="telegram:42",
                ttl_seconds=30,
            ),
            record_telegram_approval_atomically(
                client,
                signer=signer,
                jti=jti,
                incident_id=incident.incident_id,
                decision="approve",
                subject="telegram-chat:999",
                email="telegram:42",
                ttl_seconds=30,
            ),
        )
        assert sorted(recorded for _, recorded in telegram_votes) == [False, True]
        assert await client.get(token_key) is None
        assert await client.get(telegram_vote_key) is not None

        request_id = sink.store_twilio_request(incident.incident_id, 30)
        request_key = TWILIO_REQUEST_KEY.format(request_id=request_id)
        await bind_twilio_call_from_request(
            client,
            request_id=request_id,
            call_sid=call_sid,
            incident_id=incident.incident_id,
            ttl_seconds=30,
        )
        assert await load_twilio_call(client, call_sid) == incident.incident_id
        assert await client.get(request_key) is None

        votes = await asyncio.gather(
            record_twilio_approval_atomically(
                client,
                call_sid=call_sid,
                incident_id=incident.incident_id,
                decision="approve",
                ttl_seconds=30,
            ),
            record_twilio_approval_atomically(
                client,
                call_sid=call_sid,
                incident_id=incident.incident_id,
                decision="approve",
                ttl_seconds=30,
            ),
        )
        assert sorted(recorded for _, recorded in votes) == [False, True]
        stored = votes[0][0].model_validate_json(await client.get(incident_key))
        assert {approver.email for approver in stored.approvers} == {
            "telegram:42",
            f"twilio:{call_sid}",
        }
        owners = await asyncio.gather(
            acquire_twilio_effects(
                client,
                call_sid=call_sid,
                incident_id=incident.incident_id,
                ttl_seconds=30,
            ),
            acquire_twilio_effects(
                client,
                call_sid=call_sid,
                incident_id=incident.incident_id,
                ttl_seconds=30,
            ),
        )
        active_owners = [owner for owner in owners if owner is not None]
        assert len(active_owners) == 1
        await complete_twilio_effects(
            client,
            call_sid=call_sid,
            incident_id=incident.incident_id,
            owner=active_owners[0],
            ttl_seconds=30,
        )
        assert (
            await acquire_twilio_effects(
                client,
                call_sid=call_sid,
                incident_id=incident.incident_id,
                ttl_seconds=30,
            )
            is None
        )
        assert 0 < await client.ttl(call_key) <= 30
        assert 0 < await client.ttl(vote_key) <= 30
    finally:
        await client.delete(
            token_key,
            telegram_vote_key,
            call_key,
            vote_key,
            incident_key,
        )
        await client.aclose()
