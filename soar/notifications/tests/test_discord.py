"""Tests del canal Discord. HTTP mockeado con respx (no toca red real)."""

from __future__ import annotations

import json

import httpx
import respx

from argos_contracts.enums import Tier
from soar.notifications.channels.discord import _COLOR, DiscordChannel, _embed

_URL = "https://discord.com/api/webhooks/123/abc"


def _channel() -> DiscordChannel:
    return DiscordChannel(webhook_url=_URL, client=httpx.Client())


def test_embed_uses_contract_fields(make_incident):
    embed = _embed(make_incident(tier=Tier.T0))
    assert embed["title"] == "ARGOS T0 - LIN-DB-01"      # host.id (NO host.hostname)
    assert embed["color"] == _COLOR[Tier.T0]
    field_values = [f["value"] for f in embed["fields"]]
    assert "T1486" in field_values                       # alert.technique_mitre
    assert "layer_1" in field_values                     # alert.source_layer
    assert "`INC-2026-05-30-001`" in field_values        # incident_id


def test_embed_color_per_tier(make_incident):
    assert _embed(make_incident(tier=Tier.T2))["color"] == _COLOR[Tier.T2]


def test_dispatch_success_204(make_incident):
    with respx.mock:
        route = respx.post(_URL).mock(return_value=httpx.Response(204))
        r = _channel().dispatch(make_incident(tier=Tier.T1))
    assert r.success is True and r.error is None
    body = json.loads(route.calls.last.request.content)
    assert "embeds" in body


def test_dispatch_non_2xx_is_failure(make_incident):
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(400, text="bad webhook"))
        r = _channel().dispatch(make_incident(tier=Tier.T0))
    assert r.success is False
    assert "http 400" in (r.error or "")


def test_dispatch_connection_error_is_contained(make_incident):
    with respx.mock:
        respx.post(_URL).mock(side_effect=httpx.ConnectError("down"))
        r = _channel().dispatch(make_incident(tier=Tier.T0))
    assert r.success is False
    assert "http:" in (r.error or "")
