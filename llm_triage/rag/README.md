# rag/ — mini-RAG retrieval pipeline

Retrieval-augmented generation pipeline que ancla la salida del LLM triage en un corpus de seguridad. Implementación in-house basada en el patrón industrial de **hybrid retrieval** (léxico + denso) sin cross-encoder por motivos de costo/beneficio en el alcance v1.

## Pipeline (per SAD §7.2 actualizado)

`BM25 (léxico) → BGE-large embeddings (denso) → Reciprocal Rank Fusion (RRF)`

**Decisión de v1:** el cross-encoder reranker original se descarta del scope inicial. Aporta marginalmente ~5-10% mejora en precision@k para corpus pequeños pero añade ~300ms de latencia por consulta y otro modelo a mantener. La hybrid retrieval BM25+denso con RRF cubre el caso de uso del proyecto académico. Cross-encoder queda documentado como upgrade trivial si la evaluación EV-05 muestra que la calidad del contexto retrieved no es suficiente.

## Indexed sources

- MITRE ATT&CK STIX bundle (técnicas, mitigaciones, detecciones).
- Sigma rules documentation.
- NIST SP 800-61r2 (Computer Security Incident Handling Guide).
- SANS publicly available IR playbooks.
- Internal post-mortems of simulated attacks (grow over time).

## Stack

| Tool | Role |
|------|------|
| `rank-bm25` | BM25 léxico (índice in-memory, suficiente para corpus <10k chunks) |
| `sentence-transformers` (BGE-large) | Embeddings densos |
| `faiss-cpu` | Índice ANN para retrieval denso |
| custom RRF implementation | Fusión de rankings (~20 líneas, no requiere librería) |

## Status

**Esqueleto.** Implementación arranca tras el lab base y los stubs LLM. El corpus es 100% nuevo para ARGOS — no se reutiliza de proyectos previos para evitar deuda implícita y dependencias externas.

## TODO

- Implementar BM25 + BGE-large + RRF en un solo módulo (`rag/retriever.py`).
- Loader de STIX para MITRE ATT&CK (parser local del JSON oficial).
- Markdown parser para SANS / NIST.
- Per-query latency budget para que el RAG no bloquee el SLO del `/triage`.
- Citation extraction para que la UI del analista pueda expandir a fuente original (SAD §9.2.1).

## References

- SAD §7.2 (Block 06 — Mini-RAG corpus).
- ADR-0001 v2 (LLMClient consume el contexto producido aquí).
