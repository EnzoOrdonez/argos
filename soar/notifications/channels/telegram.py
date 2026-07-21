"""Telegram — canal primario de notificación a t=0 (ADR-0007 v2).

Mensaje en MarkdownV2. Los botones inline Approve/Reject aparecen cuando el
incidente espera decisión humana: tier T2 o two-person por host
production-critical / acción irreversible (ADR-0013 §7.9; UC-04 es T1+crítico
y lleva botones). Con un `ApprovalSigner` configurado (ADR-0010 §4.4), cada
botón viaja con un `jti` corto (`accion:incident:jti`, < 64 bytes del límite
de Telegram) y el token completo queda en Redis vía `token_sink`; el Approval
API lo verifica y consume antes de mutar estado. El botón "Revert" para
T0/T1 post-facto sigue siendo Fase 4.

Adaptado al contrato congelado argos_contracts v1.1.0: los datos salen de
`incident.alert` (NormalizedAlert) y `incident.host.id`, no de los campos planos
que asumía el manual (`host.hostname`, `mitre_technique`, `num_layers_fired`,
`requires_approval`), que NO existen en v1.1.0. `num_layers_fired` no se muestra:
el Incident persiste un único alert representativo, no un conteo de capas.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable

import httpx

from argos_contracts.enums import Criticality, NotificationChannelType, Tier
from argos_contracts.incident import Incident
from soar.approval_api.jwt_signer import ApprovalSigner
from soar.notifications.base import DispatchResult, NotificationChannel

# Persiste (jti, token, ttl_seconds) para que el API lo resuelva server-side.
TokenSink = Callable[[str, str, int], None]

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


def _inline_keyboard(
    incident_id: str,
    jti_approve: str,
    jti_reject: str,
) -> dict[str, object]:
    """Build signed, server-side token references. Legacy buttons are forbidden."""
    approve = f"approve:{incident_id}:{jti_approve}"
    reject = f"reject:{incident_id}:{jti_reject}"
    return {
        "inline_keyboard": [
            [
                {"text": "Approve", "callback_data": approve},
                {"text": "Reject", "callback_data": reject},
            ]
        ]
    }


def _needs_buttons(incident: Incident) -> bool:
    """Espera humana = T2 o two-person (ADR-0013 §7.9). Refleja
    `approval_api.handlers.requires_two_person` sin acoplar los paquetes."""
    if incident.tier == Tier.T2:
        return True
    if incident.host.criticality == Criticality.PRODUCTION_CRITICAL:
        return True
    return any(not action.reversible for action in incident.proposed_actions)


class TelegramChannel(NotificationChannel):
    channel_type = NotificationChannelType.TELEGRAM

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 5.0,
        signer: ApprovalSigner | None = None,
        token_sink: TokenSink | None = None,
    ) -> None:
        self._token = bot_token or os.environ["TELEGRAM_BOT_TOKEN"]
        self._chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
        self._client = client or httpx.Client(timeout=timeout)
        self._signer = signer
        self._token_sink = token_sink

    def _signed_keyboard(self, incident_id: str) -> dict[str, object]:
        if self._signer is None or self._token_sink is None:
            raise RuntimeError("authenticated Telegram approvals are not configured")
        approver = f"telegram-chat:{self._chat_id}"
        token_a, jti_a = self._signer.sign_approval(incident_id, approver, "approve")
        token_r, jti_r = self._signer.sign_approval(incident_id, approver, "reject")
        self._token_sink(jti_a, token_a, self._signer.ttl_seconds)
        self._token_sink(jti_r, token_r, self._signer.ttl_seconds)
        return _inline_keyboard(incident_id, jti_a, jti_r)

    def dispatch(self, incident: Incident) -> DispatchResult:
        started = time.monotonic()
        body: dict[str, object] = {
            "chat_id": self._chat_id,
            "text": _format(incident),
            "parse_mode": "MarkdownV2",
        }
        try:
            # Botones cuando hay espera humana (T2 o two-person, ADR-0013 §7.9).
            # `requires_approval` se DERIVA; no es un campo del Incident en v1.1.0.
            if _needs_buttons(incident):
                body["reply_markup"] = self._signed_keyboard(incident.incident_id)
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
        except httpx.HTTPError:
            return DispatchResult(
                channel=self.channel_type,
                success=False,
                latency_ms=_elapsed_ms(started),
                error="Telegram provider request failed",
            )
        except Exception as exc:
            return DispatchResult(
                channel=self.channel_type,
                success=False,
                latency_ms=_elapsed_ms(started),
                error=f"Telegram approval state failed: {type(exc).__name__}",
            )
