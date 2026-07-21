"""Provider authenticity and authorization for approval webhooks."""

from __future__ import annotations

import hmac
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from twilio.request_validator import RequestValidator  # type: ignore[import-untyped]

_TELEGRAM_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{32,256}$")
_CALL_SID_RE = re.compile(r"^CA[0-9a-fA-F]{32}$")


class WebhookConfigurationError(RuntimeError):
    """Configuration cannot authenticate the provider securely."""


class WebhookAuthenticationError(ValueError):
    """Request lacks sufficient provider authenticity or authorization."""


def _csv_ints(raw: str) -> frozenset[int]:
    try:
        values = frozenset(int(value.strip()) for value in raw.split(",") if value.strip())
    except ValueError as exc:
        raise WebhookConfigurationError(
            "TELEGRAM_APPROVER_USER_IDS must contain comma-separated numeric IDs"
        ) from exc
    if not values:
        raise WebhookConfigurationError("TELEGRAM_APPROVER_USER_IDS cannot be empty")
    return values


@dataclass(frozen=True)
class TelegramWebhookAuth:
    secret: str
    chat_id: int
    approver_user_ids: frozenset[int]

    @classmethod
    def from_env(cls) -> TelegramWebhookAuth | None:
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
        chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        approvers = os.environ.get("TELEGRAM_APPROVER_USER_IDS", "").strip()
        configured = bool(
            secret or chat or approvers or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        )
        if not configured:
            return None
        if not secret or not chat or not approvers:
            raise WebhookConfigurationError(
                "Telegram requires TELEGRAM_WEBHOOK_SECRET, TELEGRAM_CHAT_ID and "
                "TELEGRAM_APPROVER_USER_IDS"
            )
        if not _TELEGRAM_SECRET_RE.fullmatch(secret):
            raise WebhookConfigurationError(
                "TELEGRAM_WEBHOOK_SECRET must be 32-256 characters [A-Za-z0-9_-]"
            )
        try:
            chat_id = int(chat)
        except ValueError as exc:
            raise WebhookConfigurationError("TELEGRAM_CHAT_ID must be numeric") from exc
        return cls(secret=secret, chat_id=chat_id, approver_user_ids=_csv_ints(approvers))

    def authenticate(
        self, supplied_secret: str | None, update: Mapping[str, Any]
    ) -> tuple[int, int]:
        if supplied_secret is None or not hmac.compare_digest(
            supplied_secret.encode(), self.secret.encode()
        ):
            raise WebhookAuthenticationError("invalid provider signature")
        callback = update.get("callback_query")
        if not isinstance(callback, Mapping):
            raise WebhookAuthenticationError("missing callback_query")
        sender = callback.get("from")
        message = callback.get("message")
        chat = message.get("chat") if isinstance(message, Mapping) else None
        try:
            user_id = int(sender["id"]) if isinstance(sender, Mapping) else 0
            chat_id = int(chat["id"]) if isinstance(chat, Mapping) else 0
        except (KeyError, TypeError, ValueError) as exc:
            raise WebhookAuthenticationError("invalid Telegram identity") from exc
        if chat_id != self.chat_id or user_id not in self.approver_user_ids:
            raise WebhookAuthenticationError("unauthorized Telegram actor")
        return user_id, chat_id


@dataclass(frozen=True)
class TwilioWebhookAuth:
    auth_token: str
    public_base_url: str

    @classmethod
    def from_env(cls) -> TwilioWebhookAuth | None:
        token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
        canonical = (
            os.environ.get("APPROVAL_API_PUBLIC_URL")
            or os.environ.get("ARGOS_PUBLIC_URL")
            or ""
        ).strip().rstrip("/")
        configured = bool(
            token
            or os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
            or os.environ.get("TWILIO_FROM_NUMBER", "").strip()
            or os.environ.get("TWILIO_TO_NUMBER", "").strip()
        )
        if not configured:
            return None
        if not token or not canonical:
            raise WebhookConfigurationError(
                "Twilio requires TWILIO_AUTH_TOKEN and APPROVAL_API_PUBLIC_URL"
            )
        environment = os.environ.get("ENVIRONMENT", "production").strip().lower()
        if environment == "production" and not canonical.startswith("https://"):
            raise WebhookConfigurationError(
                "APPROVAL_API_PUBLIC_URL must use HTTPS in production"
            )
        return cls(auth_token=token, public_base_url=canonical)

    def canonical_url(self, request: Request) -> str:
        url = f"{self.public_base_url}{request.url.path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"
        return url

    def authenticate(
        self, request: Request, form: Mapping[str, str], signature: str | None
    ) -> str:
        if not signature or not RequestValidator(self.auth_token).validate(
            self.canonical_url(request), dict(form), signature
        ):
            raise WebhookAuthenticationError("invalid provider signature")
        call_sid = form.get("CallSid", "")
        if not _CALL_SID_RE.fullmatch(call_sid):
            raise WebhookAuthenticationError("invalid CallSid")
        return call_sid
