"""Sanitización del `AlertContext` antes de cruzar a un backend cloud (T-030, ADR-0001).

Implementa los regex de `docs/data-handling.md §2`: redacta credenciales, IPs RFC1918,
usuarios en paths, emails, control chars y marcadores de prompt-injection (T-014). NO
redacta lo que §2.6 marca como público (IDs MITRE, nombres de proceso, extensiones).

Se aplica a los campos de texto libre del contexto (título del alerta, host, y todo
string dentro de `recent_telemetry`, que es lo que el atacante puede influenciar). Si el
JSON total supera 64 KB se rechaza (payload bomb).
"""

from __future__ import annotations

import json
import re

from argos_contracts.triage import AlertContext

_MAX_FIELD_CHARS = 2048
_MAX_TOTAL_BYTES = 64 * 1024

# Orden importa: PEM y password antes que el genérico base64 (que si no se los come).
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z ]+-----[\s\S]+?-----END [A-Z ]+-----"), "<PEM_REDACTED>"),
    (re.compile(r"(?i)password\s*=\s*\S+"), "password=<REDACTED>"),
    (re.compile(r"--password=\S+"), "--password=<REDACTED>"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]+"), "Bearer <REDACTED>"),
    (re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"), "<BASE64_REDACTED>"),
    (re.compile(r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}"), "10.X.X.X"),
    (re.compile(r"172\.(?:1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}"), "172.X.X.X"),
    (re.compile(r"192\.168\.\d{1,3}\.\d{1,3}"), "192.168.X.X"),
    (re.compile(r"(?:fe80:|fc00:|fd00:)[0-9a-f:]+"), "<IPv6_LOCAL_REDACTED>"),
    (re.compile(r"\b(?:victim-|wazuh-mgr|infra-)[\w-]+"), "<HOST_REDACTED>"),
    (re.compile(r"C:\\Users\\[^\\]+\\"), r"C:\\Users\\<USER>\\"),
    (re.compile(r"/home/[^/]+/"), "/home/<USER>/"),
    (re.compile(r"/Users/[^/]+/"), "/Users/<USER>/"),
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "<EMAIL_REDACTED>"),
]

# Marcadores de prompt-injection (T-014): se neutralizan, no se borran.
_INJECTION: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"<\|im_start\|>"), "[im_start]"),
    (re.compile(r"<\|im_end\|>"), "[im_end]"),
    (re.compile(r"<(system|user|assistant)>"), r"[\1]"),
]

# Control chars salvo \t \n \r.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def redact_text(text: str) -> tuple[str, int]:
    """Redacta un string. Devuelve (texto_sanitizado, nº de coincidencias redactadas)."""
    count = 0
    for pattern, replacement in _PATTERNS:
        text, n = pattern.subn(replacement, text)
        count += n
    for pattern, replacement in _INJECTION:
        text, n = pattern.subn(replacement, text)
        count += n
    text, n = _CONTROL.subn("", text)
    count += n
    if len(text) > _MAX_FIELD_CHARS:
        text = text[:_MAX_FIELD_CHARS]
        count += 1
    return text, count


def sanitize(context: AlertContext) -> tuple[AlertContext, int]:
    """Devuelve el `AlertContext` redactado + el total de redacciones (para el audit).

    Rechaza con ValueError si el JSON supera 64 KB (`docs/data-handling.md §2.5`).
    """
    raw = context.model_dump(mode="json")
    size = len(json.dumps(raw, ensure_ascii=False).encode("utf-8"))
    if size > _MAX_TOTAL_BYTES:
        raise ValueError(
            f"AlertContext de {size} bytes supera el límite de {_MAX_TOTAL_BYTES} (T-014)"
        )

    total = 0

    def _walk(value: object) -> object:
        nonlocal total
        if isinstance(value, str):
            new, n = redact_text(value)
            total += n
            return new
        if isinstance(value, dict):
            return {key: _walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_walk(item) for item in value]
        return value

    raw["alert_summary"]["title"] = _walk(raw["alert_summary"]["title"])
    raw["host"]["id"] = _walk(raw["host"]["id"])
    if raw["host"].get("ip"):
        raw["host"]["ip"] = _walk(raw["host"]["ip"])
    raw["recent_telemetry"] = _walk(raw["recent_telemetry"])

    return AlertContext.model_validate(raw), total
