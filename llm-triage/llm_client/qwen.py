"""Qwen2.5-72B-Instruct backend for `LLMClient` (fallback).

Uses Alibaba DashScope API. Larger context window than DeepSeek with
similar cost; serves as automatic fallback when the primary is degraded
(SAD §12.1 R-08, SAD §12.2 — vendor portability and designed degradation).

References:
    - ADR-0001 §Decisión (fallback backend selection rationale).
    - ADR-0001 §Plan de implementación (`QwenClient` skeleton).

TODO:
    - Implement `QwenClient(LLMClient)` with async HTTP via `httpx`.
    - Read `QWEN_API_KEY` from environment.
    - Default model: `qwen2.5-72b-instruct`.
    - Wrap calls with `tenacity` retry on 429 / 5xx.
    - Adapt prompt template if Qwen needs slight phrasing tweaks
      (ADR-0001 §Negativas — prompt tuning per backend).
"""
