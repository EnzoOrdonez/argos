"""DeepSeek-V3 backend for `LLMClient` (primary).

Uses the OpenAI-compatible API endpoint exposed by DeepSeek. Selected for
quality/cost ratio (~1/30 of GPT-4o for comparable structured-reasoning
quality, per ADR-0001).

References:
    - ADR-0001 §Decisión (primary backend selection rationale).
    - ADR-0001 §Plan de implementación (`DeepSeekClient` skeleton).
    - ADR-0001 §Riesgo (China-vendor objection and prepared response).

TODO:
    - Implement `DeepSeekClient(LLMClient)` with async HTTP via `httpx`.
    - Read `DEEPSEEK_API_KEY` from environment.
    - Default model: `deepseek-chat` (V3 endpoint).
    - Wrap calls with `tenacity` retry on 429 / 5xx.
    - Enforce JSON-mode / structured output for `TriageResponse`
      conformance.
"""
