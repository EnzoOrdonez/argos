"""Llama 3.1 8B local backend for `LLMClient` (fallback, per ADR-0001 v2).

Uses Ollama running on the same machine as the SOAR service. Selected
in v2 as the fallback because it offers something no external API can:
**zero-egress inference**. If the OpenAI primary fails, the network
drops, or an air-gap deployment is required, ARGOS keeps producing
analyses without any byte of telemetry leaving the lab.

Quality is lower than the cloud primary (NVIDIA NIM, ADR-0001 v3) but
sufficient to produce a valid structured `TriageResponse`. Status: deferred
(Fase 4 only wired the NVIDIA backend; this stays stub until air-gap is needed).

References:
    - ADR-0001 v2 §Decisión (fallback backend rationale).
    - ADR-0001 v2 §Plan de implementación (`LlamaLocalClient` skeleton).
    - docs/data-handling.md (sanitization optional for this backend;
      data never crosses the trust boundary).

TODO:
    - Implement `LlamaLocalClient(LLMClient)` against the Ollama REST
      API (`POST /api/generate` with `format=json` for JSON-mode).
    - Default `base_url = "http://localhost:11434"`.
    - Default model: `llama3.1:8b`.
    - Prompt template adjusted for Llama's tendency to add commentary
      outside JSON braces — use stricter system prompt.
    - Wrap with `tenacity` retry on connection errors (Ollama service
      startup race).
    - Health probe at service start to ensure `llama3.1:8b` is pulled;
      otherwise emit a clear error message pointing to
      `ollama pull llama3.1:8b`.
"""
