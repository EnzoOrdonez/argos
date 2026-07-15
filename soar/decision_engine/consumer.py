"""Consumer del stream `events:normalized`: correlación y orquestación (ADR-0013).

Pipeline (§2.1, con las correcciones del review §7):

1. Cada entry trae un campo `payload` = `NormalizedAlert.model_dump_json()`
   de una capa (`source_layer` en layer_1|layer_2|layer_3; la capa LLM no
   emite alertas, §7.1/§7.2).
2. Correlación por `host_id` con dos índices (§7.3): `corr:{host}` con TTL
   deslizante de 5s (agrupa la ráfaga) y `corr:open:{host}` que apunta al
   incidente sin `final_decision` (alerta tardía enriquece y re-rutea; tras
   la decisión solo se anexa al audit).
3. `route(RoutingSignal)` decide el tier; la fusión L1+L2 usa noisy-OR de los
   mejores scores por capa (§7.10).
4. T0/T1 en host estándar: auto-execute (isolation + kill) y notificación
   post-facto. T2 o production-critical: throttle + snapshot inmediatos
   pre-aprobación (ADR-0012), hook LLM no bloqueante, notificación con
   botones y relojes (timeout 180s + voz 60s). T3: solo notificación.
5. XACK solo si el procesamiento no lanzó; un entry que falla se reintenta y
   a la tercera entrega se descarta con audit `poison_discarded` (§7.7).

Procesamiento con consumer group `soar-router` (documentación de Redis
Streams, sección Consumer Groups: entrega at-least-once con ACK explícito).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

import redis.asyncio as redis
from redis.exceptions import ResponseError

from argos_contracts.alert import NormalizedAlert
from argos_contracts.enums import ActionType, IncidentState, Layer, Tier
from argos_contracts.incident import FinalDecision, Incident
from soar.approval_api.handlers import (
    load_incident,
    requires_two_person,
    save_incident,
)
from soar.audit.logger import AuditLogger
from soar.decision_engine.containment import apply_decision
from soar.decision_engine.policies import AUTO_T0_TECHNIQUES
from soar.decision_engine.scheduler import WindowScheduler
from soar.decision_engine.tier_router import RoutingSignal, route
from soar.decision_engine.triage_hook import TriageClient
from soar.notifications.service import NotificationService
from soar.playbooks.base import ResponseExecutor
from soar.playbooks.builders import build_snapshot, build_throttle

logger = logging.getLogger(__name__)

STREAM = "events:normalized"
GROUP = "soar-router"

CORRELATION_TTL_SECONDS = 5  # rafaga (TTL deslizante, §7.3)
OPEN_TTL_SECONDS = 600  # seguridad del puntero al incidente abierto
COUNTER_TTL_SECONDS = 48 * 3600  # contador diario (§7.8)
MAX_DELIVERIES = 3  # poison guard (§7.7)

# Orden de severidad de tiers: menor indice = mas critico. La correlacion
# solo escala (mas evidencia nunca baja el tier en vuelo).
_TIER_RANK: dict[Tier, int] = {Tier.T0: 0, Tier.T1: 1, Tier.T2: 2, Tier.T3: 3}


def _noisy_or(scores: list[float]) -> float:
    fused = 1.0
    for score in scores:
        fused *= 1.0 - score
    return 1.0 - fused


def build_signal(alerts: list[NormalizedAlert], host_id: str) -> RoutingSignal:
    """Funde las alertas correlacionadas de un host en un RoutingSignal."""
    layers = frozenset(a.source_layer for a in alerts)
    l1_alerts = [a for a in alerts if a.source_layer == Layer.LAYER_1]
    l2_alerts = [a for a in alerts if a.source_layer == Layer.LAYER_2]

    l1_best = max(l1_alerts, key=lambda a: a.severity_score, default=None)
    l2_best = max(l2_alerts, key=lambda a: a.severity_score, default=None)

    corroboration = None
    if l1_best is not None and l2_best is not None:
        corroboration = _noisy_or([l1_best.severity_score, l2_best.severity_score])

    # Fast-path: la primera tecnica AUTO_T0 manda; si no, la del representativo.
    technique = next(
        (a.technique_mitre for a in alerts if a.technique_mitre in AUTO_T0_TECHNIQUES),
        None,
    )
    if technique is None:
        representative = max(alerts, key=lambda a: a.severity_score)
        technique = representative.technique_mitre

    return RoutingSignal(
        fired_layers=layers,
        technique_mitre=technique,
        l1_severity=l1_best.severity_label if l1_best else None,
        l2_score=l2_best.severity_score if l2_best else None,
        corroboration_confidence=corroboration,
        host_id=host_id,
        contributing_alert_ids=tuple(a.alert_id for a in alerts),
    )


class SOARConsumer:
    """Orquestador de Fase 3: consume, correlaciona, decide y actúa."""

    def __init__(
        self,
        r: redis.Redis,
        *,
        executor: ResponseExecutor,
        notifier: NotificationService | None = None,
        scheduler: WindowScheduler | None = None,
        audit: AuditLogger | None = None,
        triage: TriageClient | None = None,
        consumer_name: str = "soar-1",
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._r = r
        self._executor = executor
        self._notifier = notifier
        self._scheduler = scheduler
        self._audit = audit
        self._triage = triage
        self._name = consumer_name
        self._now = now_fn or (lambda: datetime.now(UTC))

    # -- plumbing ----------------------------------------------------------

    def _emit(self, kind: str, incident_id: str, **payload: object) -> None:
        if self._audit is not None:
            self._audit.emit(kind, incident_id, **payload)

    def _dispatch(self, incident: Incident) -> None:
        if self._notifier is not None:
            self._notifier.dispatch_for_tier(incident)

    async def ensure_group(self) -> None:
        try:
            await self._r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def run(self, *, block_ms: int = 1000, once: bool = False) -> None:
        """Loop principal. `once=True` procesa lo disponible y retorna (tests/demo)."""
        # Valida el inventario de criticidad al arrancar (fail-loud si ARGOS_HOST_INVENTORY
        # apunta a un archivo malformado), no a mitad del primer incidente.
        from soar.inventory import load_effective_inventory

        load_effective_inventory()
        await self.ensure_group()
        while True:
            response = await self._r.xreadgroup(
                GROUP, self._name, {STREAM: ">"}, count=16, block=block_ms
            )
            for _stream, entries in response or []:
                for entry_id, fields in entries:
                    await self._handle_entry(entry_id, fields)
            if once:
                return

    async def _handle_entry(self, entry_id: str, fields: dict[str, str]) -> None:
        """ACK solo si el procesamiento no lanzo (ADR-0013 §2.1). Un entry
        defectuoso queda pendiente y se reintenta; a la N-esima entrega se
        descarta con audit para no ciclar infinito (§7.7)."""
        try:
            await self.process_entry(fields)
        except Exception:
            logger.exception("entry %s fallo; queda sin ACK", entry_id)
            attempts = await self._r.incr(f"poison:{entry_id}")
            await self._r.expire(f"poison:{entry_id}", 3600)
            if int(attempts) >= MAX_DELIVERIES:
                self._emit(
                    "poison_discarded",
                    "unparsed",
                    entry_id=str(entry_id),
                    attempts=int(attempts),
                )
                await self._r.xack(STREAM, GROUP, entry_id)
            return
        await self._r.xack(STREAM, GROUP, entry_id)

    async def process_entry(self, fields: dict[str, str]) -> Incident:
        alert = NormalizedAlert.model_validate_json(fields["payload"])
        return await self.handle_alert(alert)

    # -- correlacion (§2.2 + §7.3) ------------------------------------------

    async def handle_alert(self, alert: NormalizedAlert) -> Incident:
        host_id = alert.host_id
        incident_id = await self._r.get(f"corr:{host_id}")
        if incident_id is None:
            incident_id = await self._r.get(f"corr:open:{host_id}")
        if incident_id is not None:
            try:
                incident = await load_incident(self._r, incident_id)
            except KeyError:
                incident = None
            if incident is not None:
                return await self._enrich(incident, alert)
        return await self._create(alert)

    async def _alerts_for(self, incident_id: str) -> list[NormalizedAlert]:
        raw_items = await self._r.lrange(f"corr:alerts:{incident_id}", 0, -1)
        return [NormalizedAlert.model_validate_json(raw) for raw in raw_items]

    async def _remember_alert(self, incident_id: str, alert: NormalizedAlert) -> None:
        key = f"corr:alerts:{incident_id}"
        await self._r.rpush(key, alert.model_dump_json())
        await self._r.expire(key, OPEN_TTL_SECONDS)

    async def _next_incident_id(self) -> str:
        today = self._now().strftime("%Y-%m-%d")
        key = f"incident:counter:{today}"
        sequence = int(await self._r.incr(key))
        await self._r.expire(key, COUNTER_TTL_SECONDS)
        return f"INC-{today}-{sequence:03d}"

    async def _create(self, alert: NormalizedAlert) -> Incident:
        from soar.inventory import resolve_host

        host = resolve_host(alert.host_id, ip=alert.host_ip)
        incident_id = await self._next_incident_id()
        await self._remember_alert(incident_id, alert)
        signal = build_signal([alert], host.id)
        tier = route(signal)
        now = self._now()
        incident = Incident(
            incident_id=incident_id,
            created_at=now,
            updated_at=now,
            tier=tier,
            state=IncidentState.RECEIVED,
            host=host,
            alert=alert,
            proposed_actions=[],
        )
        await save_incident(self._r, incident)
        await self._r.set(f"corr:{host.id}", incident_id, ex=CORRELATION_TTL_SECONDS)
        await self._r.set(f"corr:open:{host.id}", incident_id, ex=OPEN_TTL_SECONDS)
        self._emit(
            "incident_created",
            incident_id,
            tier=tier.value,
            host=host.id,
            criticality=host.criticality.value,
            technique=signal.technique_mitre,
            layers=sorted(layer.value for layer in signal.fired_layers),
        )
        return await self._act(incident, signal)

    async def _enrich(self, incident: Incident, alert: NormalizedAlert) -> Incident:
        await self._remember_alert(incident.incident_id, alert)
        # TTL deslizante de la rafaga (§7.3).
        await self._r.set(
            f"corr:{alert.host_id}", incident.incident_id, ex=CORRELATION_TTL_SECONDS
        )
        self._emit(
            "alert_correlated",
            incident.incident_id,
            alert_id=alert.alert_id,
            layer=alert.source_layer.value,
        )
        if incident.final_decision is not None:
            # Decidido: la alerta queda en audit y en corr:alerts, sin re-ejecutar.
            return incident

        alerts = await self._alerts_for(incident.incident_id)
        signal = build_signal(alerts, incident.host.id)
        new_tier = route(signal)
        representative = max(alerts, key=lambda a: a.severity_score)
        incident.alert = representative
        incident.updated_at = self._now()

        if _TIER_RANK[new_tier] < _TIER_RANK[incident.tier]:
            old_tier = incident.tier
            incident.tier = new_tier
            await save_incident(self._r, incident)
            self._emit(
                "tier_escalated",
                incident.incident_id,
                from_tier=old_tier.value,
                to_tier=new_tier.value,
                layers=sorted(layer.value for layer in signal.fired_layers),
            )
            # Re-ruteo con re-notificacion (§2.2): el flujo del tier nuevo manda.
            return await self._act(incident, signal, escalation=True)

        await save_incident(self._r, incident)
        return incident

    # -- accion por tier (§2.4-§2.7) ----------------------------------------

    def _waits_human(self, incident: Incident) -> bool:
        return incident.tier == Tier.T2 or requires_two_person(incident)

    async def _act(
        self, incident: Incident, signal: RoutingSignal, *, escalation: bool = False
    ) -> Incident:
        if self._waits_human(incident):
            return await self._act_waiting(incident, signal, escalation=escalation)
        if incident.tier in (Tier.T0, Tier.T1):
            return await self._act_auto(incident)
        # T3: solo notificacion informativa (ADR-0003).
        await save_incident(self._r, incident)
        self._dispatch(incident)
        return incident

    async def _act_auto(self, incident: Incident) -> Incident:
        """T0/T1 en host estandar: auto-execute + notificacion post-facto."""
        incident.final_decision = FinalDecision(
            outcome="EXECUTE_ISOLATION",
            policy_applied="auto-execute",
            rationale=f"auto-execute: tier {incident.tier.value} (ADR-0003)",
        )
        incident.state = IncidentState.PENDING_EXECUTION
        incident.updated_at = self._now()
        await save_incident(self._r, incident)
        await self._r.delete(f"corr:open:{incident.host.id}")
        self._emit(
            "decision_final",
            incident.incident_id,
            outcome="EXECUTE_ISOLATION",
            policy="auto-execute",
            rationale=incident.final_decision.rationale,
        )
        incident = await apply_decision(
            self._r, incident.incident_id, executor=self._executor, audit=self._audit
        )
        self._dispatch(incident)
        return incident

    async def _act_waiting(
        self, incident: Incident, signal: RoutingSignal, *, escalation: bool
    ) -> Incident:
        """T2 o production-critical: protege, enriquece, notifica y agenda."""
        first_wait = incident.state != IncidentState.AWAITING_APPROVAL

        # Throttle + snapshot inmediatos, PRE-aprobacion (ADR-0012 §2.2).
        has_throttle = any(
            action.type == ActionType.PROCESS_THROTTLE
            for action in incident.proposed_actions
        )
        if not has_throttle:
            pid = None
            if incident.alert.process_info:
                raw_pid = incident.alert.process_info.get("pid")
                pid = int(raw_pid) if isinstance(raw_pid, (int, str)) else None
            throttle = build_throttle(
                incident.host.id,
                action_id=f"act-{len(incident.proposed_actions) + 1:03d}",
                pid=pid,
            )
            incident.proposed_actions.append(throttle)
            snapshot = build_snapshot(
                incident.host.id,
                action_id=f"act-{len(incident.proposed_actions) + 1:03d}",
            )
            incident.proposed_actions.append(snapshot)
            for action in (throttle, snapshot):
                result = self._executor.run(action)
                kind = "action_failed" if result.status == "failed" else "action_executed"
                self._emit(
                    kind,
                    incident.incident_id,
                    action_id=action.id,
                    action_type=action.type.value,
                    status=result.status,
                )

        incident.state = IncidentState.AWAITING_APPROVAL
        incident.updated_at = self._now()
        await save_incident(self._r, incident)

        # Hook LLM no bloqueante (§2.5 + §7.5): el fallo deja None y se sigue.
        # El audit llm_triage_ok/failed lo emite el propio TriageClient.
        if self._triage is not None and incident.llm_analysis is None:
            incident.llm_analysis = await self._triage.fetch(
                incident, signal.fired_layers
            )
            await save_incident(self._r, incident)

        self._dispatch(incident)

        if self._scheduler is not None and first_wait:
            self._scheduler.start_t2_timeout(incident.incident_id)
            self._scheduler.start_voice_escalation(incident.incident_id)
        return incident
