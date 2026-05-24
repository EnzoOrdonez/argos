# EVALUATION CRITERIA — ARGOS

| Field | Value |
|-------|-------|
| Document type | Course rubric — formal evaluation criteria |
| Source | Profesor del curso *Tópicos Avanzados de Ciberseguridad* · Universidad de Lima · 2026-1 |
| Status | Authoritative (rubric provided by the course) |
| Owner | P1 (Enzo) — keeps this in sync with any updates from the professor |
| Last updated | Week 7 (calendar) |

---

## 0. Purpose

Document, **inside the repo**, the exact rubric the course uses to evaluate this project. Without this, every implementation decision is a guess about what the grader values most. With this in plain text alongside the rest of the docs, the team can trade off scope honestly against what carries grade weight.

---

## 1. Required deliverables

The course specifies **three** mandatory deliverables per project. Every architectural and scope decision in this repo should map back to at least one of them.

### 1.1 Informe Final Técnico

Formal written report. Required sections (verbatim from the course brief):

- Portada (título del proyecto, curso, integrantes, fecha)
- Resumen ejecutivo
- Objetivos del proyecto
- Descripción del entorno y herramientas utilizadas
- Metodología de implementación
- Resultados y evidencias técnicas (casos de uso, capturas de pantalla, logs, reportes)
- Análisis de riesgos o vulnerabilidades encontradas
- Recomendaciones de mejora o endurecimiento
- Conclusiones
- Referencias bibliográficas

**How this repo serves this deliverable:**

| Required section | Source in this repo |
|------------------|---------------------|
| Portada + Resumen ejecutivo | `docs/PROJECT_BRIEF.md` (90-second overview) |
| Objetivos | `README.md` §"What is ARGOS?" + `docs/PROJECT_BRIEF.md` |
| Entorno + herramientas | `docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md` §2-11 + `README.md` §"Tech stack" |
| Metodología | `docs/CONTEXT.md` §6 (plan 14 semanas) + ADRs 0001-0007 |
| Resultados / evidencias técnicas | `evaluation/` (when produced) + `docs/use-cases/USE_CASES.md` + screenshots from `ui/` |
| Análisis de riesgos | `docs/architecture/THREAT_MODEL.md` (full STRIDE + FMEA + Risk Register) |
| Recomendaciones | `docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md` §14 (Future work) |
| Conclusiones | informe-final-tecnico.md (Week 13 deliverable, lives in `evaluation/reports/`) |
| Referencias | `README.md` §"References" + `docs/CONTEXT.md` §14 |

### 1.2 Presentación para Exposición

Live presentation to defend the project. Required structure (verbatim):

- Título y autores
- Objetivo del proyecto
- Descripción del problema o reto
- Herramientas utilizadas
- Esquema de arquitectura / diagrama de red
- Explicación de los casos de uso
- Evidencias destacadas (casos de uso, capturas, logs, resultados)
- Aprendizajes y dificultades encontradas
- Conclusiones y recomendaciones
- Bibliografía breve

**How this repo serves this deliverable:**

- The interactive deck at `docs/use-cases/argos_use_cases.html` covers most of the structure visually (5 demo scenarios, MITRE coverage, SIEM comparison, KPI dashboard).
- The architecture diagram is at `docs/architecture/architecture_diagram.html` (interactive).
- "Aprendizajes y dificultades" → keep an explicit `docs/LESSONS_LEARNED.md` log starting now (Week 7) — every gate retrospective adds an entry.

### 1.3 Implementación Técnica Funcional

Working demo. The course specifies:

- Implementación en entornos virtuales o controlados de la solución.
- Demostración de casos de uso.

**How this repo serves this deliverable:**

- The lab is defined in `lab/` (Vagrant + Terraform) — reproducible from zero in <30 min per SAD §13.2.
- The 5 use cases (UC-01..UC-05) are scripted with full reproducible attacks via `attack-simulation/` and detection across `detection/` + `ml/` + `deception/` + `soar/`.
- The 7 evaluation scenarios (EV-01..EV-07) are scripted in `evaluation/`.

---

## 2. Seguimiento (checkpoints)

The course mandates **three review checkpoints**:

| Checkpoint | Calendar week | What it traditionally evaluates | Status |
|-----------|:------------:|--------------------------------|--------|
| Review 1 | **5** | Initial architecture + first signs of implementation | ⚠️ Architecture and contracts shipped, no Layer 1 implementation yet |
| Review 2 | **7** | Mid-project progress; layers operational; first metrics | ⚠️ **Currently due** — team is presenting use cases only |
| Review 3 | **9** | Pre-demo readiness; full stack integrated | 📅 Pending |

> **Each checkpoint contributes to the final score** ("contribuirán al puntaje global"). The team should walk into each one with concrete evidence of progress, even if the scope is reduced. Slipping a checkpoint silently is worse than declaring a deliberate scope cut.

---

## 3. Implicit weight inference (the team's working assumption)

The course does **not** publish per-section weights. The team's working assumption, based on the structure of the deliverables list:

| Deliverable | Estimated weight (team assumption — not authoritative) | Implication |
|-------------|:-----------------------------------------------------:|-------------|
| Implementación Técnica Funcional (demo) | ~40% | Working demo is non-negotiable. Reduce scope before reducing demo quality. |
| Informe Final Técnico | ~30% | Comprehensive informe matters — the doc-heavy ARGOS approach plays to this. |
| Presentación para Exposición | ~20% | Polished deck + rehearsed presentation. Already invested in `docs/use-cases/argos_use_cases.html`. |
| Seguimientos (W5/W7/W9) | ~10% combined | Showing up to each with measurable progress. |

**Action when the assumption proves wrong:** if the professor in office hours specifies different weights, update this section *immediately* and re-prioritize accordingly. Track this as P-005 evolution in the Risk Register.

---

## 4. Trade-offs already locked

Decisions where the rubric directly informed the choice:

| Decision | Where | Rubric tie |
|----------|-------|------------|
| Demo-grade reliability via custom Python simulator | SAD §2 | "Implementación técnica funcional" → demo must work live |
| HTML interactive deck instead of static PDF deck | `docs/use-cases/argos_use_cases.html` | "Presentación" benefits from visual evidence |
| Public repo at end of course | `README.md` §License | Portfolio-worthy artifact for "Aprendizajes" + post-course visibility |
| Tiered test coverage targets (not flat 70%) | SAD §13.5 per Q3 | Realistic effort budget given the rubric weights demo > tests |

---

## 5. Open questions for the professor

To resolve in next office hours (every team member should review this list before that conversation):

1. **Per-section weights** — confirm or correct the assumed split in §3.
2. **Layer 4 LLM** — is the use of an external LLM API (DeepSeek/Qwen) within course scope? See P-005 risk and `OPEN_QUESTIONS_RESOLUTION.md` §Q1.
3. **Sigma upstream PRs** — does upstream contribution count toward the grade or is it pure bonus?
4. **Reproducibility test in defense** — will the professor try to rebuild the lab from the repo? If yes, `lab/` Vagrantfile must be bulletproof.
5. **Late checkpoint penalty** — if Review 1 or Review 2 is missed due to schedule slippage, is there a recovery path?

---

## 6. Change log

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | Week 7 | Initial document — rubric transcribed from course brief; implicit weights documented; cross-mapped each deliverable to the repo artifacts that serve it. | P1 |
