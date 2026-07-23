"""Inyector de alertas demo-safe (dual-track, ADR-0010 / manual P1 §4.3).

Publica secuencias realistas de `NormalizedAlert` en `events:normalized` y
corre el flujo completo de P1 (consumer -> tier -> playbooks simulados ->
notificaciones -> HITL -> audit) sin lab. Ensayo reproducible del plan de
respuesta: NIST SP 800-61r3 (ejercicios y validación del plan) e
ISO/IEC 27035-2 (pruebas del plan de respuesta).

Un comando por UC:

    .venv\\Scripts\\python scripts\\demo_injector.py uc01 --in-process
    .venv\\Scripts\\python scripts\\demo_injector.py uc04 --redis-url redis://localhost:6379/0

- `--in-process` usa fakeredis (cero dependencias externas, smoke en CI).
- Con Redis real, el inyector publica y consume en el mismo proceso con
  `SimulatedExecutor`; el estado queda en Redis para inspección.
- Si hay credenciales en el entorno (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID,
  DISCORD_WEBHOOK_URL), las notificaciones salen de verdad; si no, se omiten.

Modo `--live` (Fase 1, HITL real): inyecta la(s) alerta(s) y NO castea los votos
del escenario; deja el incidente para que un humano apruebe/rechace por
`scripts/live_approve.py` (trigger local) o por Telegram real. El executor pasa a
elegirse por `ENVIRONMENT` + `ARGOS_EXECUTOR`. Sin `--live`, el comportamiento
del demo simulado es idéntico.

Escenarios (capas per matriz ADR-0009 §2.6):
  uc01  ransomware 3 capas casi simultáneas (T1486) en WIN-VICTIM-01 -> T0 auto
  uc02  canary sola (Capa 3) -> T0 auto, cero archivos reales tocados
  uc03  variante novedosa (ML sola T2) -> split-brain 2A/1R/1timeout -> conservative-wins (CENTERPIECE)
  uc04  DB production-critical (L1 pg_mass_read + L2) -> T1 two-person, 2 approve
  uc05  agent-kill (T1562.001): L1 stop-service + L3 canary -> T0 auto
  uc06  DDoS T1498 fast-path -> T0 auto
  uc07  L1+L2 en host crítico, el humano rechaza -> NO_ACTION two-person
  uc08  SQLi web (T1190): L1 firmas + L2 patron -> T1 auto (block IP)

Sale con código 0 si el desenlace coincide con el esperado del UC (o, en --live,
si el incidente quedó creado a la espera de aprobación).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from _runtime import make_executor

from argos_contracts.alert import NormalizedAlert
from argos_contracts.enums import ApproverStatus, Layer, NotificationChannelType, Severity
from argos_contracts.incident import ApproverState
from soar.approval_api.handlers import (
    build_final_decision_if_ready,
    load_incident,
    record_approval_response,
    save_incident,
)
from soar.audit.logger import AuditLogger
from soar.audit.memory import MemorySink
from soar.decision_engine.consumer import STREAM, SOARConsumer
from soar.decision_engine.containment import apply_decision
from soar.decision_engine.scheduler import WindowScheduler
from soar.decision_engine.triage_hook import TriageClient
from soar.execution.journal import (
    MemoryExecutionStore,
    ResponseExecutionJournal,
)
from soar.execution.postgres import execution_journal_from_env
from soar.notifications.base import NotificationChannel
from soar.notifications.service import NotificationService
from soar.playbooks.base import ResponseExecutor
from soar.playbooks.simulated import SimulatedExecutor


def _now() -> datetime:
    return datetime.now(UTC)


def _alert(
    layer: Layer,
    host: str,
    *,
    score: float,
    severity: Severity,
    technique: str | None,
    alert_id: str,
    rule: str | None = None,
) -> NormalizedAlert:
    return NormalizedAlert(
        alert_id=alert_id,
        source_layer=layer,
        timestamp=_now(),
        host_id=host,
        severity_score=score,
        severity_label=severity,
        technique_mitre=technique,
        triggering_rule=rule,
    )


@dataclass
class Scenario:
    description: str
    alerts: list[NormalizedAlert]
    votes: list[tuple[str, str]] = field(default_factory=list)  # (email, decision)
    expected_outcome: str | None = None
    expected_policy: str | None = None
    expected_state: str = "executed"
    # uc03 (split-brain): aprobadores sembrados PENDING que NO votan -> TIMEOUT al cierre.
    pending: list[str] = field(default_factory=list)
    # uc03: resolver por el cierre de la ventana de consolidacion (no per-voto), para
    # exhibir el conflicto (conflict_detected) + el TIMEOUT en la consola.
    use_window: bool = False


def _scenarios() -> dict[str, Scenario]:
    return {
        "uc01": Scenario(
            description="Ransomware LockBit-like, 3 capas casi simultaneas (T1486)",
            alerts=[
                _alert(Layer.LAYER_1, "WIN-VICTIM-01", score=0.92,
                       severity=Severity.CRITICAL, technique="T1486",
                       alert_id="uc01-sigma", rule="win_ransom_mass_rename"),
                _alert(Layer.LAYER_2, "WIN-VICTIM-01", score=0.94,
                       severity=Severity.CRITICAL, technique="T1486",
                       alert_id="uc01-ml", rule="iforest-ocsvm"),
                _alert(Layer.LAYER_3, "WIN-VICTIM-01", score=0.99,
                       severity=Severity.CRITICAL, technique="T1486",
                       alert_id="uc01-canary", rule="canary-fim-whodata"),
            ],
            expected_outcome="EXECUTE_ISOLATION",
            expected_policy="auto-execute",
        ),
        "uc02": Scenario(
            description="Canary sola (Capa 3): deteccion ultra-temprana, zero-FP",
            alerts=[
                _alert(Layer.LAYER_3, "WIN-VICTIM-01", score=0.99,
                       severity=Severity.CRITICAL, technique=None,
                       alert_id="uc02-canary", rule="canary-fim-whodata"),
            ],
            expected_outcome="EXECUTE_ISOLATION",
            expected_policy="auto-execute",
        ),
        "uc03": Scenario(
            description="Variante novedosa (ML sola, T2) -> snapshot irreversible -> two-person",
            alerts=[
                # Capa 2 sola, score 0.74 (= L2_ALONE_T2_MIN_SCORE) -> T2.
                # Tecnica T1083 (whitelisted, NO en AUTO_T0) para no caer en T0 fast-path.
                # El snapshot forense es irreversible: activa two-person incluso en host standard.
                _alert(Layer.LAYER_2, "WIN-WS-07", score=0.74,
                       severity=Severity.HIGH, technique="T1083",
                       alert_id="uc03-ml", rule="iforest-ocsvm-entropy"),
            ],
            # 3 votos reales (2 approve, 1 reject); el 4to (telegram:p4) no vota -> TIMEOUT.
            votes=[
                ("telegram:enzo", "reject"),
                ("telegram:p2", "approve"),
                ("telegram:p3", "approve"),
            ],
            pending=["telegram:p4"],
            use_window=True,
            expected_outcome="NO_ACTION",
            expected_policy="two-person-rule",
            expected_state="rejected",
        ),
        "uc04": Scenario(
            description="Ataque a la DB IntiBank (two-person rule, 2 aprueban)",
            alerts=[
                _alert(Layer.LAYER_1, "LIN-VICTIM-01", score=0.85,
                       severity=Severity.HIGH, technique="T1190",
                       alert_id="uc04-sigma", rule="pg_mass_read"),
                _alert(Layer.LAYER_2, "LIN-VICTIM-01", score=0.90,
                       severity=Severity.HIGH, technique="T1190",
                       alert_id="uc04-ml", rule="query-pattern-outlier"),
            ],
            votes=[("telegram:soc-lead", "approve"), ("telegram:dba", "approve")],
            expected_outcome="EXECUTE_ISOLATION",
            expected_policy="two-person-rule",
        ),
        "uc05": Scenario(
            description="Agent-kill sigiloso (T1562.001): L1 stop-service + L3 canary -> T0 auto",
            alerts=[
                # "1 + 3 + heartbeat" (USE_CASES): L1 Sigma stop-service + L3 canary.
                # La capa 3 (canary) enruta a T0 (zero-FP) -> auto-aislar sin HITL.
                _alert(Layer.LAYER_1, "WIN-VICTIM-01", score=0.88,
                       severity=Severity.HIGH, technique="T1562.001",
                       alert_id="uc05-sigma", rule="stop_service_wazuh_agent"),
                _alert(Layer.LAYER_3, "WIN-VICTIM-01", score=0.99,
                       severity=Severity.CRITICAL, technique=None,
                       alert_id="uc05-canary", rule="canary-fim-whodata"),
            ],
            votes=[("telegram:soc-lead", "approve"), ("telegram:ir", "approve")],
            expected_outcome="EXECUTE_ISOLATION",
            expected_policy="two-person-rule",
        ),
        "uc06": Scenario(
            description="DDoS volumetrico (T1498): fast-path a T0",
            alerts=[
                _alert(Layer.LAYER_1, "EDGE-FW-01", score=0.95,
                       severity=Severity.CRITICAL, technique="T1498",
                       alert_id="uc06-sigma", rule="net_syn_flood_rate"),
            ],
            expected_outcome="EXECUTE_ISOLATION",
            expected_policy="auto-execute",
        ),
        "uc07": Scenario(
            description="SELECT masivo legitimo en la DB: el humano cancela (FP)",
            alerts=[
                _alert(Layer.LAYER_1, "LIN-VICTIM-01", score=0.82,
                       severity=Severity.HIGH, technique="T1078",
                       alert_id="uc07-sigma", rule="pg_mass_read"),
                _alert(Layer.LAYER_2, "LIN-VICTIM-01", score=0.85,
                       severity=Severity.HIGH, technique="T1078",
                       alert_id="uc07-ml", rule="query-pattern-outlier"),
            ],
            votes=[("telegram:compliance", "reject")],
            expected_outcome="NO_ACTION",
            expected_policy="two-person-rule",
            expected_state="rejected",
        ),
        "uc08": Scenario(
            description="SQL injection web (T1190): L1 firmas SQLi + L2 patron -> T1 auto, block IP",
            alerts=[
                # "1 + 2" (USE_CASES): L1 Sigma SQLi + L2 anomalia de patron de request.
                # Corroboracion L1+L2 alta -> T1. Host STANDARD -> auto-execute (sin two-person).
                _alert(Layer.LAYER_1, "WIN-WEB-01", score=0.88,
                       severity=Severity.HIGH, technique="T1190",
                       alert_id="uc08-sigma", rule="sql_injection_signatures"),
                _alert(Layer.LAYER_2, "WIN-WEB-01", score=0.91,
                       severity=Severity.HIGH, technique="T1190",
                       alert_id="uc08-ml", rule="request-pattern-anomaly"),
            ],
            votes=[("telegram:soc-lead", "approve"), ("telegram:web-owner", "approve")],
            expected_outcome="EXECUTE_ISOLATION",
            expected_policy="two-person-rule",
        ),
    }


def _build_notifier() -> NotificationService:
    """Canales reales solo si hay credenciales en el entorno (fail-soft)."""
    channels: list[NotificationChannel] = []
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        from soar.notifications.channels.telegram import TelegramChannel

        channels.append(TelegramChannel())
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        from soar.notifications.channels.discord import DiscordChannel

        channels.append(DiscordChannel())
    return NotificationService(channels)


def build_runtime(
    r: object,
    *,
    live: bool,
    fast_window: bool = False,
    executor: ResponseExecutor | None = None,
    journal: ResponseExecutionJournal | None = None,
):
    """Arma el pipeline P1 (consumer + colaboradores). En --live el executor lo
    elige `ARGOS_EXECUTOR`; en el demo simulado es siempre `SimulatedExecutor`.

    `fast_window`: comprime la ventana de consolidacion a 0s con sleep instantaneo
    (uc03 en --in-process/tests). Con Redis real la ventana la fija el env
    APPROVAL_CONSOLIDATION_WINDOW_SECONDS (ej. 5s para que el countdown se vea)."""
    if executor is None:
        executor = make_executor() if live else SimulatedExecutor()
    if journal is None:
        if live:
            journal = execution_journal_from_env()
            journal.check_ready()
        else:
            journal = ResponseExecutionJournal(MemoryExecutionStore())
    memory = MemorySink()
    sinks = [memory]
    # Sink SQL opcional: si ARGOS_AUDIT_SQL_DSN está, persiste a Postgres argos_audit
    # (para mostrar una fila real en la grabación). Fail-soft: sin DB no-opea.
    dsn = os.environ.get("ARGOS_AUDIT_SQL_DSN")
    if dsn:
        from soar.audit.postgres import PostgresSink

        sinks.append(PostgresSink(dsn))
    audit = AuditLogger(sinks)
    notifier = _build_notifier()
    scheduler = WindowScheduler(r, notifier=notifier, audit=audit)
    if fast_window:
        # Ventana de consolidacion a 0s (asyncio.sleep(0) real). Se setea el atributo
        # directo porque el ctor hace `consolidation_seconds or env` y 0 es falsy
        # (0 or 60 == 60). NO se toca t2_timeout/voice: si se comprimieran, el failsafe
        # T2-sin-respuesta dispararia ANTES de los votos y lockearia timeout-escalation.
        # Quedan en 180s/60s reales y nunca disparan en el smoke (await solo consolidacion).
        scheduler._consolidation_seconds = 0
    triage = TriageClient(audit=audit)  # apunta al stub si esta corriendo
    consumer = SOARConsumer(
        r,
        executor=executor,
        journal=journal,
        notifier=notifier,
        scheduler=scheduler,
        audit=audit,
        triage=triage,
    )
    return consumer, executor, scheduler, audit, memory


async def inject_scenario(r: object, scenario: Scenario, consumer: SOARConsumer) -> str:
    """Publica las alertas, corre el consumer y devuelve el incident_id creado."""
    for alert in scenario.alerts:
        await r.xadd(STREAM, {"payload": alert.model_dump_json()})
        await consumer.run(once=True, block_ms=50)
        await asyncio.sleep(0.3)  # capas "casi simultaneas" dentro de la rafaga de 5s
    today = _now().strftime("%Y-%m-%d")
    sequence = int(await r.get(f"incident:counter:{today}") or 0)
    return f"INC-{today}-{sequence:03d}"


async def drive_window_scenario(
    r: object,
    incident_id: str,
    scenario: Scenario,
    *,
    scheduler,
    executor,
    journal,
    audit,
) -> None:
    """uc03 split-brain: registra los votos SIN resolver per-voto, siembra el aprobador
    PENDING, y resuelve por el CIERRE de la ventana de consolidacion (conservative-wins,
    `finalize_after_window`). Es la unica via que exhibe `conflict_detected` + el TIMEOUT
    en la consola. Usa la logica real de soar; solo cambia el driving (no per-voto)."""
    for email, decision in scenario.votes:
        print(f"   voto HITL: {email} -> {decision}")
        await record_approval_response(
            r, incident_id, email=email, role="approver",
            decision=decision,  # type: ignore[arg-type]
            channel=NotificationChannelType.TELEGRAM,
        )
        audit.emit("approval_response", incident_id, email=email, decision=decision)
    if scenario.pending:
        incident = await load_incident(r, incident_id)
        for email in scenario.pending:
            print(f"   aprobador sin responder (sembrado PENDING): {email}")
            incident.approvers.append(
                ApproverState(
                    email=email, role="approver",
                    status=ApproverStatus.PENDING,
                    channel=NotificationChannelType.TELEGRAM,
                )
            )
        await save_incident(r, incident)
    # Abrir la ventana y AWAIT solo la task de consolidacion (no la t2-timeout/voice que
    # arma el consumer: voice=60s no es env-overridable y colgaria el gather).
    before = set(scheduler._tasks)
    await scheduler.ensure_consolidation_started(incident_id)
    new_tasks = [t for t in scheduler._tasks if t not in before]
    await asyncio.gather(*new_tasks, return_exceptions=True)
    incident = await load_incident(r, incident_id)
    if (
        incident.final_decision is not None
        and incident.final_decision.execution_status is None
    ):
        audit.emit(
            "decision_final", incident_id,
            outcome=incident.final_decision.outcome,
            policy=incident.final_decision.policy_applied,
        )
        await apply_decision(
            r,
            incident_id,
            executor=executor,
            journal=journal,
            audit=audit,
        )


async def run_scenario(uc: str, redis_url: str, in_process: bool, live: bool = False) -> int:
    scenario = _scenarios()[uc]
    executor_override = None
    journal_override = None
    if live:
        executor_override = make_executor()
        journal_override = execution_journal_from_env()
        journal_override.check_ready()
    if in_process:
        from fakeredis import FakeAsyncRedis

        r = FakeAsyncRedis(decode_responses=True)
    else:
        import redis.asyncio as redis

        r = redis.from_url(redis_url, decode_responses=True)

    consumer, executor, scheduler, audit, memory = build_runtime(
        r,
        live=live,
        fast_window=scenario.use_window and in_process,
        executor=executor_override,
        journal=journal_override,
    )

    print(f"== {uc.upper()}: {scenario.description}{' [LIVE]' if live else ''}")
    incident_id = await inject_scenario(r, scenario, consumer)

    if not live and scenario.use_window:
        await drive_window_scenario(
            r,
            incident_id,
            scenario,
            scheduler=scheduler,
            executor=executor,
            journal=consumer._journal,
            audit=audit,
        )
    elif not live:
        for email, decision in scenario.votes:
            print(f"   voto HITL: {email} -> {decision}")
            await record_approval_response(
                r,
                incident_id,
                email=email,
                role="approver",
                decision=decision,  # type: ignore[arg-type]
                channel=NotificationChannelType.TELEGRAM,
            )
            audit.emit("approval_response", incident_id, email=email, decision=decision)
            incident = await build_final_decision_if_ready(r, incident_id)
            await scheduler.ensure_consolidation_started(incident_id)
            if (
                incident.final_decision is not None
                and incident.final_decision.execution_status is None
            ):
                audit.emit(
                    "decision_final",
                    incident_id,
                    outcome=incident.final_decision.outcome,
                    policy=incident.final_decision.policy_applied,
                )
                await apply_decision(
                    r,
                    incident_id,
                    executor=executor,
                    journal=consumer._journal,
                    audit=audit,
                )

    incident = await load_incident(r, incident_id)
    for task in list(scheduler._tasks):  # relojes pendientes: el proceso termina
        task.cancel()

    print(f"   incidente: {incident.incident_id}  tier={incident.tier.value}  "
          f"estado={incident.state.value}  host={incident.host.id} "
          f"({incident.host.criticality.value})")
    if incident.final_decision:
        d = incident.final_decision
        print(f"   decision: {d.outcome} / {d.policy_applied} "
              f"[exec={d.execution_status}]  rationale: {d.rationale}")
    history = getattr(executor, "history", [])
    print(f"   acciones simuladas: {[f'{op}:{aid}:{st}' for op, aid, st in history]}")
    backend = (
        f"poblado ({incident.llm_analysis.llm_backend})" if incident.llm_analysis else "None"
    )
    print(f"   llm_analysis: {backend}")
    print("   audit:")
    for event in memory.events:
        print(f"     - {event.ts.strftime('%H:%M:%S')} {event.kind:22s} {event.payload}")

    if live:
        if incident.final_decision is None:
            print("   >> MODO LIVE: el incidente espera aprobación humana.")
            print(f"      aprobar:  python scripts/live_approve.py --incident {incident_id} "
                  f"--decision approve --email telegram:tu-id")
            print(f"      rechazar: python scripts/live_approve.py --incident {incident_id} "
                  f"--decision reject --email telegram:tu-id")
            print("      (o por Telegram real con el Approval API + ngrok)")
        else:
            print(f"   >> MODO LIVE: el incidente se auto-resolvió "
                  f"({incident.final_decision.outcome}); sin HITL (T0/T1 auto).")
        if not in_process:
            await r.aclose()
        audit.close()
        return 0

    ok = incident.state.value == scenario.expected_state
    if scenario.expected_outcome:
        ok = ok and incident.final_decision is not None
        if incident.final_decision:
            ok = ok and incident.final_decision.outcome == scenario.expected_outcome
            ok = ok and incident.final_decision.policy_applied == scenario.expected_policy
    print(f"== desenlace {'ESPERADO' if ok else 'INESPERADO'} para {uc.upper()}")
    if not in_process:
        await r.aclose()
    audit.close()
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("uc", choices=sorted(_scenarios()))
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="usa fakeredis: smoke sin Redis instalado",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="HITL real: no castea los votos, deja el incidente para aprobación humana",
    )
    args = parser.parse_args()
    return asyncio.run(run_scenario(args.uc, args.redis_url, args.in_process, args.live))


if __name__ == "__main__":
    sys.exit(main())
