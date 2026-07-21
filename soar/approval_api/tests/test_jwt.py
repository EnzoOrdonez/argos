"""JWT signing (ADR-0010 §4.4 + ADR-0006 §política JWT, RFC 7519/8725).

Unitarios del signer + integración del callback de Telegram con firma activa:
expirado, algoritmo no permitido (incl. `none`), replay (jti consumido) y
token inválido respondido sin tumbar el API.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import jwt as pyjwt
import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport

from argos_contracts.enums import ApproverStatus
from argos_contracts.incident import Incident
from soar.approval_api.callback_state import TELEGRAM_TOKEN_KEY, TELEGRAM_VOTE_KEY
from soar.approval_api.handlers import save_incident
from soar.approval_api.jwt_signer import (
    ALGORITHM,
    ISSUER,
    ApprovalSigner,
    TokenInvalid,
    store_token,
)
from soar.approval_api.main import app, get_redis
from soar.approval_api.webhook_auth import TelegramWebhookAuth

# >= 64 bytes: valido para HS256 (RFC 7518 §3.2) y para el encode HS512 que
# usa el test del algoritmo no permitido (asi pyjwt no emite warnings).
SECRET = "unit-test-secret-0123456789abcdef-0123456789abcdef-0123456789abcdef"  # pragma: allowlist secret


class FailOnceTelegramRedis(FakeAsyncRedis):
    fail_next_vote_write = False

    async def set(self, name, *args, **kwargs):
        if self.fail_next_vote_write and str(name).startswith("incident:"):
            self.fail_next_vote_write = False
            raise ConnectionError("injected Telegram vote persistence failure")
        return await super().set(name, *args, **kwargs)

    def pipeline(self, *args, **kwargs):
        pipeline = super().pipeline(*args, **kwargs)
        execute = pipeline.execute

        async def execute_with_failure(*execute_args, **execute_kwargs):
            if self.fail_next_vote_write:
                self.fail_next_vote_write = False
                raise ConnectionError("injected Telegram vote transaction failure")
            return await execute(*execute_args, **execute_kwargs)

        pipeline.execute = execute_with_failure
        return pipeline


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
    now = int(time.time())
    token = pyjwt.encode(
        {
            "iss": ISSUER,
            "sub": "x",
            "incident_id": "INC-2026-06-10-001",
            "decision": "approve",
            "iat": now - 600,
            "exp": now - 300,
            "jti": "expired",
        },
        SECRET,
        algorithm=ALGORITHM,
    )
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
    assert ApprovalSigner.from_env() is None

    monkeypatch.setenv("JWT_SECRET", "legacy-secret")
    assert ApprovalSigner.from_env() is None

    monkeypatch.setenv("ARGOS_JWT_SECRET", SECRET)
    monkeypatch.setenv("JWT_EXPIRATION_MINUTES", "3")
    primary = ApprovalSigner.from_env()
    assert primary is not None
    assert primary.secret == SECRET
    assert primary.expiration_minutes == 3


# -- integracion: callback de Telegram con firma activa ------------------------


@pytest_asyncio.fixture
async def signed_api():
    fake = FakeAsyncRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake
    app.state.signer = _signer()
    app.state.telegram_auth = TelegramWebhookAuth(
        secret="telegram-webhook-secret-0123456789",  # pragma: allowlist secret
        chat_id=999,
        approver_user_ids=frozenset({42}),
    )
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": "telegram-webhook-secret-0123456789"
        },
    ) as client:
        yield client, fake
    app.dependency_overrides.clear()
    del app.state.signer
    del app.state.telegram_auth


async def _minted(fake: FakeAsyncRedis, incident_id: str, decision: str) -> str:
    token, jti = _signer().sign_approval(incident_id, "telegram-chat:999", decision)
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
            "message": {"chat": {"id": 999}},
        }
    }
    r = await client.post("/telegram/callback", json=update)

    assert r.json() == {"ok": True}
    stored = Incident.model_validate_json(await fake.get(f"incident:{inc.incident_id}"))
    assert stored.approvers[0].status == ApproverStatus.APPROVED
    assert await fake.get(TELEGRAM_TOKEN_KEY.format(jti=jti)) is None
    assert await fake.get(TELEGRAM_VOTE_KEY.format(jti=jti)) is not None


async def test_callback_reintenta_si_falla_persistencia_sin_consumir_jti(
    make_incident,
):
    fake = FailOnceTelegramRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake
    app.state.signer = _signer()
    app.state.telegram_auth = TelegramWebhookAuth(
        secret="telegram-webhook-secret-0123456789",  # pragma: allowlist secret
        chat_id=999,
        approver_user_ids=frozenset({42}),
    )
    incident = make_incident()
    await save_incident(fake, incident)
    jti = await _minted(fake, incident.incident_id, "approve")
    update = {
        "callback_query": {
            "data": f"approve:{incident.incident_id}:{jti}",
            "from": {"id": 42},
            "message": {"chat": {"id": 999}},
        }
    }
    transport = ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={
                "X-Telegram-Bot-Api-Secret-Token": (
                    "telegram-webhook-secret-0123456789"
                )
            },
        ) as client:
            fake.fail_next_vote_write = True
            with pytest.raises(ConnectionError):
                await client.post("/telegram/callback", json=update)

            assert await fake.get(TELEGRAM_TOKEN_KEY.format(jti=jti)) is not None
            retry = await client.post("/telegram/callback", json=update)
    finally:
        app.dependency_overrides.clear()
        del app.state.signer
        del app.state.telegram_auth

    assert retry.json() == {"ok": True}
    stored = Incident.model_validate_json(
        await fake.get(f"incident:{incident.incident_id}")
    )
    assert len(stored.approvers) == 1


async def test_callback_replay_rechazado(signed_api, make_incident):
    client, fake = signed_api
    inc = make_incident()
    await save_incident(fake, inc)
    jti = await _minted(fake, inc.incident_id, "approve")
    update = {
        "callback_query": {
            "data": f"approve:{inc.incident_id}:{jti}",
            "from": {"id": 42},
            "message": {"chat": {"id": 999}},
        }
    }

    first = await client.post("/telegram/callback", json=update)
    second = await client.post("/telegram/callback", json=update)

    assert first.json()["ok"] is True
    assert second.json() == {"ok": False, "error": "unknown or replayed token"}
    stored = Incident.model_validate_json(await fake.get(f"incident:{inc.incident_id}"))
    assert len(stored.approvers) == 1
    assert await fake.get(TELEGRAM_VOTE_KEY.format(jti=jti)) is not None


async def test_callback_concurrente_muta_una_sola_vez(signed_api, make_incident):
    client, fake = signed_api
    inc = make_incident()
    await save_incident(fake, inc)
    jti = await _minted(fake, inc.incident_id, "approve")
    update = {
        "callback_query": {
            "data": f"approve:{inc.incident_id}:{jti}",
            "from": {"id": 42},
            "message": {"chat": {"id": 999}},
        }
    }

    first, second = await asyncio.gather(
        client.post("/telegram/callback", json=update),
        client.post("/telegram/callback", json=update),
    )

    assert sorted([first.json()["ok"], second.json()["ok"]]) == [False, True]
    stored = Incident.model_validate_json(await fake.get(f"incident:{inc.incident_id}"))
    assert len(stored.approvers) == 1
    assert await fake.get(TELEGRAM_TOKEN_KEY.format(jti=jti)) is None
    assert await fake.get(TELEGRAM_VOTE_KEY.format(jti=jti)) is not None


async def test_callback_rechaza_proveedor_o_usuario_no_autorizado(
    signed_api, make_incident
):
    client, fake = signed_api
    inc = make_incident()
    await save_incident(fake, inc)
    jti = await _minted(fake, inc.incident_id, "approve")
    update = {
        "callback_query": {
            "data": f"approve:{inc.incident_id}:{jti}",
            "from": {"id": 7},
            "message": {"chat": {"id": 999}},
        }
    }

    bad_provider = await client.post(
        "/telegram/callback",
        json=update,
        headers={"X-Telegram-Bot-Api-Secret-Token": "x" * 32},
    )
    bad_user = await client.post("/telegram/callback", json=update)

    assert bad_provider.status_code == 403
    assert bad_user.status_code == 403
    assert await fake.get(TELEGRAM_TOKEN_KEY.format(jti=jti)) is not None


async def test_callback_sin_jti_rechazado_con_firma_activa(signed_api, make_incident):
    client, fake = signed_api
    inc = make_incident()
    await save_incident(fake, inc)

    update = {
        "callback_query": {
            "data": f"approve:{inc.incident_id}",
            "from": {"id": 42},
            "message": {"chat": {"id": 999}},
        }
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
            "message": {"chat": {"id": 999}},
        }
    }
    r = await client.post("/telegram/callback", json=update)

    assert r.status_code == 200  # responde, no explota
    assert r.json()["ok"] is False
    assert r.json()["error"] == "invalid signed token"
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
            "message": {"chat": {"id": 999}},
        }
    }
    r = await client.post("/telegram/callback", json=update)

    assert r.json()["ok"] is False


async def test_callback_data_extra_preserva_token(signed_api, make_incident):
    client, fake = signed_api
    inc = make_incident()
    await save_incident(fake, inc)
    jti = await _minted(fake, inc.incident_id, "approve")
    update = {
        "callback_query": {
            "data": f"approve:{inc.incident_id}:{jti}:extra",
            "from": {"id": 42},
            "message": {"chat": {"id": 999}},
        }
    }

    response = await client.post("/telegram/callback", json=update)

    assert response.json() == {"ok": False, "error": "bad callback_data"}
    assert await fake.get(TELEGRAM_TOKEN_KEY.format(jti=jti)) is not None
