# deception/ — Layer 3 (Canary Files + FIM whodata)

| Field | Value |
|-------|-------|
| Owner | **P3** (Detection Engineer — same as `detection/`) |
| Status | 📅 Planned · Weeks 4-7 (Gate 2 functional) |
| Related | [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](../docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) §5.3, [`docs/use-cases/USE_CASES.md`](../docs/use-cases/USE_CASES.md) UC-02 |

---

## Purpose

Layer 3 of the defense-in-depth stack. Honeypot files placed in paths a legitimate user would never touch — first access/modification fires a **critical alert with maximum confidence (zero-FP by design)**.

**Trade-off:** ultra-early detection, but a sophisticated attacker who knows the canaries can avoid them. That's why Layer 3 **complements**, not replaces, Layers 1+2.

This layer is the **only one that fires in UC-02** — and it stops the attack before a single real file is encrypted.

---

## Stack

| Tool | Role |
|------|------|
| Python 3.11+ | Canary generator (filenames, realistic dummy content, timestamps) |
| Wazuh FIM (`syscheck`) | File integrity monitoring with `whodata` (Windows) / auditd (Linux) |
| Sysmon (Windows) | EventID 11 (file create), EventID 23 (file delete) — supplements FIM |
| auditd (Linux) | Watch rules on canary paths capturing offending process |
| pytest | Generator + Wazuh rule unit tests |

---

## What lives here (planned)

```
deception/
├── README.md                # This file
├── canary-generator/
│   ├── generator.py         # Creates canaries with realistic names + content
│   ├── templates/           # Word/Excel/PDF dummy file templates
│   │   ├── financials.xlsx
│   │   ├── passwords.txt
│   │   └── db_backup.sql
│   └── config.yaml          # Per-host canary placement strategy
├── fim-configs/
│   ├── ossec-windows.conf   # syscheck block for canary paths + whodata
│   └── ossec-linux.conf     # syscheck + auditd rules
├── wazuh-rules/
│   └── canary_rules.xml     # Severity 12 (critical) on any canary touch
├── integrity-check/
│   └── verify_canaries.sh   # Hourly cron — recreate missing canaries (F-040)
└── tests/
    ├── test_generator.py
    └── test_fim_config.py
```

---

## Contracts (`argos_contracts`)

Same pattern as `detection/`: this layer does **not** directly import `argos_contracts`. It produces Wazuh alerts that the Decision Engine wraps as `WazuhAlert` → `NormalizedAlert` with `source_layer = Layer.LAYER_3`.

**Critical commitment** — every canary-triggered alert MUST carry:
- The offending **process tree** (PID, parent PID, command line) captured by whodata/auditd.
- The **canary path** that was touched (verbatim from FIM event).
- A `severity_score` ≥ **0.95** — by design, Layer 3 alerts qualify for **Tier T0** alone (zero-FP property, per ADR-0003).

The Decision Engine relies on this guarantee to route Layer 3 directly to auto-isolation without corroboration.

---

## Canary design discipline

| Rule | Why |
|------|-----|
| **Absolute paths only.** No relative or wildcard patterns. | Prevents the attacker from matching the canary by creating same-name files elsewhere (T-004 in THREAT_MODEL.md §3.1) |
| **Realistic content (not empty / lorem ipsum).** | Avoids the obvious tell that the file is bait |
| **Realistic timestamps and ACLs.** | Modification time set to plausible past dates (e.g., 60-180 days ago) |
| **Names that match what an attacker would prioritize.** | `financials_Q4_2025.xlsx`, `passwords.txt`, `db_backup.sql`, `accounts_admin.csv` |
| **Per-host placement randomized** (production deployment future work). | Mitigates T-031 (repo leakage of canary paths) — for the academic demo we accept public paths and document it |

---

## How to run

```bash
cd deception/
pip install -r requirements.txt

# Generate canaries on a target host (requires SSH or local exec)
python -m deception.canary_generator.generator --config config.yaml --host victim-windows-01

# Deploy FIM rules (requires lab/ up)
scp fim-configs/ossec-windows.conf wazuh-mgr:/var/ossec/etc/agents/victim-windows-01/
vagrant ssh wazuh-mgr -c "sudo /var/ossec/bin/wazuh-control restart"

# Run integrity check manually (cron will do this hourly in prod)
bash integrity-check/verify_canaries.sh
```

---

## Tests

| Type | What it validates |
|------|-------------------|
| `test_generator.py` | Generated files have realistic content + size + timestamp distribution |
| `test_fim_config.py` | FIM config blocks all reference paths in `config.yaml`; rules emit severity 12 on touch |
| Integration (manual / CI) | Touch a canary on victim → alert appears in Wazuh manager within 2s with full whodata payload |
| Adversarial | Touch a non-canary file in the same directory → no alert (negative test) |

---

## Milestones by Gate

| Gate | Week | Deliverable |
|------|:----:|-------------|
| **Gate 1** | 5 | Generator skeleton + 5 canaries on Windows victim (no FIM yet) |
| **Gate 2** | 7 | FIM whodata + rules deployed; UC-02 scenario fires end-to-end with full whodata payload (PID + parent + command line) |
| **Gate 3** | 9 | Integrity check cron running; FP rate measured (target: 0 on 48h baseline); EV-01 (zero-FP) validated |

---

## Risks specific to this layer

- **F-040 (canary deleted by legitimate cleanup script):** mitigated by hourly integrity check + auto-recreation.
- **F-041 (FIM whodata service stops):** monitored by Wazuh rule 502 on `wazuh-agent` itself — `cu05/UC-05` covers this.
- **T-031 (canary path leakage via repo):** accepted for academic demo; for production, paths driven by env vars + per-host random subset.

---

## References

- SAD §5.3 (Layer 3 spec).
- USE_CASES UC-02 (canary deception demo, target: zero real files encrypted).
- THREAT_MODEL.md §3.1 (T-004), §3.4 (T-031), §4.5 (F-040, F-041).
- ADR-0003 §"Esquema de tiers" — canary alone = T0 with confidence 1.0.
