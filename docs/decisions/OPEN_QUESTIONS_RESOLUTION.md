# OPEN QUESTIONS RESOLUTION — closure before use-case definition

**Document type:** Decision log (closing minor open questions)
**Version:** 1.0
**Date:** Week 1
**Owner:** P1 (Enzo)
**Status:** Approved

---

## Purpose

After kickoff documentation (PROJECT_BRIEF, SAD, THREAT_MODEL, ADRs 0001-0006), several smaller decisions remained unresolved. This document closes them in one batch so we can proceed to use-case definition and implementation. Each item is too small for a full ADR but too important to leave unresolved.

---

## Q1. Approval Workflow Console — ownership

**Decision:** P4 builds the Streamlit Console with detailed specs delivered by P1.

**Rationale:** P4 owns Streamlit work overall; consistent ownership prevents fragmented UI patterns. P1 delivers a written spec including JSON schema (see Q4 below), state diagram, and acceptance criteria before P4 starts work.

**Handoff:** P1 delivers specs at end of Week 6. P4 implements Weeks 7-8. Joint review Week 8 Friday.

---

## Q2. "Production critical" host for two-person rule demo

**Decision:** The Linux Ubuntu Server VM in the lab hosts a **PostgreSQL 15** instance with synthetic but representative data — this is the concrete asset ARGOS defends. The VM is tagged in Wazuh with `criticality=production-critical`, and that tag triggers the two-person rule for any containment action.

**Rationale:** Naming a concrete defended asset turns the abstract "production database server" into something a viewer can point at on the screen. PostgreSQL was chosen because it is the de-facto reference for relational databases in modern infrastructure, it is OSS, and the simulator can target its data directory (`/var/lib/postgresql`) and dump exports (`*.sql`) as plausible ransomware targets. Adds vocabulary (compliance, governance, four-eyes principle) to the demo narrative.

**Implementation:**

- `lab/` provisioning installs PostgreSQL 15 on the Linux VM during `vagrant up` and seeds it with a synthetic schema `argos_demo_prod` containing tables that look like a small business backend (employees, payroll, customers, invoices, payments — no real PII).
- The same provisioning script also dumps `pg_dump` exports to `/var/backups/postgres/*.sql` so the canary FIM and the ransomware simulator have file-level targets to interact with.
- The host is tagged in Wazuh with `criticality=production-critical` so the Decision Engine routes any containment through the two-person approval path regardless of tier (ADR-0003 override).
- `.env.example` exposes `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` so other modules can connect for evaluation queries; secrets never leave the lab subnet.

**Demo storyline:** "Our crown-jewel asset is this PostgreSQL database — payroll, customers, invoices. When the attack reaches its host, the system requires two approvers — even at T1 confidence, because some actions are too costly to delegate to a single human."

---

## Q3. Testing coverage target — moderation

**Decision:** Replace "70% coverage target" with tiered targets:

| Module category | Target | Rationale |
|-----------------|--------|-----------|
| Decision Engine, LLMClient, Approval API | ≥60% line coverage | Critical-path code, must be tested |
| ML feature extractors, Sigma rule converters | ≥50% line coverage | Important but more straightforward |
| Streamlit UI, scripts, glue code | Best-effort, smoke tests only | Low ROI for unit tests |
| Integration tests | At least 1 happy-path + 1 error-path per layer interface | Confidence in component boundaries |
| End-to-end | At least 3 scenarios in CI (T0, T2, split-brain) | Demo confidence |

**Rationale:** Honest assessment of 16h/week × 4 people × 14 weeks budget. Higher coverage targets sound impressive but are unrealistic and would steal time from implementation, demo polish, and informe writing. Documented modesty here is a feature, not a bug.

**Update:** SAD §13.5 to reflect this.

---

## Q4. Incident & data contract conventions

### Q4.1 Incident naming convention

**Decision:** `INC-{YYYY}-{MM}-{DD}-{NNN}` where `NNN` is a daily-reset sequence number, zero-padded to 3 digits.

Example: `INC-2026-04-30-001`, `INC-2026-04-30-002`, `INC-2026-05-01-001`.

**Implementation:** Decision Engine generates ID at incident creation time; counter persisted in Redis key `incidents:counter:{YYYY-MM-DD}` with daily TTL.

### Q4.2 Incident JSON schema (Decision Engine ↔ Redis ↔ Streamlit contract)

This is the schema that P1's backend writes to Redis and P4's Streamlit reads. Defining it now prevents integration friction in Weeks 7-8.

```json
{
  "incident_id": "INC-2026-04-30-001",
  "created_at": "2026-04-30T15:32:14.123Z",
  "updated_at": "2026-04-30T15:33:15.456Z",
  "tier": "T2",
  "state": "EXECUTED",
  "host": {
    "id": "WIN-VICTIM-01",
    "criticality": "standard",
    "ip": "10.0.0.21",
    "os": "Windows 10"
  },
  "alert_summary": {
    "title": "Suspicious file enumeration on host WIN-VICTIM-01",
    "technique_mitre": "T1083",
    "severity_score": 0.72,
    "triggering_layers": ["layer_1"],
    "raw_alert_id": "wazuh-alert-12345"
  },
  "llm_analysis": {
    "technique_mitre": "T1083",
    "confidence": 0.85,
    "severity": "medium",
    "runbook_applicable": "NIST 800-61 §3.4 Containment",
    "recommended_action": "Isolate host pending forensic review",
    "indicators_to_correlate": ["unusual_file_enum_pattern", "non_business_hours_activity"],
    "llm_backend": "deepseek-v3",
    "generated_at": "2026-04-30T15:32:18.789Z"
  },
  "proposed_actions": [
    {"id": "act-001", "type": "host_isolation", "target": "WIN-VICTIM-01", "reversible": true},
    {"id": "act-002", "type": "disk_snapshot", "target": "WIN-VICTIM-01", "reversible": true}
  ],
  "approvers": [
    {
      "email": "enzo@demo.local",
      "role": "it_lead",
      "status": "rejected",
      "responded_at": "2026-04-30T15:32:32.000Z",
      "latency_seconds": 18,
      "channel": "email"
    },
    {
      "email": "p2@demo.local",
      "role": "analyst",
      "status": "approved",
      "responded_at": "2026-04-30T15:32:49.000Z",
      "latency_seconds": 35,
      "channel": "email"
    },
    {
      "email": "p3@demo.local",
      "role": "analyst",
      "status": "approved",
      "responded_at": "2026-04-30T15:33:06.000Z",
      "latency_seconds": 52,
      "channel": "email"
    },
    {
      "email": "p4@demo.local",
      "role": "analyst",
      "status": "timeout",
      "responded_at": null,
      "latency_seconds": null,
      "channel": "email"
    }
  ],
  "consolidation_window": {
    "started_at": "2026-04-30T15:32:32.000Z",
    "duration_seconds": 60,
    "ended_at": "2026-04-30T15:33:32.000Z",
    "conflict_detected": true
  },
  "final_decision": {
    "outcome": "EXECUTE_ISOLATION",
    "policy_applied": "conservative-wins",
    "rationale": "2 approve, 1 reject, 1 timeout — conservative-wins applied per ADR-0006",
    "executed_at": "2026-04-30T15:33:33.000Z",
    "execution_status": "success"
  }
}
```

**Schema versioning:** include `"schema_version": "1.0"` field at root for forward compatibility. Breaking changes increment major version.

**Storage:**
- Redis key: `incident:{incident_id}` (full JSON, TTL 24h).
- OpenSearch index: `argos-incidents-{YYYY-MM}` (long-term, queryable).

---

## Q5. Tier threshold calibration protocol (Week 9)

**Decision:** Define a concrete protocol now so Week 9 isn't improvised.

**Steps:**

1. **Collect labelled dataset (Weeks 6-8).**
   - Run Atomic Red Team and custom ransomware simulator against lab. Each run produces alerts with ground-truth label `ransomware`.
   - Run benign baseline (normal user activity, software installs, file operations) for 48h. Alerts produced are labelled `benign`.
   - Target: ~100 ransomware alerts, ~500 benign alerts.

2. **Compute confidence scores per alert (Week 9).**
   - For each alert, compute the system's confidence score using current scoring logic from each layer.
   - Plot precision-recall curve at varying thresholds.

3. **Set thresholds to optimize tier semantics.**
   - **T0 threshold (≥0.95):** target precision ≥99% on labelled set. If current threshold doesn't reach this, raise it.
   - **T1 threshold (0.80):** target precision ≥90%, recall ≥80%.
   - **T2 threshold (0.60):** target precision ≥70%, recall ≥95%.
   - **T3 threshold (0.40):** target recall ≥99% (catches almost everything).

4. **Document calibration in informe.**
   - Include precision-recall curves.
   - Justify each threshold with the metric it optimizes.
   - Acknowledge: thresholds tuned on lab dataset, would require recalibration in production.

**Deliverable:** notebook `evaluation/tier_calibration.ipynb` + section in technical informe.

**Owner:** P2 leads (ML evaluation expertise) with P1 input on tier semantics.

---

## Q6. JWT secret management for v1

**Decision:** v1 uses static secret in `.env` file with `.gitignore` enforcement. Manual rotation only on credential leak.

**v2 path documented (out of scope for academic project):**
- Production deployment uses dedicated secrets manager service (Azure Key Vault, AWS Secrets Manager, or HashiCorp Vault).
- Properties of these services that matter: access by IAM identity + policy (not file read), automated rotation cadence (90 days default), full audit log of every read, never persists to disk.
- For the team's roadmap: Azure Key Vault is the natural choice given alignment with Azure certification stack (AZ-104 → AZ-305).

**Note for informe:** explicitly call out that secrets-manager-based deployment is the production-grade path, not implemented in academic v1. This honesty itself signals professional maturity.

**Update:** SAD §13.7 to reflect this clarification.

---

## Q7. OpenSearch backup/restore

**Decision:** Out of scope for v1.

**Rationale:** A 14-week academic project with a lab that can be rebuilt from scratch in <30 minutes does not need backup infrastructure. Implementing it would steal time from implementation/demo/informe with no return.

**Documented as future work in SAD §14:** "OpenSearch backup with snapshot lifecycle policy, restore procedure tested. Out of scope for v1."

**What happens if the lab dies during the project:** rebuild from Vagrant + Terraform IaC. Lose data, accept the cost. Not a security gap — an operational gap, deliberately accepted.

---

## Q8. Updates to existing documents

The following updates needed to be applied. Status as of Week 2:

| Document | Update | Section | Status |
|----------|--------|---------|--------|
| SAD | Coverage targets per Q3 | §13.5 | ✅ Applied W2 |
| SAD | Secret manager clarification per Q6 | §13.7 | ✅ Applied W1 |
| SAD | Backup as future work per Q7 | §14 (item 9) | ✅ Applied W2 |
| SAD | Incident schema reference per Q4 | §6.5 | ✅ Applied W2 |
| SAD | Tier calibration protocol per Q5 | §15 (item 5 closed) | ✅ Applied W2 |
| SAD | T2 timeout + throttle/snapshot per Q9 | §6.3 | ✅ Applied W1 |
| ADR-0006 | JWT rotation policy clarification per Q6 | "Audit trail" section | ✅ Applied W2 |
| ADR-0003 | Two-person rule applied to production-critical hosts per Q2 | "Reversibility" → new subsection | ✅ Applied W2 |
| ADR-0003 | T2 timeout corrected per Q9 | "Approval flow" section | ✅ Applied W1 |
| THREAT_MODEL | New metric: throttle effectiveness during countdown | F-052 mitigation + residual risks | ✅ Applied W1 |

All Q8 patches are now applied. The "Status W2" entries were batched and verified together — see SAD §16, ADR-0003 "Actualizaciones posteriores", ADR-0006 "Actualizaciones posteriores".

---

## Q9. T2 timeout behavior — correction to original Q1

**Decision:** T2 timeout fixed at exactly 3 minutes, with mandatory throttle + proactive snapshot during the countdown window. **No re-broadcast or extended waits.**

**Why this matters (the math we initially missed):**

Modern ransomware encrypts files at industrial speeds:
- LockBit 3.0: ~25,000 files/minute on typical SSD.
- BlackCat/ALPHV: ~15,000 files/minute.
- Conti (historical): ~5,000-10,000 files/minute.

A naive "wait 30 minutes for human" timeout would result in 150,000-750,000 files encrypted before action — catastrophic by any definition. The original recommendation in this document for a long timeout window was **incompatible with the actual threat model** ARGOS exists to mitigate.

### Corrected T2 timeout flow

| Time | State | Action |
|------|-------|--------|
| 0s | Alert classified as T2 | Email sent to approvers + **immediate throttle of offending process** (CPU/IO limits) + **proactive disk snapshot** |
| 0-3min | `AWAITING_APPROVAL` | Throttle active. Approvers can approve/reject. |
| At 3min if no response | `TIMEOUT_ESCALATED` | **Auto-execute full isolation immediately.** No further waiting. |
| Post-execution | Notification | Email to team: "executed by timeout, throttle prevented mass encryption, snapshot preserved" |

### Why throttle+snapshot during countdown is the right answer

- **Throttle reduces encryption velocity** during the human-in-the-loop window from ~25,000/min to ~100-500/min. This converts a 3-minute countdown from "5,000-75,000 files lost" to "300-1,500 files lost" — manageable and recoverable from the proactive snapshot.
- **Snapshot is non-destructive.** If the alert was a false positive and approvers reject, the snapshot is discarded. No cost.
- **3 minutes is enough for human decision** in attended scenarios; throttle bounds the damage in unattended scenarios.

### What this rules out

- **Indefinite waiting** (original Option C): incompatible with ransomware speed.
- **30-minute escalation cascade** (original C-modified): catastrophic file loss before any action.
- **No-throttle countdown** (original A): same problem — even 3 minutes at full encryption speed = 5,000-75,000 files lost.

### New metric for informe

**"Files saved by throttle during countdown"** — measure effectiveness of the throttle mitigation in T2 scenarios. Target: ≥90% of files that would have been encrypted at full speed are preserved.

This becomes a sellable metric: *"Our system prevented encryption of 96% of files during the human approval window through proactive throttling."*

### Lesson learned (worth naming)

Numbers matter more than prose. A design decision that sounds prudent ("preserve human agency, don't auto-execute") can be catastrophically wrong if it ignores the temporal scale of the threat being addressed. ARGOS is specifically built for ransomware, which has its own time scale where minutes are catastrophic. Generic security wisdom about "human in the loop" must be calibrated to the specific threat. This correction was caught by team review (P1 questioned the original timeout proposal); the original recommendation would have shipped a system with a 30-minute defense window against a 3-minute attack. Documented here as evidence of design rigor.

---

## Confirmed scope freeze

After this document, **architecture and design are frozen**. Any additional architectural decision after this point requires a new ADR with explicit justification of why the change is necessary post-freeze.

This freeze does not apply to:
- Implementation details (specific code patterns, library choices).
- UI polish.
- Demo scripting.

It does apply to:
- Layer architecture.
- Decision logic.
- Tier definitions.
- Approval flow semantics.

---

## Sign-off

This closes the architectural design phase. Next step: **use-case definition**.

| Role | Name | Status |
|------|------|--------|
| P1 (Lead) | Enzo Ordoñez Flores | ✅ Approved |
| P2 (ML) | Sebastian Montenegro | ✅ Confirmed |
| P3 (Detection) | Angeles Castillo | ✅ Confirmed |
| P4 (Infra/UI) | Diego Jara | ✅ Confirmed |

---

## Change log

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | Week 1 | Initial closure document. Resolves Q1 through Q8. | P1 |
| 1.1 | Week 1 | Added Q9: T2 timeout correction. Original recommendation of long timeout was incompatible with ransomware encryption velocity. Corrected to 3min fixed timeout with proactive throttle + snapshot during countdown. | P1 |
| 1.2 | Week 2 | Q8 closure status updated: confirmed all 10 cross-document patches were applied (six remaining patches applied this week — SAD §13.5/§14/§6.5/§15, ADR-0003 override por criticidad, ADR-0006 política JWT). | P1 |
| 1.3 | Week 7 calendar | Sign-off table updated with confirmed names (Sebastian Montenegro P2, Angeles Castillo P3, Diego Jara P4). Cross-references added to new `EVALUATION_CRITERIA.md` and `data-handling.md`. | P1 |
| 1.4 | 2026-05-23 | Name corrections: P1 ahora "Enzo Ordoñez Flores" (era "Enzo Cáceres"); P4 ahora "Diego Jara" (era "Loli Jara"). | P1 |
