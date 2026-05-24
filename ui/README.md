# ui/ — Analyst UI + Approval Workflow Console

| Field | Value |
|-------|-------|
| Owner | **P4 · Diego Jara** (Infra · UI · Eval) |
| Status | 📅 Planned · Weeks 6-9 (Gate 2 v1 · Gate 3 Approval Console) |
| Related | [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](../docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) §9.2, [`docs/decisions/0006-split-brain-resolution.md`](../docs/decisions/0006-split-brain-resolution.md), [`docs/use-cases/USE_CASES.md`](../docs/use-cases/USE_CASES.md) UC-03 (centerpiece visual) |

---

## Purpose

Two UI surfaces with different audiences:

1. **Streamlit Analyst UI** — per-incident triage. Three tabs: Alert Inspection, **Approval Workflow Console**, Audit & Forensics.
2. **OpenSearch Dashboards** — SOC-wide visibility. Three dashboards: Alerts Timeline, MITRE Coverage Heatmap, Layer Performance.

The **Approval Workflow Console is the visual centerpiece of the demo** — it turns the abstract conservative-wins logic of UC-03 into something visible, defensible in audit, and dramatic on-screen.

---

## Stack

| Tool | Role |
|------|------|
| Streamlit 1.30+ | Analyst UI |
| `streamlit-autorefresh` | Polling Redis state every 1-2s |
| redis-py | Reading `Incident` state |
| Plotly / Altair | Charts (decision matrix, action timeline) |
| Pydantic v2 + `argos_contracts` | Type-safe `Incident` parsing |
| OpenSearch Dashboards | JSON-exported dashboards in version control |
| pytest + `streamlit.testing.v1` | Smoke tests |

---

## What lives here (planned)

```
ui/
├── README.md                   # This file
├── requirements.txt
├── streamlit_app/
│   ├── app.py                  # Entry point (tabs: Alert Inspection / Approval Console / Audit)
│   ├── pages/
│   │   ├── 01_alert_inspection.py
│   │   ├── 02_approval_console.py   # ← CENTERPIECE
│   │   └── 03_audit_forensics.py
│   ├── components/
│   │   ├── incident_card.py
│   │   ├── decision_matrix.py       # Per-approver row with live status
│   │   ├── countdown_clock.py       # 3-min HITL + 60s consolidation
│   │   ├── action_timeline.py
│   │   └── final_decision_banner.py
│   └── lib/
│       ├── redis_subscriber.py
│       └── incident_loader.py
├── opensearch-dashboards/
│   ├── alerts-timeline.ndjson
│   ├── mitre-heatmap.ndjson
│   └── layer-performance.ndjson
└── tests/
    ├── test_smoke.py                # Streamlit doesn't crash on cold start
    ├── test_decision_matrix.py      # Right number of rows per approver count
    └── test_dashboard_json.py       # OpenSearch dashboard JSON is valid
```

---

## Contracts (`argos_contracts`)

This layer is **read-only** w.r.t. contracts — it never writes any model, only displays them.

| Direction | Model | Source |
|-----------|:-----:|--------|
| **Consumes** | `Incident` | Redis key `incident:{id}` (full JSON dump) |
| **Consumes** | `ApproverState` | Embedded in `Incident.approvers` — drives the Decision Matrix rows |
| **Consumes** | `ConsolidationWindow` | Embedded in `Incident` — drives the 60s countdown component |
| **Consumes** | `FinalDecision` | Embedded in `Incident.final_decision` — drives the banner at the end |
| **Uses enums** | `Tier`, `IncidentState`, `ApproverStatus` | For color-coding (T0 red, T2 amber; pending yellow, approved green, rejected red, timeout grey) |

**Discipline:** UI must never branch on string literals — always parse via the enums. `FinalDecision.outcome`, `policy_applied` y `execution_status` ya son `Literal[...]` desde `argos_contracts` v1.1.0, así que cualquier valor inesperado falla en construcción, no en runtime.

---

## Approval Workflow Console layout (per SAD §9.2.2)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  [Incident Card]              [Decision Matrix]         [System Logic]   │
│  Tier T2 (amber)              Approver  Status  Latency Current state    │
│  WIN-VICTIM-01                Enzo     🔴 rej   18s     WAITING_CONFLICT │
│  T1083                        P2       🟢 app   35s     ⏱ 0:42 / 1:00   │
│  LLM analysis ▼               P3       🟢 app   52s     ⚠ CONFLICT       │
│                               P4       ⚫ timeout —     Policy: cons-wins │
│                                                                          │
│  [Action Timeline]                                                       │
│  alert → emails sent → 1st response → conflict → window closed → execute │
└──────────────────────────────────────────────────────────────────────────┘
```

Color palette: T0/T1 red, T2 amber, T3 blue, executed green, rejected red, timeout grey.

Live updates: `streamlit-autorefresh` polls Redis every 1-2 seconds. Rows highlight on new response (2s animation).

---

## How to run

```bash
cd ui/
pip install -r requirements.txt

# Streamlit Analyst UI (requires Redis + soar/)
streamlit run streamlit_app/app.py

# Import OpenSearch Dashboards (requires OpenSearch + lab/)
curl -X POST "${OPENSEARCH_DASHBOARDS_URL}/api/saved_objects/_import" \
  -H "osd-xsrf: true" \
  --form file=@opensearch-dashboards/alerts-timeline.ndjson

# Tests
pytest tests/ -v
```

---

## Tests

| Type | What it validates |
|------|-------------------|
| `test_smoke.py` | Streamlit starts without errors, default page renders |
| `test_decision_matrix.py` | Decision Matrix renders the right number of rows per approver count (2, 4, 8) |
| `test_dashboard_json.py` | All `*.ndjson` parse as valid OpenSearch saved objects |

Target coverage: **smoke tests only** (per SAD §13.5 tiered targets — UI is "best-effort, smoke tests only").

---

## Milestones by Gate

| Gate | Week | Deliverable |
|------|:----:|-------------|
| **Gate 1** | 5 | n/a |
| **Gate 2** | 7 | Streamlit v1: Alert Inspection tab functional with raw alert + LLM analysis split view |
| **Gate 3** | 9 | **Approval Workflow Console live for UC-03 demo**; OpenSearch dashboards imported and operational; Audit & Forensics tab queryable |
| **Week 10-11** | — | Visual polish for demo; pre-rehearsal animations tested; backup video recording |

---

## Demo-specific requirements (UC-03 centerpiece)

For the live exposition:

- Decision Matrix must update **within 2s** of any approver click.
- "CONFLICT DETECTED" banner must appear the moment the first opposite-sign response arrives.
- Countdown clock must tick visibly (1s resolution) for the 60s consolidation window.
- Final decision banner must show: `"2 approve · 1 reject · 1 timeout · conservative-wins applied"` with the policy applied verbatim from `Incident.final_decision.policy_applied`.

If any of the above fails, fallback to pre-recorded video (per `THREAT_MODEL.md` §7 demo contingency).

---

## References

- SAD §9.2 (full UI spec).
- ADR-0006 (split-brain visualization is the centerpiece).
- ADR-0007 (multi-channel — UI shows which channel each approver used).
- USE_CASES UC-03 (centerpiece scenario the Approval Console serves).
- `argos_contracts` v1.1.0 cerró TD-01 (`Incident.host: HostInfo`) y TD-02 (`FinalDecision` literal types). UI puede branchar directamente sobre los valores con type-safety.
