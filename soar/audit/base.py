"""Audit de decisiones del SOAR: evento + interfaz de sink (ADR-0013 §2.8).

Los registros de decisiones de respuesta son evidencia de primera clase
(NIST SP 800-92, gestión de logs de seguridad) y el audit trail multi-actor
lo exige ADR-0006. Dos sinks: OpenSearch (primario, índice
`argos-audit-decisions`) y SQL (lo arma P4 con `soar/audit/schema.sql`).
Ambos fail-soft: la contención nunca se pierde por un fallo de auditoría.

Vocabulario de `kind` (el consumer/scheduler/API emiten estos):
- incident_created, alert_correlated, tier_escalated
- action_executed, action_failed, action_reverted
- approval_response, decision_final, timeout_wait, voice_escalated
- llm_triage_ok, llm_triage_failed
- poison_discarded
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class AuditEvent:
    """Un hecho auditable, con timestamp tz-aware y payload abierto."""

    ts: datetime
    kind: str
    incident_id: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_document(self) -> dict[str, Any]:
        """Forma serializable (para OpenSearch o JSON plano)."""
        return {
            "ts": self.ts.isoformat(),
            "kind": self.kind,
            "incident_id": self.incident_id,
            **self.payload,
        }


class AuditSink(Protocol):
    """Destino de eventos de audit. Puede lanzar: el AuditLogger lo contiene."""

    def emit(self, event: AuditEvent) -> None: ...
