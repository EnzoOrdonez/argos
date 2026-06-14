"""Orquesta el despacho a múltiples canales según el Tier del incidente.

Política de canales por tier (ADR-0003 §Esquema de tiers + ADR-0007 v2):
- T0/T1: notificación post-facto (la auto-acción ya se ejecutó) — Telegram + Discord.
- T2: pre-aprobación — Telegram (botones inline) + Discord; Twilio Voice como
  escalación a t=60s sin respuesta (via `escalate_to_voice`, no en el dispatch t=0).
- T3: solo notificación informativa al analista — Telegram + Discord, sin botones.

Email queda como resumen post-facto (ADR-0007 v2), fuera del camino crítico t=0.
El formato del mensaje (botones sí/no, post-facto vs pre-aprobación) es
responsabilidad de cada canal concreto (§2.3+), no de este orquestador.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable

from argos_contracts.enums import NotificationChannelType, Tier
from argos_contracts.incident import Incident
from soar.notifications.base import DispatchResult, NotificationChannel

logger = logging.getLogger(__name__)

# Canales a t=0 por tier. T3 SÍ notifica (ADR-0003: "análisis al analista vía
# Telegram + Discord, sin botón ejecutar") — corrige el `T3: []` del manual.
TIER_CHANNELS: dict[Tier, list[NotificationChannelType]] = {
    Tier.T0: [NotificationChannelType.TELEGRAM, NotificationChannelType.DISCORD],
    Tier.T1: [NotificationChannelType.TELEGRAM, NotificationChannelType.DISCORD],
    Tier.T2: [NotificationChannelType.TELEGRAM, NotificationChannelType.DISCORD],
    Tier.T3: [NotificationChannelType.TELEGRAM, NotificationChannelType.DISCORD],
}


class NotificationService:
    """Despacha un incidente a los canales que corresponden a su tier.

    Un canal que falla o no está configurado NUNCA tumba al resto: el servicio
    recoge un `DispatchResult(success=False)` y sigue (fail-soft, ADR-0007 v2).
    """

    def __init__(self, channels: Iterable[NotificationChannel]) -> None:
        self._channels: dict[NotificationChannelType, NotificationChannel] = {
            c.channel_type: c for c in channels
        }

    def dispatch_for_tier(self, incident: Incident) -> list[DispatchResult]:
        wanted = TIER_CHANNELS.get(incident.tier, [])
        results: list[DispatchResult] = []
        for channel_type in wanted:
            channel = self._channels.get(channel_type)
            if channel is None:
                results.append(
                    DispatchResult(
                        channel=channel_type,
                        success=False,
                        latency_ms=0,
                        error="channel not configured",
                    )
                )
                continue
            started = time.monotonic()
            try:
                results.append(channel.dispatch(incident))
            except Exception as exc:
                # Un canal concreto no debería lanzar (su contrato es degradar),
                # pero si lo hace lo contenemos acá para no romper el despacho.
                logger.exception("channel %s raised during dispatch", channel_type)
                results.append(
                    DispatchResult(
                        channel=channel_type,
                        success=False,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        error=f"unexpected: {type(exc).__name__}: {exc}",
                    )
                )
        return results

    def escalate_to_voice(self, incident: Incident) -> DispatchResult:
        """Escalación T2 por voz (Twilio DTMF) a t=60s sin respuesta (ADR-0007 v2)."""
        voice = self._channels.get(NotificationChannelType.TWILIO_VOICE)
        if voice is None:
            return DispatchResult(
                channel=NotificationChannelType.TWILIO_VOICE,
                success=False,
                latency_ms=0,
                error="twilio not configured",
            )
        return voice.dispatch(incident)
