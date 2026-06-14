"""Sink en memoria: tests y ensayos sin OpenSearch ni Postgres (ADR-0013 §2.8).

P4 todavía no tiene la DB del lab; este sink mantiene el flujo auditable
end-to-end en el sandbox y en el inyector demo.
"""

from __future__ import annotations

from soar.audit.base import AuditEvent


class MemorySink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def emit(self, event: AuditEvent) -> None:
        self.events.append(event)

    def kinds(self) -> list[str]:
        return [e.kind for e in self.events]

    def for_incident(self, incident_id: str) -> list[AuditEvent]:
        return [e for e in self.events if e.incident_id == incident_id]
