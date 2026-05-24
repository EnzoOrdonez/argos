# llm_triage

ARGOS Layer 4 — LLM-based alert triage and enrichment service.

## Purpose

FastAPI microservice that enriches Wazuh alerts with structured analysis (MITRE technique, severity, runbook citation, recommended action, IoCs to correlate). Uses a vendor-agnostic LLM client over a mini-RAG corpus indexed on MITRE ATT&CK + NIST 800-61 + Sigma docs + SANS playbooks.

**Critical design property:** this service is **enrichment-only**. It is never on the containment critical path. The SOAR Decision Engine triggers containment from Layers 1–3 alone; a malfunctioning, hallucinating, or compromised LLM cannot prevent isolation, only fail to enrich the analyst view. See `SOLUTION_ARCHITECTURE_DOCUMENT.md` §12.1 (resilience property R-02).

## References

- Architecture: `docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md` §7 (Block 06 — LLM Triage / Layer 4).
- LLM vendor abstraction: `docs/decisions/0001-llm-vendor-agnostic.md` (v2).
- Data handling y sanitization: `docs/data-handling.md`.
- Incident schema (full contract): `docs/decisions/OPEN_QUESTIONS_RESOLUTION.md` §Q4.2.
- Use case exercising this layer the most: `docs/use-cases/USE_CASES.md` UC-03 (novel variant + split-brain approval).

## Module layout

```
llm_triage/
├── api/           FastAPI app + /triage endpoint
├── llm_client/    Vendor-agnostic LLM abstraction (OpenAI primary, Llama 3.1 local fallback per ADR-0001 v2)
├── rag/           Mini-RAG retrieval pipeline (BM25 + BGE-large + RRF)
├── prompts/       Jinja2 templates for triage prompts
└── tests/         pytest suite
```

## Status

Scaffolding only. No implementation logic yet.

## Owner

P1 (Enzo Ordoñez Flores).
