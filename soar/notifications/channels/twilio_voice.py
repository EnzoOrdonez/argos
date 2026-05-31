"""Twilio Voice — escalacion T2 por voz con DTMF a t=60s sin respuesta (ADR-0007 v2).

Ultimo recurso antes de que la ventana de consolidacion / conservative-wins decida
sola (ADR-0006). No manda texto: inicia una llamada saliente via la API de Twilio
que, al ser atendida, hace callback a la URL TwiML servida por el Approval API (§2.6);
esa URL enuncia el incidente y captura DTMF (1=approve, 2=reject).

Plan B si el trial Twilio no llega a Peru (ADR-0007 v2): la escalacion cae a
Telegram + Discord con prefijo [T2-ESCALATION]; eso lo decide el orquestador, no
este canal. Adaptado a argos_contracts v1.1.0: solo usa incident.incident_id.
"""

from __future__ import annotations

import os
import time
from urllib.parse import urlencode

import httpx

from argos_contracts.enums import NotificationChannelType
from argos_contracts.incident import Incident
from soar.notifications.base import DispatchResult, NotificationChannel

_TWILIO_CALLS = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _twiml_url(incident_id: str, base: str) -> str:
    """URL pública (ngrok) que Twilio invoca para obtener el TwiML del incidente."""
    return f"{base}/voice/twiml?{urlencode({'incident': incident_id})}"


class TwilioVoiceChannel(NotificationChannel):
    channel_type = NotificationChannelType.TWILIO_VOICE

    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
        from_number: str | None = None,
        to_number: str | None = None,
        public_base_url: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 8.0,
    ) -> None:
        self._sid = account_sid or os.environ["TWILIO_ACCOUNT_SID"]
        self._tok = auth_token or os.environ["TWILIO_AUTH_TOKEN"]
        self._from = from_number or os.environ["TWILIO_FROM_NUMBER"]
        self._to = to_number or os.environ["TWILIO_TO_NUMBER"]
        self._base = public_base_url or os.environ.get("ARGOS_PUBLIC_URL", "")
        self._client = client or httpx.Client(timeout=timeout, auth=(self._sid, self._tok))

    def dispatch(self, incident: Incident) -> DispatchResult:
        started = time.monotonic()
        url = _TWILIO_CALLS.format(sid=self._sid)
        try:
            response = self._client.post(
                url,
                data={
                    "From": self._from,
                    "To": self._to,
                    "Url": _twiml_url(incident.incident_id, self._base),
                    "Method": "POST",
                    "Timeout": "20",
                },
            )
            if response.status_code in (200, 201):
                return DispatchResult(
                    channel=self.channel_type, success=True, latency_ms=_elapsed_ms(started)
                )
            return DispatchResult(
                channel=self.channel_type,
                success=False,
                latency_ms=_elapsed_ms(started),
                error=f"http {response.status_code}: {response.text[:300]}",
            )
        except httpx.HTTPError as exc:
            return DispatchResult(
                channel=self.channel_type,
                success=False,
                latency_ms=_elapsed_ms(started),
                error=f"http: {exc}",
            )
