# USE CASES — ARGOS demo scenarios + evaluation cases

| Field | Value |
|-------|-------|
| Document type | Use Case Specification |
| Version | 1.1 |
| Status | Approved |
| Owner | P1 (Enzo) |
| Reviewers | P2, P3, P4 |
| Related | `SOLUTION_ARCHITECTURE_DOCUMENT.md`, `THREAT_MODEL.md`, ADRs 0001-0008, `OPEN_QUESTIONS_RESOLUTION.md` |

---

## 0. Purpose

This document specifies the concrete attack scenarios that ARGOS will detect and respond to, both for the live exposition (demo scenarios) and for system robustness evaluation (non-demo scenarios). Each scenario defines: the attack TTPs, expected detection layers, expected tier classification, expected system response, demo narration if applicable, and success criteria.

The demo scenarios are designed to be reproducible end-to-end on the lab VMs and to tell a coherent story to the evaluator. Non-demo scenarios stress-test the system's robustness and feed the evaluation metrics in the technical informe.

---

## 1. Demo success definition

Per Q9 resolution and Q3 of `OPEN_QUESTIONS_RESOLUTION.md`, demo success requires **all four** elements per scenario:

1. **Detection:** at least one expected detection layer fires correctly.
2. **Containment:** ransomware activity is contained before majority of real files are encrypted (>80% preservation target).
3. **LLM analysis:** technique MITRE correctly identified, severity coherent, runbook citation valid.
4. **Audit trail:** complete, queryable in OpenSearch, decision rationale explicit.

The exception is the **Canary Deception scenario** (UC-02), which targets a stronger criterion: **zero real files encrypted** (canary fires before attacker reaches real files).

---

## 2. Demo scenarios overview

The exposition presents **four demo scenarios** in narrative sequence, plus an optional fifth as time allows:

| ID | Name | Tier | Vector | Layers triggered | Approval flow | Duration | Purpose |
|----|------|------|--------|------------------|---------------|----------|---------|
| **UC-01** | Classic Ransomware (LockBit-like) | T0 | Ransomware | 1 + 2 + 3 | Auto-execute, multi-canal post-facto | ~2 min | Show full stack working end-to-end |
| **UC-02** | Canary Deception (early detection) | T0 | Ransomware | 3 alone | Auto-execute, multi-canal post-facto | ~1.5 min | Showcase ultra-early detection, zero damage |
| **UC-03** | Novel Variant (ML detection) | T2 | Ransomware | 2 alone | Pre-approval with split-brain | ~4 min | **Centerpiece**: demonstrate human-in-the-loop with conservative-wins |
| **UC-04** | PostgreSQL en Producción (two-person rule) | T1 | Ransomware | 1 + 2 | Two-person approval | ~3 min | Compliance vocabulary, governance maturity |
| **UC-05** | Stealth Attack (agent kill attempt) | T0 | Ransomware | 1 + 3 + heartbeat | Auto-execute | ~2 min | Resilience: agent disconnect as signal |
| **UC-06** | DDoS volumetric (per ADR-0008) | T0 | Network DoS | 1 (rate rules) + 2 (network anomaly) | Auto-execute con rate-limit | ~2 min | Demuestra cobertura multi-vector: el sistema defiende contra ataques de red, no solo endpoint. T1498. |
| **UC-07** | SELECT masivo legítimo — false positive cancelado (per ADR-0008) | T2 | Application abuse / Valid Accounts | 2 (query pattern anomaly) | **Pre-approval, REJECTED por aprobador → contención cancelada** | ~3 min | **Pieza clave del HITL**: ML detecta anomalía real pero es actividad legítima, humano reconoce contexto y previene daño por false positive. T1078. |
| **UC-08** | SQL injection contra app web (per ADR-0008) | T1 | Application abuse / Initial Access | 1 (SQLi signatures) + 2 (request pattern anomaly) | Auto-execute + block IP | ~2 min | OWASP Top 10 #1. Cobertura de Initial Access via Exploit Public-Facing Application. T1190. |

**Total demo runtime con 8 UCs:** ~19-20 min en vivo. Si excede la ventana típica de 15 min de exposición, ajustar narración para que UC-02 sea más rápida (1 min) y UC-05/UC-06 se cubran en 1.5 min cada uno. UC-03 y UC-07 son los que más tiempo merecen porque son los que muestran HITL en profundidad (split-brain y false positive cancelado respectivamente).

**Cobertura MITRE ampliada (per ADR-0008):**
- **Impact:** T1486 (Data Encrypted), T1490 (Inhibit Recovery), T1498 (Network DoS), T1499 (Endpoint DoS)
- **Initial Access:** T1190 (Exploit Public-Facing Application = SQL injection)
- **Valid Accounts:** T1078 (legitimate user activity como FP)
- **Defense Evasion:** T1562 (Impair Defenses), T1070 (Indicator Removal)
- **Discovery:** T1083 (File and Directory Discovery)
- **Lateral Movement:** T1021 (Remote Services)
- **C2:** T1071 (Application Layer Protocol)

---

## 3. Scenario details

### UC-01 — Classic Ransomware (LockBit-like)

**Purpose:** Open the demo with a high-confidence end-to-end run. Establishes that the full system works on the canonical ransomware case.

#### Attack details

- **Source:** Custom Python ransomware simulator on Windows victim VM.
- **Behavior chain:**
  1. File enumeration of `C:\Users\Demo\Documents\*` (T1083 — File and Directory Discovery).
  2. Shadow copy deletion via `vssadmin delete shadows /all /quiet` (T1490 — Inhibit System Recovery).
  3. AES-256 encryption of enumerated files with `.locked` extension (T1486 — Data Encrypted for Impact).
  4. Ransom note dropped to desktop.
  5. Beacon attempt to fake C2 endpoint (T1071 — Application Layer Protocol).

#### Expected system behavior

- **Layer 1 (Sigma):** Fires on `vssadmin delete shadows` rule (T1490). Score: 0.92.
- **Layer 2 (ML):** Detects entropy spike + rapid file write rate. Score: 0.88.
- **Layer 3 (Canary):** Fires when ransomware enumerates and encrypts canary files. Score: 1.0.
- **Tier classification:** T0 (all three layers fire = critical confirmed).
- **Decision Engine action:** Immediate auto-isolation + disk snapshot + process kill. Email post-facto with "Revert" button.
- **LLM analysis:** Correctly identifies T1486, severity critical, cites NIST 800-61 §3.4.

#### Success criteria

- Time-to-detect: ≤5 seconds from attack initiation to first alert.
- Files encrypted before containment: ≤50 (out of ~500 in test corpus, including canaries that are designed to be touched).
- All three layers fire within 10s of each other.
- LLM correctly identifies technique with confidence >0.85.
- Audit log shows complete event chain.

#### Demo narration script (~2 min)

| Time | Narrator | Screen |
|------|----------|--------|
| 0:00 | "We'll start with the canonical case: classic ransomware behavior." | Streamlit dashboard, OpenSearch dashboard side-by-side |
| 0:15 | P4 launches attack from terminal: `python ransomware_sim.py --target windows-victim --speed full` | Terminal command visible |
| 0:30 | "Within seconds, three independent detectors fire." | Dashboard lights up: 3 alerts in 5s |
| 0:45 | "All three layers agree, confidence 0.95+, classified as T0 — critical confirmed." | Tier badge visible, layers highlighted |
| 1:00 | "Decision Engine triggers immediate isolation. No human approval needed at this confidence." | Isolation action card with timestamp |
| 1:15 | "Email goes to the team post-facto with full forensic context and a Revert button." | Show email on phone screen |
| 1:30 | "LLM analysis confirms T1486 — Data Encrypted for Impact, with NIST 800-61 runbook citation." | LLM panel visible |
| 1:45 | "Audit log captures every decision. Containment in 4.2 seconds. 31 files encrypted, 469 preserved." | Metrics card |

#### Owner: P4 (attack orchestration), P1 (decision logic narration)

---

### UC-02 — Canary Deception (early detection)

**Purpose:** Showcase the most distinctive feature of the architecture: deception-based detection that catches attacks *before* they reach real files.

#### Attack details

- **Source:** Custom Python ransomware simulator with **directory-traversal enumeration order** (alphabetical or path-walking, not filtered). Canaries are placed in paths that any indiscriminate enumeration will hit.
- **Behavior chain:**
  1. File enumeration starting from `C:\Users\Demo\Documents\` (T1083).
  2. Reaches canary file `financials_Q4_2025.xlsx` early in enumeration.
  3. Attempts to read/encrypt the canary.
  4. **At this point, system already isolated host — no further behavior observed.**

#### Expected system behavior

- **Layer 3 (Canary FIM):** Fires immediately on canary access. Score: 1.0.
- **Layer 1 / Layer 2:** Do NOT fire — attack interrupted before producing enough signal.
- **Tier classification:** T0 (canary alone = critical confirmed by design, zero-FP property).
- **Decision Engine action:** Immediate auto-isolation. No need for corroboration.
- **LLM analysis:** Identifies the alert as canary-triggered. Cites NIST 800-61 §3.3.4 on deception-based detection. Recommends forensic review of process tree.

#### Success criteria

- **Zero real files encrypted** (only canary touched).
- Time-to-detect: ≤2 seconds from canary access.
- Time-to-containment: ≤8 seconds total.
- Canary file integrity event logged with full whodata (offending PID, parent process, command line).

#### Demo narration script (~1.5 min)

| Time | Narrator | Screen |
|------|----------|--------|
| 0:00 | "Now a different scenario. Same ransomware, but this time we have canaries deployed strategically." | Show canary file list in `C:\Users\Demo\Documents\` |
| 0:15 | "These files are honeypots. A legitimate user would never touch `financials_Q4.xlsx` because it's a fake." | Highlight canary names |
| 0:30 | P4 launches: `python ransomware_sim.py --enumeration alphabetical` | Attack runs |
| 0:45 | "Within 1.4 seconds, the attacker reaches the canary." | Alert fires, ONE alert this time, severity critical |
| 1:00 | "Canary access has a special property: zero-FP by design. The system trusts this signal absolutely." | Tier T0, single layer |
| 1:15 | "Isolation in 6 seconds total. Zero real files encrypted." | Metrics: 0/500 files affected |
| 1:30 | "This is the value of deception. We caught the attacker before they reached anything that mattered." | Final state visible |

**Key narrative point:** "Most defenses detect the attack while it's happening. Deception detects it *as soon as it starts*."

#### Owner: P3 (canary configuration), P4 (attack orchestration)

---

### UC-03 — Novel Variant (ML detection + split-brain) ⭐ CENTERPIECE

**Purpose:** Demonstrate the unique combination that no other student project will have: ML-based detection of an unknown variant + human-in-the-loop with multi-approver split-brain resolution.

#### Attack details

- **Source:** A second variant of the ransomware simulator, deliberately modified to **NOT match any Sigma rule** in our ruleset. The variant:
  - Does NOT call `vssadmin` (uses WMIC for shadow copy deletion instead, less common).
  - Does NOT use the `.locked` extension (uses random extensions per file).
  - Does NOT drop a ransom note in standard locations.
  - Encrypts at a moderate rate (~5,000 files/min) that's still anomalous but slower than a benchmark match.
- **Behavior chain:**
  1. File enumeration via PowerShell (T1083 — but using a code path our Sigma rules don't catch).
  2. WMIC-based shadow copy manipulation (variant of T1490).
  3. AES encryption with random extensions.
- **Crucial:** canaries **are not in the path** of this attack. Only ML can catch it.

#### Expected system behavior

- **Layer 1 (Sigma):** Does NOT fire. By design.
- **Layer 2 (ML):** Fires on entropy + write rate anomaly. Score: 0.74. Above T2 threshold but below T1.
- **Layer 3 (Canary):** Does NOT fire (canaries outside attack path).
- **Tier classification:** T2 (ML alone, medium-uncertain confidence).
- **Decision Engine action:**
  1. Immediately applies throttle on offending process (CPU/IO limits).
  2. Triggers proactive disk snapshot.
  3. Sends approval requests through the multi-channel chain defined in ADR-0007 v2 to all 4 team members (Telegram bot con botones inline + Discord webhook con `@mention` de role en paralelo a t=0; llamada Twilio con DTMF como escalación a t=60s si nadie respondió).
  4. Starts 3-minute countdown with conflict detection.
  5. Email post-facto resume goes to all approvers after final decision (`EmailChannel`, post-facto notification only, per ADR-0007 v2).
- **The split-brain happens here:**
  - **Enzo (P1) at +18s:** clicks "Reject — false positive" (deliberately, per script).
  - **P2 at +35s:** clicks "Approve isolation".
  - **P3 at +52s:** clicks "Approve isolation".
  - **P4:** does NOT respond (deliberately, per script — demonstrates timeout handling).
- **At 60s consolidation window close:** conservative-wins applied. 2 approve vs 1 reject vs 1 timeout → execute isolation.
- **LLM analysis:** Identifies pattern as likely ransomware variant despite no rule match. Suggests the WMIC technique as MITRE T1490 sub-technique. Confidence 0.78.

#### Success criteria

- Throttle reduces encryption velocity by ≥80% (verifiable: files encrypted during 3-min countdown should be ≤500 instead of ~15,000 unmitigated).
- Split-brain detected and visualized in Approval Workflow Console.
- Conservative-wins policy applied correctly.
- Audit trail captures all 4 approver responses (including P4's timeout) with timestamps and latencies.
- Final email summary lists policy applied and rationale.

#### Demo narration script (~4 min — longest scenario, justified)

| Time | Narrator | Screen |
|------|----------|--------|
| 0:00 | "Now the hardest case: a variant we've never seen. Our Sigma rules don't match it. Canaries aren't in its path." | Static intro slide |
| 0:15 | P4 launches: `python ransomware_variant_2.py --target windows-victim --evade-rules` | Terminal command |
| 0:30 | "Layer 1 stays silent. Layer 3 stays silent." | Dashboard shows no rule alerts |
| 0:45 | "But our ML model is watching the *behavior*, not the signature." | ML panel highlights |
| 1:00 | "Score 0.74 — anomalous but not certain. Tier T2. This requires human approval." | Tier badge, score visible |
| 1:15 | "But before any human looks at it, two things happen automatically: throttle and snapshot." | Show throttle indicator + snapshot timestamp |
| 1:30 | "Encryption velocity drops 80%. Forensic state preserved. Now we wait — but we wait safely." | Velocity graph drops |
| 1:45 | "Four team members get the request via Telegram and Discord in parallel. Watch what happens." | Show 4 phones with Telegram inline buttons + Discord channel mirror with role mention |
| 2:00 | Enzo clicks **Reject**. | Console shows row 1 turn red |
| 2:15 | P2 clicks **Approve**. | Console shows row 2 turn green. Banner: "CONFLICT DETECTED" |
| 2:30 | "We have a split-brain. The system started a 60-second consolidation window." | Countdown timer visible |
| 2:45 | P3 clicks **Approve**. | Row 3 green. Score becomes 2 approve vs 1 reject |
| 3:00 | P4 deliberately doesn't respond. | Row 4 stays yellow |
| 3:15 | Window closes. Banner: "EXECUTING — 2 approve · 1 reject · 1 timeout · conservative-wins applied" | Action executes |
| 3:30 | "Conservative-wins is intentional. In ambiguity, we err toward action. The audit log captures every decision." | Audit trail panel |
| 3:45 | "Throttle prevented mass damage during the wait. ML caught what rules couldn't. Multiple humans participated. Disagreement was resolved by policy, not power." | Final state |

**Key narrative points to emphasize:**
1. ML catches what rules can't (novel variant detection).
2. Throttle is the silent hero — it bounds damage during human deliberation.
3. Split-brain has a documented resolution policy, not improvisation.
4. Audit trail makes every decision defensible.

#### Owner: P1 (decision logic + Approval Console), P2 (ML behavior), P4 (attack orchestration), P3 (rule absence verification)

---

### UC-04 — Production Database (two-person rule)

**Purpose:** Show governance and compliance vocabulary. Demonstrate that not all hosts are equal — el host que aloja la **base PostgreSQL de producción** (activo defendido por ARGOS) requiere autorización adicional per ADR-0003.

#### Attack details

- **Target:** Linux Ubuntu Server VM con **PostgreSQL 15** corriendo (esquema `argos_demo_prod` con tablas employees / payroll / customers / invoices / payments y datos sintéticos representativos). Host tagged en Wazuh como `criticality=production-critical` per OPEN_QUESTIONS_RESOLUTION §Q2.
- **Source:** Atomic Red Team T1490 — shadow copy deletion equivalent on Linux + `pg_dump` exfil simulation.
- **Behavior chain:**
  1. SSH access (legitimate-looking but using stolen credential simulation).
  2. Snapshot deletion: `btrfs subvolume delete /backup/snapshots/*` y borrado de los `pg_dump` exports en `/var/backups/postgres/*.sql`.
  3. Tar archive de `/var/lib/postgresql/15/main/` (data directory de PostgreSQL) a staging.
  4. Intento de encriptación de los dumps SQL antes de exfil (signal claro para ML).
  5. (Attack interrupted by detection)

#### Expected system behavior

- **Layer 1 (Sigma):** Fires on snapshot deletion rule. Score: 0.85.
- **Layer 2 (ML):** Fires on anomalous archive creation pattern. Score: 0.81.
- **Tier classification:** T1 (high-confirmed, both layers corroborate).
- **Decision Engine action:**
  - Standard T1 flow would auto-execute isolation.
  - **BUT** host is tagged `production-critical`, so two-person rule applies.
  - System sends approval email requiring TWO approvals (not one) before isolation executes.
  - Throttle and snapshot proactive actions happen immediately (same as T2).
- **Split scenario in demo:**
  - First approver (Enzo) clicks **Approve**.
  - Console shows "1 of 2 required approvals — awaiting second".
  - Second approver (P2) clicks **Approve**.
  - Containment executes.

#### Success criteria

- Two-person rule visibly enforced in Approval Console (counter "1 of 2 required").
- Throttle active throughout dual-approval wait (~30-45s).
- Final isolation executes only after second approval.
- Audit log captures both approvals with timestamps and roles.

#### Demo narration script (~3 min)

| Time | Narrator | Screen |
|------|----------|--------|
| 0:00 | "Our crown-jewel asset: PostgreSQL en producción con payroll, customers, invoices. Tagged production-critical." | Show host inventory + `\dt` output del esquema argos_demo_prod |
| 0:15 | P4 launches attack: `python attack_db_server.py` | Terminal |
| 0:30 | "Detection fires from Layers 1 and 2. Tier T1, normally auto-execute." | Dashboard lights up |
| 0:45 | "But this host requires two-person rule. The system asks for *two* approvals, not one." | Console shows counter "0 of 2" |
| 1:00 | "Throttle and snapshot are already running. The database is protected, but not yet isolated." | Throttle indicator |
| 1:30 | Enzo clicks Approve. | Counter: "1 of 2" |
| 1:45 | "One approval received. Action still pending. This is the four-eyes principle." | Console state |
| 2:15 | P2 clicks Approve. | Counter: "2 of 2 — executing" |
| 2:30 | "Both approvals received. Containment now executes." | Action card |
| 2:45 | "This is governance baked into automation. Compliance vocabulary: SOC 2 §CC6, ISO 27001 §A.9.4." | Closing slide |

**Vocabulary used:** four-eyes principle, two-person integrity, separation of duties, governance, compliance.

#### Owner: P1 (decision logic), P3 (Linux attack adaptation)

---

### UC-05 — Stealth Attack (agent kill attempt)

**Purpose:** Demonstrate resilience property R-04: "Agent disconnect is itself a signal" (per SAD §12.1).

#### Attack details

- **Source:** Atomic Red Team T1562.001 — Disable or Modify Tools.
- **Behavior chain:**
  1. Privilege escalation simulated (assumed admin/SYSTEM achieved).
  2. Attempt to stop Wazuh agent service: `Stop-Service -Name "WazuhSvc" -Force`.
  3. Attempt to delete agent binary or configuration.
  4. Begin ransomware behavior (assumes agent is silenced).

#### Expected system behavior

- **Layer 1 (Sigma):** Fires on `Stop-Service WazuhSvc` rule before agent dies (real-time event shipping). Score: 0.88.
- **Wazuh rule 502 (agent stopped):** Fires within heartbeat interval (~60s) after agent disconnects.
- **Combined signal:** "Stop-Service of monitoring agent" + "agent went offline" within ~60s = high-confidence indicator of attack.
- **Tier classification:** T0 (intent + execution = critical confirmed). Per SAD R-04, agent disconnect alone could justify lower tier; combined with Layer 1 signal it's T0.
- **Decision Engine action:** Immediate auto-isolation (host is offline already from agent perspective, but network-level isolation kicks in regardless via SOAR command to network controller).
- **LLM analysis:** Identifies attack pattern. Cites MITRE T1562.001 and recommends investigation of all activity in 5-min window before agent kill.

#### Success criteria

- Layer 1 catches the stop-service event before agent dies (real-time shipping).
- Rule 502 fires within 60-90s of disconnect.
- Network-level isolation executes despite agent unavailability.
- Audit trail shows full sequence: stop-service → agent disconnect → isolation.

#### Demo narration script (~2 min)

| Time | Narrator | Screen |
|------|----------|--------|
| 0:00 | "What if the attacker tries to disable our defense?" | Title card |
| 0:15 | P4 launches: `python attack_kill_agent.py` (privilege escalation + service stop) | Terminal |
| 0:30 | "First, attacker stops the Wazuh agent. But events ship in real-time — the stop event reaches the manager before the agent dies." | Layer 1 fires |
| 0:45 | "Within seconds, agent goes offline. Rule 502 fires automatically." | Disconnect alert |
| 1:00 | "Suspicious silence is itself a signal. The system isolates the host at the network level, even though the agent can't speak anymore." | Network isolation card |
| 1:30 | "This is resilience property R-04 from our threat model: an attacker disabling our agent doesn't disable our defense." | SAD reference |
| 1:45 | "Audit trail captures the full sequence. The attacker tried to go silent. The silence betrayed them." | Audit trail panel |

#### Owner: P3 (agent kill rules), P4 (attack scripts)

---

### UC-06 — DDoS volumétrico contra PostgreSQL (per ADR-0008)

**Purpose:** Demostrar cobertura multi-vector. El sistema defiende el activo PostgreSQL no solo contra cifrado de archivos sino también contra ataques de red que buscan saturar el servicio. Cubre tactic **Impact** via técnica T1498 (Network Denial of Service) — categoría distinta al kill chain de ransomware.

#### Attack details

- **Source:** atacante remoto (ejecutado desde laptop del demo o desde el host Vagrant) usando `hping3` para SYN flood, `slowhttptest` para slow-rate DoS, o `iperf3 -c <victim> -P 100` para flood UDP/TCP.
- **Target:** puerto 5432 (PostgreSQL) o puerto 80/443 si hay nginx delante del servicio, sobre la Linux VM víctima.
- **Behavior chain:**
  1. Atacante envía 1000+ paquetes/segundo al puerto 5432 (T1498.001 Direct Network Flood) o 10K conexiones HTTP semi-abiertas (T1499.002).
  2. Capa de detección Wazuh observa burst de eventos en `iptables` logs / `nginx access logs`.
  3. Regla Sigma rate-based dispara cuando count > umbral en ventana de 10s.

#### Expected system behavior

- **Layer 1 (Sigma rate-based):** dispara via regla `network_flood_detected` (definida sobre `<frequency>` nativa de Wazuh). Score: 0.95+.
- **Layer 2 (ML network anomaly):** modelo especializado `network_traffic_anomaly.pkl` (features: connections/sec, packet rate, source IP entropy, packet size variance) corrobora con score 0.90+.
- **Tier classification:** T0 (rate inequívoco + ML corrobora).
- **Decision Engine action:** rate-limit del IP atacante via iptables (`iptables -A INPUT -s <attacker_ip> -p tcp --dport 5432 -m limit --limit 10/sec -j ACCEPT`), drop del resto, snapshot de estado del servicio.
- **LLM analysis:** identifica T1498, severidad crítica, runbook NIST 800-61 §3.3.2 sobre containment de DoS, recomienda revisar logs de upstream router para tracear el origen.

#### Success criteria

- Detección dentro de 30 segundos de iniciado el flood.
- Rate-limit aplicado preserva la capacidad de respuesta del servicio a tráfico legítimo durante el ataque.
- Audit log captura: IP atacante, rate alcanzado, técnica MITRE.

#### Demo narration script (~2 min)

| Time | Narrator | Screen |
|------|----------|--------|
| 0:00 | "Cambiamos de vector: ahora no atacamos archivos, atacamos disponibilidad. El atacante busca saturar nuestra base de datos." | Show network topology + PostgreSQL endpoint |
| 0:20 | P4 lanza: `hping3 --flood --syn -p 5432 <linux-victim-ip>` | Terminal con flood corriendo |
| 0:30 | "Wazuh detecta el burst de conexiones en segundos." | Sigma rate rule firing |
| 0:50 | "Capa 2 ML confirma: el patrón de tráfico es anómalo respecto al baseline." | ML score panel |
| 1:10 | "T0 — el sistema aplica rate-limit al IP atacante. El servicio sigue disponible para tráfico legítimo." | iptables rule applied + servicio respondiendo |
| 1:30 | "Esto demuestra que la misma arquitectura defiende contra ransomware Y contra ataques de red. El framework es adaptativo." | MITRE coverage matrix con T1498 destacado |

#### Owner: P3 (Sigma rate rules), P4 (hping3 + slowhttptest scripts), P2 (network anomaly model)

---

### UC-07 — SELECT masivo legítimo — false positive cancelado por humano (per ADR-0008)

**Purpose:** La pieza más valiosa del demo. Demuestra el escenario T2 donde el sistema NO está seguro y el humano cancela una contención por reconocer que la actividad es legítima. Es la diferencia fundamental entre un SIEM (que solo alerta) y un EDR/XDR con HITL (que respeta la incertidumbre).

#### Attack details — pero NO es un ataque

- **Source:** Sebastian (P2) ejecuta legítimamente `SELECT * FROM payroll JOIN employees ON ...` que devuelve 100,000 filas a las 03:47 AM (fuera de horario laboral) porque está generando el reporte mensual de nómina con deadline el día siguiente.
- **Target:** PostgreSQL `argos_demo_prod` schema, mismo activo defendido.
- **Behavior chain:** query SELECT muy amplia, devuelve volumen anormal, en horario no laboral, desde IP del laptop de P2 que no es servidor de reporting habitual.

#### Expected system behavior

- **Layer 1 (Sigma):** NO dispara — no hay patrón de query malicioso, es SELECT válido.
- **Layer 2 (ML query pattern anomaly):** dispara con score 0.65. Modelo entrenado sobre baseline de queries normales encuentra que la combinación (rows_returned=100K, duration=8s, hour=3am, user=sebastian, query_template=join_payroll_employees) es estadísticamente anómala respecto a las queries previas de Sebastian.
- **Tier classification:** **T2** (medium-uncertain — ML solo con score moderado, sin corroboración de Layer 1). Esta es justamente la zona del countdown de 3 minutos.
- **Decision Engine action:**
  1. Throttle preventivo: limita conexiones de Sebastian a 1 query/min (no destructivo, no rompe nada).
  2. Snapshot proactivo de PostgreSQL.
  3. Notificación multicanal (Telegram + Discord) a los 4 aprobadores con countdown 3min y análisis LLM enriquecido: *"User sebastian@argos.local ejecutó SELECT que devolvió 100K filas (anomaly score 0.65) a las 03:47 AM. Patrón no observado previamente. Possible legitimate reporting OR data exfiltration."*
- **Human decision:**
  1. Enzo (P1, primero en ver el Telegram) revisa el contexto: identifica que es Sebastian y que es deadline de reporte mensual.
  2. Enzo clickea **"Reject — false positive"** en el botón inline JWT.
  3. Sistema cancela el throttle, libera la conexión, registra el caso en OpenSearch como False Positive con razón