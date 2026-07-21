from __future__ import annotations

from typing import Any

import pytest

from soar.approval_api.callback_state import callback_ttl_seconds_from_env
from soar.approval_api.jwt_signer import ApprovalSigner
from soar.approval_api.webhook_auth import (
    TelegramWebhookAuth,
    TwilioWebhookAuth,
    WebhookAuthenticationError,
    WebhookConfigurationError,
)

_TELEGRAM_ENV = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_APPROVER_USER_IDS",
)
_TWILIO_ENV = (
    "TWILIO_AUTH_TOKEN",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_FROM_NUMBER",
    "TWILIO_TO_NUMBER",
    "APPROVAL_API_PUBLIC_URL",
    "ARGOS_PUBLIC_URL",
    "ENVIRONMENT",
)


def _clear(monkeypatch: pytest.MonkeyPatch, names: tuple[str, ...]) -> None:
    for name in names:
        monkeypatch.delenv(name, raising=False)


def test_partial_telegram_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch, _TELEGRAM_ENV)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "configured")

    with pytest.raises(WebhookConfigurationError):
        TelegramWebhookAuth.from_env()


def test_telegram_requires_provider_secret_chat_and_individual_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch, _TELEGRAM_ENV)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s" * 32)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123")
    monkeypatch.setenv("TELEGRAM_APPROVER_USER_IDS", "41, 42")
    auth = TelegramWebhookAuth.from_env()
    assert auth is not None

    update: dict[str, Any] = {
        "callback_query": {
            "from": {"id": 42},
            "message": {"chat": {"id": -100123}},
        }
    }
    assert auth.authenticate("s" * 32, update) == (42, -100123)
    with pytest.raises(WebhookAuthenticationError):
        auth.authenticate("wrong", update)
    update["callback_query"]["from"]["id"] = 99
    with pytest.raises(WebhookAuthenticationError):
        auth.authenticate("s" * 32, update)


def test_public_url_alone_does_not_enable_twilio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch, _TWILIO_ENV)
    monkeypatch.setenv("APPROVAL_API_PUBLIC_URL", "https://argos.example")

    assert TwilioWebhookAuth.from_env() is None


def test_twilio_rejects_http_public_url_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch, _TWILIO_ENV)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-auth-token")
    monkeypatch.setenv("APPROVAL_API_PUBLIC_URL", "http://argos.example")
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(WebhookConfigurationError):
        TwilioWebhookAuth.from_env()


@pytest.mark.parametrize("secret", ["short", "change-me", "changeme"])
def test_signer_rejects_weak_or_known_secrets(secret: str) -> None:
    with pytest.raises(ValueError):
        ApprovalSigner(secret)


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_callback_ttl_must_be_positive_integer(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPROVAL_CALLBACK_TTL_SECONDS", value)
    with pytest.raises(ValueError):
        callback_ttl_seconds_from_env()
