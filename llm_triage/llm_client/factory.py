"""Selección del backend LLM por `LLM_BACKEND` (ADR-0001: swap por env, sin tocar código).

`openai` → `OpenAIClient` (endpoint OpenAI-compatible, default NVIDIA). `llama_local`
(Ollama, air-gap) queda **diferido** en Fase 4: el factory avisa claro si se lo selecciona.
"""

from __future__ import annotations

import os

from llm_triage.llm_client.base import LLMClient
from llm_triage.llm_client.openai_client import OpenAIClient


def get_llm_client(backend: str | None = None) -> LLMClient:
    """Devuelve el cliente LLM activo según `LLM_BACKEND` (default `openai`).

    Con `DEMO_MODE=true` envuelve el backend en `CachedClient` (sirve respuestas
    pre-generadas por técnica desde `DEMO_CACHE_PATH`; miss → backend real, R-2)."""
    backend = (backend or os.environ.get("LLM_BACKEND", "openai")).strip().lower()
    if backend == "openai":
        client: LLMClient = OpenAIClient()
    elif backend == "llama_local":
        raise NotImplementedError(
            "backend 'llama_local' (Ollama) está diferido en Fase 4; usá LLM_BACKEND=openai"
        )
    else:
        raise ValueError(
            f"LLM_BACKEND desconocido: {backend!r} (opciones: openai | llama_local)"
        )

    if os.environ.get("DEMO_MODE", "false").strip().lower() == "true":
        from pathlib import Path

        from llm_triage.llm_client.cached_client import CachedClient

        cache_dir = Path(os.environ.get("DEMO_CACHE_PATH", "./demo/cached-responses"))
        return CachedClient(client, cache_dir)
    return client
