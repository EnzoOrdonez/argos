"""Abstract `LLMClient` interface and the `TriageResponse` Pydantic schema.

This module defines the vendor-agnostic contract every LLM backend must
implement. All callers depend on `LLMClient` (the abstract base) so that
swapping backends is a one-line config change with no code modifications
in the rest of the system.

References:
    - ADR-0001 (LLM vendor-agnostic via LLMClient interface) — full
      rationale, alternatives considered, and the canonical class skeleton.
    - SAD §7.3 (LLMClient — vendor-agnostic interface).
    - SAD §7.4 (Structured output schema for `TriageResponse`).
    - SAD §12.1 R-08 (vendor portability prevents lock-in failure).

TODO:
    - Define `TriageResponse` Pydantic model with the six fields from
      ADR-0001 §Plan de implementación (tecnica_mitre, confianza,
      severidad, runbook_aplicable, accion_recomendada,
      indicadores_correlacionar).
    - Define abstract `LLMClient` ABC with async `analyze(alert_context)`.
    - Validation: `tecnica_mitre` must be a member of the loaded MITRE
      ATT&CK ID whitelist (SAD §12.1 R-06; rejects hallucinated IDs).
"""
