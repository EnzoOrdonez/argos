"""FastAPI entry point for the ARGOS Layer 4 LLM Triage service.

This module will expose the single endpoint `POST /triage` that accepts an
`AlertContext` (alert payload, recent process tree, network connections,
file modifications) and returns a `TriageResponse` with structured fields.

References:
    - SAD §7.1 (Block 06 — FastAPI service).
    - SAD §7.4 (Structured output contract).
    - ADR-0001 (LLMClient abstraction used by this endpoint).
    - OPEN_QUESTIONS_RESOLUTION.md §Q4.2 (Incident schema; the
      `llm_analysis` sub-object of that schema is what `/triage` populates).

TODO:
    - Define `AlertContext` Pydantic model (request body).
    - Wire the endpoint to the LLMClient factory (`llm_client.factory.get_llm_client`).
    - Add `GET /health` for the external heartbeat service (SAD §13.6).
    - Add request-id middleware for audit correlation.
    - Enforce per-incident rate limit and monthly budget cap (resilience
      property R-10, SAD §12.1).
"""
