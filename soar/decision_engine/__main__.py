"""Daemon consumer del SOAR: dren del stream `events:normalized` (blocker Fase 0).

    python -m soar.decision_engine

Arma la composición viva (mismo cableado que `scripts/demo_injector.build_runtime`,
sin el hack de demo) y corre `SOARConsumer.run()` indefinidamente. Este es el proceso
que faltaba: el servicio `soar` del compose solo levanta la Approval API (callbacks de
voto); nadie consumía el stream que el bridge publica. Con esto, la cadena
bridge -> Redis -> SOAR -> tier -> respuesta corre de verdad.

`require_approval` (`ARGOS_REQUIRE_APPROVAL`, default true) llega al consumer Y al
scheduler → un install nuevo es secure-by-default (RF-4).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import redis.asyncio as redis

from argos_contracts.incident import Incident
from soar.approval_api.callback_state import RedisCallbackStateSink
from soar.audit.logger import AuditLogger
from soar.audit.memory import MemorySink
from soar.decision_engine.consumer import SOARConsumer
from soar.decision_engine.containment import apply_decision
from soar.decision_engine.scheduler import WindowScheduler
from soar.decision_engine.triage_hook import TriageClient
from soar.execution.journal import ResponseExecutionJournal
from soar.execution.postgres import execution_journal_from_env
from soar.notifications.base import NotificationChannel
from soar.notifications.service import NotificationService
from soar.playbooks.base import ResponseExecutor
from soar.playbooks.factory import make_executor

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _build_notifier() -> NotificationService:
    """Compone canales completos; una configuracion parcial falla al arrancar."""
    channels: list[NotificationChannel] = []
    state_sink: RedisCallbackStateSink | None = None

    def callback_state() -> RedisCallbackStateSink:
        nonlocal state_sink
        if state_sink is None:
            state_sink = RedisCallbackStateSink(
                os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            )
        return state_sink

    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        from soar.approval_api.jwt_signer import ApprovalSigner
        from soar.approval_api.webhook_auth import (
            TelegramWebhookAuth,
            WebhookConfigurationError,
        )
        from soar.notifications.channels.telegram import TelegramChannel

        signer = ApprovalSigner.from_env()
        telegram_auth = TelegramWebhookAuth.from_env()
        if signer is None or telegram_auth is None:
            raise WebhookConfigurationError(
                "Telegram notifications with approval buttons require authenticated callbacks"
            )
        store = callback_state()
        channels.append(
            TelegramChannel(
                signer=signer,
                token_sink=store.store_telegram_token,
            )
        )
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        from soar.notifications.channels.discord import DiscordChannel

        channels.append(DiscordChannel())
    if os.environ.get("TWILIO_ACCOUNT_SID") or os.environ.get("TWILIO_AUTH_TOKEN"):
        from soar.approval_api.webhook_auth import (
            TwilioWebhookAuth,
            WebhookConfigurationError,
        )
        from soar.notifications.channels.twilio_voice import TwilioVoiceChannel

        twilio_auth = TwilioWebhookAuth.from_env()
        if twilio_auth is None:
            raise WebhookConfigurationError(
                "Twilio voice approvals require authenticated callbacks"
            )
        store = callback_state()
        channels.append(
            TwilioVoiceChannel(
                public_base_url=twilio_auth.public_base_url,
                request_sink=store.store_twilio_request,
            )
        )
    return NotificationService(channels)


def build_consumer(
    r: redis.Redis,
    *,
    executor: ResponseExecutor | None = None,
    journal: ResponseExecutionJournal | None = None,
) -> SOARConsumer:
    """Compone el consumer vivo con todos sus colaboradores reales.

    `require_approval` (ARGOS_REQUIRE_APPROVAL, default ON) se pasa al MISMO valor al
    consumer (gatea `_act`) y al scheduler (gatea el failsafe de timeout)."""
    if executor is None:
        executor = make_executor()
    if journal is None:
        journal = execution_journal_from_env()
        journal.check_ready()
    require_approval = _env_flag("ARGOS_REQUIRE_APPROVAL", True)

    sinks = [MemorySink()]
    dsn = os.environ.get("ARGOS_AUDIT_SQL_DSN")
    if dsn:
        from soar.audit.postgres import PostgresSink

        sinks.append(PostgresSink(dsn))
    audit = AuditLogger(sinks)

    notifier = _build_notifier()

    async def _on_decision(incident: Incident) -> None:
        # Los relojes (scheduler) que fijan final_decision ejecutan la contención; el
        # injector lo hacía a mano, el daemon lo cablea (apply_decision es idempotente).
        await apply_decision(
            r,
            incident.incident_id,
            executor=executor,
            journal=journal,
            audit=audit,
        )

    scheduler = WindowScheduler(
        r,
        notifier=notifier,
        audit=audit,
        on_decision=_on_decision,
        require_approval=require_approval,
    )
    triage = TriageClient(audit=audit)
    return SOARConsumer(
        r,
        executor=executor,
        journal=journal,
        notifier=notifier,
        scheduler=scheduler,
        audit=audit,
        triage=triage,
        require_approval=require_approval,
    )


async def amain(
    r: redis.Redis | None = None,
    *,
    once: bool = False,
    journal: ResponseExecutionJournal | None = None,
) -> None:
    """Loop del daemon. `r`/`once` son seams de test (fakeredis + once=True no cuelga)."""
    executor = make_executor()
    if journal is None:
        journal = execution_journal_from_env()
        journal.check_ready()
    close = False
    if r is None:
        r = redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
        close = True
    consumer = build_consumer(r, executor=executor, journal=journal)
    logger.info("soar-consumer: drenando events:normalized")
    try:
        await consumer.run(once=once)
    finally:
        consumer.close()
        if close:
            await r.aclose()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(amain())
    return 0


if __name__ == "__main__":
    sys.exit(main())
