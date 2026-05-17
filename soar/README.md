# soar/ — SOAR Decision Engine + HITL Approval

| Field | Value |
|-------|-------|
| Owner | **P1** (Lead · LLM/SOAR · Coordinator) |
| Status | 📅 Planned · Weeks 4-9 (Gate 2 decision engine v1 · Gate 3 full HITL) |
| Related | [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](../docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) §6, ADRs [0003](../docs/decisions/0003-confidence-tiered-automation.md) · [0005](../docs/decisions/0005-notification-channel-abstraction.md) · [0006](../docs/decisions/0006-split-brain-resolution.md) · [0007](../docs/decisions/0007-notification-multichannel-escalation.md) |

---

## Purpose

The **brain** that fuses Layer 1/2/3 signals into tiered decisions and orchestrates the response. The Decision Engine is the only component allowed to trigger containment playbooks.

**Critical invariant (R-2 from THREAT_MODEL.md):** the LLM (Layer 4) is **never on the containment critical path**. SOAR decides from Layers 1-3 alone; LLM only enriches the analyst view.

This layer also owns the **state machine** for the human-in-the-loop approval flow (T2/T3) including conservative-wins split-brain resolution (ADR-0006) and multi-channel escalation (ADR-0007).

---

## Stack

| Tool | Role |
|------|------|
| Python 3.11+ + Pydantic v2 | Service + I/O validation via `argos_contracts` |
| FastAPI | Approval API (`POST /approval/{token}`) + health |
| Redis 7+ | State machine persistence + alert stream |
| APScheduler | Timeouts, consolidation windows, escalation triggers |
| PyJWT | JWT signing for approval tokens (HS256 v1) |
| Jinja2 | Notification message templates per channel |
| python-telegram-bot, twilio, slack-sdk | Notification channels (per ADR-0007) |
| pytest + respx + fakeredis | Testing |

---

## What lives here (planned)

```
soar/
├── README.md                       # This file
├── requirements.txt
├── decision_engine/
│   ├── tier_classifier.py          # Layer signals + scores → Tier (T0..T3) per ADR-0003
│   ├── fusion.py                   # Layer combination rules (SAD §6.2 table)
│   ├── criticality_router.py       # production-critical host → two-person rule (Q2)
│   └── state_machine.py            # Incident state transitions in Redis
├── approval/
│   ├── api.py                      # FastAPI router: POST /approval/{token}
│   ├── jwt_signer.py               # JWT generation + validation (HS256)
│   ├── consolidation.py            # 60s window (ADR-0006) + conservative-wins
│   └── timeout.py                  # 3-min T2 timeout (ADR-0003 Q9)
├── notification/
│   ├── base.py                     # NotificationChannel ABC (ADR-0005)
│   ├── email_channel.py            # Post-facto summary (ADR-0007 §"role degradation")
│   ├── telegram_channel.py         # Primary (ADR-0007)
│   ├── ntfy_channel.py             # Backup push (ADR-0007)
│   ├── slack_channel.py            # SOC visibility (ADR-0007)
│   ├── twilio_voice_channel.py     # Escalation t=60s (ADR-0007)
│   └── orchestrator.py             # EscalationOrchestrator (which channel when)
├── playbooks/
│   ├── host_isolation.py           # iptables / NetFirewallRule
│   ├── process_kill.py             # SIGKILL / Stop-Process
│   ├── process_throttle.py         # cpulimit / ionice / rate-limit (T2 active mitigation)
│   ├── disk_snapshot.py            # VSS / dd
│   └── audit_logger.py             # Append-only JSON → OpenSearch
└── tests/
    ├── test_tier_classifier.py     # All 4 tiers covered with synthetic alerts
    ├── test_state_machine.py
    ├── test_consolidation.py       # Split-brain scenarios
    ├── test_jwt.py
    ├── test_channels/*.py
    └── integration/
        ├── test_t0_auto_isolate.py
        ├── test_t2_full_flow.py    # Throttle + email + approve → isolate
        └── test_t2_split_brain.py  # UC-03 scenario
```

---

## Contracts (`argos_contracts`)

This layer is the **central hub** — everything flows through it.

| Direction | Model | From / To |
|-----------|:-----:|-----------|
| **Consumes** | `WazuhAlert` | Wazuh manager (raw) |
| **Consumes** | `MLScore` | `ml/` via Redis stream |
| **Consumes** | `TriageResponse` | `llm-triage/` via HTTP |
| **Produces** | `NormalizedAlert` | Internal, persisted to OpenSearch for audit |
| **Produces** | `Incident` | Persisted to Redis (`incident:{id}`) and OpenSearch (`argos-incidents-{YYYY-MM}`) per `OPEN_QUESTIONS_RESOLUTION.md` §Q4 |
| **Produces** | `ProposedAction` | Embedded in `Incident.proposed_actions` |
| **Produces** | `ApprovalRequest` | Sent to all configured `NotificationChannel`s |
| **Consumes** | `ApprovalResponse` | From channels via API endpoints (JWT-validated) |
| **Produces** | `FinalDecision` | Embedded in `Incident.final_decision` after consolidation |
| **Uses enums** | `Tier`, `IncidentState`, `Criticality`, `ApprovalDecision`, `ApproverStatus`, `ActionType`, `Severity`, `Layer`, `NotificationChannelType` | All pervasively |

Strict typing **everywhere**. Pydantic v2 `model_validate_json` on every Redis read; `model_dump_json` on every write. No raw dicts crossing module boundaries.

---

## Tier classification rules (per ADR-0003 + SAD §6.2)

| Triggered layers | Tier | Action |
|------------------|:----:|--------|
| Layer 3 alone (canary) | T0 | Immediate isolation |
| Layers 1+2+3 simultaneous | T0 | Immediate isolation + snapshot |
| Layers 1+2 corroborate (no canary) | T1 | Immediate isolation + snapshot |
| Layer 1 alone (high-fidelity rule) | T2 | Throttle + snapshot **now**, isolation pending 3-min approval |
| Layer 2 alone (high score, ≥0.74) | T2 | Same as above |
| Layer 1 alone (experimental rule) | T3 | LLM-enriched notification only |
| Layer 2 medium score (0.40-0.60) | T3 | Same as above |

**Override per `Criticality.PRODUCTION_CRITICAL`** (Q2 + ADR-0003 update): any tier on a production-critical host routes through **two-person rule** regardless. Throttle + snapshot still fire immediately (non-destructive). See UC-04.

---

## How to run

```bash
cd soar/
pip install -r requirements.txt

# Run API service (requires Redis + lab/)
uvicorn soar.approval.api:app --host 0.0.0.0 --port 8080 --reload

# Tests
pytest tests/ -v
pytest tests/integration/ -v --redis-host=localhost
```

---

## Tests

| Type | What it validates | Target coverage |
|------|-------------------|:---------------:|
| `test_tier_classifier.py` | All 4 tiers covered with synthetic `NormalizedAlert`s × all `MLScore` combinations | **≥60%** (critical-path, SAD §13.5) |
| `test_state_machine.py` | All transitions valid; invalid transitions raise; state survives Redis restart (F-050) | ≥60% |
| `test_consolidation.py` | UC-03 split-brain pattern (2 approve · 1 reject · 1 timeout) → conservative-wins → execute |  |
| `test_jwt.py` | Token expires at 5min; single-use enforced; tampered tokens rejected |  |
| `integration/test_t0_auto_isolate.py` | UC-01 happy path end-to-end with stubbed Wazuh |  |
| `integration/test_t2_full_flow.py` | T2 full flow: throttle + multi-channel notify + JWT click → isolate |  |
| `integration/test_t2_split_brain.py` | UC-03 demo scenario reproducible deterministically |  |

---

## Milestones by Gate

| Gate | Week | Deliverable |
|------|:----:|-------------|
| **Gate 1** | 5 | n/a — focus on Layer 1 |
| **Gate 2** | 7 | Decision Engine v1: tier classifier + state machine + email channel (legacy) wired end-to-end; UC-01 + UC-02 work |
| **Gate 3** | 9 | Full HITL: Telegram + ntfy + Slack + Twilio per ADR-0007; UC-03 split-brain rehearsable; UC-04 two-person rule; audit log in OpenSearch |
| **Week 10-11** | — | Hardening + edge cases (F-050, F-051); throttle effectiveness metric (EV-03) |

---

## Threats this layer must defend against (T-060..T-069 per THREAT_MODEL §3.7)

| Threat | Mitigation owned here |
|--------|----------------------|
| T-060 JWT interception | 5-min expiry, single-use, TLS only (`approval/jwt_signer.py`) |
| T-061 fake email response | Only accept via tokenized URL, not email reply parsing |
| T-062 compromised approver email | Conservative-wins (ADR-0006) — single reject can't block legitimate isolation |
| T-063 token replay | Token bound to `incident_id`, reuse rejected |
| T-064 defensive DoS via flooding | Per-incident dedup + rate limit on email send |
| T-066 audit log tampering | Append-only OpenSearch index settings + daily snapshot |
| T-067 SIM-swap | Cross-channel notification when new session detected (ADR-0007 design) |
| T-068 Twilio caller-ID spoofing | DTMF callbacks correlated with active outbound call only |
| T-069 Telegram bot token leak | Bot only `send`, responses validated against expected `chat_id` |

---

## References

- SAD §6 (full SOAR spec).
- ADR-0003 (confidence-tiered automation + criticality override).
- ADR-0005 (NotificationChannel abstraction).
- ADR-0006 (conservative-wins + JWT rotation policy).
- ADR-0007 (multi-channel escalation chain).
- `OPEN_QUESTIONS_RESOLUTION.md` §Q4 (Incident schema) + §Q9 (T2 timeout = 3min).
- THREAT_MODEL.md §3.7 (approval system threats).
