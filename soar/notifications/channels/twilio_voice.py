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
import re
import time
from collections.abc import Callable
from urllib.parse import urlencode

import httpx

from argos_contracts.enums import NotificationChannelType
from argos_contracts.incident import Incident
from soar.approval_api.callback_state import callback_ttl_seconds_from_env
from soar.notifications.base import DispatchResult, NotificationChannel

_TWILIO_CALLS = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
_CALL_SID_RE = re.compile(r"^CA[0-9a-fA-F]{32}$")
RequestSink = Callable[[str, int], str]


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _twiml_url(incident_id: str, base: str, request_id: str) -> str:
    """URL pública (ngrok) que Twilio invoca para obtener el TwiML del incidente."""
    return (
        f"{base}/voice/twiml?"
        f"{urlencode({'incident': incident_id, 'request_id': request_id})}"
    )


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
        request_sink: RequestSink | None = None,
        callback_ttl_seconds: int | None = None,
    ) -> None:
        self._sid = account_sid or os.environ["TWILIO_ACCOUNT_SID"]
        self._tok = auth_token or os.environ["TWILIO_AUTH_TOKEN"]
        self._from = from_number or os.environ["TWILIO_FROM_NUMBER"]
        self._to = to_number or os.environ["TWILIO_TO_NUMBER"]
        self._base = (
            public_base_url
            or os.environ.get("APPROVAL_API_PUBLIC_URL")
            or os.environ.get("ARGOS_PUBLIC_URL", "")
        ).rstrip("/")
        self._client = client or httpx.Client(timeout=timeout, auth=(self._sid, self._tok))
        self._request_sink = request_sink
        self._callback_ttl_seconds = (
            callback_ttl_seconds
            if callback_ttl_seconds is not None
            else callback_ttl_seconds_from_env()
        )
        if self._callback_ttl_seconds <= 0:
            raise ValueError("callback_ttl_seconds must be positive")

    def dispatch(self, incident: Incident) -> DispatchResult:
        started = time.monotonic()
        url = _TWILIO_CALLS.format(sid=self._sid)
        if self._request_sink is None or not self._base:
            return DispatchResult(
                channel=self.channel_type,
                success=False,
                latency_ms=_elapsed_ms(started),
                error="authenticated Twilio approvals are not configured",
            )
        try:
            request_id = self._request_sink(
                incident.incident_id, self._callback_ttl_seconds
            )
            response = self._client.post(
                url,
                data={
                    "From": self._from,
                    "To": self._to,
                    "Url": _twiml_url(incident.incident_id, self._base, request_id),
                    "Method": "POST",
                    "Timeout": "20",
                },
            )
            if response.status_code in (200, 201):
                call_sid = str(response.json().get("sid", ""))
                if not _CALL_SID_RE.fullmatch(call_sid):
                    return DispatchResult(
                        channel=self.channel_type,
                        success=False,
                        latency_ms=_elapsed_ms(started),
                        error="Twilio response did not include a CallSid",
                    )
                return DispatchResult(
                    channel=self.channel_type, success=True, latency_ms=_elapsed_ms(started)
                )
            return DispatchResult(
                channel=self.channel_type,
                success=False,
                latency_ms=_elapsed_ms(started),
                error=f"Twilio provider returned HTTP {response.status_code}",
            )
        except Exception as exc:
            return DispatchResult(
                channel=self.channel_type,
                success=False,
                latency_ms=_elapsed_ms(started),
                error=f"Twilio approval dispatch failed: {type(exc).__name__}",
            )
