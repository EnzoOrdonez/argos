"""Backend de triage vía endpoint OpenAI-compatible (default NVIDIA NIM).

Lee del entorno: `OPENAI_BASE_URL` (default NVIDIA), `OPENAI_API_KEY`, `OPENAI_MODEL`
(primario), `OPENAI_FALLBACK_MODEL`. ADR-0001 / Fase 4: primario
`deepseek-ai/deepseek-v4-pro` (con `thinking:false` para salida estructurada más
rápida), fallback `moonshotai/kimi-k2.6`.

Flujo: sanitizar (T-030) → render prompts → llamar al modelo (JSON mode) → si falla,
probar el fallback → parsear y validar contra `TriageResponse` (la validación del
MITRE whitelist es la defensa anti-alucinación, R-6). Falla total → lanza (el hook
del SOAR lo vuelve None; nunca bloquea la contención).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from openai import AsyncOpenAI

from argos_contracts.triage import MITRE_WHITELIST, AlertContext, TriageResponse
from llm_triage.llm_client.base import LLMClient
from llm_triage.prompts import render_system, render_user
from llm_triage.sanitizer import sanitize

logger = logging.getLogger(__name__)

_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
_DEFAULT_MODEL = "deepseek-ai/deepseek-v4-pro"
_DEFAULT_FALLBACK = "moonshotai/kimi-k2.6"


def _strip_json(content: str) -> str:
    """Extrae el primer objeto JSON, tolerando fences ```json y prosa alrededor."""
    text = content.strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 and end > start else text


class OpenAIClient(LLMClient):
    """Cliente OpenAI-compatible con primario→fallback de modelo."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
        timeout: float | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._base_url = base_url or os.environ.get("OPENAI_BASE_URL", _NVIDIA_BASE)
        self._model = model or os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL)
        self._fallback = fallback_model or os.environ.get(
            "OPENAI_FALLBACK_MODEL", _DEFAULT_FALLBACK
        )
        timeout = timeout or float(os.environ.get("LLM_REQUEST_TIMEOUT_SECONDS", "30"))
        # max_retries=0: el fallback de modelo es nuestra resiliencia, no el retry del SDK.
        self._client = client or AsyncOpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY") or "missing",
            base_url=self._base_url,
            timeout=timeout,
            max_retries=0,
        )
        self.backend_id = self._model

    async def analyze(self, context: AlertContext) -> TriageResponse:
        sanitized, redactions = sanitize(context)
        logger.info(
            "triage %s: %d redacciones de sanitización", context.incident_id, redactions
        )
        messages = [
            {"role": "system", "content": render_system()},
            {"role": "user", "content": render_user(sanitized, sorted(MITRE_WHITELIST))},
        ]
        last_exc: Exception | None = None
        for model in (self._model, self._fallback):
            try:
                return await self._call_model(model, context, messages)
            except Exception as exc:  # primario falla → se prueba el fallback
                logger.warning(
                    "modelo %s falló para %s: %s", model, context.incident_id, exc
                )
                last_exc = exc
        raise RuntimeError(f"todos los modelos LLM fallaron: {last_exc}") from last_exc

    async def _call_model(
        self, model: str, context: AlertContext, messages: list[dict[str, str]]
    ) -> TriageResponse:
        # DeepSeek en NVIDIA: thinking:false acelera y limpia la salida estructurada.
        extra_body = {"chat_template_kwargs": {"thinking": False}} if "deepseek" in model else {}
        completion = await self._client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            response_format={"type": "json_object"},
            temperature=0.2,
            extra_body=extra_body,
        )
        content = completion.choices[0].message.content or ""
        data = json.loads(_strip_json(content))
        # Campos que NO se confían al modelo: se fuerzan desde el contexto/runtime.
        data["incident_id"] = context.incident_id
        data["llm_backend"] = model
        data["generated_at"] = datetime.now(timezone.utc).isoformat()
        return TriageResponse.model_validate(data)  # valida MITRE whitelist (R-6)
