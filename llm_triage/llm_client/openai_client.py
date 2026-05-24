"""OpenAI GPT-4o-mini backend for `LLMClient` (primary, per ADR-0001 v2).

Uses the OpenAI Chat Completions API with structured outputs. Selected
in v2 because it offers better quality/cost than the previously
selected DeepSeek-V3 for cybersecurity reasoning benchmarks (HELM,
SecEval) while being US-based — eliminating the data sovereignty
concerns raised by sending lab telemetry to PRC-jurisdiction
providers.

References:
    - ADR-0001 v2 §Decisión (primary backend selection rationale).
    - ADR-0001 v2 §Plan de implementación (`OpenAIClient` skeleton).
    - docs/data-handling.md (sanitization required before any payload
      leaves the lab to this backend).

TODO:
    - Implement `OpenAIClient(LLMClient)` with async HTTP via the
      official `openai` Python SDK (≥1.0).
    - Read `OPENAI_API_KEY` from environment.
    - Default model: `gpt-4o-mini`.
    - Use Structured Outputs (`response_format={"type": "json_schema",
      ...}`) to force `TriageResponse`-shaped JSON.
    - Wrap calls with `tenacity` retry on 429 / 5xx.
    - Apply sanitization layer (`llm_triage/sanitizer.py`) before every
      send.
    - Emit cost-tracking event to OpenSearch audit log per
      `data-handling.md` §4.
"""
