"""Audit dual fail-soft (ADR-0013 §2.8): fan-out, sinks y caída simulada."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import respx

from soar.audit.base import AuditEvent
from soar.audit.logger import AuditLogger
from soar.audit.memory import MemorySink
from soar.audit.opensearch import OpenSearchSink

OS_BASE = "https://opensearch.test:9200"


class _ExplodingSink:
    def emit(self, event: AuditEvent) -> None:
        raise RuntimeError("sink caido")


def test_memory_sink_registra_eventos_con_ts_tz_aware():
    memory = MemorySink()
    logger = AuditLogger([memory])

    event = logger.emit("incident_created", "INC-2026-06-10-001", tier="T2")

    assert memory.kinds() == ["incident_created"]
    assert memory.for_incident("INC-2026-06-10-001") == [event]
    assert event.ts.tzinfo is not None
    assert event.payload == {"tier": "T2"}


def test_sink_caido_no_afecta_al_resto_del_fan_out():
    memory = MemorySink()
    logger = AuditLogger([_ExplodingSink(), memory])

    logger.emit("decision_final", "INC-2026-06-10-001", outcome="EXECUTE_ISOLATION")

    # El sink que explota no impide que el sink sano reciba el evento.
    assert memory.kinds() == ["decision_final"]


@respx.mock
def test_opensearch_sink_indexa_documento(respx_mock: respx.Router):
    route = respx_mock.post(f"{OS_BASE}/argos-audit-decisions/_doc").respond(
        201, json={"result": "created"}
    )
    sink = OpenSearchSink(OS_BASE, "admin", "secret", client=httpx.Client())
    logger = AuditLogger([sink])

    logger.emit("approval_response", "INC-2026-06-10-002", decision="approve")

    assert route.call_count == 1
    import json

    body = json.loads(route.calls.last.request.content)
    assert body["kind"] == "approval_response"
    assert body["incident_id"] == "INC-2026-06-10-002"
    assert body["decision"] == "approve"


@respx.mock
def test_opensearch_caido_no_lanza_y_el_flujo_sigue(respx_mock: respx.Router):
    respx_mock.post(f"{OS_BASE}/argos-audit-decisions/_doc").mock(
        side_effect=httpx.ConnectError("down")
    )
    memory = MemorySink()
    sink = OpenSearchSink(OS_BASE, "admin", "secret", client=httpx.Client())
    logger = AuditLogger([sink, memory])

    logger.emit("action_executed", "INC-2026-06-10-003", action="host_isolation")

    assert memory.kinds() == ["action_executed"]


@respx.mock
def test_opensearch_500_no_lanza(respx_mock: respx.Router):
    respx_mock.post(f"{OS_BASE}/argos-audit-decisions/_doc").respond(500)
    sink = OpenSearchSink(OS_BASE, "admin", "secret", client=httpx.Client())

    sink.emit(
        AuditEvent(
            ts=datetime.now(timezone.utc),
            kind="x",
            incident_id="INC-2026-06-10-004",
        )
    )
