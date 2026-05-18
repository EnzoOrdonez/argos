# DATA HANDLING — what ARGOS sends to external services and how it's sanitized

| Field | Value |
|-------|-------|
| Document type | Data handling policy + sanitization spec |
| Status | v1 (academic project) — to harden for any production deployment |
| Owner | P1 |
| Related | [`docs/architecture/THREAT_MODEL.md`](./architecture/THREAT_MODEL.md) §3.4 T-030, [`docs/decisions/0001-llm-vendor-agnostic.md`](./decisions/0001-llm-vendor-agnostic.md), [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](./architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) §12.1 R-6 |

---

## 0. Purpose

The Threat Model identifies T-030 ("Sensitive logs sent to third-party API — DeepSeek/Qwen, both China-based") as a **High** residual risk for an academic project, and mandates a sanitization layer + this document. The document was referenced as a mitigation deliverable but did not exist until Week 7. This file closes that gap.

The principle is simple: **the LLM API is treated as an untrusted external service** (per Trust Boundary 4 in `THREAT_MODEL.md` §2). Everything that crosses that boundary is sanitized; everything coming back is validated.

---

## 1. What goes to the LLM API

The only ARGOS component that calls the external LLM API is **Layer 4 LLM Triage** (`llm-triage/api/main.py`), through the abstract `LLMClient` interface (`llm-triage/llm_client/base.py` — DeepSeek or Qwen backend).

For each `/triage` request, the payload sent is an `AlertContext` Pydantic model (`argos_contracts/triage.py`). The fields that cross the network are:

| Field | Source | Sanitization before sending |
|-------|--------|----------------------------|
| `alert_summary.title` | Wazuh rule description (mostly static, low risk) | None — text is rule-author-controlled |
| `alert_summary.technique_mitre` | MITRE ID from Sigma rule | None — only valid MITRE IDs are sent |
| `alert_summary.severity_score` | Score from L1/L2/L3 fusion | None — numeric only |
| `host.id` / `host.ip` | Wazuh agent identifier | **Redacted** — see §2 |
| `process.command_line` | Sysmon / auditd captured command | **Sanitized** — see §2 |
| `process.parent_process_name` | Process tree | None — process names are low-sensitivity |
| `file.path` | FIM event | **Sanitized** — username paths redacted |
| `network.connections` (last 5 min) | Sysmon / auditd | **Redacted** — internal IPs replaced |
| `recent_user_actions` (last 5 min) | auditd command history | **Sanitized + truncated** — see §2 |

What is **never** sent under any circumstance:

- API keys, JWT secrets, SMTP credentials (any `.env` value).
- Full file contents.
- Cleartext network captures (.pcap, packet payloads).
- Email addresses of approvers (only opaque user IDs cross the boundary).
- Repository contents (rule files, ADRs, etc.).

---

## 2. Sanitization rules (concrete regex patterns)

Implemented in `llm-triage/sanitizer.py` (to be added in Gate 2 implementation per `soar/README.md` milestones). Applied to every string field before it crosses the boundary to DeepSeek/Qwen.

### 2.1 Credentials and secrets

| Pattern | Replacement | Notes |
|---------|-------------|-------|
| `password\s*=\s*\S+` (case-insensitive) | `password=<REDACTED>` | Common in command lines |
| `--password=\S+` | `--password=<REDACTED>` | CLI flag form |
| `Bearer\s+[A-Za-z0-9._-]+` | `Bearer <REDACTED>` | JWT and OAuth tokens |
| `[A-Za-z0-9+/]{40,}={0,2}` (anywhere) | `<BASE64_REDACTED>` | Likely API keys, certs, tokens |
| `-----BEGIN [A-Z ]+-----[\s\S]+?-----END [A-Z ]+-----` | `<PEM_REDACTED>` | Inline certs / private keys |

### 2.2 Internal IPs and hostnames

| Pattern | Replacement | Notes |
|---------|-------------|-------|
| `10\.\d{1,3}\.\d{1,3}\.\d{1,3}` | `10.X.X.X` | RFC1918 class A |
| `172\.(1[6-9]\|2[0-9]\|3[0-1])\.\d{1,3}\.\d{1,3}` | `172.X.X.X` | RFC1918 class B |
| `192\.168\.\d{1,3}\.\d{1,3}` | `192.168.X.X` | RFC1918 class C |
| `(?:fe80:\|fc00:\|fd00:)[0-9a-f:]+` (IPv6) | `<IPv6_LOCAL_REDACTED>` | Link-local + ULA |
| Hostnames matching `^(victim-\|wazuh-mgr\|infra-)[\w-]+` | `<HOST_REDACTED>` | ARGOS-specific lab host patterns |

### 2.3 Usernames in paths

| Pattern | Replacement | Notes |
|---------|-------------|-------|
| `C:\\Users\\([^\\]+)\\` | `C:\Users\<USER>\\` | Windows user dirs |
| `/home/([^/]+)/` | `/home/<USER>/` | Linux user dirs |
| `/Users/([^/]+)/` | `/Users/<USER>/` | macOS user dirs |

### 2.4 Email addresses

| Pattern | Replacement | Notes |
|---------|-------------|-------|
| `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}` | `<EMAIL_REDACTED>` | Catch-all |

### 2.5 Control chars and prompt-injection markers

To mitigate T-014 (prompt injection in process names, command lines, file paths):

| Action | Why |
|--------|-----|
| Strip ASCII control chars (0x00-0x1F except `\t`, `\n`, `\r`) | Removes invisible characters that could manipulate LLM token parsing |
| Replace `<\|im_start\|>`, `<\|im_end\|>`, `<system>`, `<user>`, `<assistant>` with safe escaped forms | Removes obvious prompt injection tags |
| Length limit: truncate any single string field to **2048 chars** | Bounds prompt-injection payload size |
| Reject the request entirely if total `AlertContext` JSON exceeds **64 KB** | Defense against payload bombs |

### 2.6 What is deliberately NOT sanitized

- **MITRE technique IDs** — these are public taxonomy, no risk.
- **Process names without arguments** (e.g., `vssadmin.exe`, `cmd.exe`) — public, contextually necessary.
- **File extensions** — public, needed for ransomware behavior signal.
- **Public IPs of known C2 endpoints** — actually useful intel.

---

## 3. Validation of LLM response

Defense-in-depth on the way back, per R-6:

| Check | Enforced by | Failure mode |
|-------|-------------|--------------|
| JSON schema (Pydantic v2) | `TriageResponse.model_validate_json` | Reject response, retry once, fall to "needs human triage" |
| MITRE technique ID in `MITRE_WHITELIST` | `argos_contracts.MITRE_WHITELIST` cross-check | Reject hallucinated IDs |
| `confianza` ∈ [0, 1] | Pydantic Field constraint | Reject malformed |
| `severidad` ∈ {low, medium, high, critical} | `Severity` enum | Reject unknown values |
| `accion_recomendada` is text-only, not parsed | `soar/decision_engine/` ignores this field for action selection | Per R-2, see ADR-0001 |

---

## 4. Audit trail

Every LLM call writes a structured log entry to OpenSearch index `argos-llm-calls-{YYYY-MM}` with:

- `incident_id` (links back to the `Incident` that triggered the triage)
- `request_hash` (SHA-256 of the sanitized `AlertContext` JSON — for deduplication and replay analysis)
- `response_hash` (SHA-256 of the raw response)
- `backend_used` (`deepseek` or `qwen`)
- `latency_ms`
- `cost_estimated_usd` (per ADR-0001 budget tracking)
- `sanitization_redactions_count` (how many patterns matched — high count = noisy data, investigate)

**What the audit log does NOT capture:** the actual content of the request or response. Only hashes. This is intentional — if the OpenSearch index itself is compromised, the attacker doesn't get a log of every alert detail that left the network.

For forensic replay, the raw sanitized request can be reconstructed from the source `AlertContext` (still in OpenSearch under `argos-incidents-{YYYY-MM}`) plus the sanitization rules in this document, which are versioned in git.

---

## 5. v2 path (out of scope for academic project)

For production deployment:

1. **Local LLM (Llama 3.1 / Mistral via Ollama).** Eliminates the trust boundary entirely. Foundation laid by ADR-0001 `LLMClient` abstraction. Documented as future work in SAD §14 item 4.
2. **Field-level encryption at rest** for `AlertContext` payloads in OpenSearch.
3. **DLP scanner** as a final gate before any outbound HTTPS connection, independent of the sanitization rules in §2 (defense-in-depth).
4. **Annual penetration test** specifically targeting the sanitizer (try to leak data through obscure patterns).

---

## 6. Acceptance criteria for v1 academic project

- ✅ Document exists (this file).
- 📅 `llm-triage/sanitizer.py` implements all patterns in §2 (Gate 2 deliverable, owner P1).
- 📅 Unit tests in `llm-triage/tests/test_sanitizer.py` cover each pattern with positive + negative cases (Gate 2).
- 📅 EV-05 (adversarial probes against LLM) validates that no prompt injection bypasses the sanitizer (Week 10, owner P1+P2).
- 📅 Cost tracking in audit log validates against the `<$20 USD total` claim (Week 12).

---

## 7. Change log

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | Week 7 | Initial document — closes T-030 mitigation gap by formalizing what crosses the trust boundary to the external LLM API, the concrete sanitization patterns, response validation, and audit trail. | P1 |
