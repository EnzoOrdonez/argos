"""Genera la cache LLM a prueba de cámara (DEMO_MODE).

Corre el triage REAL (gpt-oss vía NVIDIA) una vez por UC que llama al LLM
(uc03/uc04/uc07: T2 o two-person; uc01/02/06 NO llaman LLM por R-2) y escribe las
respuestas en `DEMO_CACHE_PATH` keyed por técnica MITRE. Después, con `DEMO_MODE=true`,
el servicio sirve estas respuestas sin tocar la red (elimina el blip en la grabación).

    .venv\\Scripts\\python scripts\\gen_llm_cache.py        # usa OPENAI_* del .env

Requiere `OPENAI_API_KEY`/`OPENAI_BASE_URL`/`OPENAI_MODEL` (NVIDIA). Si un UC falla,
lo reporta y sigue: un miss en vivo cae al cliente real (R-2 intacto).
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from argos_contracts.enums import Criticality, Layer
from argos_contracts.triage import AlertContext, AlertSummary, HostInfo
from llm_triage.llm_client.cached_client import CachedClient
from llm_triage.llm_client.openai_client import OpenAIClient


def _ctx(incident_id, technique, *, title, host, crit, score, layers) -> AlertContext:
    return AlertContext(
        incident_id=incident_id,
        created_at=datetime.now(UTC),
        host=HostInfo(id=host, criticality=crit),
        alert_summary=AlertSummary(
            title=title, technique_mitre=technique, severity_score=score,
            triggering_layers=layers, raw_alert_id=f"{incident_id}-raw",
        ),
    )


# Un contexto representativo por UC que enriquece con LLM (key = técnica).
UC_CONTEXTS = {
    "uc03": _ctx("INC-DEMO-UC03", "T1083", title="Variante ransomware detectada por ML (sin firma Sigma)",
                 host="WIN-WS-07", crit=Criticality.STANDARD, score=0.74, layers=[Layer.LAYER_2]),
    "uc04": _ctx("INC-DEMO-UC04", "T1190", title="Lectura masiva sobre la DB IntiBank (production-critical)",
                 host="LIN-VICTIM-01", crit=Criticality.PRODUCTION_CRITICAL, score=0.90,
                 layers=[Layer.LAYER_1, Layer.LAYER_2]),
    "uc07": _ctx("INC-DEMO-UC07", "T1078", title="SELECT masivo de un analista (posible falso positivo)",
                 host="LIN-VICTIM-01", crit=Criticality.PRODUCTION_CRITICAL, score=0.85,
                 layers=[Layer.LAYER_1, Layer.LAYER_2]),
}


async def main() -> int:
    cache_dir = Path(os.environ.get("DEMO_CACHE_PATH", "./demo/cached-responses"))
    client = OpenAIClient()
    cache = CachedClient(client, cache_dir)
    print(f"[cache] destino: {cache_dir.resolve()}  modelo: {client.backend_id}")
    failures = 0
    for uc, ctx in UC_CONTEXTS.items():
        tech = ctx.alert_summary.technique_mitre
        try:
            resp = await client.analyze(ctx)
            path = cache.write(ctx, resp)
            print(f"[cache] {uc} {tech} -> {path.name}  "
                  f"(tecnica={resp.tecnica_mitre} conf={resp.confianza} sev={resp.severidad})")
        except Exception as exc:
            failures += 1
            print(f"[cache] {uc} {tech} FALLO: {type(exc).__name__}: {exc}", file=sys.stderr)
    print(f"[cache] listo. {len(UC_CONTEXTS) - failures}/{len(UC_CONTEXTS)} ok.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
