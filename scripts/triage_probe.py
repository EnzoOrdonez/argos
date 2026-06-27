"""Probe directo al servicio LLM Triage real (NVIDIA NIM).

Prueba que deepseek-v4-pro responde de verdad, SIN el cap de 5s del hook del SOAR.
Por qué hace falta: el hook del SOAR (`soar/decision_engine/triage_hook.py`, intocable)
corta a los 5s; deepseek suele tardar más → el panel de la consola sale vacío (fail-soft
R-2, no es un bug). Este probe le pega directo al `/triage` con timeout largo para mostrar
el `TriageResponse` real + la latencia, y así demostrar el LLM aparte del flujo del SOAR.

Correr (con el contenedor `llm-triage` real arriba en :8002, OPENAI_API_KEY seteada):
    .venv\\Scripts\\python scripts\\triage_probe.py
    .venv\\Scripts\\python scripts\\triage_probe.py --url http://localhost:8002/triage --timeout 60
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import httpx

from argos_contracts.enums import Criticality, Layer
from argos_contracts.triage import AlertContext, AlertSummary, HostInfo


def build_context() -> AlertContext:
    return AlertContext(
        incident_id="INC-2026-06-27-001",
        created_at=datetime.now(timezone.utc),
        host=HostInfo(
            id="LIN-VICTIM-01",
            criticality=Criticality.PRODUCTION_CRITICAL,
            ip="192.168.56.21",
            os="Debian",
        ),
        alert_summary=AlertSummary(
            title="Acceso masivo a la DB del banco fuera de horario",
            technique_mitre="T1005",
            severity_score=0.85,
            triggering_layers=[Layer.LAYER_1, Layer.LAYER_2],
            raw_alert_id="probe-001",
        ),
        recent_telemetry={
            "network_connections": ["192.168.56.50 -> LIN-VICTIM-01:5432"],
            "queries": "SELECT * masivo sobre intibank.transactions fuera de horario",
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe directo al /triage real (sin el cap de 5s del SOAR)."
    )
    parser.add_argument("--url", default="http://localhost:8002/triage")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    context = build_context()
    print(f"[probe] POST {args.url}  (timeout {args.timeout:.0f}s, sin el cap de 5s del SOAR)...")
    started = time.perf_counter()
    try:
        resp = httpx.post(args.url, json=context.model_dump(mode="json"), timeout=args.timeout)
    except httpx.HTTPError as exc:
        print(f"[probe] error de red: {exc}")
        return 1
    elapsed = time.perf_counter() - started
    print(f"[probe] HTTP {resp.status_code} en {elapsed:.1f}s")
    if resp.status_code != 200:
        print(f"[probe] body: {resp.text[:400]}")
        return 1
    body = resp.json()
    print(f"[probe] backend   : {body.get('llm_backend')}")
    print(f"[probe] tecnica   : {body.get('tecnica_mitre')}")
    print(f"[probe] severidad : {body.get('severidad')}  · confianza {body.get('confianza')}")
    print(f"[probe] runbook   : {body.get('runbook_aplicable')}")
    print(f"[probe] accion    : {body.get('accion_recomendada')}")
    print(f"\n[probe] OK -> el modelo respondió en {elapsed:.1f}s.")
    print("[probe] El SOAR corta a 5s -> por eso el panel sale vacío (fail-soft R-2).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
