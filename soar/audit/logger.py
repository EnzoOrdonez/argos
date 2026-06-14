"""Fan-out de eventos de audit a N sinks, fail-soft (ADR-0013 §2.8).

Si un sink lanza, se loguea y se sigue con el resto: el audit es evidencia,
no camino crítico. Mismo principio que los canales de notificación.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from soar.audit.base import AuditEvent, AuditSink

logger = logging.getLogger(__name__)


class AuditLogger:
    def __init__(self, sinks: Iterable[AuditSink]) -> None:
        self._sinks: list[AuditSink] = list(sinks)

    def emit(self, kind: str, incident_id: str, **payload: Any) -> AuditEvent:
        event = AuditEvent(
            ts=datetime.now(timezone.utc),
            kind=kind,
            incident_id=incident_id,
            payload=payload,
        )
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception:
                logger.exception(
                    "audit sink %s fallo para %s/%s; el flujo sigue",
                    type(sink).__name__,
                    incident_id,
                    kind,
                )
        return event
