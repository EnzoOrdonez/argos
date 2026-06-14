"""Helpers TwiML para la escalacion por voz (Twilio): generacion del XML + parseo DTMF.

Puro, sin I/O. El `action` del <Gather> incluye el incident_id como query param
para que el endpoint /voice/dtmf sepa a que incidente corresponde el dígito; el
manual omitia esto y el endpoint nunca habria recibido el incidente.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlencode

Decision = Literal["approve", "reject"]

_DTMF: dict[str, Decision] = {"1": "approve", "2": "reject"}


def build_voice_gather_xml(incident_id: str) -> str:
    """TwiML que enuncia el incidente y captura 1 dígito (1=approve, 2=reject)."""
    action = f"/voice/dtmf?{urlencode({'incident': incident_id})}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f'  <Gather numDigits="1" action="{action}" method="POST" timeout="20">\n'
        f"    <Say>ARGOS incident {incident_id}. "
        "Press one to approve, two to reject.</Say>\n"
        "  </Gather>\n"
        "  <Say>No input received. Goodbye.</Say>\n"
        "  <Hangup/>\n"
        "</Response>"
    )


def dtmf_to_response(digits: str) -> Decision | None:
    """Traduce el dígito DTMF a una decisión; None si es invalido o vacio."""
    return _DTMF.get(digits.strip()) if digits else None
