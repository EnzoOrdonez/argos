"""Test del servicio FastAPI /triage con un cliente fake (wiring + manejo de error).

El cliente real contra NVIDIA se testea en test_openai_client (respx). Acá se usa un
fake para evitar el choque respx↔ASGITransport y testear el endpoint en sí."""

from __future__ import annotations

from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from argos_contracts.triage import AlertContext, TriageResponse
from llm_triage.api.main import app


class _FakeClient:
    backend_id = "fake-test"

    def __init__(self, *, raises: bool = False) -> None:
        self._raises = raises

    async def analyze(self, context: AlertContext) -> TriageResponse:
        if self._raises:
            raise RuntimeError("backend caído")
        return TriageResponse(
            incident_id=context.incident_id,
            tecnica_mitre="T1486",
            confianza=0.9,
            severidad="high",
            runbook_aplicable="NIST SP 800-61r2",
            accion_recomendada="Aislar el host y validar el snapshot antes de restaurar.",
            indicadores_correlacionar=[],
            llm_backend="fake-test",
            generated_at=datetime.now(timezone.utc),
        )


async def _post_triage(alert_context: AlertContext):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/triage", json=alert_context.model_dump(mode="json"))


async def test_triage_ok(alert_context) -> None:
    app.state.client = _FakeClient()
    resp = await _post_triage(alert_context)
    assert resp.status_code == 200
    body = TriageResponse.model_validate(resp.json())
    assert body.incident_id == alert_context.incident_id


async def test_triage_502_on_backend_failure(alert_context) -> None:
    app.state.client = _FakeClient(raises=True)
    resp = await _post_triage(alert_context)
    assert resp.status_code == 502  # el hook del SOAR lo absorbe a None (R-2)


async def test_health() -> None:
    app.state.client = _FakeClient()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "backend": "fake-test"}
