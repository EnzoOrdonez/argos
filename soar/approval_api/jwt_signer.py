"""Firma JWT de los botones de aprobación (ADR-0010 §4.4 ideal, vigente por la
prórroga del 28-jun; trigger T-10 = 18-jun).

Estructura per RFC 7519; endurecimiento per RFC 8725 (JWT Best Current
Practices): §3.1 verificación estricta de algoritmo contra una lista de UN
solo elemento (rechaza `none` y la confusión de algoritmos), §3.9 validación
de `iss`, vida corta del token. Propiedades del token per ADR-0006 §política
JWT: expira a los 5 minutos (configurable con `JWT_EXPIRATION_MINUTES`),
single-use, atado al `incident_id`. El snippet de 600s en ADR-0010 es
ilustrativo; la política de token la fija ADR-0006.

Telegram limita `callback_data` a 64 bytes, así que el botón lleva
`accion:incident_id:jti` (~37 bytes) y el token completo vive en Redis
(`jwt:tok:{jti}`, TTL = exp). El callback lo resuelve y CONSUME con GETDEL:
un `jti` usado desaparece y el replay muere ahí (T-063 del threat model).

Secreto: `ARGOS_JWT_SECRET` (nombre de ADR-0010 §4.4) con fallback al
`JWT_SECRET` que `.env.example` define desde la semana 1. Nunca commiteado.
Sin secreto configurado el API opera en modo legacy sin firma (Fase 2).
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal

import jwt
import redis.asyncio as redis

logger = logging.getLogger(__name__)

# RFC 7518 §3.2: la clave HMAC para HS256 debe medir al menos el tamano del
# hash (32 bytes). Por debajo se degrada la resistencia a fuerza bruta.
MIN_SECRET_BYTES = 32

ISSUER = "argos-soar"
ALGORITHM = "HS256"  # lista de un solo elemento en decode (RFC 8725 §3.1)
DEFAULT_EXPIRATION_MINUTES = 5  # ADR-0006 §política JWT

Decision = Literal["approve", "reject"]

_TOKEN_KEY = "jwt:tok:{jti}"


class TokenInvalid(Exception):
    """Token rechazado: firma, algoritmo, exp, iss o claims que no calzan."""


@dataclass(frozen=True)
class ApprovalSigner:
    secret: str
    expiration_minutes: int = DEFAULT_EXPIRATION_MINUTES

    def __post_init__(self) -> None:
        if len(self.secret.encode()) < MIN_SECRET_BYTES:
            logger.warning(
                "ARGOS_JWT_SECRET mide %d bytes; RFC 7518 §3.2 pide >= %d para HS256",
                len(self.secret.encode()),
                MIN_SECRET_BYTES,
            )

    @classmethod
    def from_env(cls) -> ApprovalSigner | None:
        """Signer desde el entorno, o None (modo legacy) si no hay secreto."""
        secret = os.environ.get("ARGOS_JWT_SECRET") or os.environ.get("JWT_SECRET")
        if not secret:
            return None
        minutes = int(
            os.environ.get("JWT_EXPIRATION_MINUTES", str(DEFAULT_EXPIRATION_MINUTES))
        )
        return cls(secret=secret, expiration_minutes=minutes)

    @property
    def ttl_seconds(self) -> int:
        return self.expiration_minutes * 60

    def sign_approval(
        self, incident_id: str, approver_id: str, decision: Decision
    ) -> tuple[str, str]:
        """Devuelve (token, jti). El jti corto viaja en el callback_data."""
        jti = secrets.token_hex(6)
        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": ISSUER,
            "sub": approver_id,
            "incident_id": incident_id,
            "decision": decision,
            "iat": now,
            "exp": now + self.ttl_seconds,
            "jti": jti,
        }
        return jwt.encode(payload, self.secret, algorithm=ALGORITHM), jti

    def verify_approval(
        self, token: str, *, expected_incident: str, expected_decision: str
    ) -> dict[str, Any]:
        """Valida firma, algoritmo (solo HS256), exp, iss y el binding al
        incidente y la decisión del botón. Lanza TokenInvalid si algo no calza."""
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self.secret,
                algorithms=[ALGORITHM],
                issuer=ISSUER,
                options={
                    "require": ["exp", "iat", "iss", "sub", "jti"],
                },
            )
        except jwt.InvalidTokenError as exc:
            raise TokenInvalid(str(exc)) from exc
        if payload.get("incident_id") != expected_incident:
            raise TokenInvalid("incident_id no coincide con el boton")
        if payload.get("decision") != expected_decision:
            raise TokenInvalid("decision no coincide con el boton")
        return payload


async def store_token(r: redis.Redis, jti: str, token: str, ttl_seconds: int) -> None:
    """Guarda el token completo resoluble server-side (TTL = exp)."""
    await r.set(_TOKEN_KEY.format(jti=jti), token, ex=ttl_seconds)


async def consume_token(r: redis.Redis, jti: str) -> str | None:
    """Resuelve y CONSUME el token (GETDEL): single-use, el replay no existe."""
    return await r.getdel(_TOKEN_KEY.format(jti=jti))
