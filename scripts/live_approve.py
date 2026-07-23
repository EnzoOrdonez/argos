"""Trigger local de aprobación HITL (Fase 1a — sin JWT/ngrok).

Castea un voto REAL sobre un incidente que quedó en `AWAITING_APPROVAL` (lo dejó
`demo_injector.py --live`), replicando exactamente el path de `/telegram/callback`:
record_approval_response -> build_final_decision_if_ready -> ventana de
consolidación -> apply_decision si hay decisión. No toca soar/: reusa sus
handlers. El executor exige `ENVIRONMENT` y `ARGOS_EXECUTOR` explícitos (ADR-0017).

    python scripts/live_approve.py --latest  --decision approve --email telegram:soc-lead
    python scripts/live_approve.py --incident INC-2026-06-26-001 --decision reject

Two-person (host production-critical): el 2º approve fija EXECUTE_ISOLATION y un
solo reject cancela, sin esperar la ventana. La espera de 60s solo aplica al
conservative-wins con un único reject (un approve posterior aún puede voltearlo).
Si el Approval API está corriendo (camino Telegram), él dueña el reloj: usá
`--no-wait` para no programar una segunda ventana.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import redis.asyncio as aioredis
from _runtime import latest_incident_id, make_executor

from argos_contracts.enums import NotificationChannelType
from soar.approval_api.handlers import (
    build_final_decision_if_ready,
    load_incident,
    record_approval_response,
)
from soar.audit.logger import AuditLogger
from soar.audit.memory import MemorySink
from soar.decision_engine.containment import apply_decision
from soar.decision_engine.scheduler import WindowScheduler
from soar.execution.journal import ResponseExecutionJournal
from soar.execution.postgres import execution_journal_from_env


async def cast_vote(
    r: aioredis.Redis,
    incident_id: str,
    *,
    email: str,
    role: str,
    decision: str,
    executor: object,
    journal: ResponseExecutionJournal,
    scheduler: WindowScheduler,
    audit: AuditLogger,
    wait: bool = True,
) -> object:
    """Registra el voto y resuelve como el callback de Telegram. Devuelve el Incident."""
    await record_approval_response(
        r,
        incident_id,
        email=email,
        role=role,
        decision=decision,  # type: ignore[arg-type]
        channel=NotificationChannelType.TELEGRAM,
    )
    audit.emit("approval_response", incident_id, email=email, decision=decision)
    incident = await build_final_decision_if_ready(r, incident_id)
    await scheduler.ensure_consolidation_started(incident_id)

    async def _execute_if_ready(inc: object) -> object:
        decision_obj = getattr(inc, "final_decision", None)
        if decision_obj is not None and decision_obj.execution_status is None:
            audit.emit(
                "decision_final",
                incident_id,
                outcome=decision_obj.outcome,
                policy=decision_obj.policy_applied,
            )
            return await apply_decision(
                r,
                incident_id,
                executor=executor,
                journal=journal,
                audit=audit,
            )
        return inc

    incident = await _execute_if_ready(incident)
    if wait and getattr(incident, "final_decision", None) is None:
        # conservative-wins con un solo reject: la decisión se fija al cerrar la
        # ventana. Esperamos las tasks del reloj (puede que ya hayan cerrado con un
        # sleep instantáneo) y SIEMPRE recargamos para tomar la decisión resultante.
        if scheduler._tasks:
            await asyncio.gather(*list(scheduler._tasks), return_exceptions=True)
        incident = await _execute_if_ready(await load_incident(r, incident_id))
    return incident


async def run(args: argparse.Namespace) -> int:
    executor = make_executor()
    journal = execution_journal_from_env()
    journal.check_ready()
    r = aioredis.from_url(args.redis_url, decode_responses=True)
    try:
        incident_id = args.incident or await latest_incident_id(r)
        if incident_id is None:
            print("No hay incidente. Pasá --incident INC-... o corré demo_injector --live primero.")
            return 2
        try:
            await load_incident(r, incident_id)
        except KeyError:
            print(f"Incidente {incident_id} no existe en Redis.")
            return 2

        audit = AuditLogger([MemorySink()])
        scheduler = WindowScheduler(r, audit=audit)
        print(f"== voto live: {args.email} -> {args.decision} sobre {incident_id}")
        incident = await cast_vote(
            r,
            incident_id,
            email=args.email,
            role=args.role,
            decision=args.decision,
            executor=executor,
            journal=journal,
            scheduler=scheduler,
            audit=audit,
            wait=not args.no_wait,
        )

        print(f"   estado={incident.state.value}")
        if incident.final_decision is not None:
            d = incident.final_decision
            print(f"   decision: {d.outcome} / {d.policy_applied} [exec={d.execution_status}]")
            print(f"   rationale: {d.rationale}")
        else:
            print("   sin decisión final todavía (falta el 2º aprobador o la ventana).")
        history = getattr(executor, "history", None)
        if history is not None:
            print(f"   acciones: {[f'{op}:{aid}:{st}' for op, aid, st in history]}")
        return 0
    finally:
        journal.close()
        await r.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--incident", help="ID del incidente (INC-YYYY-MM-DD-NNN)")
    target.add_argument(
        "--latest", action="store_true", help="usa el último incidente del día"
    )
    parser.add_argument("--decision", required=True, choices=("approve", "reject"))
    parser.add_argument("--email", default="local:operator", help="identidad del aprobador")
    parser.add_argument("--role", default="approver")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="no esperar el cierre de la ventana (cuando el Approval API dueña el reloj)",
    )
    args = parser.parse_args()
    if args.latest:
        args.incident = None
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
