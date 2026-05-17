# evaluation/ — Metrics, Datasets, Reports

| Field | Value |
|-------|-------|
| Owner | **P4** (Infra · UI · Eval) — with P2 leading ML evaluation per Q5 |
| Status | 📅 Planned · Weeks 9-13 (Gate 3 initial · W10-11 full EVs · W13 informe) |
| Related | [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](../docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) §10, [`docs/use-cases/USE_CASES.md`](../docs/use-cases/USE_CASES.md) §4 (EV-01..EV-07), [`docs/decisions/OPEN_QUESTIONS_RESOLUTION.md`](../docs/decisions/OPEN_QUESTIONS_RESOLUTION.md) §Q5 (tier calibration) |

---

## Purpose

Compute, store and visualize the **three categories of metrics** defined in SAD §10 + EV-01..EV-07 evaluation scenarios from USE_CASES.md.

The deliverables here feed:
1. The **demo headline slide** (3 metrics: TTD, files affected, FP rate).
2. The **NIST 800-61 incident report timeline** (auto-generated per incident).
3. The **technical informe** (precision/recall/F1 per layer, MITRE coverage matrix, ablation, throttle effectiveness).

---

## Stack

| Tool | Role |
|------|------|
| Python 3.11+ | Metrics computation |
| Jupyter Lab | Interactive analysis + notebooks shipped as artifacts |
| pandas + numpy | Data wrangling |
| scikit-learn | Precision-recall curves, ROC, ablation |
| matplotlib + seaborn | Plots for informe |
| Pydantic v2 + `argos_contracts` | Parsing OpenSearch incident docs as `Incident` models |
| OpenSearch Python client | Query historical incidents |

---

## What lives here (planned)

```
evaluation/
├── README.md                       # This file
├── requirements.txt
├── metrics/
│   ├── demo_headline.py            # TTD + files-affected + FP rate (3 numbers for slide)
│   ├── forensic_timeline.py        # NIST 800-61 timeline generator per Incident
│   ├── per_layer.py                # Precision / Recall / F1 per layer
│   ├── mitre_coverage.py           # Coverage matrix builder
│   ├── throttle_effectiveness.py   # EV-03 (Q9 new metric)
│   └── latency.py                  # EV-04 P50/P95
├── datasets/
│   ├── baseline/                   # 48h benign baseline (W3-4 by P4, used by ml/)
│   ├── ransomware/                 # Labeled ransomware alerts (W6-8)
│   └── ground-truth.csv            # Manual labels per alert ID
├── notebooks/
│   ├── 01-fp-baseline.ipynb        # EV-01 false positive rate measurement
│   ├── 02-mitre-coverage.ipynb     # EV-02 heatmap
│   ├── 03-tier-calibration.ipynb   # ← mirrored from ml/; canonical lives here per Q5
│   ├── 04-throttle-eff.ipynb       # EV-03
│   ├── 05-latency.ipynb            # EV-04
│   ├── 06-llm-injection.ipynb      # EV-05 adversarial probes (with llm-triage/)
│   ├── 07-split-brain-policy.ipynb # EV-06
│   └── 08-recovery-outage.ipynb    # EV-07
├── reports/
│   ├── informe-tecnico.md          # Master informe (W13)
│   ├── informe-tecnico.pdf         # Rendered (W13)
│   └── per-incident/               # NIST 800-61 timelines per real demo run
└── tests/
    ├── test_metrics_math.py        # Precision/Recall/F1 with known fixtures
    └── test_timeline_generation.py
```

---

## Contracts (`argos_contracts`)

Read-only consumer:

| Direction | Model | Source |
|-----------|:-----:|--------|
| **Consumes** | `Incident` | OpenSearch index `argos-incidents-{YYYY-MM}` |
| **Consumes** | `NormalizedAlert` | OpenSearch (audit trail) |
| **Consumes** | `MLScore` | OpenSearch (ML scoring history) |
| **Consumes** | `FinalDecision` | Embedded in `Incident` |

Discipline: parse every doc via `Incident.model_validate(opensearch_doc)`. If parsing fails, **the doc is dropped from the metric** and logged — never silently accepted as raw dict (this is what TECHNICAL_DEBT.md TD-01/TD-02 want to harden later).

---

## Metrics by category (per SAD §10 + USE_CASES §4)

### A. Demo headline (3 numbers for slide)

| Metric | Target | Source |
|--------|--------|--------|
| Time-to-Detect (TTD) P95 | <5s (Layer 3) · <30s end-to-end | EV-04 |
| Files affected before containment | <50 of 500 (10%) · 0 for UC-02 | UC-01/02 instrumented runs |
| False Positive Rate per layer | <2% over 24-48h benign baseline | EV-01 |

### B. Forensic timeline (per-incident, NIST 800-61)

Auto-generated from `Incident` + correlated logs:
- Event chain chronological
- Process tree of offender
- Network connections
- User actions correlated
- File hashes (SHA-256)
- Full command line

### C. System evaluation (informe técnico)

| Evaluation | Notebook | Target |
|------------|----------|--------|
| **EV-01** False positive baseline | `01-fp-baseline.ipynb` | <2% per layer |
| **EV-02** MITRE coverage | `02-mitre-coverage.ipynb` | ≥80% of techniques in scope |
| **EV-03** Throttle effectiveness | `04-throttle-eff.ipynb` | ≥90% files preserved during T2 countdown |
| **EV-04** Latency by layer | `05-latency.ipynb` | P95 end-to-end <30s |
| **EV-05** LLM prompt injection | `06-llm-injection.ipynb` | Zero successful injections |
| **EV-06** Split-brain N approvers | `07-split-brain-policy.ipynb` | 100% policy compliance |
| **EV-07** Manager outage recovery | `08-recovery-outage.ipynb` | Zero events lost · recovery <60s |

---

## How to run

```bash
cd evaluation/
pip install -r requirements.txt

# Demo headline (3 numbers, fast)
python -m evaluation.metrics.demo_headline --since 2026-05-13 --to 2026-05-17

# Per-layer P/R/F1 (slow, needs labeled set)
python -m evaluation.metrics.per_layer --labels datasets/ground-truth.csv

# Notebooks (canonical eval artifacts)
jupyter lab notebooks/

# Tests
pytest tests/ -v
```

---

## Tests

| Type | What it validates |
|------|-------------------|
| `test_metrics_math.py` | Precision/Recall/F1 computed correctly against known fixtures |
| `test_timeline_generation.py` | NIST 800-61 timeline includes all required fields (event chain, process tree, network, hashes) |

Target coverage: **scripts + glue, best-effort** (per SAD §13.5 tiered).

---

## Milestones by Gate

| Gate | Week | Deliverable |
|------|:----:|-------------|
| **Gate 1** | 5 | TTD measured manually for UC-01 |
| **Gate 2** | 7 | `metrics/demo_headline.py` working + baseline dataset collected |
| **Gate 3** | 9 | All per-layer metrics + tier calibration notebook (Q5 protocol) + MITRE coverage matrix |
| **Week 10-11** | — | Full EV-01..EV-07 runs · ablation report |
| **Week 13** | — | Informe técnico final (PDF) + per-incident NIST timelines for demo recordings |

---

## Dependencies on other layers

| Needs from | What | When |
|------------|------|------|
| `lab/` | 48h baseline run (no attacks) | W3-4 |
| `ml/` | Trained models for ablation comparison | W7-9 |
| `soar/` | Incident audit logs in OpenSearch | W7+ |
| `attack-simulation/` | 10× UC-01 + UC-02 + UC-03 runs with consistent corpus | W9-11 |
| `llm-triage/` | LLM verdicts with injected payloads for EV-05 | W10 |

---

## References

- SAD §10 (metric categories).
- USE_CASES §4 (EV-01..EV-07 full specs with targets).
- `OPEN_QUESTIONS_RESOLUTION.md` §Q5 (tier calibration protocol — canonical here, mirrored in `ml/`).
- THREAT_MODEL.md §6 (resilience properties — some are measured here, e.g. F-052 race condition floor of 3-5s).
