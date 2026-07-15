"""Sink SQL del audit: Postgres `argos_audit` (ADR-0013 §2.8, schema en schema.sql).

Mapea el stream de `AuditEvent` (granular, por hecho) a las dos tablas
incident-céntricas del schema: `audit_incidents` (upsert por incidente) y
`audit_responses` (una fila por voto). Sync (la interfaz `AuditSink.emit` lo es) y
**fail-soft**: cualquier error de DB se loguea y se traga — la contención NUNCA se
pierde por un fallo de auditoría (igual que `OpenSearchSink`).

Conexión: DSN explícito (`dsn=`) o `psycopg.connect` lazy. Para el injector corriendo
en el host contra el Postgres del compose: `postgresql://argos:<pw>@localhost:5432/argos_audit`.
Los CHECK del schema usan los valores reales del contrato; los payloads de los eventos
ya traen esos valores (tier 'T0'.., criticality 'standard'/'production_critical', etc.).
"""

from __future__ import annotations

import logging
from typing import Any

from soar.audit.base import AuditEvent

logger = logging.getLogger(__name__)

_S = "argos_audit"  # schema

_FINAL_STATE = {
    "EXECUTE_ISOLATION": "executed",
    "NO_ACTION": "rejected",
    "REVERTED": "reverted",
}
_VOTE_STATUS = {"approve": "approved", "reject": "rejected"}


class PostgresSink:
    """Persiste eventos de audit en Postgres. Fail-soft; nunca lanza desde emit()."""

    def __init__(self, dsn: str | None = None, *, conn: Any | None = None) -> None:
        self._conn = conn
        if self._conn is None and dsn is not None:
            try:
                import psycopg

                self._conn = psycopg.connect(dsn, autocommit=True)
            except Exception as exc:
                logger.warning("audit sink postgres no conectó (%s); deshabilitado", exc)
                self._conn = None

    def emit(self, event: AuditEvent) -> None:
        if self._conn is None:
            return
        try:
            handler = getattr(self, f"_on_{event.kind}", None)
            if handler is not None:
                handler(event)
        except Exception as exc:
            logger.warning(
                "audit sink postgres falló para %s/%s: %s",
                event.incident_id, event.kind, exc,
            )

    # -- handlers por kind (sin handler = evento ignorado) --------------------

    def _on_incident_created(self, e: AuditEvent) -> None:
        p = e.payload
        self._conn.execute(
            f"""INSERT INTO {_S}.audit_incidents
                (incident_id, created_at, updated_at, tier, state, host_id,
                 criticality, technique_mitre)
                VALUES (%(id)s, %(ts)s, %(ts)s, %(tier)s, 'received', %(host)s,
                        %(crit)s, %(tech)s)
                ON CONFLICT (incident_id) DO NOTHING""",
            {"id": e.incident_id, "ts": e.ts, "tier": p.get("tier"),
             "host": p.get("host"), "crit": p.get("criticality"), "tech": p.get("technique")},
        )

    def _on_tier_escalated(self, e: AuditEvent) -> None:
        self._conn.execute(
            f"UPDATE {_S}.audit_incidents SET tier=%(tier)s, updated_at=%(ts)s "
            f"WHERE incident_id=%(id)s",
            {"id": e.incident_id, "ts": e.ts, "tier": e.payload.get("to_tier")},
        )

    def _on_decision_final(self, e: AuditEvent) -> None:
        p = e.payload
        outcome = p.get("outcome")
        self._conn.execute(
            f"""UPDATE {_S}.audit_incidents SET
                  final_outcome=%(out)s, final_policy=%(pol)s, rationale=%(rat)s,
                  state=COALESCE(%(state)s, state), executed_at=%(ts)s, updated_at=%(ts)s
                WHERE incident_id=%(id)s""",
            {"id": e.incident_id, "ts": e.ts, "out": outcome, "pol": p.get("policy"),
             "rat": p.get("rationale"), "state": _FINAL_STATE.get(outcome)},
        )

    def _on_action_executed(self, e: AuditEvent) -> None:
        self._conn.execute(
            f"UPDATE {_S}.audit_incidents SET execution_status=%(st)s, updated_at=%(ts)s "
            f"WHERE incident_id=%(id)s",
            {"id": e.incident_id, "ts": e.ts, "st": e.payload.get("status")},
        )

    # action_failed/reverted comparten el mismo update de execution_status
    _on_action_failed = _on_action_executed
    _on_action_reverted = _on_action_executed

    def _on_approval_response(self, e: AuditEvent) -> None:
        decision = e.payload.get("decision")
        self._conn.execute(
            f"""INSERT INTO {_S}.audit_responses
                (incident_id, approver_email, approver_role, status, channel, responded_at)
                VALUES (%(id)s, %(email)s, 'approver', %(status)s, 'telegram', %(ts)s)""",
            {"id": e.incident_id, "ts": e.ts, "email": e.payload.get("email"),
             "status": _VOTE_STATUS.get(decision, "pending")},
        )
