# rag/ — mini-RAG retrieval pipeline

Retrieval-augmented generation pipeline that grounds the LLM triage output in a security corpus. Reuses approximately 70% of the retrieval code from the CloudRAG reference project; the corpus is 100% new.

## Pipeline (per SAD §7.2)

`BM25 → BGE-large embeddings → Reciprocal Rank Fusion → cross-encoder reranker`

## Indexed sources

- MITRE ATT&CK STIX bundle (techniques, mitigations, detections).
- Sigma rules documentation.
- NIST SP 800-61r2 (Computer Security Incident Handling Guide).
- SANS publicly available IR playbooks.
- Internal post-mortems of simulated attacks (grow over time).

## Status

**Placeholder.** Implementation scheduled for week 3 of the 14-week plan. Until then the LLM Triage endpoint runs without retrieval context (raw alert only).

## TODO

- Port retrieval pipeline from CloudRAG.
- Build initial corpus loader (STIX parser, Markdown parser for SANS/NIST).
- Add per-query latency budget so RAG cannot block the `/triage` SLO.
- Citation extraction so the analyst UI can expand to source documents (SAD §9.2.1).

## References

- SAD §7.2 (Block 06 — Mini-RAG corpus).
- SAD §7.4 (citations are part of the analyst-visible output, not the structured `TriageResponse`).
