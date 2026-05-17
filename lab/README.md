# lab/ — Lab Provisioning (Infrastructure as Code)

| Field | Value |
|-------|-------|
| Owner | **P4** (Infra · UI · Eval) |
| Status | 📅 Planned · Weeks 2-3 |
| Related | [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](../docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) §3 (Block 02 — Victim Lab), [`docs/decisions/0002-heartbeat-default-60s.md`](../docs/decisions/0002-heartbeat-default-60s.md) |

---

## Purpose

Isolated virtualized environment that receives attacks and produces telemetry. Reproducible from zero in <30 minutes via Infrastructure as Code, per the reproducibility property in SAD §13.2.

The lab is the **substrate** that every other layer assumes exists. Without it, no use case can run.

---

## Stack

| Tool | Role |
|------|------|
| Vagrant 2.4+ | Primary provisioner — VirtualBox VMs + shell provisioners |
| VirtualBox 7.x | Hypervisor for local dev |
| Terraform 1.7+ (optional) | Azure deployment for the stretch goal "hybrid on-prem / cloud" demo |
| Bash / PowerShell | Provisioning scripts inside each VM |

**Network topology:** isolated host-only or internal network. No internet access from victim hosts during attack runs (mitigates accidental real-world impact — see THREAT_MODEL.md §3.1).

---

## What lives here (planned)

```
lab/
├── README.md                  # This file
├── Vagrantfile                # All VMs defined here (manager + 2 victims)
├── provision/
│   ├── wazuh-manager.sh       # Wazuh manager + OpenSearch install
│   ├── victim-windows.ps1     # Sysmon (SwiftOnSecurity baseline) + Wazuh agent
│   ├── victim-linux.sh        # auditd + Wazuh agent
│   └── network-isolation.sh   # iptables / NetFirewallRule rules
├── terraform/                 # Optional Azure stretch goal
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
└── inventory.yaml             # Host inventory consumed by attack-simulation/
```

---

## Contracts (`argos_contracts`)

This layer **does not consume or produce** any `argos_contracts` models directly — it's pure infrastructure. The contract it *enables* is "Wazuh manager API is reachable at `${WAZUH_API_URL}`, victim agents are registered, FIM is configured on canary paths".

Tag hosts in Wazuh with `criticality=production-critical` on the Linux victim per `OPEN_QUESTIONS_RESOLUTION.md` §Q2 — this is what triggers the two-person rule in UC-04.

---

## How to run

```bash
cd lab/
vagrant up               # provisions all 3 VMs (~10-15 min first time)
vagrant status           # confirm all running
vagrant ssh wazuh-mgr    # connect to manager
```

Validate without bringing VMs up:

```bash
vagrant validate
terraform -chdir=terraform validate
```

---

## Tests

| Type | What it validates |
|------|-------------------|
| `vagrant validate` | Vagrantfile syntax correct |
| `terraform validate` | Terraform module syntax (if used) |
| Smoke test (manual) | Wazuh API answers `200` on `GET /` ; each agent appears in `wazuh-agent list` with status `active` |
| External heartbeat (per SAD §13.6) | bash script via cron — manager API + agents reachable every 30s |

---

## Milestones by Gate

| Gate | Week | Deliverable |
|------|:----:|-------------|
| **Gate 1** | 5 | Wazuh manager + 2 victim agents up, basic Sigma rule fires on canonical event |
| **Gate 2** | 7 | FIM whodata configured on canary paths, Redis stream wired for ML consumer, network isolation tested |
| **Gate 3** | 9 | `production-critical` tag on Linux VM, isolated subnet, external heartbeat running, full stack reproducible from zero |

---

## Out of scope for v1

- HA for Wazuh manager (SPOF accepted, see SAD §14 item 5).
- Production-grade hardening of OS images (CIS baselines mentioned in SAD but lab uses Vagrant defaults).
- Backup/restore for OpenSearch (deliberately accepted, see `OPEN_QUESTIONS_RESOLUTION.md` §Q7).

---

## References

- SAD §3 — Block 02 (Victim Lab) full spec.
- ADR-0002 — heartbeat 60s default (impacts what counts as "agent stopped").
- `OPEN_QUESTIONS_RESOLUTION.md` §Q2 — production-critical host tagging.
- THREAT_MODEL.md §3.1 (T-001 spoofed agent), §3.5 (T-040 event flood), §4.3 (F-021 manager crash).
