"""Tests del canal Telegram. HTTP mockeado con respx (no toca red real)."""

from __future__ import annotations

import json

import httpx
import respx

from argos_contracts.enums import Criticality, Tier
from argos_contracts.triage import HostInfo
from soar.approval_api.jwt_signer import ApprovalSigner
from soar.notifications.channels.telegram import (
    TelegramChannel,
    _code_safe,
    _format,
    _inline_keyboard,
)

_URL = "https://api.telegram.org/botTESTTOKEN/sendMessage"


def _channel(**kwargs: object) -> TelegramChannel:
    return TelegramChannel(
        bot_token="TESTTOKEN", chat_id="999", client=httpx.Client(), **kwargs
    )


def _signed_channel(**kwargs: object) -> TelegramChannel:
    return _channel(
        signer=ApprovalSigner(secret="s3cret-de-test-0123456789abcdef-32B+"),
        token_sink=lambda _jti, _token, _ttl: None,
        **kwargs,
    )


def _standard_host() -> HostInfo:
    return HostInfo(
        id="WIN-VICTIM-01", criticality=Criticality.STANDARD, ip="10.0.0.21", os="Win11"
    )


def test_code_safe_escapes_backtick_and_backslash():
    assert _code_safe("a`b\\c") == "a\\`b\\\\c"


def test_format_uses_contract_fields(make_incident):
    msg = _format(make_incident(tier=Tier.T0))
    assert "ARGOS T0" in msg
    assert "`LIN-DB-01`" in msg            # host.id  (NO host.hostname)
    assert "`T1486`" in msg                # alert.technique_mitre
    assert "`layer_1`" in msg              # alert.source_layer
    assert "`INC-2026-05-30-001`" in msg   # incident_id


def test_inline_keyboard_has_approve_and_reject():
    btns = _inline_keyboard("INC-2026-05-30-001", "a1", "r1")["inline_keyboard"][0]
    assert btns[0]["callback_data"] == "approve:INC-2026-05-30-001:a1"
    assert btns[1]["callback_data"] == "reject:INC-2026-05-30-001:r1"


def test_dispatch_success_no_buttons_for_t0_standard(make_incident):
    """T0 en host ESTANDAR es auto-execute post-facto, sin botones. (El host
    critico del conftest si lleva botones desde ADR-0013 §7.9: ver test abajo.)"""
    with respx.mock:
        route = respx.post(_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        r = _channel().dispatch(make_incident(tier=Tier.T0, host=_standard_host()))
    assert r.success is True and r.error is None
    body = json.loads(route.calls.last.request.content)
    assert body["parse_mode"] == "MarkdownV2"
    assert "reply_markup" not in body


def test_dispatch_t1_production_critical_lleva_botones(make_incident):
    """ADR-0013 §7.9: botones por espera humana, no por tier. UC-04 = T1+critico."""
    with respx.mock:
        route = respx.post(_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        _signed_channel().dispatch(make_incident(tier=Tier.T1))
    body = json.loads(route.calls.last.request.content)
    assert "reply_markup" in body


def test_dispatch_con_signer_manda_jti_corto_y_persiste_tokens(make_incident):
    """ADR-0010 §4.4: callback_data = accion:incident:jti, < 64 bytes; el token
    completo va al sink para resolverlo server-side."""
    sink: dict[str, str] = {}
    signer = ApprovalSigner(secret="s3cret-de-test-0123456789abcdef-32B+")
    channel = _channel(
        signer=signer, token_sink=lambda jti, token, ttl: sink.__setitem__(jti, token)
    )
    with respx.mock:
        route = respx.post(_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        channel.dispatch(make_incident(tier=Tier.T2))
    body = json.loads(route.calls.last.request.content)
    buttons = body["reply_markup"]["inline_keyboard"][0]
    for button in buttons:
        data = button["callback_data"]
        assert len(data.encode()) <= 64  # limite de Telegram
        action, incident_id, jti = data.split(":")
        assert action in ("approve", "reject")
        assert incident_id == "INC-2026-05-30-001"
        assert jti in sink  # token completo persistido
    assert len(sink) == 2


def test_dispatch_t2_includes_inline_keyboard(make_incident):
    with respx.mock:
        route = respx.post(_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        r = _signed_channel().dispatch(make_incident(tier=Tier.T2))
    assert r.success is True
    body = json.loads(route.calls.last.request.content)
    cb = body["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert cb.startswith("approve:")


def test_dispatch_telegram_not_ok_is_failure(make_incident):
    with respx.mock:
        respx.post(_URL).mock(
            return_value=httpx.Response(200, json={"ok": False, "description": "chat not found"})
        )
        r = _channel().dispatch(make_incident(tier=Tier.T0, host=_standard_host()))
    assert r.success is False
    assert "chat not found" in (r.error or "")


def test_dispatch_http_error_is_contained(make_incident):
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(500))
        r = _channel().dispatch(make_incident(tier=Tier.T0, host=_standard_host()))
    assert r.success is False
    assert r.error == "Telegram provider request failed"
    assert "test-token" not in r.error


def test_dispatch_state_failure_is_contained_without_sending(make_incident):
    def failing_sink(jti: str, token: str, ttl: int) -> None:
        raise RuntimeError("sensitive provider endpoint detail")

    signer = ApprovalSigner(secret="s3cret-de-test-0123456789abcdef-32B+")
    with respx.mock:
        route = respx.post(_URL).mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        r = _channel(signer=signer, token_sink=failing_sink).dispatch(
            make_incident(tier=Tier.T2)
        )
    assert r.success is False
    assert r.error == "Telegram approval state failed: RuntimeError"
    assert "sensitive" not in r.error
    assert route.call_count == 0
