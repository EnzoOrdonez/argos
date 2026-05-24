"""Abstract `LLMClient` interface for the Layer 4 LLM Triage service.

Defines the vendor-agnostic contract every LLM backend must implement.
All callers depend on `LLMClient` (the abstract base) so that swapping
backends is a one-line config change with no code modifications.

References:
    - ADR-0001 v2 (LLM vendor-agnostic — primary OpenAI GPT-4o-mini,
      fallback Llama 3.1 8B local).
    - SAD §7.3 (LLMClient — vendor-agnostic interface).
    - SAD §7.4 (Structured output schema for `TriageResponse`).
    - SAD §12.1 R-08 (vendor portability prevents lock-in failure).

TODO:
    - Define abstract `LLMClient` ABC with async `analyze(alert_context)`
      returning `TriageResponse` from `argos_contracts.triage`.
    - Validation: `tecnica_mitre` must be a member of
      `argos_contracts.MITRE_WHITELIST` (SAD §12.1 R-06).
"""
