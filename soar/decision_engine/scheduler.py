"""Los tres relojes del HITL, con asyncio puro (ADR-0013 §2.6 + review §7.6).

Reloj A: ventana de consolidación de 60s (ADR-0006), arranca con el PRIMER
voto. Puebla `Incident.consolidation_window` y al cierre delega en
`close_window` (Fase 2, idempotente), que aplica conservative-wins o deja
esperando al two-person (Situación B).

Reloj B: timeout de 3 minutos del T2 (ADR-0003), arranca al notificar.
Al expirar: si hay decisión o hay votos, no hace nada (la ventana manda).
Con cero votos: host estándar cierra con el failsafe (EXECUTE_ISOLATION /
timeout-escalation: el atacante no gana por silencio); host
production-critical sigue esperando con el throttle activo (ADR-0006 Sit.B,
caso "3 AM": el four-eyes no se anula por un timeout administrativo,
NIST SP 800-53 rev. 5 AC-3(2) Dual Authorization).

Reloj C: escalación Twilio Voice a t=60s sin respuesta (ADR-0007 v2).

Mecanismo: asyncio.create_task + sleep inyectable, mismo patrón que
`consolidation_task` de Fase 2. Tests deterministas sin sleeps reales.
`close_window` es idempotente, así que la doble programación (A y B sobre el
mismo incidente) es segura.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import redis.asyncio as redis

from argos_contracts.enums import ApproverStatus, Criticality
from argos_contracts.incident import ConsolidationWindow, Incident
from soar.approval_api.consolidation import close_window
from soar.approval_api.handlers import load_incident, save_incident
from soar.audit.logger import AuditLogger
from soar.notifications.service import NotificationService

logger = logging.getLogger(__name__)

SleepFn = Callable[[float], Awaitable[None]]
DecisionCallback = Callable[[Incident], Awaitable[None]]

VOICE_ESCALATION_SECONDS = 60  # ADR-0007 v2: Twilio a t=60s sin respuesta.


def _responded(incident: Incident) -> bool:
    return any(
        a.status in (ApproverStatus.APPROVED, ApproverStatus.REJECTED)
        for a in incident.approvers
    )


class WindowScheduler:
    """Agenda los relojes de un incidente en espera humana.

    `on_decision` (opcional): corrutina que el orquestador inyecta para
    ejecutar la contención cuando un reloj fija `final_decision`
    (ADR-0013 §2.7). `sleep` se inyecta en tests para no dormir de verdad.
    """

    def __init__(
        self,
        r: redis.Redis,
        *,
        notifier: NotificationService | None = None,
        audit: AuditLogger | None = None,
        on_decision: DecisionCallback | None = None,
        sleep: SleepFn = asyncio.sleep,
        consolidation_seconds: int | None = None,
        t2_timeout_seconds: int | None = None,
        voice_escalation_seconds: int = VOICE_ESCALATION_SECONDS,
        require_approval: bool = False,
    ) -> None:
        self._r = r
        self._notifier = notifier
        self._audit = audit
        self._on_decision = on_decision
        self._sleep = sleep
        # RF-4: con el rail explícito ON, el failsafe de timeout NO auto-aísla a un
        # host estándar sin votos (segundo camino de auto-ejecución sin humano);
        # sigue esperando como un production-critical. Default False = histórico.
        self._require_approval = require_approval
        self._consolidation_seconds = consolidation_seconds or int(
            os.environ.get("APPROVAL_CONSOLIDATION_WINDOW_SECONDS", "60")
        )
        self._t2_timeout_seconds = t2_timeout_seconds or int(
            os.environ.get("APPROVAL_T2_TIMEOUT_SECONDS", "180")
        )
        self._voice_seconds = voice_escalation_seconds
        # Referencias vivas para que el GC no cancele tasks en vuelo.
        self._tasks: set[asyncio.Task[None]] = set()

    def _spawn(self, coro: Awaitable[None]) -> asyncio.Task[None]:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _emit(self, kind: str, incident_id: str, **payload: object) -> None:
        if self._audit is not None:
            self._audit.emit(kind, incident_id, **payload)

    async def _notify_decision(self, incident: Incident) -> None:
        if incident.final_decision is None:
            return
        self._emit(
            "decision_final",
            incident.incident_id,
            outcome=incident.final_decision.outcome,
            policy=incident.final_decision.policy_applied,
            rationale=incident.final_decision.rationale,
        )
        if self._on_decision is not None:
            await self._on_decision(incident)

    # -- Reloj A: ventana de consolidacion (desde el primer voto) ----------

    async def ensure_consolidation_started(self, incident_id: str) -> bool:
        """La llama el Approval API tras registrar un voto. Idempotente:
        solo el primer voto puebla `consolidation_window` y agenda el cierre."""
        incident = await load_incident(self._r, incident_id)
        if incident.final_decision is not None:
            return False
        if incident.consolidation_window is not None:
            return False
        if not _responded(incident):
            return False
        incident.consolidation_window = ConsolidationWindow(
            started_at=datetime.now(UTC),
            duration_seconds=self._consolidation_seconds,
        )
        incident.updated_at = datetime.now(UTC)
        await save_incident(self._r, incident)
        self._spawn(self._consolidation(incident_id))
        return True

    async def _consolidation(self, incident_id: str) -> None:
        await self._sleep(self._consolidation_seconds)
        incident = await close_window(self._r, incident_id)
        approved = sum(
            a.status == ApproverStatus.APPROVED for a in incident.approvers
        )
        rejected = sum(
            a.status == ApproverStatus.REJECTED for a in incident.approvers
        )
        if incident.consolidation_window is not None:
            incident.consolidation_window.ended_at = datetime.now(UTC)
            incident.consolidation_window.conflict_detected = (
                approved >= 1 and rejected >= 1
            )
            await save_incident(self._r, incident)
        if incident.final_decision is None:
            # Two-person sin quorum: sigue esperando (ADR-0006 Sit.B).
            self._emit("timeout_wait", incident_id, reason="consolidation-two-person")
            return
        await self._notify_decision(incident)

    # -- Reloj B: timeout T2 de 180s (desde la notificacion) ---------------

    def start_t2_timeout(self, incident_id: str) -> asyncio.Task[None]:
        return self._spawn(self._t2_timeout(incident_id))

    async def _t2_timeout(self, incident_id: str) -> None:
        await self._sleep(self._t2_timeout_seconds)
        try:
            incident = await load_incident(self._r, incident_id)
        except KeyError:
            return
        if incident.final_decision is not None:
            return  # Ya decidido: el timer no hace nada.
        if _responded(incident):
            return  # Hay votos: la ventana de consolidacion manda.
        if incident.host.criticality == Criticality.PRODUCTION_CRITICAL or self._require_approval:
            # ADR-0006 Sit.B (production-critical) o RF-4 (rail explícito ON): sin
            # auto-execute por timeout; throttle activo, sigue esperando al humano.
            reason = (
                "rail require_approval: espera aprobacion humana, throttle activo"
                if self._require_approval
                and incident.host.criticality != Criticality.PRODUCTION_CRITICAL
                else "production-critical espera 2do aprobador, throttle activo"
            )
            self._emit("timeout_wait", incident_id, reason=reason)
            return
        incident = await close_window(self._r, incident_id)
        await self._notify_decision(incident)

    # -- Reloj C: escalacion por voz a t=60s sin respuesta ------------------

    def start_voice_escalation(self, incident_id: str) -> asyncio.Task[None]:
        return self._spawn(self._voice_escalation(incident_id))

    async def _voice_escalation(self, incident_id: str) -> None:
        await self._sleep(self._voice_seconds)
        try:
            incident = await load_incident(self._r, incident_id)
        except KeyError:
            return
        if incident.final_decision is not None or _responded(incident):
            return
        if self._notifier is None:
            return
        result = self._notifier.escalate_to_voice(incident)
        self._emit(
            "voice_escalated",
            incident_id,
            success=result.success,
            error=result.error,
        )
