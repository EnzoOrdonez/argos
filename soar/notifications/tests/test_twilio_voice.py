"""Tests del canal Twilio Voice. API de Twilio mockeada con respx (no llama de verdad)."""

from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import respx

from argos_contracts.enums import Tier
from soar.notifications.channels.twilio_voice import TwilioVoiceChannel, _twiml_url

_CALLS_URL = "https://api.twilio.com/2010-04-01/Accounts/ACtest/Calls.json"


def _channel(request_sink=lambda _incident, _ttl: "r" * 32) -> TwilioVoiceChannel:
    return TwilioVoiceChannel(
        account_sid="ACtest",
        auth_token="tok",
        from_number="+15550000000",
        to_number="+51999888777",
        public_base_url="https://ngrok.test",
        client=httpx.Client(),
        request_sink=request_sink,
    )


def test_twiml_url_builds_callback():
    assert (
        _twiml_url("INC-2026-05-30-001", "https://ngrok.test", "r" * 32)
        == "https://ngrok.test/voice/twiml?"
        "incident=INC-2026-05-30-001&request_id=" + "r" * 32
    )


def test_dispatch_initiates_call_201(make_incident):
    requests: list[tuple[str, int]] = []
    with respx.mock:
        route = respx.post(_CALLS_URL).mock(
            return_value=httpx.Response(
                201, json={"sid": "CA" + "a" * 32, "status": "queued"}
            )
        )
        r = _channel(
            lambda incident, ttl: requests.append((incident, ttl)) or "r" * 32
        ).dispatch(make_incident(tier=Tier.T2))
    assert r.success is True and r.error is None
    form = parse_qs(route.calls.last.request.content.decode())
    assert form["To"] == ["+51999888777"]
    assert form["From"] == ["+15550000000"]
    assert "voice/twiml?incident=INC-2026-05-30-001" in form["Url"][0]
    assert "request_id=" + "r" * 32 in form["Url"][0]
    assert requests == [("INC-2026-05-30-001", 300)]


def test_dispatch_twilio_error_status_is_failure(make_incident):
    with respx.mock:
        respx.post(_CALLS_URL).mock(return_value=httpx.Response(400, text="invalid 'To' number"))
        r = _channel().dispatch(make_incident(tier=Tier.T2))
    assert r.success is False
    assert r.error == "Twilio provider returned HTTP 400"
    assert "invalid" not in r.error


def test_dispatch_rejects_malformed_call_sid(make_incident):
    with respx.mock:
        respx.post(_CALLS_URL).mock(
            return_value=httpx.Response(201, json={"sid": "CAshort"})
        )
        r = _channel().dispatch(make_incident(tier=Tier.T2))
    assert r.success is False
    assert r.error == "Twilio response did not include a CallSid"


def test_dispatch_connection_error_is_contained(make_incident):
    with respx.mock:
        respx.post(_CALLS_URL).mock(side_effect=httpx.ConnectError("down"))
        r = _channel().dispatch(make_incident(tier=Tier.T2))
    assert r.success is False
    assert "ConnectError" in (r.error or "")


def test_dispatch_does_not_call_provider_when_correlation_persistence_fails(
    make_incident,
):
    def failing_sink(_incident: str, _ttl: int) -> str:
        raise ConnectionError("injected Redis failure")

    with respx.mock:
        route = respx.post(_CALLS_URL).mock(
            return_value=httpx.Response(
                201, json={"sid": "CA" + "a" * 32, "status": "queued"}
            )
        )
        result = _channel(failing_sink).dispatch(make_incident(tier=Tier.T2))

    assert result.success is False
    assert result.error == "Twilio approval dispatch failed: ConnectionError"
    assert route.call_count == 0
