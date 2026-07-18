"""Autenticación mínima de la consola: HTTP Basic con credencial compartida.

RF-7/HU-6: barra mínima para exponer la consola más allá de localhost sin regalar
los datos de incidentes. NO es un sistema de usuarios (v1 = credencial compartida).

Sin `CONSOLE_BASIC_USER`/`CONSOLE_BASIC_PASS` en el entorno la auth queda DESHABILITADA
(dev en localhost sin fricción) con un warning de arranque; un deployment real las setea
(`.env.example` las trae). Se gatea `/` y `/api/*` para que el navegador muestre el
diálogo Basic nativo — una vez autenticado, el fetch del SPA lleva las credenciales;
`/health` queda abierto (liveness/monitoring) y `/static` no expone datos.
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

logger = logging.getLogger(__name__)

_security = HTTPBasic(auto_error=False)
_warned = False


def _configured() -> tuple[str, str] | None:
    """Credencial esperada, o None si la auth está deshabilitada (env sin setear)."""
    user = os.environ.get("CONSOLE_BASIC_USER", "")
    password = os.environ.get("CONSOLE_BASIC_PASS", "")
    if user and password:
        return user, password
    return None


def require_auth(
    credentials: HTTPBasicCredentials | None = Depends(_security),
) -> None:
    """Dependency: exige Basic si CONSOLE_BASIC_* está configurado; si no, no-op."""
    expected = _configured()
    if expected is None:
        global _warned
        if not _warned:
            logger.warning(
                "consola SIN autenticación: seteá CONSOLE_BASIC_USER/CONSOLE_BASIC_PASS "
                "antes de exponerla más allá de localhost"
            )
            _warned = True
        return
    exp_user, exp_pass = expected
    # compare_digest en ambos campos (tiempo constante); sin short-circuit que filtre
    # cuál falló: se evalúan los dos aunque falte el usuario.
    user_ok = credentials is not None and secrets.compare_digest(
        credentials.username, exp_user
    )
    pass_ok = credentials is not None and secrets.compare_digest(
        credentials.password, exp_pass
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="credenciales inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
