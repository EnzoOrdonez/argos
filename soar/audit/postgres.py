"""Sink SQL del audit: Postgres `argos_audit` (ADR-0013 §2.8, schema en schema.sql).

Mapea el stream de `AuditEvent` (granular, por hecho) a las dos tablas
incident-céntricas del schema: `audit_incidents` (upsert por incidente) y
`audit_responses` (una fila por voto). Sync (la interfaz `AuditSink.emit` lo es) y
**fail-soft**: cualquier error de DB se registra sin exponer el detalle del driver y
no bloquea la contención. La pérdida del evento queda explícita en logs.

Conexión: constructor no bloqueante, conexión lazy con timeout acotado y cierre
explícito. DSN explícito (`dsn=`) o `psycopg.connect`. Para el injector corriendo
en el host contra el Postgres del compose: `postgresql://argos:<pw>@localhost:5432/argos_audit`.
Los CHECK del schema usan los valores reales del contrato; los payloads de los eventos
ya traen esos valores (tier 'T0'.., criticality 'standard'/'production_critical', etc.).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
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
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
CONNECT_TIMEOUT_ENV = "ARGOS_AUDIT_SQL_CONNECT_TIMEOUT_SECONDS"


def _configured_connect_timeout_seconds() -> int:
    raw = os.environ.get(CONNECT_TIMEOUT_ENV)
    if raw is None:
        return DEFAULT_CONNECT_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{CONNECT_TIMEOUT_ENV} must be an integer between 1 and 60") from exc
    if not 1 <= value <= 60:
        raise ValueError(f"{CONNECT_TIMEOUT_ENV} must be an integer between 1 and 60")
    return value


class PostgresSink:
    """Persiste eventos de audit en Postgres. Fail-soft; nunca lanza desde emit()."""

    def __init__(
        self,
        dsn: str | None = None,
        *,
        conn: Any | None = None,
        connection_factory: Callable[..., Any] | None = None,
        connect_timeout_seconds: int | None = None,
    ) -> None:
        if connect_timeout_seconds is None:
            connect_timeout_seconds = _configured_connect_timeout_seconds()
        if not 1 <= connect_timeout_seconds <= 60:
            raise ValueError("connect_timeout_seconds must be between 1 and 60")
        self._dsn = dsn
        self._conn = conn
        self._connection_factory = connection_factory
        self._connect_timeout_seconds = connect_timeout_seconds

    def connect(self) -> bool:
        """Open the configured connection once; return False on a bounded failure."""
        if self._conn is not None:
            return True
        if self._dsn is None:
            return False
        try:
            factory = self._connection_factory
            if factory is None:
                import psycopg

                factory = psycopg.connect
            self._conn = factory(
                self._dsn,
                autocommit=True,
                connect_timeout=self._connect_timeout_seconds,
            )
        except Exception:
            logger.warning("audit sink postgres unavailable; connection failed")
            self._conn = None
            return False
        return True

    def emit(self, event: AuditEvent) -> None:
        if not self.connect():
            logger.warning(
                "audit event %s/%s was not persisted: postgres unavailable",
                event.incident_id,
                event.kind,
            )
            return
        try:
            # Todo evento se persiste en audit_events (log append-only, fuente del
            # timeline). Los handlers _on_{kind} de abajo mantienen además los agregados.
            self._insert_event(event)
            handler = getattr(self, f"_on_{event.kind}", None)
            if handler is not None:
                handler(event)
        except Exception:
            logger.warning(
                "audit sink postgres write failed for %s/%s; event was not fully persisted",
                event.incident_id,
                event.kind,
            )
            self.close()

    def close(self) -> None:
        """Close the owned connection once."""
        conn = self._conn
        self._conn = None
        if conn is None:
            return
        try:
            conn.close()
        except Exception:
            logger.warning("audit sink postgres connection close failed")

    def _execute(self, sql: str, params: dict[str, Any]) -> None:
        conn = self._conn
        if conn is None:
            raise RuntimeError("postgres connection is not open")
        cursor = conn.execute(sql, params)
        close = getattr(cursor, "close", None)
        if close is not None:
            close()

    def _insert_event(self, e: AuditEvent) -> None:
        # payload como string + cast ::jsonb evita depender del wrapper Json de psycopg.
        self._execute(
            f"INSERT INTO {_S}.audit_events (incident_id, ts, kind, payload) "
            f"VALUES (%(id)s, %(ts)s, %(kind)s, %(payload)s::jsonb)",
            {"id": e.incident_id, "ts": e.ts, "kind": e.kind, "payload": json.dumps(e.payload)},
        )

    # -- handlers por kind: agregados incident-céntricos (sin handler = solo audit_events) --

    def _on_incident_created(self, e: AuditEvent) -> None:
        p = e.payload
        self._execute(
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
        self._execute(
            f"UPDATE {_S}.audit_incidents SET tier=%(tier)s, updated_at=%(ts)s "
            f"WHERE incident_id=%(id)s",
            {"id": e.incident_id, "ts": e.ts, "tier": e.payload.get("to_tier")},
        )

    def _on_decision_final(self, e: AuditEvent) -> None:
        p = e.payload
        outcome = p.get("outcome")
        state = _FINAL_STATE.get(outcome) if isinstance(outcome, str) else None
        self._execute(
            f"""UPDATE {_S}.audit_incidents SET
                  final_outcome=%(out)s, final_policy=%(pol)s, rationale=%(rat)s,
                  state=COALESCE(%(state)s, state), executed_at=%(ts)s, updated_at=%(ts)s
                WHERE incident_id=%(id)s""",
            {"id": e.incident_id, "ts": e.ts, "out": outcome, "pol": p.get("policy"),
             "rat": p.get("rationale"), "state": state},
        )

    def _on_action_executed(self, e: AuditEvent) -> None:
        self._execute(
            f"UPDATE {_S}.audit_incidents SET execution_status=%(st)s, updated_at=%(ts)s "
            f"WHERE incident_id=%(id)s",
            {"id": e.incident_id, "ts": e.ts, "st": e.payload.get("status")},
        )

    # action_failed/reverted comparten el mismo update de execution_status
    _on_action_failed = _on_action_executed
    _on_action_reverted = _on_action_executed

    def _on_approval_response(self, e: AuditEvent) -> None:
        decision = e.payload.get("decision")
        status = _VOTE_STATUS.get(decision, "pending") if isinstance(decision, str) else "pending"
        self._execute(
            f"""INSERT INTO {_S}.audit_responses
                (incident_id, approver_email, approver_role, status, channel, responded_at)
                VALUES (%(id)s, %(email)s, 'approver', %(status)s, 'telegram', %(ts)s)""",
            {"id": e.incident_id, "ts": e.ts, "email": e.payload.get("email"),
             "status": status},
        )
