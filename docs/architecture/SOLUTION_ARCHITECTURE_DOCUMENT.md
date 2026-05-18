# SOLUTION ARCHITECTURE DOCUMENT — ARGOS

**Adaptive Ransomware Guard with Orchestrated Surveillance**

| Field | Value |
|-------|-------|
| Document type | Solution Architecture Document (SAD) |
| Version | 1.0 |
| Status | Baseline · Approved at Kickoff |
| Course | Tópicos Avanzados de Ciberseguridad |
| Term | 2026-1 |
| Owner | P1 (Enzo Cáceres) |
| Reviewers | P2, P3, P4 |
| Related documents | `PROJECT_BRIEF.md`, `CONTEXT.md`, `architecture_diagram.html`, `THREAT_MODEL.md`, ADRs 0001-0006 |

---

## 0. Purpose of this document

This Solution Architecture Document (SAD) explains every block of the ARGOS architecture diagram in functional and technical detail. It is the canonical reference when a team member, reviewer, or evaluator asks: *"what does this component do, why is it there, and how does it interact with the rest?"* Each section below corresponds to one block of the architecture diagram (`architecture_diagram.html`).

For context, scope, planning, and team conventions see `CONTEXT.md`. For the one-page summary see `PROJECT_BRIEF.md`. For specific design decisions see the `docs/adr/` folder.

---

## 1. System overview

ARGOS is a layered ransomware detection and response system that mirrors the architecture of commercial high-end EDR/XDR products (Microsoft Defender XDR, CrowdStrike Falcon, Palo Alto Cortex XDR) using exclusively open source components plus a low-cost LLM API for the triage layer.

The system follows a **defense-in-depth** principle: four independent detection layers run in parallel, each with different precision/recall trade-offs, feeding a SOAR (Security Orchestration, Automation and Response) decision engine that fuses their signals and triggers automated containment. A fourth detection layer leverages a Large Language Model for context enrichment and analyst-facing triage.

The end-to-end flow is: *attack → telemetry → parallel detection → score fusion → automated response + LLM enrichment → analyst review → metrics and forensics*.

---

## 2. Block 01 — Attack Simulation

**Diagram location:** Top of the diagram (red).
**Purpose:** Generate controlled, reproducible positive cases for evaluation, demo, and rule tuning.

### Components

- **Atomic Red Team (Red Canary, MIT licence).** Library of atomic tests mapped one-to-one to MITRE ATT&CK techniques. Each test is a small script (PowerShell, Bash, Python) that executes a single TTP. Used to validate that individual Sigma rules fire on their target technique.
- **Caldera (MITRE, Apache 2.0).** Adversary emulation framework. Lets us chain multiple TTPs into a realistic attack scenario (initial access → discovery → privilege escalation → impact). Used to test multi-step detection logic and Decision Engine fusion.
- **Custom ransomware simulator.** Internal Python script that performs the full ransomware behavioral chain in a controlled way: enumerate files, disable Volume Shadow Copies, encrypt files with AES-256, drop ransom note, beacon to a fake C2 endpoint. Built by P4 to guarantee reproducible demo behaviour.

### Why all three

Atomic Red Team alone cannot test multi-step detection. Caldera alone does not give the encryption-specific signals we need for Layer 2 ML. The custom simulator gives demo-grade reliability — no surprises from external tooling during the exposition.

### Outputs

Telemetry events on the victim hosts (file events, process creation, registry modifications, network connections), all captured by Sysmon (Windows) and auditd (Linux).

---

## 3. Block 02 — Victim Lab

**Diagram location:** Below Attack Simulation (yellow).
**Purpose:** Isolated environment that receives the attacks and produces the telemetry.

### Components

- **Windows VM (Windows 10/11).** Sysmon installed with a tuned configuration (e.g. SwiftOnSecurity baseline) for high-fidelity event logging. Wazuh agent forwards events to the manager.
- **Linux VM (Ubuntu Server LTS).** auditd configured with Wazuh-recommended rules. Wazuh agent installed.
- **Canary files.** Strategically placed honeypot files with attractive names (`financials_Q4_2025.xlsx`, `passwords.txt`, `db_backup.sql`) in user profile and simulated network share paths. Monitored by Wazuh File Integrity Monitoring with `whodata` (Windows) to capture the offending process identity.

### Network topology

The lab runs on an isolated virtual network (host-only adapter or internal Vagrant network). No internet access from victim hosts during attack runs to prevent any accidental real-world impact.

### Provisioning

Vagrant + shell provisioners for reproducibility. Optional Terraform module for Azure deployment (P4 stretch goal) to demonstrate hybrid on-prem / cloud architecture.

---

## 4. Block 03 — Wazuh Manager

**Diagram location:** Center of the diagram (amber border, core component).
**Purpose:** Single point of event ingestion, normalization and storage. The "brain" that all detection layers query.

### Why Wazuh

Wazuh is the open-source SIEM/HIDS standard with the largest community, broad MITRE ATT&CK rule library, native Sigma rule support via converters, FIM with whodata, and integration with OpenSearch for storage and visualization. Avoids the licensing concerns of Elastic Stack post-2021.

### Configuration

- **Manager:** central server receiving agent events, running rules, generating alerts.
- **Indexer:** OpenSearch (Apache 2.0 fork of Elasticsearch) for log storage and search.
- **Custom rules:** Sigma rules converted to Wazuh format via `sigma-cli` and placed in `/var/ossec/etc/rules/`.
- **API:** Wazuh REST API exposes alerts, used by the SOAR Decision Engine to pull events.

### Outputs

JSON alerts streamed to:
1. Layer 1 (rule engine, native Wazuh).
2. Layer 2 (Redis stream → ML consumer).
3. Layer 3 (FIM canary alerts, native Wazuh).

---

## 5. Block 04 — Detection Layers (parallel)

**Diagram location:** Below Wazuh Manager (blue).
**Purpose:** Three independent detection layers running in parallel. Each layer can fail without bringing down the others.

### 5.1 Layer 1 — Rule-Based Detection

Sigma rules written in YAML, mapped explicitly to MITRE ATT&CK techniques, converted to Wazuh format with `sigma-cli`. Detect known ransomware patterns.

**Target techniques (minimum coverage):**
- T1486 — Data Encrypted for Impact
- T1490 — Inhibit System Recovery (e.g. `vssadmin delete shadows`)
- T1083 — File and Directory Discovery
- T1562.001 — Disable or Modify Tools (Defender, AV)
- T1021 — Remote Services (lateral movement SMB/RDP)
- T1071 — Application Layer Protocol (C2 channels)

**Trade-off:** high precision, limited recall against new variants. Layer 2 covers that gap.

**Owner:** P3.

### 5.2 Layer 2 — ML Anomaly Detection

Unsupervised models trained on a benign baseline of approximately two weeks of normal lab activity. Detect deviations that signature rules miss.

**Feature extraction (per process, 60-second window):**
- File write rate
- Average entropy of files written (Shannon entropy via scipy)
- Ratio of modified file extensions
- Cryptographic API calls (CryptEncrypt, BCryptEncrypt on Windows; OpenSSL/libsodium hooks on Linux)
- New outbound network connections
- CPU/IO burst pattern indicators

**Models:**
- **Isolation Forest** as the first detector (fast, interpretable, robust with limited training data).
- **One-Class SVM** as a complement.

**Ensemble formula:**

```
ensemble_score = 0.6 × isolation_forest_score + 0.4 × one_class_svm_score
```

Isolation Forest receives the higher weight (0.6) because (a) it is more interpretable for the informe técnico, (b) it is more robust with the limited training data available in the 14-week academic budget, and (c) its output is calibrated to [0,1] without requiring distance-to-hyperplane normalization. One-Class SVM (0.4) acts as a sanity check that catches anomalies the isolation forest's tree-cuts miss.

The single threshold is applied to `ensemble_score`, not to the individual model scores. Individual scores are persisted in the `MLScore` payload (per `argos_contracts/ml_score.py`) for forensic analysis but are not consumed by the tier classifier.

If empirical evaluation (Q5 calibration) shows that one model dominates the signal, the weights can be re-tuned without changing the contract or the decision logic — they live in `ml/models/ensemble.py` as a config constant.

**Pipeline:** Wazuh alerts published to a Redis stream → Python consumer extracts features → models score → score above threshold becomes a new Wazuh alert via custom decoder.

**Trade-off:** higher recall against unknown variants, but higher false-positive rate. Requires a clean baseline.

**Owner:** P2.

### 5.3 Layer 3 — Deception (Canary Files)

Honeypot files placed where legitimate users would never touch but indiscriminate ransomware would. First access/modification fires a critical alert with maximum confidence.

**Mechanism:**
- Canary generator (Python) creates files with realistic content and names.
- Wazuh FIM monitors the canary paths with `whodata` (Windows) or `auditd` (Linux) to capture the offending process PID, command line, and parent process.
- Custom Wazuh rule: any `write|rename|delete` event on a canary path → severity 12 (critical).

**Trade-off:** by design, false-positive rate ≈ 0. Limitation: a sophisticated attacker who knows the canaries can avoid them. This is why Layer 3 complements but does not replace Layers 1 and 2.

**Owner:** P3.

---

## 6. Block 05 — SOAR Decision Engine + Human-in-the-Loop Approval

**Diagram location:** Center-low (purple).
**Purpose:** Fuse signals from Layers 1, 2, 3 into a tiered decision and either trigger automated response or solicit human approval.

### 6.1 Confidence-tiered automation

Per `ADR-0003`, alerts are classified into four tiers based on which detection layers fired and the confidence of each:

| Tier | Triggered by | Confidence | Action | Email |
|------|--------------|------------|--------|-------|
| **T0 — Critical confirmed** | Layer 3 (canary) alone, or Layers 1+2+3 simultaneous | ≥0.95 | Auto-isolate immediate | Post-facto with "Revert" button |
| **T1 — High confirmed** | Layer 1 + Layer 2 corroborate (no canary) | 0.80–0.95 | Auto-isolate immediate | Post-facto with "Revert" button |
| **T2 — Medium uncertain** | Layer 1 alone with high-fidelity rule, or Layer 2 alone with very high score | 0.60–0.80 | Pending with 3-min countdown | Pre-approval with buttons |
| **T3 — Low uncertain** | Layer 2 medium score, Layer 1 with experimental rule | 0.40–0.60 | Notification only, no action | LLM analysis to analyst, no execute button |

### 6.2 Fusion logic per layer combination

| Triggered layers | Tier | Action |
|------------------|------|--------|
| Layer 3 alone | T0 | Immediate isolation (canary = zero-FP by design) |
| Layer 1 + Layer 3 | T0 | Immediate isolation + disk snapshot (L3 already qualifies for T0; L1 corroboration adds context) |
| Layer 2 + Layer 3 | T0 | Immediate isolation + disk snapshot (idem) |
| Layers 1+2+3 simultaneous | T0 | Immediate isolation + disk snapshot + full LLM analysis |
| Layer 1 + Layer 2 corroborate (no canary) | T1 | Immediate isolation + disk snapshot |
| Layer 1 alone (high-fidelity rule — Sigma `level: high\|critical`) | T2 | Throttle + snapshot now, awaiting approval (3-min countdown), LLM analysis to analyst |
| Layer 2 alone (ensemble_score ≥ 0.74) | T2 | Throttle + snapshot now, awaiting approval, LLM analysis to analyst |
| Layer 1 alone (experimental rule — Sigma `level: medium\|low`) | T3 | Notification only with LLM enrichment |
| Layer 2 alone (ensemble_score 0.40–0.60) | T3 | Notification only with LLM enrichment |

**Coverage note:** the 9 rows above exhaust the 2³ = 8 combinations of L1/L2/L3 (firing or not), plus the two tier T3 cases. Layer 3 firing always wins to T0 because Layer 3 is zero-FP by design — there is no T2 or T3 row that includes Layer 3.

**High-fidelity vs experimental rule classification:** the Decision Engine reads the standard Sigma `level:` field from the rule definition. `critical` and `high` map to **high-fidelity** (route to T2 when alone). `medium` and `low` map to **experimental** (route to T3 when alone). This uses the canonical Sigma format (`https://github.com/SigmaHQ/sigma/wiki/Specification`) so rules are upstream-portable and the classification stays in the rule file itself, not in a hardcoded allowlist.

### 6.3 Approval flow (T2/T3)

When an alert classifies as T2:

1. Decision Engine sets state `AWAITING_APPROVAL` in Redis with TTL 3 minutes.
2. **Immediately** triggers two non-destructive protective actions:
   - **Throttle of offending process** (CPU/IO limits via `cpulimit`/`ionice` on Linux, `Set-Process` priority + `Process Mitigation Policy` rate-limits on Windows). Reduces encryption velocity from ~25,000 files/min to ~100-500 files/min.
   - **Proactive disk snapshot** (VSS on Windows, `dd` on Linux). Preserves forensic evidence and provides recovery point if attack is confirmed.
3. Notification service sends approval requests through the **multi-channel chain defined in `ADR-0007`** (Telegram bot with inline buttons + ntfy.sh push + Slack webhook in parallel at t=0; Twilio Voice DTMF escalation at t=60s if no response). Each channel carries a **JWT-signed token** for "Approve isolation" / "Reject — false positive". Email is retained as post-facto summary channel only (not primary), per ADR-0007.
4. Approval API receives clicks via `POST /approval/{token}`, validates JWT, updates state.
5. Multiple recipients may respond — split-brain resolution per ADR-0006 (see §6.4).
6. **On approval:** SOAR triggers full containment playbook (isolation + kill). Throttle and snapshot already in place.
7. **On rejection:** state `REJECTED`. Throttle removed, snapshot discarded.
8. **On timeout (no response after 3 min):** state `TIMEOUT_ESCALATED`. Auto-execute full isolation immediately. No re-broadcast or extended waits — see Q9 in `OPEN_QUESTIONS_RESOLUTION.md` for rationale (ransomware encryption velocity makes long timeouts incompatible with the threat model).

**Critical design property:** the throttle+snapshot during countdown means that even if the human approval window is fully consumed without response, the damage is bounded. Empirically targeted: ≥90% of files-that-would-have-been-encrypted are preserved by throttle effectiveness.

For T3 alerts:

1. Notification only, no executable action proposed.
2. Analyst reviews via Streamlit dashboard.
3. Manual escalation if needed.

### 6.4 Split-brain resolution

Multiple approvers may give contradictory responses. Per `ADR-0006`, ARGOS applies **conservative-wins policy** with 60-second consolidation window:

1. **First positive response** (approve OR reject) starts a 60-second consolidation window.
2. **During the window:** additional responses arrive. If all align with the first response, decision confirmed. If any opposite-sign response arrives, **conflict detected**.
3. **At window close with conflict:** conservative-wins applied. In containment context, *conservative* = isolate. So if any approver said "approve isolation", the action executes regardless of how many said "reject".
4. **Audit trail logged** to OpenSearch index `argos-audit-decisions` with full per-responder timeline, conflict flag, policy applied, final decision rationale.

For irreversible actions (account deletion, disk wipe — out of scope v1), a **two-person rule** is enforced instead: requires two explicit approves, single reject cancels.

### 6.5 Implementation

Python service (FastAPI) with:
- Subscriber to Wazuh alerts stream.
- Tier classifier based on layer signals + confidence scores.
- State machine in Redis (states: `RECEIVED`, `AWAITING_APPROVAL`, `PENDING_EXECUTION`, `PENDING_REJECTION`, `PENDING_SECOND_APPROVAL` (production-critical only — see ADR-0003 §"Edge case 3 AM"), `EXECUTING`, `EXECUTED`, `REVERTED`, `REJECTED`, `TIMEOUT_ESCALATED`).
- Async scheduler (`apscheduler`) for timeouts and consolidation windows.
- Audit logger writing structured JSON to OpenSearch.

**Incident schema and naming convention:** the canonical incident JSON contract (Decision Engine ↔ Redis ↔ Streamlit) is defined in `OPEN_QUESTIONS_RESOLUTION.md` §Q4 and implemented as Pydantic models in the `argos_contracts` module (`CONTRACTS_SPECIFICATION.md`). Incidents are named `INC-{YYYY}-{MM}-{DD}-{NNN}` with a daily-reset counter persisted in Redis.

**Owner:** P1.

---

## 7. Block 06 — LLM Triage (Layer 4)

**Diagram location:** Right side (green).
**Purpose:** Enrich alerts with structured analysis (technique, severity, runbook, recommended action) using retrieval-augmented generation over a security corpus.

### Components

#### 7.1 FastAPI service

Single endpoint `POST /triage` accepting an `AlertContext` (alert payload, recent process tree, network connections, file modifications). Returns a `TriageResponse` with structured fields.

#### 7.2 Mini-RAG corpus

Reuses the retrieval pipeline from CloudRAG (BM25 + BGE-large embeddings + Reciprocal Rank Fusion + cross-encoder reranker). Approximately 70% of the code is inherited; the corpus is 100% new.

**Indexed sources:**
- MITRE ATT&CK STIX bundle (techniques, mitigations, detections)
- Sigma rules documentation
- NIST SP 800-61r2 (Computer Security Incident Handling Guide)
- SANS publicly available IR playbooks
- Internal post-mortems of simulated attacks (grow over time)

#### 7.3 LLMClient — vendor-agnostic interface

Abstract client with two backends:
- **Primary:** DeepSeek-V3 via OpenAI-compatible API. Selected for quality/cost ratio.
- **Fallback:** Qwen2.5-72B-Instruct via DashScope. Larger context window, similar cost.

Backend selection via environment variable `LLM_BACKEND`. See `ADR-0001` for full rationale.

#### 7.4 Structured output

```json
{
  "tecnica_mitre": "T1486",
  "confianza": 0.92,
  "severidad": "critical",
  "runbook_aplicable": "NIST 800-61 §3.4 Containment, Eradication, Recovery",
  "accion_recomendada": "Isolate host, capture memory, preserve disk snapshot before remediation",
  "indicadores_correlacionar": ["vssadmin.exe", "high entropy writes", "C2 beacon to <ip>"]
}
```

Validation: Pydantic models enforce schema. Hallucinated MITRE technique IDs are rejected by cross-checking against the loaded ATT&CK bundle.

**Owner:** P1.

---

## 8. Block 07 — Automated Response

**Diagram location:** Right side (red).
**Purpose:** Execute containment actions when the Decision Engine commands it.

### Playbooks

- **Host isolation.** `iptables -A OUTPUT -j DROP` (Linux) or PowerShell `New-NetFirewallRule -Action Block` (Windows). Excepted: management network for analyst access.
- **Process kill.** Identify offending PID from FIM/Sysmon event, `kill -9` (Linux) or `Stop-Process -Force` (Windows).
- **Disk snapshot.** Volume Shadow Copy (Windows) or `dd` of relevant partitions (Linux). Stored on isolated forensic volume.
- **Notification.** Email + Slack webhook. The notification payload includes the LLM analysis output for immediate analyst context.

All actions are logged to OpenSearch for the forensic timeline.

**Owner:** P1 (engine) + P4 (playbook scripts).

---

## 9. Block 08 — Visualization

**Diagram location:** Bottom-right (cyan).
**Purpose:** Two interfaces optimized for different audiences.

### 9.1 OpenSearch Dashboards

For SOC-wide visibility and metrics. Three dashboards:
- **Alerts timeline:** chronological event view, filterable by host, severity, layer.
- **MITRE coverage heatmap:** which techniques the system has detected over time, color-coded by frequency.
- **Layer performance:** per-layer false-positive rate, time-to-detect histogram, throughput.

### 9.2 Streamlit Analyst UI

For per-incident triage. Three views accessible via tabs:

#### 9.2.1 Alert Inspection

Split view of an active alert:
- **Left pane:** raw alert with all telemetry (process tree, command lines, network connections, hashes).
- **Right pane:** LLM analysis with citations expandable to source documents.
- **Action buttons:** "Approve auto-action", "Mark false positive", "Escalate to L2".

#### 9.2.2 Approval Workflow Console

Real-time view of active approval flows (per ADR-0003 and ADR-0006). Three panels:

- **Left — Incident card:** severity tier badge (T0/T1/T2/T3 color-coded), incident summary, technique MITRE, compact LLM analysis, link to raw alert.
- **Center — Decision Matrix:** grid with one row per approver. Columns: name, role, email destination, response status (🟡 pending / 🟢 approved / 🔴 rejected / ⚫ timeout), response timestamp, latency from email send. Rows highlight on new response (2s animation).
- **Right — System Decision Logic:** current state (`PENDING` / `WAITING_CONFLICT_WINDOW` / `EXECUTING` / `EXECUTED` / `REVERTED`); live countdown timer when applicable; conflict indicator when responses diverge; final decision banner with justification (`"2 approve · 1 reject · conservative-wins applied"`).
- **Bottom — Action Timeline:** horizontal chronology of incident events (alert created → emails sent → first response → conflict detected → window closed → action executed).

Real-time updates via `streamlit-autorefresh` polling Redis state every 1-2 seconds.

This console is the visual centerpiece of the demo. It transforms the abstract conservative-wins logic into something visible, defensible in audit, and dramatically illustrative.

#### 9.2.3 Audit & Forensics

Search interface over historical incidents:
- Filter by date, severity tier, host, decision (auto-executed / approved / rejected / timeout-escalated).
- Click an incident → full audit trail with per-responder vote timeline, applied policy, post-incident metrics.

**Owner:** P4.

---

## 10. Block 09 — Metrics

**Diagram location:** Bottom (gray).
**Purpose:** Three distinct metric categories for three distinct audiences.

### 10.1 Demo headline metrics (3, for slides)

- **Time-to-Detect (TTD).** Seconds from attack start to first valid alert.
- **Files affected before containment.** Number of real files encrypted before host isolation.
- **False-Positive Rate.** Measured over 24-48h of benign baseline activity.

### 10.2 Forensic timeline (for incident reports following NIST 800-61)

- Complete chronological event chain.
- Process tree of the offending process.
- Network connections (origin, destination, port, protocol).
- Correlated user actions (logins, commands).
- SHA-256 hashes of all modified files.
- Full command line of the offending process.

All natively captured by Wazuh + OpenSearch — no extra work, only reporting.

### 10.3 System evaluation (for technical report)

- Precision / Recall / F1 per layer individually.
- MITRE ATT&CK coverage matrix (detected vs not detected).
- Latency per layer.
- Events processed per second (throughput).
- Ablation: rules-only vs ML-only vs ensemble comparison.

**Owner:** P4 (dashboards), all (per-layer reporting).

---

## 11. End-to-end flow — illustrative incident

1. **Attack initiation.** Atomic Red Team executes T1486 on the Windows victim. Custom Python ransomware enumerates and begins encrypting files.
2. **Telemetry capture.** Sysmon logs file events, process creations, registry changes. Wazuh agent forwards to manager. Canary file is touched within seconds.
3. **Parallel detection.** Layer 3 (canary) fires immediately with high confidence. Layer 1 matches T1486 Sigma rule. Layer 2 ML detects entropy spike + crypto syscall pattern.
4. **Decision fusion.** Decision Engine receives all three signals within the same 5-minute window. Logic: Layer 3 + corroboration → maximum severity → immediate isolation playbook.
5. **LLM enrichment.** FastAPI receives full context. RAG retrieves MITRE T1486 + NIST 800-61 ransomware playbook. DeepSeek-V3 generates structured analysis with technique, severity, recommended action, and correlating IoCs.
6. **Automated containment.** Host isolated via firewall rules. Offending PID killed. Disk snapshot captured for forensics. Team notified via Slack with LLM analysis attached.
7. **Analyst review.** Streamlit UI shows alert + LLM analysis side-by-side with citations. OpenSearch dashboard updates MITRE coverage heatmap and time-to-detect histogram.

---

## 12. Resilience & failure modes

A defensive system that can be silently disabled by an adversary, or that fails open without warning, is worse than no system at all. ARGOS is designed with explicit failure paths and adversarial assumptions. **The full threat model (STRIDE + FMEA + Risk Register) is documented separately in `THREAT_MODEL.md`.** This section summarizes the resilience properties baked into the architecture.

### 12.1 Ten resilience properties (testable claims, not aspirations)

1. **No single point of failure in detection.** Three detection layers run in parallel and independent. Failure of any one degrades coverage; it does not blind the system.
2. **LLM is never on the containment critical path.** The Decision Engine triggers containment from Layers 1–3 alone. A malfunctioning, hallucinating, or compromised LLM cannot prevent isolation — only fail to enrich the analyst's view.
3. **Containment fails closed.** If an automated isolation playbook fails, the alert state remains "uncontained" and escalates to manual response. There is no silent success.
4. **Agent disconnect is itself a signal.** An attacker who kills the Wazuh agent on a victim produces a high-priority alert (rule 502 + heartbeat monitoring). Suspicious silence is treated as a positive indicator of compromise.
5. **Logs ship in real time.** All telemetry forwards to the manager immediately, not buffered locally. An attacker clearing local logs after action cannot prevent the events from being already indexed remotely (mitigation against MITRE T1070.001).
6. **LLM output validated, never trusted blindly.** Pydantic schema validation, MITRE ATT&CK ID whitelist (rejects hallucinated technique IDs), confidence thresholds, and a hard no-action constraint (LLM cannot trigger isolation or kill commands).
7. **Redundant log shipping for high-value hosts.** Sysmon writes to local file; a separate Filebeat agent ships to a backup collector. Compromise of one shipping channel does not eliminate the evidence trail.
8. **Vendor portability prevents lock-in failure.** LLM backend abstracted: DeepSeek primary → Qwen fallback → continue without enrichment if both down → swap to local Llama with one config change.
9. **State persistence across crashes.** Decision Engine queue (Redis with persistence), ML consumer state, and OpenSearch indexes all survive process restarts. A 30-second outage does not lose pending alerts.
10. **Cost-bounded operations.** LLM API calls have per-incident rate limits and monthly budget caps. A pathological attack pattern (or runaway bug) cannot drain the project budget — the system fails closed on cost before exceeding the cap.

### 12.2 Critical failure scenarios — designed degradation paths

| Scenario | What happens | Why it's acceptable |
|----------|--------------|---------------------|
| LLM API completely down | Alerts continue without enrichment; analyst sees raw alert | LLM is enrichment-only; SOAR unaffected |
| LLM hallucinates non-existent MITRE technique | Pydantic + whitelist rejects response; alert proceeds without enrichment | Validation layer prevents bad analysis from reaching analyst |
| Attacker kills Wazuh agent on victim | Heartbeat loss → high-priority "agent stopped" alert → host investigated as compromised | Suspicious silence becomes a detection signal |
| Wazuh manager service crashes | systemd auto-restart (~30s); during outage no new detection | External heartbeat alerts the team; queued events processed on recovery |
| Attacker clears local Windows Event Log | Events already shipped to manager; clear event itself is a Sigma rule | Real-time forwarding mitigates the gap |
| ML model file corrupted | Service crash detected by heartbeat; fallback to last-known-good model | Capas 1+3 still active during recovery |
| Decision Engine crashes mid-incident | Persistent queue survives crash; on restart processes queued alerts | Brief delay, no alert loss |
| Live demo: LLM API down at exposition time | Visible failover to Qwen during demo (good story); pre-recorded backup video as last resort | Multiple contingency layers |

### 12.3 Top accepted residual risks

After mitigations, these risks remain and are explicitly accepted:

1. **Sensitive lab data sent to China-based LLM API (DeepSeek/Qwen).** Acceptable for academic project with synthetic data; would require local LLM for production. Documented in threat model T-030.
2. **Fast attacker disables agent before alert ships (sub-heartbeat-interval window).** Heartbeat interval can be reduced but trades off network noise. Documented as fundamental limit (T-050).
3. **Race condition: very fast ransomware encrypts some files before isolation triggers.** Documented theoretical TTD floor of 3–5 seconds; acceptable as a transparent metric (F-052).

For the complete analysis of ~40 identified threats and failure modes with likelihood × impact scoring, see `THREAT_MODEL.md`.

---

## 13. Cross-cutting concerns

### 13.1 Security and isolation

- Lab network isolated from corporate/home networks during attack runs.
- API keys stored in `.env` files, never committed (`.gitignore` enforced).
- Repository private during the course, public after grading.
- Wazuh manager on isolated subnet; no inbound from victim subnet beyond agent port (1514).

### 13.2 Reproducibility

- All infrastructure as code (Vagrant primary, Terraform optional).
- All Python services have `requirements.txt` and `Dockerfile`.
- ML model training is fully scripted; no manual notebook-only pipelines for production paths.
- Lab can be rebuilt from scratch in <30 minutes by any team member.

### 13.3 Vendor portability

- Every commercial component (LLM APIs) sits behind an abstract interface.
- Switching DeepSeek to Claude or GPT-4 requires editing one configuration value, not changing application code.

### 13.4 Open-source contribution

- Custom Sigma rules of upstream quality are submitted to `SigmaHQ/sigma` as Pull Requests by each team member.
- Target: 2-4 accepted PRs by end of project.

### 13.5 Testing strategy

Test pyramid mandatory for components in critical detection / decision paths. Coverage targets are tiered by module criticality per `OPEN_QUESTIONS_RESOLUTION.md` §Q3 (honest assessment of the 16h/week × 4 people × 14 weeks budget — uniform 70% would steal time from implementation, demo polish, and informe):

| Module category | Target | Rationale |
|-----------------|--------|-----------|
| Decision Engine, LLMClient, Approval API | ≥60% line coverage | Critical-path code, must be tested |
| ML feature extractors, Sigma rule converters | ≥50% line coverage | Important but more straightforward |
| Streamlit UI, scripts, glue code | Best-effort, smoke tests only | Low ROI for unit tests |
| Integration tests | ≥1 happy-path + ≥1 error-path per layer interface | Confidence in component boundaries |
| End-to-end | ≥3 scenarios in CI (T0, T2, split-brain) | Demo confidence |

- **Unit tests** by tier above:
  - Each `LLMClient` implementation against mocked HTTP (`respx`).
  - Feature extractors with sample log inputs.
  - Decision Engine tier classifier with synthetic alerts covering all 4 tiers.
  - Notification channel JWT generation/validation.
- **Integration tests** between adjacent components:
  - Wazuh alert → Redis stream → ML consumer (with synthetic alerts).
  - Decision Engine → Approval API → state transitions in Redis.
  - LLM Triage end-to-end with stubbed LLM API.
- **End-to-end tests** with Atomic Red Team in CI pipeline:
  - Weekly scheduled run executes a subset of TTPs against the lab.
  - Validates that all expected layers fire and that response actions execute.
  - Coverage report mapped to MITRE ATT&CK matrix.

CI: GitHub Actions runs unit + integration on every PR; e2e runs scheduled weekly. PRs require green CI before merge.

### 13.6 Self-monitoring (meta-observability)

ARGOS is the monitor — but who monitors ARGOS itself?

**External heartbeat service** (lightweight Python script on a separate host or cron job) verifies every 30s:
- Wazuh manager API responding (`GET /security/user/authenticate`).
- FastAPI services healthy (`GET /health`).
- Redis reachable (`PING`).
- OpenSearch cluster green (`GET /_cluster/health`).

On failure, sends alert via independent channel (different email or SMS) — does NOT use the same notification channel as ARGOS itself, so a complete ARGOS outage is still detected and reported.

For v1 (lab): bash script with `curl` + `mailx` running every 30s via cron.
For production (out of scope): proper monitoring (Prometheus + Alertmanager).

### 13.7 Secrets management

For v1 (academic project): `dotenv` files + `.gitignore` enforcement. Each service loads its config from `.env` at startup.

For production deployment (out of scope, mentioned for honesty in informe): proper secrets management with HashiCorp Vault, AWS Secrets Manager, or Kubernetes Secrets. Acknowledging this gap honestly is itself a sign of professional maturity — the team understands the difference between "good enough for academia" and "good enough for production".

Secrets in scope:
- Wazuh API tokens.
- LLM API keys (DeepSeek, Qwen).
- JWT signing secret for approval tokens.
- SMTP credentials for email service.
- OpenSearch admin password.

Rotation policy for v1: manual on credential leak. For production: automated rotation every 90 days.

---

## 14. Future work (explicitly out of scope for v1)

Items considered and deferred. Documented to demonstrate awareness:

1. **Progressive containment (escalating response).** Throttle process before kill, kill before isolate. Pattern reduces collateral damage on false positives. Deferred due to scope.
2. **Hierarchical approver authority.** Approvers with formal ranks; senior overrides junior. Deferred — requires role model formalization.
3. **Multi-channel notifications.** ✅ Implemented in `ADR-0007` for v1: Telegram (primary), ntfy.sh, Slack/Discord, Twilio Voice DTMF. Foundation: `ADR-0005` `NotificationChannel` abstraction. Future channels (Microsoft Teams, PagerDuty escalation policies) remain deferred but trivial to add via the same interface.
4. **Local LLM inference** (Llama 3.1, Mistral via Ollama). Foundation laid by ADR-0001 LLMClient abstraction, implementation deferred until hardware available.
5. **High availability for Wazuh manager.** Currently SPOF; production would deploy cluster mode.
6. **Automated red-team retraining.** Adversarial samples generated by AI to continuously test detection. Research-grade extension.
7. **Compliance dashboards.** SOC 2, ISO 27001, NIST CSF mapping reports. Out of scope but architecture compatible.
8. **Cloud-native deployment** (Kubernetes + Helm charts). Currently Vagrant-based. Foundation: services already containerized.
9. **OpenSearch backup with snapshot lifecycle policy and tested restore procedure.** For v1 the lab is rebuildable from Vagrant + Terraform IaC in <30 min, so backup infrastructure is deliberately out of scope (per `OPEN_QUESTIONS_RESOLUTION.md` §Q7). Production deployment would add snapshot lifecycle, immutable storage destination, and quarterly restore drills.

---

## 15. Open architectural questions

1. **Should Layer 4 LLM be on the critical containment path or analyst-only?** ~~Open~~ **closed.** Decision settled: enrichment only, never containment trigger. Enforced by Decision Engine code path (SOAR triggers from L1-3 alone) and codified in `THREAT_MODEL.md` §6 R-2 ("LLM is never on the containment critical path"). LLM hallucinations cannot prevent isolation, only fail to enrich the analyst view. No revisit required.
2. **Is OpenSearch performance sufficient for our throughput?** Baseline benchmarks pending in Week 3.
3. **Local LLM (Llama 3.1) as a third backend for full offline demo?** Stretch goal if hardware availability changes.
4. **Heartbeat interval tuning:** decision is to keep default 60s per ADR-0002. Re-evaluate at Gate 2 if evaluation data suggests issue.
5. **Tier threshold calibration:** ~~placeholder~~ **closed.** Calibration protocol defined in `OPEN_QUESTIONS_RESOLUTION.md` §Q5 — labelled dataset collection in Weeks 6-8 (~100 ransomware + ~500 benign alerts), precision-recall curves per layer, thresholds set to optimize tier semantics (T0 precision ≥99%, T1 precision ≥90% / recall ≥80%, T2 precision ≥70% / recall ≥95%, T3 recall ≥99%). Deliverable: `evaluation/tier_calibration.ipynb` + section in technical informe. Owner: P2 leads with P1 input on tier semantics.

---

## 16. Change log

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | Week 1 | Initial baseline approved at kickoff | P1 |
| 1.1 | Week 1 | Added Section 12 (Resilience & failure modes), references to `THREAT_MODEL.md`. Renumbered subsequent sections. | P1 |
| 1.2 | Week 1 | Expanded Section 6 with confidence-tiered automation (ADR-0003), approval flow, split-brain resolution (ADR-0006). Expanded Section 9.2 with Approval Workflow Console. Added Sections 13.5 (Testing), 13.6 (Self-monitoring), 13.7 (Secrets management), and Section 14 (Future work). | P1 |
| 1.3 | Week 2 | Applied pending Q8 patches from `OPEN_QUESTIONS_RESOLUTION.md`: §13.5 tiered coverage targets (Q3), §14 added OpenSearch backup as future work (Q7), §6.5 cross-references incident schema (Q4) and `argos_contracts`, §15 closed tier calibration with reference to Q5 protocol. | P1 |
| 1.4 | Week 9 | Sync with `ADR-0007` (multi-channel notification escalation): §6.3 step 3 now describes the Telegram + ntfy + Slack parallel chain with Twilio DTMF escalation; §14 item 3 marked implemented (previously "deferred"). §15 item 1 closed (LLM containment path decision was already final, formalized here). | P1 |
| 1.5 | Week 7 calendar | Audit pass: §5.2 ensemble formula made explicit (0.6·IF + 0.4·SVM); §6.2 fusion table extended to cover all 2³ layer combinations + high-fidelity Sigma `level:` mapping; §6.5 state machine adds `PENDING_SECOND_APPROVAL` per ADR-0003 §"Edge case 3 AM"; cross-references to new `docs/EVALUATION_CRITERIA.md` and `docs/data-handling.md`. | P1 |

---

*This document is a living artifact and is updated whenever an Architecture Decision Record (ADR) is accepted or a design changes. Last updated: Week 9.*
