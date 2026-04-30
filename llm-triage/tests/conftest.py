"""Shared pytest fixtures for the llm-triage test suite.

Coverage targets for this module (per OPEN_QUESTIONS_RESOLUTION.md §Q3):
    - LLMClient implementations and the FastAPI `/triage` endpoint count
      as critical-path code; target >=60% line coverage.
    - At least one happy-path and one error-path integration test per
      LLMClient backend.

References:
    - ADR-0001 §Métricas de éxito ("ambos backends pasan el mismo test
      suite de structured output validation").
    - SAD §13.5 (Testing strategy; `respx` is the chosen tool for mocking
      LLM HTTP calls).
    - OPEN_QUESTIONS_RESOLUTION.md §Q3 (tiered coverage targets).

TODO:
    - `respx_mock` fixture preconfigured with DeepSeek and Qwen base URLs.
    - `sample_alert_context` fixture: representative AlertContext payload
      drawn from UC-01 (classic ransomware) for happy-path tests.
    - `sample_alert_context_novel` fixture: UC-03 payload (ML-only T2)
      for the centerpiece scenario.
    - `mitre_whitelist` fixture: subset of ATT&CK technique IDs used by
      the validation tests (T1486, T1490, T1083, T1562, T1021, T1071).
    - Hallucinated-technique fixture: response containing `T9999` to
      verify the whitelist rejects it (SAD §12.1 R-06).
"""
