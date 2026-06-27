"""Tests del factory: selección de backend por LLM_BACKEND."""

from __future__ import annotations

import pytest

from llm_triage.llm_client.factory import get_llm_client
from llm_triage.llm_client.openai_client import OpenAIClient


def test_openai_backend(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    assert isinstance(get_llm_client(), OpenAIClient)


def test_llama_local_is_deferred() -> None:
    with pytest.raises(NotImplementedError):
        get_llm_client("llama_local")


def test_unknown_backend_raises() -> None:
    with pytest.raises(ValueError, match="desconocido"):
        get_llm_client("bogus")
