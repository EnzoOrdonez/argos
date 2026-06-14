"""JWT signing (ADR-0010 §4.4 + ADR-0006 §política JWT, RFC 7519/8725).

Unitarios del signer + integración del callback de Telegram con firma activa:
expirado, algoritmo no permitido (incl. `none`), replay (jti consumido) y
token inválido respondido sin tumbar el API.
"""

from __future__ import annotations

import time

import httpx
import jwt as pyjwt
import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport

from argos_contracts.enums import ApproverStatus
from argos_contracts.incident import Incident
from soar.approval_api.handlers import save_incident
from soar.approval_api.jwt_signer import (
    ALGORITHM,
    ISSUER,
    ApprovalSigner,
    TokenInvalid,
    consume_token,
    store_token,
)
from soar.approval_api.main import app, get_redis

# >= 64 bytes: valido para HS256 (RFC 7518 §3.2) y para el encode HS512 que
# usa el test del algoritmo no permitido (asi pyjwt no emite warnings).
SECRET = "unit-test-secret-0123456789abcdef-0123456789abcdef-0123456789abcdef"


def _signer(minutes: int = 5) -> ApprovalSigner:
    return ApprovalSigner(secret=SECRET, expiration_minutes=minutes)


# -- unitarios del signer ------------------------------------------------------


def test_firma_y_verificacion_roundtrip():
    token, jti = _signer().sign_approval("INC-2026-06-10-001", "telegram:999", "approve")

    payload = _signer().verify_approval(
        token, expected_incident="INC-2026-06-10-001", expected_decision="approve"
    )

    assert payload["iss"] == ISSUER
    assert payload["sub"] == "telegram:999"
    assert payload["jti"] == jti
    assert payload["exp"] - payload["iat"] == 5 * 60  # 5 min per ADR-0006


def test_token_expirado_rechazado():
    token, _ = _signer(minutes=-1).sign_approval("INC-2026-06-10-001", "x", "approve")
    with pytest.raises(TokenInvalid, match="expired"):
        _signer().verify_approval(
            token, expected_incident="INC-2026-06-10-001", expected_decision="approve"
        )


def test_algoritmo_distinto_rechazado():
    """RFC 8725 §3.1: la lista de algoritmos tiene UN elemento."""
    now = int(time.time())
    claims = {
        "iss": ISSUER, "sub": "x", "incident_id": "INC-2026-06-10-001",
        "decision": "approve", "iat": now, "exp": now + 300, "jti": "abc123",
    }
    hs512 = pyjwt.encode(claims, SECRET, algorithm="HS512")
    with pytest.raises(TokenInvalid):
        _signer().verify_approval(
            hs512, expected_incident="INC-2026-06-10-001", expected_decision="approve"
        )


def test_algoritmo_none_rechazado():
    now = int(time.time())
    claims = {
        "iss": ISSUER, "sub": "x", "incident_id": "INC-2026-06-10-001",
        "decision": "approve", "iat": now, "exp": now + 300, "jti": "abc123",
    }
    unsigned = pyjwt.encode(claims, key=None, algorithm="none")
    with pytest.raises(TokenInvalid):
        _signer().verify_approval(
            unsigned, expected_incident="INC-2026-06-10-001", expected_decision="approve"
        )


def test_issuer_equivocado_rechazado():
    now = int(time.time())
    claims = {
        "iss": "otro-emisor", "sub": "x", "incident_id": "INC-2026-06-10-001",
        "decision": "approve", "iat": now, "exp": now + 300, "jti": "abc123",
    }
    token = pyjwt.encode(claims, SECRET, algorithm=ALGORITHM)
    with pytest.raises(TokenInvalid):
        _signer().verify_approval(
            token, expected_incident="INC-2026-06-10-001", expected_decision="approve"
        )


def test_binding_a_incidente_y_decision():
    token, _ = _signer().sign_approval("INC-2026-06-10-001", "x", "approve")
    with pytest.raises(TokenInvalid, match="incident_id"):
        _signer().verify_approval(
            token, expected_incident="INC-2026-06-10-002", expected_decision="approve"
        )
    with pytest.raises(TokenInvalid, match="decision"):
        _signer().verify_approval(
            token, expected_incident="INC-2026-06-10-001", expected_decision="reject"
        )


def test_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ARGOS_JWT_SECRET", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    assert ApprovalSigner.from_env() is None  # sin secreto: modo legacy

    monkeypatch.setenv("JWT_SECRET", "legacy-secret")
    fallback = ApprovalSigner.from_env()
    assert fallback is not None and fallback.secret == "legacy-secret"

    monkeypatch.setenv("ARGOS_JWT_SECRET", "primary-secret")
    monkeypatch.setenv("JWT_EXPIRATION_MINUTES", "3")
    primary = ApprovalSigner.from_env()
    assert primary is not None
    assert primary.secret == "primary-secret"  # ADR-0010 §4.4 manda
    assert primary.expiration_minutes == 3


async def test_consume_token_es_single_use():
    r = FakeAsyncRedis(decode_responses=True)
    await store_token(r, "jti123", "el-token", 300)
    assert await consume_token(r, "jti123") == "el-token"
    assert await consume_token(r, "jti123") is None  # replay: ya no existe


# -- integracion: callback de Telegram con firma activa ------------------------


@pytest_asyncio.fixture
async def signed_api():
    fake = FakeAsyncRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake
    app.state.signer = _signer()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake
    app.dependency_overrides.clear()
    del app.state.signer


async def _minted(fake: FakeAsyncRedis, incident_id: str, decision: str) -> str:
    token, jti = _signer().sign_approval(incident_id, "telegram:999", decision)
    await store_token(fake, jti, token, 300)
    return jti


async def test_callback_firmado_registra_voto(signed_api, make_incident):
    client, fake = signed_api
    inc = make_incident()
    await save_incident(fake, inc)
    jti = await _minted(fake, inc.incident_id, "approve")

    update = {
        "callback_query": {
            "data": f"approve:{inc.incident_id}:{jti}",
            "from": {"id": 42},
        }
    }
    r = await client.post("/telegram/callback", json=update)

    assert r.json() == {"ok": True}
    stored = Incident.model_validate_json(await fake.get(f"incident:{inc.incident_id}"))
    assert stored.approvers[0].status == ApproverStatus.APPROVED


async def test_callback_replay_rechazado(signed_api, make_incident):
    client, fake = signed_api
    inc = make_incident()
    await save_incident(fake, inc)
    jti = await _minted(fake, inc.incident_id, "approve")
    update = {
        "callback_query": {
            "data": f"approve:{inc.incident_id}:{jti}",
            "from": {"id": 42},
        }
    }

    first = await client.post("/telegram/callback", json=update)
    second = await client.post("/telegram/callback", json=update)

    assert first.json()["ok"] is True
    assert second.json() == {"ok": False, "error": "unknown or replayed token"}


async def test_callback_sin_jti_rechazado_con_firma_activa(signed_api, make_incident):
    client, fake = signed_api
    inc = make_incident()
    await save_incident(fake, inc)

    update = {
        "callback_query": {"data": f"approve:{inc.incident_id}", "from": {"id": 42}}
    }
    r = await client.post("/telegram/callback", json=update)

    assert r.json() == {"ok": False, "error": "missing signed token"}


async def test_callback_token_adulterado_no_tumba_el_api(signed_api, make_incident):
    client, fake = signed_api
    inc = make_incident()
    await save_incident(fake, inc)
    # Token firmado con OTRO secreto: la firma no valida.
    intruso = ApprovalSigner(secret="otro-secreto-0123456789abcdef-32-bytes")
    token, jti = intruso.sign_approval(inc.incident_id, "telegram:999", "approve")
    await store_token(fake, jti, token, 300)

    update = {
        "callback_query": {
            "data": f"approve:{inc.incident_id}:{jti}",
            "from": {"id": 42},
        }
    }
    r = await client.post("/telegram/callback", json=update)

    assert r.status_code == 200  # responde, no explota
    assert r.json()["ok"] is False
    assert "invalid token" in r.json()["error"]
    stored = Incident.model_validate_json(await fake.get(f"incident:{inc.incident_id}"))
    assert stored.approvers == []  # Redis no se muto


async def test_callback_decision_cruzada_rechazada(signed_api, make_incident):
    """Token de reject usado en el boton approve: el binding lo mata."""
    client, fake = signed_api
    inc = make_incident()
    await save_incident(fake, inc)
    jti = await _minted(fake, inc.incident_id, "reject")

    update = {
        "callback_query": {
            "data": f"approve:{inc.incident_id}:{jti}",
            "from": {"id": 42},
        }
    }
    r = await client.post("/telegram/callback", json=update)

    assert r.json()["ok"] is False
