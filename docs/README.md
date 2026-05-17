# ARGOS — Documentation

**Adaptive Ransomware Guard with Orchestrated Surveillance**

Layered ransomware detection and response system combining rule-based detection (Sigma + Wazuh), ML anomaly detection, deception (canary files), and LLM-assisted triage with human-in-the-loop SOAR.

> Tópicos Avanzados de Ciberseguridad · Universidad de Lima · 2026-1

---

## Where to start

| If you are... | Read this first |
|---------------|-----------------|
| Evaluating the project in 90 seconds | [`PROJECT_BRIEF.md`](./PROJECT_BRIEF.md) |
| A new team member onboarding | [`CONTEXT.md`](./CONTEXT.md) |
| An architect reviewing the design | [`architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](./architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) |
| Trying to understand security posture | [`architecture/THREAT_MODEL.md`](./architecture/THREAT_MODEL.md) |
| Looking for a specific design decision | [`decisions/README.md`](./decisions/README.md) |
| Wanting to see the system visually | [`architecture/architecture_diagram.html`](./architecture/architecture_diagram.html) |
| Wanting to know what the demo will show | [`use-cases/USE_CASES.md`](./use-cases/USE_CASES.md) |

---

## Documentation map

### Top level

- **`PROJECT_BRIEF.md`** — One-page executive summary. The fastest way to understand what ARGOS is and why it matters.
- **`CONTEXT.md`** — Complete team onboarding: vision, scope, stack, division of labor, plan, conventions, repo structure.

### Architecture

- **`architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`** — Solution Architecture Document (SAD). Full technical specification of every component, interaction, and cross-cutting concern. The canonical reference for "how does ARGOS work".
- **`architecture/architecture_diagram.html`** — Interactive architecture diagram with all 4 detection layers, SOAR, LLM triage, response automation, and approval workflow visualized. Open in any browser.
- **`architecture/THREAT_MODEL.md`** — STRIDE security analysis (~50 threats), FMEA reliability analysis, project Risk Register, and 10 testable resilience properties.

### Decisions

- **`decisions/README.md`** — Index of all Architecture Decision Records (ADRs) with status and summary.
- **`decisions/0001`** through **`0006`** — Individual ADRs documenting specific architectural decisions with rationale, alternatives considered, and consequences.
- **`decisions/OPEN_QUESTIONS_RESOLUTION.md`** — Closure document resolving minor open questions in batch (Q1-Q9), including the corrected T2 timeout behavior.

### Use cases

- **`use-cases/USE_CASES.md`** — 5 demo scenarios (UC-01 through UC-05) with detailed narration scripts + 7 evaluation scenarios (EV-01 through EV-07) for system robustness testing.

### Team

- **`team/standup-template.md`** — Template for weekly Monday standups.

---

## Project status

| Phase | Status |
|-------|--------|
| Architecture & design | ✅ Complete (Week 1) |
| Threat modeling | ✅ Complete (Week 1) |
| Use case specification | ✅ Complete (Week 1) |
| Implementation | 🚧 Starting Week 2 |
| Evaluation | 📅 Weeks 9-12 |
| Demo & exposition | 📅 Week 14 |

---

## Quick stats

- **Architecture:** 4 detection layers + SOAR + LLM triage + Approval Workflow Console.
- **Stack:** Wazuh, OpenSearch, Sigma, Sysmon, auditd, Atomic Red Team, Caldera, scikit-learn, FastAPI, Streamlit, Redis, DeepSeek/Qwen API.
- **Documentation:** ~210 KB across 14 documents before any code written.
- **Threats analyzed:** ~50 via STRIDE + FMEA.
- **Architecture decisions:** 7 ADRs (6 accepted, 1 rejected) + 9 closure resolutions.

---

## Team

| Role | Owner |
|------|-------|
| Lead / LLM-SOAR / Coordinator | Enzo Cáceres (P1) |
| ML Engineer | P2 (TBD) |
| Detection Engineer | P3 (TBD) |
| Infrastructure / UI / Evaluation | P4 (TBD) |

---

## License

TBD before public release at end of course (recommended: MIT).
