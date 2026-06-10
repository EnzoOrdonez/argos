# PROJECT STATUS — ARGOS

| Field | Value |
|-------|-------|
| Document type | Honest snapshot of what's executed vs what's documented |
| Calendar week | **9** of 14 (entrega movida al 28-jun ≈ semana 12) |
| Project work phase | SOAR Fase 2 entregada; Fase 3 (orquestación) en curso. Resto de capas sin arrancar. |
| Schedule slippage vs original plan | Recuperando: P1 al día con su plan revisado; capas de P2/P3/P4 siguen en folder+README |
| Owner | P1 (Enzo) — updates this file before each `git push` and at every standup |
| Last updated | 2026-06-10 (prórroga + estado Fase 2/3 SOAR) |

---

## Update 2026-06-10 — prórroga y estado SOAR

- **Entrega final movida al sábado 28 de junio de 2026** (anuncio del profesor). Todo doc que diga "13 de junio" está desactualizado en ese punto. Los triggers de fallback de ADR-0010 §5 son relativos al demo y quedan así: **T-21 = 7-jun (ya vencido: aplica a ML temporal §2.3 si P2 no entregó dataset temporal), T-14 = 14-jun (Flask UC-08, P4), T-10 = 18-jun (JWT signing, P1), T-7 = 21-jun (UC-05 cameo, P4)**.
- **SOAR Fase 2 entregada y en verde:** tier router (`tier_router.py` 100% cobertura), Notification Service (Telegram/Discord/Twilio), Approval API, two-person + conservative-wins, ventana de consolidación 60s. `pytest -q` global = **166 passed** (69 contracts + 84 soar + 13 llm_triage); cobertura `soar/` 99%. Reconciliación contra contrato v1.1.0 formalizada en ADR-0011.
- **Fase 3 en curso** sobre ADR-0012 (playbooks) y ADR-0013 (orquestación), ambos Accepted tras review P1 del 2026-06-10 con correcciones (§7 de cada uno).
- **Referencia normativa:** NIST SP 800-61 ya tiene **rev. 3 (abril 2025, alineada a CSF 2.0)**; el corpus RAG y varias referencias del repo citan la rev. 2. Actualizar el corpus es decisión de P2; se deja constancia acá.
- **Deuda de doc:** CONTEXT.md §5 asigna `llm_triage/` a P1; ADR-0011 §7 y ADR-0013 §3 tratan la capa LLM como dominio de P2. Operativamente P1 no toca `llm_triage/` en Fase 3 (solo el hook desde `soar/`).

---

## 0. Purpose

Several processes are mandated by other docs (THREAT_MODEL Risk Register, OPEN_QUESTIONS_RESOLUTION, ADR commitments, evaluation plan). When a doc says "the team does X" but the team hasn't done X yet, the gap should be visible — not hidden in optimistic prose.

This file lists every such commitment with its actual current status and the evidence (or lack of it). Honesty here is more defensible than silence: a grader who notices the gap and then finds it documented openly will judge that as professional maturity. A grader who notices it and finds the docs claiming completion will not.

---

## 1. Implementation status by layer

| Layer | Folder | Status | Evidence |
|-------|--------|:------:|----------|
| Cross-team contracts | `argos_contracts/` | ✅ **Shipped** | 69 validation tests passing (`pytest argos_contracts/tests/test_contracts.py`). `__version__ = "1.1.0"`. No GitHub release tag yet. |
| Layer 1 — Sigma rules | `detection/` | 📅 Folder + README, no rules yet | `detection/sigma-rules/` does not exist. 0 Sigma rules committed. |
| Layer 2 — ML anomaly | `ml/` | 📅 Folder + README, no code | `ml/features/`, `ml/models/`, `ml/consumer/` not created yet. |
| Layer 3 — Canary deception | `deception/` | 📅 Folder + README, no code | No generator, no FIM configs. |
| Layer 4 — LLM Triage | `llm_triage/` | 🚧 Scaffolding only | `llm_triage/llm_client/` has `base.py`, `openai_client.py`, `llama_local.py`, `factory.py` (per ADR-0001 v2) — all skeleton classes, no working API calls. |
| SOAR / HITL | `soar/` | ✅ **Fase 2 shipped** · 🚧 Fase 3 in progress | Tier router + policies, notificaciones 3 canales, Approval API, two-person/conservative-wins, ventana 60s. 84 tests en `soar/`, cobertura 99% (`tier_router.py` 100%). Fase 3 (playbooks, consumer, scheduler, hook LLM, audit, JWT) en curso per ADR-0012/0013. |
| Lab / IaC | `lab/` | 📅 Folder + README, no Vagrantfile | No VMs provisioned yet. |
| UI | `ui/` | 📅 Folder + README, no code | No Streamlit app. |
| Attack simulation | `attack-simulation/` | 📅 Folder + README, no code | No simulator, no Atomic Red Team wrappers. |
| Evaluation | `evaluation/` | 📅 Folder + README, no notebooks | No metrics scripts, no calibration notebook. |

---

## 2. Process commitments (mandated by docs vs actual status)

### D-1 · Tier threshold calibration (Q5)

- **Mandated by:** `OPEN_QUESTIONS_RESOLUTION.md` §Q5 + `SOLUTION_ARCHITECTURE_DOCUMENT.md` §15 item 5 (closed).
- **Protocol:** dataset of ~100 ransomware alerts + ~500 benign alerts, plot precision-recall per layer, set thresholds to optimize tier semantics (T0 precision ≥99%, T1 P≥90%/R≥80%, T2 P≥70%/R≥95%, T3 R≥99%).
- **Deliverable:** `evaluation/tier_calibration.ipynb`.
- **Status:** ❌ **Not started.** No notebook exists. No dataset collected. Scheduled for Gate 3 (Week 9 original; realistic estimate W10-11 given current slippage).
- **Implication for the thresholds 0.95/0.80/0.60/0.40 currently in docs:** they remain **placeholder values**. The closure of SAD §15 item 5 was a *documentation closure* (the protocol is defined) — the empirical calibration has not run.

### D-2 · Pre-demo red-team session

- **Mandated by:** `THREAT_MODEL.md` §9.
- **Description:** one team member attempts to break the system before the live exposition.
- **Status:** ❌ **Not scheduled.** No owner assigned.

### D-3 · Sigma upstream PRs (bonus killer)

- **Mandated by:** `PROJECT_BRIEF.md` §10 + Risk Register P-007.
- **Target:** 2-4 Sigma rules accepted in `SigmaHQ/sigma`.
- **Status:** ❌ **0 PRs submitted.** No rules written yet (depends on Layer 1 implementation starting). This is P-007 risk, scored Low because the bonus is not core deliverable.

### D-4 · LLM API cost tracking

- **Mandated by:** `ADR-0001` v2 (target <$20 USD total con GPT-4o-mini) + `data-handling.md` §4 (audit log per call con `cost_estimated_usd`).
- **Status:** ❌ **Not implemented.** No `argos-llm-calls-{YYYY-MM}` index, no API calls made yet (the only LLM-related code is the abstract `LLMClient` interface in `llm_triage/llm_client/`). Cost-to-date: **$0**.
- **Action when implemented:** add a row here with monthly burn-rate.

### D-5 · `argos_contracts` versioning

- **Mandated by:** `CONTRACTS_SPECIFICATION.md`.
- **Status:** ✅ `__version__ = "1.1.0"` in `argos_contracts/__init__.py`. TD-01 (`Incident.host` typed as `HostInfo`) y TD-02 (`FinalDecision` con `Literal[...]`) ya están **resueltos** en código — `TECHNICAL_DEBT.md` fue eliminado del repo en consecuencia. Tag de release pendiente en GitHub.

### D-6 · Contract tests count

- **Mandated by:** `CONTRACTS_SPECIFICATION.md` (target ≥30 tests).
- **Status:** ✅ **69 tests passing** (`pytest argos_contracts/tests/test_contracts.py --collect-only -q` returns 69). Well above the target.
- **Note:** los 5 tests adicionales sobre los 64 originales validan el tightening de tipos introducido en v1.1.0.

### D-7 · Per-layer test coverage targets (SAD §13.5 tiered)

- **Mandated by:** `SOLUTION_ARCHITECTURE_DOCUMENT.md` §13.5 (tiered per module category, ≥60% for critical paths, ≥50% for important, smoke-only for UI/scripts).
- **Status:** 🚧 `soar/` mide **99%** (Fase 2, `tier_router.py` 100% por convención ADR-0011 §4). El resto de capas no-contracts sigue en **0%** porque no tienen código.

### D-8 · External heartbeat monitor (SAD §13.6)

- **Mandated by:** `SOLUTION_ARCHITECTURE_DOCUMENT.md` §13.6 (bash + cron checks Wazuh manager, FastAPI, Redis, OpenSearch every 30s).
- **Status:** ❌ **Not implemented.** Depends on `lab/` being up first.

---

## 3. Course checkpoints status (per `EVALUATION_CRITERIA.md` §2)

| Checkpoint | Week | What's expected | Reality | Plan |
|-----------|:----:|----------------|---------|------|
| Review 1 | 5 | Initial architecture + first signs of implementation | ⚠️ Architecture and contracts shipped; no implementation | Walked into with the architectural artifacts + contracts as evidence |
| Review 2 | **7 (now)** | Mid-project progress; layers operational; first metrics | ⚠️ **Use cases just finalized; no layer is operational** | Walk in honestly with the doc-heavy approach + ADR-0007 v2 fully designed + scope cut plan |
| Review 3 | 9 | Pre-demo readiness; full stack integrated | 📅 Pending; realistic target is a partial integration of L1+L3+SOAR for UC-01+UC-02 |
| Final exposition | **28 jun 2026** (prórroga 2026-06-10; antes 13-jun) | Working demo + Informe + Presentación | 📅 Pending; UC-01, UC-02, UC-04 are the strongest candidates for live demo if scope must be cut |

---

## 4. Scope-cut order (if calendar pressure forces tradeoffs)

If the implementation window cannot deliver all 8 UCs + all 7 EVs + all 4 channels by the deadline, the sacrifice order — committed here so nobody has to improvise — is:

| Priority | Item | Reasoning |
|:---:|------|-----------|
| Must-have | UC-01 (classic ransomware) | Demo opens with canonical case; si falla, todo el demo falla |
| Must-have | UC-02 (canary deception) | 1.5 min, muestra zero-FP visualmente, bajo riesgo de integración |
| Must-have | UC-04 (PostgreSQL + two-person rule) | Compliance vocabulary + governance — visible para evaluadores no técnicos |
| Must-have | UC-06 (DDoS volumetric, ADR-0008) | Demuestra cobertura multi-vector — argumento XDR profesional |
| Must-have | UC-07 (SELECT masivo FP cancelado, ADR-0008) | **Pieza clave del HITL** — humano cancela contención cuando ML duda. Diferenciación clave vs SIEM |
| Strong nice-to-have | UC-03 (split-brain ransomware) | Centerpiece si ML llega a tiempo; si no, mocked data |
| Strong nice-to-have | UC-08 (SQL injection, ADR-0008) | OWASP Top 10 #1 — refuerza argumento XDR pero recortable si presiona tiempo |
| Strong nice-to-have | UC-05 (stealth attack agent-kill) | Per decisión usuario 2026-05-24: mantener en vivo, no degradar a video |
| Cuttable | EV-03 throttle effectiveness, EV-06 split-brain N approvers | Synthetic tests, deliverable como números en informe sin live runs |
| Cuttable | Sigma upstream PRs (P-007 bonus) | Marcado como bonus explícitamente, low risk-impact en P-007 |
| Cuttable | Twilio Voice channel | Last en ADR-0007 v2 sacrifice order; Telegram + Discord es el bottom line |

---

## 5. Change log

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | Week 7 (calendar) | Initial honest status document. Closes the gap between what the docs claim and what the repo executes. (Fila truncada en el archivo original; completada el 2026-06-10 sin cambiar su sentido.) | P1 |
| 1.1 | 2026-06-10 | Prórroga al 28-jun + triggers ADR-0010 §5 recalculados; SOAR Fase 2 shipped (166 tests global, soar 99%); ADR-0012/0013 Accepted tras review; D-7 actualizado; nota NIST 800-61r3 y deuda de ownership llm_triage. | P1 |