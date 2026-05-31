"""Tests del canal Telegram. HTTP mockeado con respx (no toca red real)."""

from __future__ import annotations

import json

import httpx
import respx

from argos_contracts.enums import Tier
from soar.notifications.channels.telegram import (
    TelegramChannel,
    _code_safe,
    _format,
    _inline_keyboard,
)

_URL = "https://api.telegram.org/botTESTTOKEN/sendMessage"


def _channel() -> TelegramChannel:
    return TelegramChannel(bot_token="TESTTOKEN", chat_id="999", client=httpx.Client())


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
    btns = _inline_keyboard("INC-2026-05-30-001")["inline_keyboard"][0]
    assert btns[0]["callback_data"] == "approve:INC-2026-05-30-001"
    assert btns[1]["callback_data"] == "reject:INC-2026-05-30-001"


def test_dispatch_success_no_buttons_for_t0(make_incident):
    with respx.mock:
        route = respx.post(_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        r = _channel().dispatch(make_incident(tier=Tier.T0))
    assert r.success is True and r.error is None
    body = json.loads(route.calls.last.request.content)
    assert body["parse_mode"] == "MarkdownV2"
    assert "reply_markup" not in body


def test_dispatch_t2_includes_inline_keyboard(make_incident):
    with respx.mock:
        route = respx.post(_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        r = _channel().dispatch(make_incident(tier=Tier.T2))
    assert r.success is True
    body = json.loads(route.calls.last.request.content)
    cb = body["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert cb.startswith("approve:")


def test_dispatch_telegram_not_ok_is_failure(make_incident):
    with respx.mock:
        respx.post(_URL).mock(
            return_value=httpx.Response(200, json={"ok": False, "description": "chat not found"})
        )
        r = _channel().dispatch(make_incident(tier=Tier.T0))
    assert r.success is False
    assert "chat not found" in (r.error or "")


def test_dispatch_http_error_is_contained(make_incident):
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(500))
        r = _channel().dispatch(make_incident(tier=Tier.T0))
    assert r.success is False
    assert "http" in (r.error or "")
