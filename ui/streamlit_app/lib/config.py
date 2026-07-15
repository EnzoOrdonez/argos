"""Configuración de la consola desde el entorno. Sin secretos hardcodeados.

La consola comparte Redis con el SOAR vía ``REDIS_URL`` (mismo nombre de variable
que ``soar/approval_api/main.py``). El intervalo de refresco se acota para no
martillar Redis ni congelar la UI.
"""

from __future__ import annotations

import os

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_REFRESH_MS = 1500
_MIN_REFRESH_MS = 500
_MAX_REFRESH_MS = 10_000


def redis_url() -> str:
    return os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)


def refresh_ms() -> int:
    """Intervalo de st_autorefresh, acotado a [500, 10000] ms."""
    raw = os.environ.get("ARGOS_UI_REFRESH_MS", str(DEFAULT_REFRESH_MS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_REFRESH_MS
    return max(_MIN_REFRESH_MS, min(value, _MAX_REFRESH_MS))


def masked_redis_url(url: str | None = None) -> str:
    """Oculta la password del URL para mostrarlo en la UI (RFC 3986 userinfo)."""
    url = url if url is not None else redis_url()
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    if not rest:  # sin esquema: el partition dejó todo en `scheme`
        scheme, rest = "", url
    creds, _, host = rest.rpartition("@")
    user = creds.split(":", 1)[0]
    masked_creds = f"{user}:***" if ":" in creds else "***"
    return f"{scheme}://{masked_creds}@{host}" if scheme else f"{masked_creds}@{host}"
