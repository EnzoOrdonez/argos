"""Tests del NotificationService (estructura base, ADR-0005 / ADR-0007 v2).

Usa un canal fake (no toca red) para verificar la política de despacho por tier,
la degradación ante canal faltante o que lanza, y la escalación a voz.
"""

from __future__ import annotations

from argos_contracts.enums import NotificationChannelType, Tier
from argos_contracts.incident import Incident
from soar.notifications.base import DispatchResult, NotificationChannel
from soar.notifications.service import TIER_CHANNELS, NotificationService

TG = NotificationChannelType.TELEGRAM
DC = NotificationChannelType.DISCORD
TW = NotificationChannelType.TWILIO_VOICE


class _FakeChannel(NotificationChannel):
    def __init__(
        self,
        channel_type: NotificationChannelType,
        *,
        raises: bool = False,
        success: bool = True,
    ) -> None:
        self.channel_type = channel_type
        self._raises = raises
        self._success = success
        self.calls = 0

    def dispatch(self, incident: Incident) -> DispatchResult:
        self.calls += 1
        if self._raises:
            raise RuntimeError("boom")
        return DispatchResult(channel=self.channel_type, success=self._success, latency_ms=5)


def test_dispatch_t0_hits_telegram_and_discord(make_incident):
    tg, dc = _FakeChannel(TG), _FakeChannel(DC)
    results = NotificationService([tg, dc]).dispatch_for_tier(make_incident(tier=Tier.T0))
    assert [r.channel for r in results] == [TG, DC]
    assert all(r.success for r in results)
    assert tg.calls == 1 and dc.calls == 1


def test_dispatch_t3_still_notifies(make_incident):
    # Corrige el `T3: []` del manual — ADR-0003: T3 notifica al analista.
    tg, dc = _FakeChannel(TG), _FakeChannel(DC)
    results = NotificationService([tg, dc]).dispatch_for_tier(make_incident(tier=Tier.T3))
    assert {r.channel for r in results} == {TG, DC}
    assert all(r.success for r in results)


def test_missing_channel_degrades_without_raising(make_incident):
    results = NotificationService([_FakeChannel(TG)]).dispatch_for_tier(
        make_incident(tier=Tier.T1)
    )
    by_ch = {r.channel: r for r in results}
    assert by_ch[TG].success is True
    assert by_ch[DC].success is False
    assert by_ch[DC].error == "channel not configured"


def test_channel_exception_is_contained(make_incident):
    tg, dc = _FakeChannel(TG, raises=True), _FakeChannel(DC)
    results = NotificationService([tg, dc]).dispatch_for_tier(make_incident(tier=Tier.T2))
    by_ch = {r.channel: r for r in results}
    assert by_ch[TG].success is False
    assert "RuntimeError" in (by_ch[TG].error or "")
    assert by_ch[DC].success is True  # un canal caído no tumba al otro


def test_escalate_to_voice_configured(make_incident):
    tw = _FakeChannel(TW)
    r = NotificationService([tw]).escalate_to_voice(make_incident(tier=Tier.T2))
    assert r.channel == TW and r.success is True and tw.calls == 1


def test_escalate_to_voice_not_configured(make_incident):
    r = NotificationService([]).escalate_to_voice(make_incident(tier=Tier.T2))
    assert r.channel == TW and r.success is False
    assert r.error == "twilio not configured"


def test_tier_channels_cover_all_four_tiers():
    assert set(TIER_CHANNELS) == {Tier.T0, Tier.T1, Tier.T2, Tier.T3}
