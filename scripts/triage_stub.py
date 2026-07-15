"""Stub HTTP del LLM Triage: herramienta de integración de P1, dual-track del demo.

NO es la Capa 4. La capa real (`llm_triage/`) es dominio de P2 y este archivo
no la toca. Esto existe para ensayar UC-04/UC-07 end-to-end (consumer -> hook
-> llm_analysis) aunque el servicio de P2 no esté listo (filosofía del video
backup, manual P1 §4.3 / ADR-0010).

Devuelve una `TriageResponse` fija y válida contra el contrato v1.1.0
(técnica dentro de MITRE_WHITELIST, campos con sus longitudes mínimas).

Correr:
    .venv\\Scripts\\python scripts\\triage_stub.py
    # escucha en http://127.0.0.1:8002 (LLM_TRIAGE_PORT para cambiar puerto)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import FastAPI

from argos_contracts.triage import MITRE_WHITELIST, AlertContext, TriageResponse

app = FastAPI(title="ARGOS Triage Stub (P1, herramienta de ensayo)")


@app.post("/triage")
async def triage(context: AlertContext) -> TriageResponse:
    technique = context.alert_summary.technique_mitre
    if technique not in MITRE_WHITELIST:
        technique = "T1486"
    return TriageResponse(
        incident_id=context.incident_id,
        tecnica_mitre=technique,
        confianza=0.87,
        severidad="high",
        runbook_aplicable=(
            "NIST SP 800-61r3, fase Containment, Eradication and Recovery"
        ),
        accion_recomendada=(
            "Mantener throttle activo, validar snapshot y aprobar el aislamiento "
            f"del host {context.host.id} si el patrón de acceso no corresponde "
            "al rol."
        ),
        indicadores_correlacionar=[
            "queries masivas fuera de horario",
            "ip de origen fuera de la red corporativa",
        ],
        llm_backend="stub-fixed",
        generated_at=datetime.now(UTC),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("LLM_TRIAGE_PORT", "8002")))
