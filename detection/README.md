# detection/ — Layer 1 (Rule-Based Detection)

| Field | Value |
|-------|-------|
| Owner | **P3 · Angeles Castillo** (Detection Engineer) |
| Status | 📅 Planned · Weeks 2-5 (Gate 1) + Weeks 8-11 (Sigma upstream PRs) |
| Related | [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](../docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) §5.1, [`docs/use-cases/USE_CASES.md`](../docs/use-cases/USE_CASES.md) |

---

## Purpose

Layer 1 of the defense-in-depth stack. Sigma rules written in YAML, mapped explicitly to MITRE ATT&CK techniques, converted to Wazuh-native format via `sigma-cli` and deployed to the Wazuh manager. **High precision, limited recall against novel variants** — Layer 2 covers that gap.

Bonus killer: **2-4 Sigma rules accepted upstream** in `SigmaHQ/sigma` (see Roadmap §10 in PROJECT_BRIEF.md).

---

## Stack

| Tool | Role |
|------|------|
| Sigma + `sigma-cli` | Detection format + converter |
| YAML | Rule source |
| pytest + `sigma-cli analyze` | Local testing |
| Wazuh 4.7 | Runtime engine (rule format `decoder` + `rule`) |
| Atomic Red Team | Positive-case validation (each rule paired with at least one Atomic test) |

---

## What lives here (planned)

```
detection/
├── README.md                  # This file
├── sigma-rules/               # Source rules (YAML, contributable upstream)
│   ├── ransomware/
│   │   ├── vssadmin_delete_shadows.yml          # T1490
│   │   ├── wmic_shadow_copy_manipulation.yml    # T1490 variant (UC-03)
│   │   ├── high_entropy_writes.yml              # T1486
│   │   ├── ransom_note_drop.yml                 # T1486
│   │   └── ...
│   ├── defense-evasion/
│   │   ├── stop_service_wazuh_agent.yml         # T1562.001 (UC-05)
│   │   └── ...
│   └── discovery/
│       └── file_enumeration_powershell.yml      # T1083 (UC-03)
├── wazuh-rules/               # Auto-generated from sigma-rules/ via sigma-cli
│   └── local_rules.xml
├── mitre-mapping.yaml         # Matrix: technique → rule(s) that detect it
├── tests/
│   ├── test_rule_syntax.py    # All rules pass `sigma-cli check`
│   ├── test_atomic_pairs.py   # Each rule has ≥1 Atomic Red Team test
│   └── fixtures/              # Sample events for unit testing
└── upstream-prs/              # Documentation of accepted/rejected upstream PRs
    ├── 001-vssadmin-evasion-variants.md
    └── ...
```

---

## Contracts (`argos_contracts`)

This layer does **not** import `argos_contracts` directly — it produces Wazuh alerts (raw JSON) that the Decision Engine (`soar/`) wraps as `WazuhAlert` and normalizes to `NormalizedAlert`.

What this layer **commits to** for downstream consumers:

| Field on Wazuh alert | Meaning for `NormalizedAlert` mapping |
|---------------------|---------------------------------------|
| `rule.mitre.id` | Becomes `NormalizedAlert.technique_mitre` — **must be a valid MITRE ATT&CK ID** present in `argos_contracts.MITRE_WHITELIST` |
| `rule.level` (0-15) | Decision Engine maps to `Severity` enum: 0-5 LOW, 6-9 MEDIUM, 10-12 HIGH, 13-15 CRITICAL |
| `rule.description` | Becomes part of `NormalizedAlert.triggering_rule` |
| `agent.id` / `agent.name` | Becomes `host_id` / used for `Criticality` lookup |

**Discipline:** any new rule that doesn't map to a MITRE technique is rejected at PR review. No "miscellaneous" rules.

---

## Target MITRE techniques (per SAD §5.1)

| Technique | Name | UC coverage |
|-----------|------|-------------|
| T1486 | Data Encrypted for Impact | UC-01, UC-02, UC-03 |
| T1490 | Inhibit System Recovery | UC-01, UC-03, UC-04 |
| T1083 | File and Directory Discovery | UC-01, UC-02, UC-03 |
| T1562.001 | Disable or Modify Tools | UC-05 |
| T1021 | Remote Services (lateral movement) | UC-04 |
| T1071 | Application Layer Protocol (C2) | UC-01 |

---

## How to run

```bash
cd detection/
pip install -r requirements.txt    # sigma-cli + pytest

# Validate all rule syntax
sigma-cli check sigma-rules/

# Convert to Wazuh format
sigma-cli convert -t wazuh -o wazuh-rules/local_rules.xml sigma-rules/

# Run tests
pytest tests/ -v

# Deploy to local lab manager (requires lab/ up)
scp wazuh-rules/local_rules.xml wazuh-mgr:/var/ossec/etc/rules/
vagrant ssh wazuh-mgr -c "sudo systemctl restart wazuh-manager"
```

---

## Tests

| Type | What it validates |
|------|-------------------|
| `test_rule_syntax.py` | Every rule passes `sigma-cli check` (YAML + Sigma schema valid) |
| `test_atomic_pairs.py` | Every rule has at least one Atomic Red Team test it should fire on |
| `test_mitre_mapping.py` | Every `rule.tags` includes a valid MITRE technique ID in `MITRE_WHITELIST` |
| Integration | Apply rules to manager, run Atomic Red Team against victim, assert alert fires within 5s |

Target coverage: **≥50% line coverage** for converter logic (per SAD §13.5 tiered targets).

---

## Milestones by Gate

| Gate | Week | Deliverable |
|------|:----:|-------------|
| **Gate 1** | 5 | 10+ rules covering all 6 target techniques, all UC-01 detections fire end-to-end |
| **Gate 2** | 7 | UC-05 stop-service rule + rule 502 heartbeat coverage; FP rate <2% on 24h benign baseline |
| **Gate 3** | 9 | UC-03 variant detection rules (deliberately not matching → ML must catch); experimental T3 rules tagged separately |
| **Week 8-11** | — | **PR #1, #2, #3, #4 to SigmaHQ/sigma** (one per team member ideally) |

---

## Discipline / conventions

- **One rule per file.** Easier to PR upstream.
- **Each rule MUST include:** `id` (UUID), `title`, `description`, `references`, `tags` (MITRE), `logsource`, `detection`, `falsepositives`, `level`.
- **Branch naming:** `feature/p3/sigma-<technique>-<short-name>`.
- **Atomic Red Team pair**: name the Atomic test file in the rule comment (`# Validated by: T1490.001/T1490.001.md`).
- **FP rate ledger:** track per-rule FP rate weekly during Gate 2-3 (`tests/fp-ledger.md`).

---

## References

- SAD §5.1 (Layer 1 spec).
- USE_CASES §3 (rules required per scenario).
- THREAT_MODEL.md §4.4 (F-030 false negative, F-031 false positive).
- SigmaHQ contribution guide: https://github.com/SigmaHQ/sigma/wiki
