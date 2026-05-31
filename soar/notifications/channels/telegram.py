"""Telegram — canal primario de notificación a t=0 (ADR-0007 v2).

Mensaje en MarkdownV2. Para incidentes T2 (pre-aprobación, ADR-0003) agrega
botones inline Approve/Reject; el `callback_data` lo consume el Approval API (§2.6).
El botón "Revert" para T0/T1 (post-facto) y la firma JWT de los callbacks son
Fase 4 (ADR-0010 §4.4 G4) — acá no se implementan.

Adaptado al contrato congelado argos_contracts v1.1.0: los datos salen de
`incident.alert` (NormalizedAlert) y `incident.host.id`, no de los campos planos
que asumía el manual (`host.hostname`, `mitre_technique`, `num_layers_fired`,
`requires_approval`), que NO existen en v1.1.0. `num_layers_fired` no se muestra:
el Incident persiste un único alert representativo, no un conteo de capas.
"""

from __future__ import annotations

import os
import time

import httpx

from argos_contracts.enums import NotificationChannelType, Tier
from argos_contracts.incident import Incident
from soar.notifications.base import DispatchResult, NotificationChannel

_API = "https://api.telegram.org/bot{token}/sendMessage"

_TIER_EMOJI: dict[Tier, str] = {
    Tier.T0: "🔴",
    Tier.T1: "🟠",
    Tier.T2: "🟡",
    Tier.T3: "🔵",
}


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _code_safe(text: str) -> str:
    r"""Escapa lo único especial dentro de un code span MarkdownV2: ` y \\."""
    return text.replace("\\", "\\\\").replace("`", "\\`")


def _format(incident: Incident) -> str:
    alert = incident.alert
    emoji = _TIER_EMOJI[incident.tier]
    return "\n".join(
        [
            f"{emoji} *ARGOS {incident.tier.value}*",
            f"*Host:* `{_code_safe(incident.host.id)}`",
            f"*Tecnica:* `{_code_safe(alert.technique_mitre or 'N/D')}`",
            f"*Capa:* `{alert.source_layer.value}`",
            f"*Severidad:* `{alert.severity_label.value}`",
            f"*Confianza:* `{alert.severity_score:.2f}`",
            f"*ID:* `{_code_safe(incident.incident_id)}`",
        ]
    )


def _inline_keyboard(incident_id: str) -> dict[str, object]:
    return {
        "inline_keyboard": [
            [
                {"text": "Approve", "callback_data": f"approve:{incident_id}"},
                {"text": "Reject", "callback_data": f"reject:{incident_id}"},
            ]
        ]
    }


class TelegramChannel(NotificationChannel):
    channel_type = NotificationChannelType.TELEGRAM

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._token = bot_token or os.environ["TELEGRAM_BOT_TOKEN"]
        self._chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
        self._client = client or httpx.Client(timeout=timeout)

    def dispatch(self, incident: Incident) -> DispatchResult:
        started = time.monotonic()
        body: dict[str, object] = {
            "chat_id": self._chat_id,
            "text": _format(incident),
            "parse_mode": "MarkdownV2",
        }
        # T2 = pre-aprobación con botones (ADR-0003). `requires_approval` se DERIVA
        # del tier; no es un campo del Incident en v1.1.0.
        if incident.tier == Tier.T2:
            body["reply_markup"] = _inline_keyboard(incident.incident_id)
        try:
            response = self._client.post(_API.format(token=self._token), json=body)
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                return DispatchResult(
                    channel=self.channel_type,
                    success=False,
                    latency_ms=_elapsed_ms(started),
                    error=str(payload.get("description")),
                )
            return DispatchResult(
                channel=self.channel_type, success=True, latency_ms=_elapsed_ms(started)
            )
        except httpx.HTTPError as exc:
            return DispatchResult(
                channel=self.channel_type,
                success=False,
                latency_ms=_elapsed_ms(started),
                error=f"http: {exc}",
            )
