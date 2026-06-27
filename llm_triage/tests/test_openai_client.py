"""Tests del OpenAIClient — respx mockea el endpoint OpenAI-compatible (NVIDIA)."""

from __future__ import annotations

import json

import httpx
import pytest

from argos_contracts.triage import TriageResponse
from llm_triage.llm_client.openai_client import OpenAIClient

_BASE = "https://nvidia.test/v1"


def _completion(content: str) -> dict:
    return {
        "id": "cmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _triage_content(tecnica: str = "T1486") -> str:
    return json.dumps(
        {
            "tecnica_mitre": tecnica,
            "confianza": 0.9,
            "severidad": "high",
            "runbook_aplicable": "NIST SP 800-61r2 Containment",
            "accion_recomendada": "Aislar el host y validar el snapshot antes de restaurar.",
            "indicadores_correlacionar": ["acceso fuera de horario"],
        }
    )


@pytest.fixture
def client() -> OpenAIClient:
    return OpenAIClient(
        api_key="k",
        base_url=_BASE,
        model="deepseek-ai/deepseek-v4-pro",
        fallback_model="moonshotai/kimi-k2.6",
    )


async def test_analyze_returns_triage(alert_context, client, respx_mock) -> None:
    respx_mock.post(f"{_BASE}/chat/completions").mock(
        return_value=httpx.Response(200, json=_completion(_triage_content()))
    )
    result = await client.analyze(alert_context)
    assert isinstance(result, TriageResponse)
    assert result.tecnica_mitre == "T1486"
    assert result.incident_id == alert_context.incident_id  # forzado del contexto
    assert result.llm_backend == "deepseek-ai/deepseek-v4-pro"


async def test_primary_fails_falls_back(alert_context, client, respx_mock) -> None:
    route = respx_mock.post(f"{_BASE}/chat/completions")
    route.side_effect = [
        httpx.Response(500, json={"error": "boom"}),
        httpx.Response(200, json=_completion(_triage_content())),
    ]
    result = await client.analyze(alert_context)
    assert result.llm_backend == "moonshotai/kimi-k2.6"  # usó el fallback
    assert route.call_count == 2


async def test_hallucinated_technique_raises(alert_context, client, respx_mock) -> None:
    respx_mock.post(f"{_BASE}/chat/completions").mock(
        return_value=httpx.Response(200, json=_completion(_triage_content("T9999")))
    )
    with pytest.raises(RuntimeError):
        await client.analyze(alert_context)  # ambos modelos -> T9999 -> validación falla
