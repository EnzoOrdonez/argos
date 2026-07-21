"""Ephemeral, atomic state for approval callbacks."""

from __future__ import annotations

import os
import re
import secrets
from typing import Protocol, cast

import redis as redis_sync
import redis.asyncio as redis_async
from redis.exceptions import WatchError

TELEGRAM_TOKEN_KEY = "approval:telegram:token:{jti}"  # nosec B105  # noqa: S105
TELEGRAM_VOTE_KEY = "approval:telegram:vote:{jti}"
TWILIO_REQUEST_KEY = "approval:twilio:request:{request_id}"
TWILIO_CALL_KEY = "approval:twilio:call:{call_sid}"
TWILIO_VOTE_KEY = "approval:twilio:vote:{call_sid}"
DEFAULT_CALLBACK_TTL_SECONDS = 300
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def callback_ttl_seconds_from_env() -> int:
    raw = os.environ.get(
        "APPROVAL_CALLBACK_TTL_SECONDS", str(DEFAULT_CALLBACK_TTL_SECONDS)
    )
    try:
        ttl_seconds = int(raw)
    except ValueError as exc:
        raise ValueError("APPROVAL_CALLBACK_TTL_SECONDS must be an integer") from exc
    if ttl_seconds <= 0:
        raise ValueError("APPROVAL_CALLBACK_TTL_SECONDS must be positive")
    return ttl_seconds


class CallbackStateSink(Protocol):
    def store_telegram_token(
        self, jti: str, token: str, ttl_seconds: int
    ) -> None: ...

    def store_twilio_request(self, incident_id: str, ttl_seconds: int) -> str: ...


class RedisCallbackStateSink:
    """Sync adapter because notification dispatch is currently synchronous."""

    def __init__(self, redis_url: str) -> None:
        self._client = redis_sync.Redis.from_url(redis_url, decode_responses=True)

    def store_telegram_token(self, jti: str, token: str, ttl_seconds: int) -> None:
        if not self._client.set(
            TELEGRAM_TOKEN_KEY.format(jti=jti), token, ex=ttl_seconds
        ):
            raise RuntimeError("Redis did not confirm the Telegram token")

    def store_twilio_request(self, incident_id: str, ttl_seconds: int) -> str:
        request_id = secrets.token_urlsafe(24)
        if not self._client.set(
            TWILIO_REQUEST_KEY.format(request_id=request_id),
            incident_id,
            ex=ttl_seconds,
            nx=True,
        ):
            raise RuntimeError("Redis did not confirm the Twilio request")
        return request_id


async def load_twilio_call(r: redis_async.Redis, call_sid: str) -> str | None:
    return cast(str | None, await r.get(TWILIO_CALL_KEY.format(call_sid=call_sid)))


async def bind_twilio_call_from_request(
    r: redis_async.Redis,
    *,
    request_id: str,
    call_sid: str,
    incident_id: str,
    ttl_seconds: int,
) -> None:
    if not _REQUEST_ID_RE.fullmatch(request_id):
        raise PermissionError("invalid Twilio request correlation")
    request_key = TWILIO_REQUEST_KEY.format(request_id=request_id)
    call_key = TWILIO_CALL_KEY.format(call_sid=call_sid)

    while True:
        async with r.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(request_key, call_key)
                existing = await pipe.get(call_key)
                if existing is not None:
                    if cast(str, existing) != incident_id:
                        raise PermissionError("CallSid is bound to another incident")
                    return
                pending = await pipe.get(request_key)
                if pending is None or cast(str, pending) != incident_id:
                    raise PermissionError("unknown Twilio request correlation")
                pipe.multi()  # type: ignore[no-untyped-call]
                pipe.set(call_key, incident_id, ex=ttl_seconds, nx=True)
                pipe.delete(request_key)
                results = await pipe.execute()
                if results[0]:
                    return
            except WatchError:
                continue
