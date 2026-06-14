# soar/ — SOAR Decision Engine + HITL Approval

| Field | Value |
|-------|-------|
| Owner | **P1 · Enzo Ordoñez Flores** (Lead · LLM/SOAR · Coordinator) |
| Status | 🚧 **Fase 2 entregada** (tier router + notificaciones + Approval API + HITL) · **Fase 3 en curso** (playbooks, consumer, relojes, hook LLM, audit) |
| Related | [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](../docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) §6, ADRs [0003](../docs/decisions/0003-confidence-tiered-automation.md) · [0005](../docs/decisions/0005-notification-channel-abstraction.md) · [0006](../docs/decisions/0006-split-brain-resolution.md) · [0007](../docs/decisions/0007-notification-multichannel-escalation.md) · [0011](../docs/decisions/0011-soar-implementation-reconciliation.md) · [0012](../docs/decisions/0012-response-playbooks.md) · [0013](../docs/decisions/0013-soar-orchestration.md) |

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
| Redis 7+ | State machine persistence + alert stream (`events:normalized`, grupo `soar-router`) |
| asyncio (relojes) | Timeouts, ventana de consolidación y escalación por voz. APScheduler quedó descartado en el review (ADR-0013 §7.6) |
| PyJWT | JWT signing for approval tokens (HS256 v1) |
| Jinja2 | Notification message templates per channel |
| python-telegram-bot, twilio, discord-webhook | Notification channels (per ADR-0007 v2) |
| pytest + respx + fakeredis | Testing |

---

## What lives here (real, Fase 2 + Fase 3)

El árbol planeado original quedó superseded por la implementación contra el
contrato v1.1.0 (ADR-0011). Cada subpaquete lleva su `tests/`.

```
soar/
├── README.md                        # Este archivo
├── conftest.py                      # fixture make_incident (contrato v1.1.0)
├── inventory.py                     # criticidad por host_id (ADR-0013 §7.4)
├── decision_engine/
│   ├── policies.py                  # AUTO_T0 + umbrales (fuente única)
│   ├── tier_router.py               # route(RoutingSignal) -> Tier (cobertura 100%)
│   ├── consumer.py                  # events:normalized: correlación + orquestación
│   ├── containment.py               # apply_decision: los 3 outcomes (ADR-0013 §2.7)
│   ├── scheduler.py                 # 3 relojes asyncio: 60s / 180s / voz 60s
│   └── triage_hook.py               # POST /triage no bloqueante (R-2)
├── approval_api/
│   ├── main.py                      # FastAPI: callbacks Telegram + Twilio DTMF
│   ├── handlers.py                  # two-person rule / conservative-wins
│   ├── consolidation.py             # close_window de la ventana de 60s
│   └── twiml.py                     # TwiML + parseo DTMF
├── notifications/
│   ├── base.py · service.py         # despacho por tier, fail-soft (ADR-0007 v2)
│   └── channels/                    # telegram · discord · twilio_voice
├── playbooks/                       # ADR-0012
│   ├── base.py                      # ResponseExecutor (Protocol) + ExecutionResult
│   ├── builders.py                  # build_throttle/snapshot/isolation/kill
│   ├── simulated.py                 # SimulatedExecutor demo-safe, idempotente
│   └── wazuh.py                     # active-response real (httpx, mockeable)
└── audit/                           # ADR-0013 §2.8
    ├── base.py · logger.py          # AuditEvent + fan-out fail-soft
    ├── memory.py · opensearch.py    # sinks (argos-audit-decisions)
    └── schema.sql                   # DDL para P4 (PostgreSQL 17.5)
```

---

## Contracts (`argos_contracts`)

This layer is the **central hub** — everything flows through it.

| Direction | Model | From / To |
|-----------|:-----:|-----------|
| **Consumes** | `WazuhAlert` | Wazuh manager (raw) |
| **Consumes** | `MLScore` | `ml/` via Redis stream |
| **Consumes** | `TriageResponse` | `llm_triage/` via HTTP |
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

Todo desde la raíz del repo (no hay `requirements.txt`; extras de `pyproject`, ADR-0011 §2.2):

```bash
pip install -e ".[soar,llm,dev]"

# Approval API (necesita Redis local y REDIS_URL en el entorno)
uvicorn soar.approval_api.main:app --port 8003

# Stub del LLM Triage en http://127.0.0.1:8002 (herramienta de P1 para
# ensayar sin el servicio de P2; la capa llm_triage/ es de P2 y no se toca)
python scripts/triage_stub.py

# Inyector demo-safe: un comando por UC, < 30s, audit verificable
python scripts/demo_injector.py uc01 --in-process   # smoke con fakeredis
python scripts/demo_injector.py uc04 --redis-url redis://localhost:6379/0

# Tests
pytest -q          # suite global
pytest soar -q     # solo SOAR
```

Desenlaces esperados del inyector (matriz ADR-0009 §2.6; sale con código 0 si coincide):

| UC | Secuencia | Desenlace |
|----|-----------|-----------|
| `uc01` | L1 T1486 + L2 + L3 en ráfaga (WIN-VICTIM-01) | `EXECUTE_ISOLATION` / `auto-execute` (T0 fast-path) |
| `uc02` | canary sola (Capa 3) | `EXECUTE_ISOLATION` / `auto-execute` (T0) |
| `uc04` | L1 `pg_mass_read` + L2 en LIN-VICTIM-01 (crítico) → 2 approve | `EXECUTE_ISOLATION` / `two-person-rule`, con throttle+snapshot pre-aprobación y `llm_analysis` poblado si el stub corre |
| `uc06` | L1 T1498 (DDoS) | `EXECUTE_ISOLATION` / `auto-execute` (fast-path, sin LLM) |
| `uc07` | L1 + L2 en LIN-VICTIM-01 → 1 reject | `NO_ACTION` / `two-person-rule`; throttle revertido, snapshot conservado |

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
| **Gate 3** | 9 | Full HITL: Telegram + Discord + Twilio per ADR-0007 v2; UC-03 split-brain rehearsable; UC-04 two-person rule; audit log in OpenSearch |
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
