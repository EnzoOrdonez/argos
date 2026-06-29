"""Cache LLM a prueba de cámara (DEMO_MODE): hit sirve la cache + re-estampa los
campos volátiles; miss delega al cliente real; JSON corrupto degrada (R-2)."""

from __future__ import annotations

from datetime import datetime, timezone

from argos_contracts.enums import Criticality, Layer, Severity
from argos_contracts.triage import AlertContext, AlertSummary, HostInfo, TriageResponse
from llm_triage.llm_client.base import LLMClient
from llm_triage.llm_client.cached_client import CachedClient


def _context(incident_id: str, technique: str | None) -> AlertContext:
    return AlertContext(
        incident_id=incident_id,
        created_at=datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc),
        host=HostInfo(id="WIN-WS-07", criticality=Criticality.STANDARD),
        alert_summary=AlertSummary(
            title="variante ML",
            technique_mitre=technique,
            severity_score=0.74,
            triggering_layers=[Layer.LAYER_2],
            raw_alert_id="uc03-ml",
        ),
    )


def _response(incident_id: str, technique: str, backend: str) -> TriageResponse:
    return TriageResponse(
        incident_id=incident_id,
        tecnica_mitre=technique,
        confianza=0.78,
        severidad=Severity.HIGH,
        runbook_aplicable="NIST SP 800-61r3 §3.3 contención",
        accion_recomendada="Aislar el host y preservar el snapshot forense antes de remediar.",
        indicadores_correlacionar=["wmic", "shadowcopy"],
        llm_backend=backend,
        generated_at=datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc),
    )


class _FakeDelegate(LLMClient):
    backend_id = "fake-real"

    def __init__(self) -> None:
        self.calls = 0

    async def analyze(self, context: AlertContext) -> TriageResponse:
        self.calls += 1
        return _response(context.incident_id, "T1486", self.backend_id)


async def test_cache_hit_serves_and_restamps(tmp_path) -> None:
    delegate = _FakeDelegate()
    cache = CachedClient(delegate, tmp_path)
    # sembrar la cache para T1083 con un incident_id viejo
    cache.write(_context("INC-OLD-000", "T1083"), _response("INC-OLD-000", "T1083", "openai/gpt-oss-120b"))

    result = await cache.analyze(_context("INC-2026-06-29-005", "T1083"))

    assert delegate.calls == 0                       # NO llamó al real (hit)
    assert result.tecnica_mitre == "T1083"           # cuerpo de la cache
    assert result.confianza == 0.78
    assert result.incident_id == "INC-2026-06-29-005"  # re-estampado al contexto actual
    assert result.llm_backend == "demo-cache:fake-real"  # re-estampado
    assert result.generated_at.tzinfo is not None    # re-estampado a now (tz-aware)


async def test_cache_miss_delegates(tmp_path) -> None:
    delegate = _FakeDelegate()
    cache = CachedClient(delegate, tmp_path)  # vacía
    result = await cache.analyze(_context("INC-2026-06-29-006", "T1083"))
    assert delegate.calls == 1                       # cayó al real
    assert result.llm_backend == "fake-real"


async def test_corrupt_cache_degrades_to_delegate(tmp_path) -> None:
    delegate = _FakeDelegate()
    cache = CachedClient(delegate, tmp_path)
    (tmp_path / "T1083.json").write_text("{ no es json válido", encoding="utf-8")
    result = await cache.analyze(_context("INC-2026-06-29-007", "T1083"))
    assert delegate.calls == 1                       # R-2: degrada, no rompe
    assert result.llm_backend == "fake-real"
