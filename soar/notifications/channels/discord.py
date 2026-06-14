"""Discord — canal de visibilidad del equipo a t=0 (ADR-0007 v2).

Webhook simple con embed coloreado por tier. No requiere bot ni token de usuario.
No lleva botones de aprobacion: la aprobacion se hace en Telegram (canal primario);
Discord da visibilidad publica en el server del equipo.

Adaptado a argos_contracts v1.1.0: datos desde incident.alert (NormalizedAlert) y
incident.host.id, no de los campos planos del manual (host.hostname, mitre_technique,
num_layers_fired, confidence_score), inexistentes en v1.1.0.
"""

from __future__ import annotations

import os
import time

import httpx

from argos_contracts.enums import NotificationChannelType, Tier
from argos_contracts.incident import Incident
from soar.notifications.base import DispatchResult, NotificationChannel

# Color del embed por tier (rojo/naranja/amarillo/azul).
_COLOR: dict[Tier, int] = {
    Tier.T0: 0xE53935,
    Tier.T1: 0xFB8C00,
    Tier.T2: 0xFDD835,
    Tier.T3: 0x1E88E5,
}


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _embed(incident: Incident) -> dict[str, object]:
    alert = incident.alert
    return {
        "title": f"ARGOS {incident.tier.value} - {incident.host.id}",
        "color": _COLOR[incident.tier],
        "fields": [
            {"name": "Tecnica MITRE", "value": alert.technique_mitre or "N/D", "inline": True},
            {"name": "Capa origen", "value": alert.source_layer.value, "inline": True},
            {
                "name": "Severidad",
                "value": f"{alert.severity_label.value} ({alert.severity_score:.2f})",
                "inline": True,
            },
            {"name": "Incident ID", "value": f"`{incident.incident_id}`", "inline": False},
        ],
        "footer": {"text": "ARGOS | aprobacion via Telegram"},
    }


class DiscordChannel(NotificationChannel):
    channel_type = NotificationChannelType.DISCORD

    def __init__(
        self,
        webhook_url: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._url = webhook_url or os.environ["DISCORD_WEBHOOK_URL"]
        self._client = client or httpx.Client(timeout=timeout)

    def dispatch(self, incident: Incident) -> DispatchResult:
        started = time.monotonic()
        body: dict[str, object] = {"embeds": [_embed(incident)]}
        try:
            response = self._client.post(self._url, json=body)
            if response.status_code in (200, 204):
                return DispatchResult(
                    channel=self.channel_type, success=True, latency_ms=_elapsed_ms(started)
                )
            return DispatchResult(
                channel=self.channel_type,
                success=False,
                latency_ms=_elapsed_ms(started),
                error=f"http {response.status_code}: {response.text[:200]}",
            )
        except httpx.HTTPError as exc:
            return DispatchResult(
                channel=self.channel_type,
                success=False,
                latency_ms=_elapsed_ms(started),
                error=f"http: {exc}",
            )
