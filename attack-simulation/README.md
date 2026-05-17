# attack-simulation/ — Ransomware Simulator + Atomic Red Team + Caldera

| Field | Value |
|-------|-------|
| Owner | **P4** (Infra · UI · Eval) |
| Status | 📅 Planned · Weeks 4-9 (simulator W4 · per-UC variants W5-9) |
| Related | [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](../docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) §2 (Block 01), [`docs/use-cases/USE_CASES.md`](../docs/use-cases/USE_CASES.md) §3 (all 5 scenarios) |

---

## Purpose

Generate **controlled, reproducible positive cases** for detection tuning, demo runs, and evaluation. Three sources, each complementary:

| Tool | Strength | Use case |
|------|----------|----------|
| **Atomic Red Team** | One-to-one mapping to MITRE techniques | Validate that individual Sigma rules fire on their target technique |
| **Caldera** | Multi-step adversary emulation | Test Decision Engine fusion logic with realistic attack chains |
| **Custom ransomware simulator** | Reproducible demo-grade behavior, no external tooling surprises | Reliability for the live exposition (P4's own Python script) |

**Discipline:** the lab is air-gapped. Nothing simulated here can touch real data outside the lab subnet (per `lab/` network topology).

---

## Stack

| Tool | Role |
|------|------|
| Python 3.11+ | Custom ransomware simulator |
| `cryptography` library | AES-256 encryption simulation |
| `psutil` | Process / IO control for rate-limit demos |
| Atomic Red Team (PowerShell / Bash) | TTP tests, vendored as submodule |
| Caldera 5.x | Adversary emulation server |
| pytest | Reproducibility tests for the simulator |

---

## What lives here (planned)

```
attack-simulation/
├── README.md                           # This file
├── ransomware-simulator/
│   ├── simulator.py                    # Main entry point
│   ├── variants/
│   │   ├── lockbit_like.py             # UC-01 — vssadmin, .locked extension, ransom note
│   │   ├── novel_evasive.py            # UC-03 — WMIC instead of vssadmin, random extensions, no ransom note
│   │   ├── canary_path.py              # UC-02 — alphabetical enumeration to hit canaries early
│   │   └── stealth_kill_agent.py       # UC-05 — kills wazuh-agent first
│   ├── config/
│   │   ├── uc01.yaml                   # Speed, target paths, beacon endpoint
│   │   ├── uc02.yaml
│   │   └── ...
│   └── corpus/
│       └── README.md                   # How to generate the 500-file test corpus per host
├── atomic-red-team/
│   ├── techniques.yaml                 # Curated list of Atomics to run, mapped to UCs
│   └── wrapper.sh                      # Runs a subset of Atomic tests + collects results
├── caldera-operations/
│   ├── uc04_db_attack.yaml             # Caldera operation: SSH credential + btrfs snapshot delete
│   └── adversary-profiles/
└── tests/
    ├── test_simulator_reproducibility.py
    └── test_corpus_generator.py
```

---

## Contracts (`argos_contracts`)

**No contracts consumed or produced** — this layer generates raw OS-level events (file writes, process executions, network connections) that are captured downstream by Wazuh agents. No Python-level integration with `argos_contracts`.

The implicit contract: the simulator **must produce signals that the detection layers can recognize**. If a rule expects `vssadmin.exe` in the command line, the simulator must invoke it (not bypass it). Variants that deliberately evade rules (UC-03) are documented in their config file.

---

## Per-UC mapping (per USE_CASES.md §3)

| UC | Variant | Detection layers expected to fire |
|----|---------|-----------------------------------|
| UC-01 | `lockbit_like.py` | L1 (vssadmin + .locked + ransom note rules) + L2 (entropy spike) + L3 (canaries touched) |
| UC-02 | `canary_path.py` | L3 alone (interrupted before L1/L2 produce signal) |
| UC-03 | `novel_evasive.py` | L2 alone (WMIC bypasses L1 Sigma rules; canaries not in path) |
| UC-04 | Atomic Red Team T1490 (Linux) | L1 + L2 (btrfs snapshot delete + tar archive) |
| UC-05 | `stealth_kill_agent.py` | L1 (Stop-Service rule before agent dies) + heartbeat-loss rule 502 |

---

## How to run

```bash
cd attack-simulation/
pip install -r requirements.txt

# Generate file corpus on a target host (one-time per VM rebuild)
python -m attack_simulation.ransomware_simulator.corpus --host victim-windows-01 --count 500

# Run a scenario (requires lab/ up, detection/ + ml/ + soar/ for full E2E)
python -m attack_simulation.ransomware_simulator.simulator --variant lockbit_like --target windows-victim --speed full

# Run an Atomic Red Team test
bash atomic-red-team/wrapper.sh T1490

# Tests
pytest tests/ -v
```

---

## Tests

| Type | What it validates |
|------|-------------------|
| `test_simulator_reproducibility.py` | Same config → same sequence of events (deterministic) |
| `test_corpus_generator.py` | Generated corpus has the expected distribution (file types, sizes, entropy of cleartext content) |
| Manual rehearsal | Each UC variant runs 10× successfully in the week before exposition (per `USE_CASES.md` §6 risks) |

Target coverage: **best-effort** (per SAD §13.5 — scripts and glue code, low ROI for unit tests).

---

## Milestones by Gate

| Gate | Week | Deliverable |
|------|:----:|-------------|
| **Gate 1** | 5 | Simulator skeleton + `lockbit_like.py` → UC-01 runs end-to-end |
| **Gate 2** | 7 | UC-02 (`canary_path.py`) functional; corpus generator stable |
| **Gate 3** | 9 | UC-03 + UC-04 + UC-05 all reproducible; deliberate Sigma evasion documented |
| **Week 12-13** | — | Demo rehearsals (≥10×) per UC, video backup recorded |

---

## Safety rails (mandatory)

- **Hard refusal to run outside the lab subnet.** Simulator checks `inventory.yaml` from `lab/` and aborts if the target IP isn't in the allowlist.
- **No real C2 callbacks.** Beacon endpoint always points to a fake server in the lab (HTTP catcher).
- **AES key never reused across runs.** Random keys, discarded after each demo run.
- **`--dry-run` mode** that logs what would happen without actually encrypting anything (useful for first-time setup).

---

## References

- SAD §2 (Block 01 — Attack Simulation full spec).
- USE_CASES §3 (all 5 demo scenarios with attack details).
- THREAT_MODEL.md §6 R-1 (defense-in-depth assumes attack reaches detection layers — this layer makes sure it does).
