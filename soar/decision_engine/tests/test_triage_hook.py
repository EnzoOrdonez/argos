"""Hook LLM Triage (ADR-0013 §2.5 + §7.5): gate, fail-soft R-2 y contexto."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from argos_contracts.alert import NormalizedAlert
from argos_contracts.enums import Criticality, Layer, Severity, Tier
from argos_contracts.triage import HostInfo, TriageResponse
from soar.audit.logger import AuditLogger
from soar.audit.memory import MemorySink
from soar.decision_engine.triage_hook import (
    TriageClient,
    build_alert_context,
    should_call_triage,
)

BASE = "http://triage.test"
L1 = frozenset({Layer.LAYER_1})


def _standard_host() -> HostInfo:
    return HostInfo(
        id="WIN-VICTIM-01",
        criticality=Criticality.STANDARD,
        ip="10.0.0.21",
        os="Windows 11",
    )


def _alert(technique: str = "T1078", **overrides: object) -> NormalizedAlert:
    defaults: dict[str, object] = {
        "alert_id": "alert-001",
        "source_layer": Layer.LAYER_1,
        "timestamp": datetime.now(UTC),
        "host_id": "WIN-VICTIM-01",
        "severity_score": 0.8,
        "severity_label": Severity.HIGH,
        "technique_mitre": technique,
    }
    defaults.update(overrides)
    return NormalizedAlert(**defaults)


def _triage_json(incident_id: str = "INC-2026-05-30-001") -> dict[str, object]:
    return {
        "incident_id": incident_id,
        "tecnica_mitre": "T1486",
        "confianza": 0.91,
        "severidad": "high",
        "runbook_aplicable": "NIST SP 800-61r3, fase Containment",
        "accion_recomendada": "Aislar el host y validar el snapshot antes de restaurar.",
        "indicadores_correlacionar": ["acceso fuera de horario"],
        "llm_backend": "stub-fixed",
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _client(audit: AuditLogger | None = None) -> TriageClient:
    return TriageClient(BASE, client=httpx.AsyncClient(), audit=audit)


async def test_t2_estandar_triage_exitoso(make_incident, respx_mock: respx.Router):
    route = respx_mock.post(f"{BASE}/triage").respond(200, json=_triage_json())
    incident = make_incident(
        tier=Tier.T2, host=_standard_host(), alert=_alert("T1078")
    )

    result = await _client().fetch(incident, L1)

    assert isinstance(result, TriageResponse)
    assert result.tecnica_mitre == "T1486"
    assert route.call_count == 1


async def test_t1_production_critical_si_llama_uc04(
    make_incident, respx_mock: respx.Router
):
    """UC-04: T1 + host crítico = espera humana, el LLM es decisivo
    (ADR-0009 §2.6). El gate 'solo T2' del borrador lo dejaba afuera."""
    route = respx_mock.post(f"{BASE}/triage").respond(200, json=_triage_json())
    incident = make_incident(tier=Tier.T1, alert=_alert("T1190"))  # host default: critico

    result = await _client().fetch(incident, frozenset({Layer.LAYER_1, Layer.LAYER_2}))

    assert result is not None
    assert route.call_count == 1


async def test_timeout_devuelve_none_y_audita(make_incident, respx_mock: respx.Router):
    respx_mock.post(f"{BASE}/triage").mock(
        side_effect=httpx.TimeoutException("triage lento")
    )
    memory = MemorySink()
    incident = make_incident(tier=Tier.T2, host=_standard_host(), alert=_alert())

    result = await _client(AuditLogger([memory])).fetch(incident, L1)

    assert result is None
    assert memory.kinds() == ["llm_triage_failed"]


async def test_5xx_devuelve_none_y_el_flujo_sigue(
    make_incident, respx_mock: respx.Router
):
    respx_mock.post(f"{BASE}/triage").respond(503)
    incident = make_incident(tier=Tier.T2, host=_standard_host(), alert=_alert())

    assert await _client().fetch(incident, L1) is None


async def test_respuesta_con_tecnica_alucinada_devuelve_none(
    make_incident, respx_mock: respx.Router
):
    body = _triage_json()
    body["tecnica_mitre"] = "T9999"  # fuera del MITRE_WHITELIST
    respx_mock.post(f"{BASE}/triage").respond(200, json=body)
    incident = make_incident(tier=Tier.T2, host=_standard_host(), alert=_alert())

    assert await _client().fetch(incident, L1) is None


@pytest.mark.parametrize("tier", [Tier.T0, Tier.T1, Tier.T3])
async def test_tiers_sin_espera_humana_no_llaman(
    make_incident, respx_mock: respx.Router, tier: Tier
):
    route = respx_mock.post(f"{BASE}/triage").respond(200, json=_triage_json())
    incident = make_incident(tier=tier, host=_standard_host(), alert=_alert())

    assert await _client().fetch(incident, L1) is None
    assert route.call_count == 0


@pytest.mark.parametrize("technique", ["T1498", "T1499"])
async def test_ddos_no_llama_ni_siquiera_con_espera_humana(
    make_incident, respx_mock: respx.Router, technique: str
):
    route = respx_mock.post(f"{BASE}/triage").respond(200, json=_triage_json())
    incident = make_incident(tier=Tier.T2, alert=_alert(technique))

    assert await _client().fetch(incident, L1) is None
    assert route.call_count == 0


def test_gate_should_call_triage(make_incident):
    t2 = make_incident(tier=Tier.T2, host=_standard_host(), alert=_alert())
    t1_critico = make_incident(tier=Tier.T1, alert=_alert())
    t1_estandar = make_incident(tier=Tier.T1, host=_standard_host(), alert=_alert())
    assert should_call_triage(t2)
    assert should_call_triage(t1_critico)
    assert not should_call_triage(t1_estandar)


def test_build_alert_context_arma_summary_y_telemetria(make_incident):
    alert = _alert(
        "T1486",
        triggering_rule="pg_mass_read",
        process_info={"pid": 4242, "name": "psql"},
        file_info={"path": "/tmp/dump.sql"},
    )
    incident = make_incident(tier=Tier.T2, alert=alert)

    context = build_alert_context(
        incident, frozenset({Layer.LAYER_2, Layer.LAYER_1})
    )

    assert context.incident_id == incident.incident_id
    assert context.alert_summary.title.startswith("pg_mass_read en")
    assert context.alert_summary.triggering_layers == [Layer.LAYER_1, Layer.LAYER_2]
    assert context.recent_telemetry["process_tree"] == {"pid": 4242, "name": "psql"}
    assert context.recent_telemetry["file_modifications"] == {"path": "/tmp/dump.sql"}
    assert "network_connections" not in context.recent_telemetry
