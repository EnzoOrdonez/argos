"""Audit dual fail-soft del SOAR (ADR-0013 §2.8)."""

from soar.audit.base import AuditEvent, AuditSink
from soar.audit.logger import AuditLogger
from soar.audit.memory import MemorySink
from soar.audit.opensearch import OpenSearchSink
from soar.audit.postgres import PostgresSink

__all__ = [
    "AuditEvent", "AuditLogger", "AuditSink",
    "MemorySink", "OpenSearchSink", "PostgresSink",
]
