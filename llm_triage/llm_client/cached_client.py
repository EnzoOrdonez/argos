"""Cache de respuestas LLM a prueba de cámara (DEMO_MODE, ADR-0010 demo).

Envuelve a otro `LLMClient`. Con `DEMO_MODE=true`, sirve un `TriageResponse`
pre-generado desde `DEMO_CACHE_PATH`, keyed por **técnica MITRE** (estable entre
corridas, a diferencia de `incident_id`/`generated_at` que se regeneran). Re-estampa
`incident_id`/`generated_at`/`llm_backend` al servir, igual que el cliente real
(`openai_client.py`). Cache-miss → delega al cliente real.

R-2 intacto: un miss o un JSON corrupto degradan al delegate (y el hook del SOAR a
None); el LLM nunca bloquea la contención. La cache solo elimina el blip de red en
vivo durante la grabación; gpt-oss igual responde ~0.9s sin ella.

Generar la cache: `scripts/gen_llm_cache.py` corre el triage real de cada UC una vez.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from argos_contracts.triage import AlertContext, TriageResponse
from llm_triage.llm_client.base import LLMClient

logger = logging.getLogger(__name__)


def cache_key(context: AlertContext) -> str:
    """Key estable: la técnica MITRE del alert (o 'none' si la capa no la trae)."""
    return context.alert_summary.technique_mitre or "none"


class CachedClient(LLMClient):
    """Sirve respuestas cacheadas por técnica; cae al delegate en miss."""

    backend_id = "demo-cache"

    def __init__(self, delegate: LLMClient, cache_dir: Path) -> None:
        self._delegate = delegate
        self._dir = Path(cache_dir)

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    async def analyze(self, context: AlertContext) -> TriageResponse:
        path = self._path(cache_key(context))
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                # Campos volátiles re-estampados en el momento de servir (no se confían
                # a la cache), igual que openai_client.py.
                data["incident_id"] = context.incident_id
                data["generated_at"] = datetime.now(timezone.utc).isoformat()
                data["llm_backend"] = f"demo-cache:{getattr(self._delegate, 'backend_id', 'llm')}"
                return TriageResponse.model_validate(data)
            except Exception as exc:  # JSON corrupto / schema inválido -> delegate (R-2)
                logger.warning("cache LLM inválida en %s: %s; delego al cliente real", path, exc)
        return await self._delegate.analyze(context)

    def write(self, context: AlertContext, response: TriageResponse) -> Path:
        """Persiste una respuesta para una técnica (lo usa el generador de cache)."""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path(cache_key(context))
        path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
        return path
