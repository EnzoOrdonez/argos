# THREAT MODEL & RISK REGISTER — ARGOS

**Adaptive Ransomware Guard with Orchestrated Surveillance**

| Field | Value |
|-------|-------|
| Document type | Threat Model + Failure Mode Analysis (FMEA) + Risk Register |
| Version | 1.0 |
| Status | Baseline · Approved at Kickoff |
| Methodology | STRIDE (security) + FMEA (reliability) + Project Risk Register |
| Course | Tópicos Avanzados de Ciberseguridad · 2026-1 |
| Owner | P1 (Enzo Cáceres) |
| Reviewers | P2, P3, P4 |
| Related | `SOLUTION_ARCHITECTURE_DOCUMENT.md`, `architecture_diagram.html` |

---

## 0. Purpose

Any defensive system can itself become an attack target or a source of catastrophic failure. This document analyzes ARGOS from three orthogonal angles:

1. **Security threats (STRIDE):** how an adversary could attack the defensive system itself.
2. **Reliability failures (FMEA):** how components could fail without an adversary, and the cascade effects.
3. **Project execution risks:** non-technical risks that could derail delivery.

The goal is not to eliminate all risk but to **make residual risk explicit and acceptable**, with clear mitigations, detection mechanisms, and degradation paths. A defensive system that "fails closed" with explicit fallback is acceptable; one that "fails silently" is not.

This document is a **living artifact** — updated whenever a new attack vector is identified during implementation or evaluation.

---

## 1. Methodology

### 1.1 STRIDE — Security Threats

For each component, we ask: can an attacker **S**poof it, **T**amper with it, **R**epudiate actions, cause **I**nformation disclosure, **D**enial of service, or **E**levate privilege through it?

### 1.2 FMEA — Reliability

For each component, we ask: how can it fail, what's the effect on the rest of the system, how would we detect the failure, and how do we degrade gracefully?

### 1.3 Risk Register — Project Execution

For the project itself, we track risks that aren't technical but could derail delivery: team availability, scope creep, integration delays.

### 1.4 Risk scoring

Each risk is scored: **Likelihood (L/M/H) × Impact (L/M/H) → Risk Level (Low/Medium/High/Critical)**. Mitigations target High and Critical first; Lows are accepted.

---

## 2. Trust boundaries

The system has four explicit trust boundaries. Any data crossing them must be validated:

1. **Attack → Victim VM:** untrusted input. Logs and telemetry from victim hosts are *suspect by default*.
2. **Victim agent → Wazuh Manager:** trusted channel (TLS, agent key registration). Compromise here = full system compromise.
3. **Wazuh Manager → Detection Layers:** internal trusted boundary. Failures here are reliability concerns, not security ones.
4. **System → External LLM API:** untrusted external service. Outputs must be validated; inputs must be sanitized (no PII, no secrets, no embedded injection vectors that affect us).

---

## 3. STRIDE Threat Analysis

Threats numbered T-NNN. Mitigations referenced in section 6.

### 3.1 Spoofing (S)

| ID | Component | Threat | L | I | Risk | Mitigation | Residual |
|----|-----------|--------|---|---|------|------------|----------|
| T-001 | Wazuh Agent | Attacker spoofs an agent and sends fabricated benign-looking events to mask real attack | M | H | **High** | Agent registration with pre-shared key, TLS mutual auth, rule on duplicate agent IDs | Low — would require key extraction first |
| T-002 | SOAR webhook | Attacker triggers fake alerts to cause auto-isolation of legitimate hosts (defensive DoS) | M | H | **High** | Webhook authentication, internal network only, source IP allowlist | Low |
| T-003 | LLM API response | Man-in-the-middle returns spoofed "benign" verdict | L | M | Medium | HTTPS to API, response signature validation if available, structured output validation | Low — LLM is enrichment-only, doesn't trigger containment |
| T-004 | Canary file | Attacker creates files matching canary names to confuse FIM rules | L | L | Low | Canary paths are absolute and unique per deployment; rules match exact paths, not just names | Negligible |

### 3.2 Tampering (T)

| ID | Component | Threat | L | I | Risk | Mitigation | Residual |
|----|-----------|--------|---|---|------|------------|----------|
| T-010 | Local logs | Attacker clears Windows Event Log / journalctl before agent ships them (T1070.001) | H | H | **Critical** | Real-time forwarding (no buffer), redundant Sysmon→file→Filebeat→manager channel, alert on log clear events | Medium — fast attacker can clear before ship |
| T-011 | Sigma rules on disk | Attacker modifies rule files to disable detection | L | H | Medium | File integrity monitoring on `/var/ossec/etc/rules/`, rules signed and version-controlled, deployment via CI not manual edit | Low |
| T-012 | ML model | Attacker replaces model with weights that always output benign | L | H | Medium | Model file hash checked at load, model storage on read-only mount, signed model deployment | Low |
| T-013 | Baseline data (Capa 2) | Attacker contaminates baseline period with subtle malicious activity | L | M | Low | Baseline collection in supervised time window, manual review of baseline activity samples | Low |
| T-014 | LLM prompt | Attacker embeds prompt injection in process names/arguments/file paths logged by Sysmon | M | M | Medium | Input sanitization (strip control chars, length limits, escape special tokens), structured output forces JSON-only response, system prompt with explicit injection refusal | Low |

### 3.3 Repudiation (R)

| ID | Component | Threat | L | I | Risk | Mitigation | Residual |
|----|-----------|--------|---|---|------|------------|----------|
| T-020 | SOAR action | System auto-isolates a host but no audit trail of why | L | M | Low | Every Decision Engine action logs: triggering layers, scores, rationale, LLM analysis (if used), to OpenSearch with sequence numbers | Negligible |
| T-021 | Analyst action | Analyst marks alert as false-positive without trace | L | L | Low | Streamlit UI logs all user actions with user ID, timestamp, prior alert state | Negligible |

### 3.4 Information Disclosure (I)

| ID | Component | Threat | L | I | Risk | Mitigation | Residual |
|----|-----------|--------|---|---|------|------------|----------|
| T-030 | LLM API request | Sensitive logs (filenames, internal hostnames, command lines with secrets) sent to third-party API (DeepSeek/Qwen, both China-based) | H | M | **High** | Sanitization layer before LLM call: redact patterns matching credentials, internal IP ranges, employee usernames; document the data sent in `docs/data-handling.md` | Medium — accept residual disclosure for academic project; for production deployment use local LLM |
| T-031 | Canary path leakage | Attacker reads documentation/repo and learns canary paths to avoid them | M | M | Medium | Canary paths configured via env vars, not hardcoded; production deployment generates random subset of canaries per host; demo uses public paths but documents this limitation | Medium — acceptable for demo, documented |
| T-032 | OpenSearch API | Attacker reads alert history to learn detection logic | L | L | Low | OpenSearch on internal network only, authentication required, no public exposure | Negligible |
| T-033 | Wazuh agent key | Attacker on victim extracts agent key to register rogue agents | M | M | Medium | Agent key file root-owned 0600, key rotation supported, anomaly rule on duplicate agent registrations | Low |

### 3.5 Denial of Service (D)

| ID | Component | Threat | L | I | Risk | Mitigation | Residual |
|----|-----------|--------|---|---|------|------------|----------|
| T-040 | Wazuh Manager | Event flood from compromised agent overwhelms manager | M | H | **High** | Wazuh built-in rate limiting per agent, queue with backpressure, manager resource alerts | Medium |
| T-041 | LLM API | Attack triggers many alerts → many LLM calls → rate limit / cost spike | M | M | Medium | Per-incident rate limit on LLM calls (1 call per alert ID per 5min), monthly budget cap with hard cutoff, deduplication of similar alerts | Low |
| T-042 | SOAR Decision Engine | Alert flood overwhelms decision queue | M | M | Medium | Redis stream with persistence, deduplication by alert hash + host, graceful degradation: drop low-priority alerts before high-priority | Low |
| T-043 | Auto-isolation playbook | Defensive DoS — attacker triggers fake alerts to isolate legitimate hosts | M | H | **High** | Allowlist of host categories: "production critical" hosts require human approval; canary alerts pre-approved; cooldown per host (no re-isolation within 1h) | Medium |

### 3.6 Elevation of Privilege (E)

| ID | Component | Threat | L | I | Risk | Mitigation | Residual |
|----|-----------|--------|---|---|------|------------|----------|
| T-050 | Wazuh agent | Attacker with admin/root on victim disables agent (T1562.001) | H | H | **Critical** | Agent disconnect is itself a Wazuh rule (rule 502); manager alerts on heartbeat loss; Sysmon continues independent; agent self-restart on supported platforms | Medium — fast attacker disables before alert ships, but disconnect is detected within heartbeat interval (60s default) |
| T-051 | Wazuh Manager | Attacker pivots from victim to manager via shared network | L | C | High | Manager on isolated subnet, no inbound from victim subnet beyond agent port (1514), hardened OS (CIS baseline), no internet access from manager | Low |
| T-052 | SOAR service | Attacker exploits FastAPI service vulnerability to gain RCE on SOAR host | L | C | High | FastAPI on isolated host, no exposure to victim subnet, dependency scanning (`pip-audit`), input validation via Pydantic, no `eval` / dynamic code paths | Low |
| T-053 | LLM service | Prompt injection causes LLM to leak system prompt or internal config | L | L | Low | System prompt minimal, no secrets in prompt, output validation rejects responses outside expected schema | Negligible |

### 3.7 Approval system threats (new — added with ADR-0003/0005/0006)

The introduction of email-based approval flow (ADR-0003) and multi-recipient notifications (ADR-0005) introduces a new attack surface. Threats analyzed:

| ID | Component | Threat | L | I | Risk | Mitigation | Residual |
|----|-----------|--------|---|---|------|------------|----------|
| T-060 | Approval token (JWT) | Attacker intercepts approval email and uses the token to approve a malicious action or reject contention of their own attack | M | H | **High** | JWT signed with rotating secret, expiration 5 minutes, single-use (token invalidated after first response), TLS-only delivery, conservative-wins policy ensures single rejection cannot block contention if at least one approver also approves | Medium — accept residual: full mitigation requires email transport security beyond our control |
| T-061 | Email delivery | Attacker spoofs approval response by sending fake email to approval API endpoint | M | H | **High** | Approval API only accepts requests via the JWT-tokenized URL, not via email reply parsing; URL hits HTTPS endpoint with token validation | Low |
| T-062 | Compromised approver email account | Attacker with access to one approver's mailbox votes "reject" on legitimate threats | M | M | Medium | Conservative-wins (ADR-0006) — single reject cannot block contention if any approver approves; audit log shows each individual vote, suspicious pattern of rejects from one account becomes detectable | Low — intentional design choice |
| T-063 | Token replay | Attacker captures token from past email and replays it on new incident | L | M | Low | Tokens bound to specific incident_id; reused tokens rejected; tokens expire after 5 min absolute time | Negligible |
| T-064 | Defensive DoS via rejection flooding | Attacker triggers many T2/T3 alerts and floods approver inbox to delay legitimate responses | L | M | Low | Per-incident dedup by alert hash; rate limit on email sends per minute; T2/T3 with no response after timeout escalates to conservative auto-execute (ADR-0003) | Low |
| T-065 | Phishing of approvers | Attacker sends fake "approval needed" email tricking approver to click malicious link mimicking ARGOS | M | H | High | Approval emails sent only from designated `argos-noreply@` domain, links only to internal ARGOS dashboard URL (verifiable), training note in onboarding for approvers, optional DKIM/SPF strict | Medium — phishing always partially residual |
| T-066 | Audit log tampering | Attacker modifies decision audit log to hide that they rejected a contention | L | H | Medium | Audit log written to OpenSearch with append-only index settings, sequence numbers, daily snapshot to immutable storage | Low |

---

## 4. Failure Mode and Effects Analysis (FMEA)

Reliability failures — no adversary required. Numbered F-NNN.

### 4.1 LLM Triage Layer (Capa 4)

| ID | Failure mode | Effect on system | Detection | Mitigation | Degradation |
|----|--------------|------------------|-----------|------------|-------------|
| F-001 | DeepSeek API down | Capa 4 enrichment unavailable | HTTP error / timeout from client | Automatic fallback to Qwen API after 2 failed attempts | Degraded: alerts continue to flow, analyst sees raw alert without LLM analysis |
| F-002 | Both LLM APIs down | Full Capa 4 outage | Both fallback attempts fail | Circuit breaker opens, alerts marked `LLM_UNAVAILABLE` | Degraded: same as above; SOAR containment unaffected |
| F-003 | LLM hallucinates non-existent MITRE technique | Wrong analysis displayed to analyst | Pydantic validator + whitelist of valid ATT&CK IDs catches it | Reject response, retry once, fall through to "needs human triage" state | Degraded: alert without LLM enrichment |
| F-004 | LLM gives inconsistent verdicts for same input | Analyst confusion | Confidence score + monitoring on response variance over time | Cache responses by input hash (24h TTL), confidence threshold cutoff | Stable verdicts within cache window |
| F-005 | LLM API latency spike (>30s) | Slow analyst experience | Timeout monitor | Hard timeout 30s, async response (alert flows immediately, enrichment populated when ready) | Eventual consistency: alert visible immediately, LLM analysis appears when ready |
| F-006 | LLM cost spike from bug (infinite loop) | Budget exhausted, project funds drained | Budget monitor with alert at 80% / hard cutoff at 100% | Daily budget cap hardcoded in client, kill switch | Daily cap protects monthly budget |

### 4.2 ML Anomaly Detection (Capa 2)

| ID | Failure mode | Effect | Detection | Mitigation | Degradation |
|----|--------------|--------|-----------|------------|-------------|
| F-010 | ML consumer service crashes | Capa 2 silent | Heartbeat from consumer to manager, Wazuh rule on missing heartbeat | systemd auto-restart, alert if restart fails 3× | Degraded: Capas 1+3 still active |
| F-011 | Concept drift — baseline outdated, FP rate climbs | Alert fatigue, analyst trust erosion | FP rate tracked per week; alert if delta >2× baseline | Quarterly baseline retraining cadence; documented in runbook | Tunable, not catastrophic |
| F-012 | Model file corrupted on load | ML detection silent | Model load fails → service crash → F-010 path | Model file hash check at load; fallback to last-known-good model | Same as F-010 |
| F-013 | Redis stream backed up | ML lag behind events, missed attacks | Stream length monitored, alert at threshold | Backpressure to Wazuh; ML consumer scales horizontally if needed | Graceful: events processed eventually, just delayed |

### 4.3 SIEM (Wazuh)

| ID | Failure mode | Effect | Detection | Mitigation | Degradation |
|----|--------------|--------|-----------|------------|-------------|
| F-020 | Wazuh agent stops on victim (crash, not attack) | Telemetry loss for that host | Wazuh rule 502 (agent stopped), heartbeat timeout | Agent auto-restart via service manager; alert escalates to L2 if 3 restart attempts fail | Single host blind — investigate as potential incident |
| F-021 | Wazuh manager service crashes | Full system blind | systemd alert + external heartbeat check | systemd auto-restart, manager health check from independent monitor | Critical — full outage during recovery (30-60s typical) |
| F-022 | OpenSearch index corruption | Loss of historical data | OpenSearch cluster health check | Nightly index snapshot to separate volume | Recovery from snapshot, possible loss of <24h |
| F-023 | Disk full on manager | New events dropped | Disk space monitor at 80% / 90% | Index lifecycle management (retain 30d hot, 90d warm), alerting before saturation | Predictable, manageable |
| F-024 | Sigma rule with bug causes rule engine to slow / crash | Detection latency or outage | Wazuh rule engine logs, latency monitor | Rule changes via PR with test suite (analyzer + sample event), staged rollout | Rule reverted, fixed, redeployed |

### 4.4 Detection Engine — Sigma Rules (Capa 1)

| ID | Failure mode | Effect | Detection | Mitigation | Degradation |
|----|--------------|--------|-----------|------------|-------------|
| F-030 | False negative on known TTP (rule too narrow) | Missed detection | Continuous testing with Atomic Red Team in CI | Atomic Red Team runs weekly, gap report; rules iteratively tuned | Capas 2 and 3 cover variants |
| F-031 | False positive flood (rule too broad) | Alert fatigue | FP rate per rule tracked | Confidence per rule, suppression rules for known-benign, threshold tuning | Rule disabled if FP > threshold pending tuning |

### 4.5 Deception Layer (Capa 3)

| ID | Failure mode | Effect | Detection | Mitigation | Degradation |
|----|--------------|--------|-----------|------------|-------------|
| F-040 | Canary deleted by legitimate cleanup script | False alarm | Canary integrity check runs hourly, alerts on missing canaries | Canaries placed in paths excluded from cleanup, recreated automatically if missing | Self-healing |
| F-041 | FIM whodata service stops on Windows | Capa 3 silent on that host | FIM service heartbeat | Auto-restart, alert if persistent | Same as F-020 |

### 4.6 SOAR Decision Engine

| ID | Failure mode | Effect | Detection | Mitigation | Degradation |
|----|--------------|--------|-----------|------------|-------------|
| F-050 | Decision Engine crashes mid-incident | Containment doesn't trigger | Service heartbeat, alert on miss | systemd auto-restart, persistent queue (Redis) survives crash, on restart processes queued alerts | Brief delay, alerts not lost |
| F-051 | Containment playbook fails (e.g., iptables command errors) | Host not isolated despite alert | Playbook logs return code, alert on failure | Playbooks idempotent; retry once; escalate to manual on second failure | Manual containment fallback |
| F-052 | Race: attack progresses faster than detection chain | Files encrypted before isolation | Time-to-detect metric tracked per incident | Capa 3 (canary) gives ultra-early signal; isolation playbook completes <5s after trigger; **for T2/T3 with human approval, proactive throttle during countdown bounds damage** | Documented limitation; minimum theoretical TTD ~3-5s; throttle effectiveness target ≥90% of files preserved during T2 countdown |

---

## 5. Project Execution Risks

Numbered P-NNN. Reviewed weekly in standup.

| ID | Risk | Likelihood | Impact | Risk | Mitigation | Owner |
|----|------|------------|--------|------|------------|-------|
| P-001 | Team member drops course / unavailable for >1 week | M | H | High | Documented runbooks per layer, pair sessions in standup, no single-author code in critical paths | All |
| P-002 | Knowledge silo — only one person understands their layer | H | M | High | Friday demo (each presents their work), code review across layers, comprehensive READMEs per module | All |
| P-003 | Tesis collision with Enzo (P1) availability | H | M | High | P1 explicitly does not commit beyond 6h/week; Capa 4 scope reducible if needed; Capa 4 abandonable per Gate 2 | P1 |
| P-004 | Scope creep — feature additions during build | H | M | High | All scope changes via written ADR; gates enforce baseline before extras; PRs Sigma upstream are stretch goals only | P1 |
| P-005 | Profesor rejects Capa 4 LLM as out-of-course-scope | L | H | Medium | Validation conversation in week 1 before commit; backup plan: simplified version with rules+ML+deception | P1 |
| P-006 | Demo failure live — VM crash, network issue, API down | M | H | High | Pre-recorded video backup; rehearsal x10; demo on local-only path (no internet dependency); LLM API key with backup credit | P4 |
| P-007 | Sigma upstream PRs all rejected | M | L | Low | PRs are bonus, not core; rejected PRs documented with feedback in repo | P3 |
| P-008 | Hardware unavailable — no team member has machine for lab VMs | L | H | Medium | Lab specs documented week 1; cloud fallback (free tier Azure/GCP) if needed | P4 |
| P-009 | Mid-semester exam weeks reduce productivity | H | L | Medium | Plan compressed in non-exam weeks; P1 absorbs critical-path work during exam weeks | All |

---

## 6. Resilience by Design — Defense in Depth Properties

The architecture has explicit resilience properties that follow from defense-in-depth. These are testable claims, not aspirations:

### R-1. No single point of failure in detection

Three detection layers run in parallel and independent. Failure of any one degrades the system to "still functional with reduced coverage", never to "blind".
- **Layer 1 fails →** Layers 2+3 still detect.
- **Layer 2 fails →** Layers 1+3 still detect.
- **Layer 3 fails →** Layers 1+2 still detect.

### R-2. LLM is never on the containment critical path

The Decision Engine triggers containment based on Layers 1-3 alone. The LLM (Capa 4) provides analyst-facing enrichment only. **A malfunctioning LLM cannot prevent containment, only fail to enrich an analyst's view.** This is enforced by the Decision Engine code path: SOAR action → response playbook → (parallel) LLM enrichment → analyst notification.

### R-3. Containment fails closed, not open

If automated isolation playbook fails, the system **does not assume success**. The alert state remains "uncontained" and escalates to manual response. There is no scenario where "couldn't isolate" silently becomes "containment complete".

### R-4. Agent disconnect is itself a signal

If an attacker disables the Wazuh agent on a victim, the disconnect produces a high-priority alert (Wazuh rule 502 + heartbeat monitoring). "Suspicious silence" is treated as a positive indicator of compromise, triggering investigation and potential isolation.

### R-5. Logs ship in real time, not batched

All telemetry forwards to the manager immediately, not buffered locally. An attacker clearing local logs after action cannot prevent the events from already being in the manager's index. Mitigation against T1070.001.

### R-6. LLM output validated, never trusted blindly

Every LLM response passes through:
- Pydantic schema validation (rejects malformed JSON).
- MITRE ATT&CK ID whitelist (rejects hallucinated technique IDs).
- Confidence threshold (low-confidence responses flagged for human review).
- No-action constraint (LLM cannot trigger isolation or kill commands; output is descriptive only).

### R-7. Redundant log shipping where critical

For high-value hosts (in production deployment), Sysmon writes to local file in addition to Wazuh forward. A separate Filebeat agent ships the file to a backup collector. Compromise of one shipping channel does not eliminate the evidence trail.

### R-8. Vendor portability prevents lock-in failure

LLM backend is abstracted. If DeepSeek is down, Qwen takes over. If both are down, system continues without enrichment. If long-term we want full sovereignty, swap to local Llama 3.1 — change of one config value.

### R-9. State persistence across crashes

Decision Engine queue, ML consumer state, and OpenSearch indexes all survive process restarts. A 30-second outage in any service does not lose pending alerts.

### R-10. Cost-bounded operations

LLM API calls have per-incident rate limits and monthly budget caps. A pathological attack pattern (or bug) cannot drain the project budget — the system fails closed on cost before spending exceeds the cap.

---

## 7. Demo-specific risks and contingencies

The exposition is the highest-stakes single event. Specific contingencies:

| Scenario | Contingency |
|----------|-------------|
| Live attack doesn't trigger as expected | Pre-recorded video of full successful run played as backup |
| LLM API down at demo time | Fall back to Qwen visibly during demo (good story); if both down, narrate "this is where the LLM analysis would appear" with screenshot |
| VM crashes during demo | Snapshot of pre-attack state restored; second laptop with full lab as backup |
| Network issue (university wifi) | Demo runs entirely on internal lab network; LLM API call cached to last-good response if internet down |
| Streamlit UI bug surfaces | Show OpenSearch dashboard as alternative view |
| One team member sick on demo day | Each member has trained on the adjacent layer; remaining team can present full system |

**Mandatory:** demo is recorded (high quality video) the day before exposition as definitive backup.

---

## 8. Residual risks accepted by the team

Risks we explicitly accept and document, in order of priority:

1. **T-030 (LLM data disclosure to China-based API):** for an academic project with synthetic lab data, accepted. Documentation states this clearly. For production, swap to local LLM.
2. **T-014 (LLM prompt injection):** mitigations reduce but don't eliminate. Accept residual risk because LLM cannot trigger actions.
3. **T-050 (fast attacker disables agent before alert ships):** documented as fundamental limit. Heartbeat interval can be reduced to mitigate but trades off network noise.
4. **F-052 (race condition: attack faster than detection):** documented theoretical TTD floor of ~3-5s. Some files will be encrypted before isolation. This is honest and documented in metrics.
5. **T-031 (canary path leakage via repo):** for demo, accepted. Production deployment should use env-var-driven random canary placement.

---

## 9. Threat model maturity & next steps

This v1.0 covers the architecture as designed. The model will be revisited at:
- **Gate 2 (Week 7):** when Layers 1+2+3 are integrated, re-verify trust boundaries.
- **Gate 3 (Week 9):** when LLM is integrated, deep-dive on prompt injection in evaluation.
- **Pre-demo (Week 13):** dedicated red-team session — one team member tries to break the system.

Future expansions (out of scope for v1.0):
- DREAD scoring (currently using simpler L×I matrix).
- Attack tree formalization for top-3 threats.
- Automated security scanning of the system itself (Semgrep, Bandit on our code; Trivy on dependencies).

---

## 10. Change log

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | Week 1 | Initial baseline. STRIDE for 4 categories, FMEA for 6 components, Risk Register with 9 project risks, 10 resilience properties documented. | P1 |
| 1.1 | Week 1 | Added Section 3.7 (approval system threats) covering 7 new threats T-060 through T-066 introduced by ADRs 0003/0005/0006. Updated residual risks list. | P1 |

---

*This is a living document. New threats identified during implementation are added with an ID continuing the existing numbering. Mitigations are revisited when the underlying component changes.*
