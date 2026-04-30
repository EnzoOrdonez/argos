# ARGOS

**Adaptive Ransomware Guard with Orchestrated Surveillance**

A defense-in-depth ransomware detection and response system combining rule-based detection (Sigma + Wazuh), ML anomaly detection, deception (canary files), and LLM-assisted triage with human-in-the-loop SOAR.

> 🎓 Tópicos Avanzados de Ciberseguridad · Universidad de Lima · 2026-1

---

## Status

🚧 **In active development** — Architecture and design phase complete, implementation starting Week 2.

---

## What is ARGOS?

ARGOS replicates the architecture of commercial high-end EDR/XDR products (Microsoft Defender XDR, CrowdStrike Falcon, Palo Alto Cortex XDR) using exclusively open-source components plus a low-cost LLM API for the triage layer. It demonstrates four parallel detection layers, automated containment with human approval flow, and visible split-brain resolution — all in a reproducible lab environment.

**For the full vision in 90 seconds:** see [`docs/PROJECT_BRIEF.md`](./docs/PROJECT_BRIEF.md).

---

## Architecture at a glance

Four parallel detection layers feed a SOAR Decision Engine that classifies alerts into four confidence tiers (T0-T3) and routes them to either automated containment (high confidence) or human approval flow with conservative-wins resolution (medium-uncertain confidence):

1. **Layer 1** — Rule-based detection (Sigma → Wazuh, mapped to MITRE ATT&CK)
2. **Layer 2** — ML anomaly detection (Isolation Forest + One-Class SVM)
3. **Layer 3** — Deception (canary files with FIM whodata)
4. **Layer 4** — LLM-assisted triage (FastAPI + mini-RAG + DeepSeek/Qwen)

For the complete architecture: see [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](./docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md).

---

## Tech stack

**Detection & SIEM:** Wazuh · OpenSearch · Sigma · Sysmon · auditd
**Attack simulation:** Atomic Red Team · Caldera · Custom ransomware simulator
**ML:** scikit-learn (Isolation Forest, One-Class SVM)
**Backend services:** FastAPI · Redis · APScheduler
**LLM Triage:** DeepSeek-V3 (primary) · Qwen2.5-72B (fallback) · BGE-large embeddings · Mini-RAG
**UI:** Streamlit · OpenSearch Dashboards
**Infra:** Vagrant · Terraform (optional Azure)

---

## Documentation

All architecture, design decisions, threat model, and use cases are in [`docs/`](./docs/):

| Topic | Document |
|-------|----------|
| 📄 90-second overview | [`docs/PROJECT_BRIEF.md`](./docs/PROJECT_BRIEF.md) |
| 👥 Team onboarding | [`docs/CONTEXT.md`](./docs/CONTEXT.md) |
| 🏗️ Full architecture | [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](./docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) |
| 🛡️ Threat model (STRIDE + FMEA) | [`docs/architecture/THREAT_MODEL.md`](./docs/architecture/THREAT_MODEL.md) |
| 🎨 Interactive diagram | [`docs/architecture/architecture_diagram.html`](./docs/architecture/architecture_diagram.html) |
| 🧠 Architecture decisions | [`docs/decisions/`](./docs/decisions/) |
| 🎬 Use cases & demo scenarios | [`docs/use-cases/USE_CASES.md`](./docs/use-cases/USE_CASES.md) |

---

## Quick start

> ⚠️ **Setup instructions will be added during Week 2-3.** This section is currently a placeholder.

```bash
# Clone the repo
git clone https://github.com/EnzoOrdonez/argos.git
cd argos

# Copy environment template
cp .env.example .env
# Then edit .env with your credentials (see .env.example for required variables)

# Setup instructions for the lab will be added in Week 2-3
```

---

## Project structure (planned)

```
argos/
├── README.md                  # This file
├── LICENSE
├── .env.example               # Environment template
├── .gitignore
│
├── docs/                      # All architecture & design documentation
│
├── lab/                       # Vagrant + Terraform IaC
├── detection/                 # Sigma rules + Wazuh rules
├── ml/                        # Layer 2 ML models + consumer
├── deception/                 # Canary generator + FIM configs
├── soar/                      # Decision Engine + playbooks
├── llm-triage/                # Layer 4 FastAPI + RAG + LLM client
├── ui/                        # Streamlit dashboards
├── attack-simulation/         # Ransomware simulator + Caldera ops
└── evaluation/                # Metrics + datasets + reports
```

---

## Team

| Role | Member |
|------|--------|
| Lead · LLM/SOAR · Coordinator | [@EnzoOrdonez](https://github.com/EnzoOrdonez) |
| ML Engineer | TBD |
| Detection Engineer | TBD |
| Infrastructure · UI · Evaluation | TBD |

---

## Roadmap

- ✅ **Week 1:** Architecture & design phase complete (~210 KB of documentation, 6 ADRs, threat model, use cases).
- 🚧 **Weeks 2-9:** Implementation across 4 layers + SOAR + Approval Workflow Console.
- 📅 **Weeks 10-12:** Evaluation runs + Sigma rules upstream contributions.
- 📅 **Week 13:** Demo polish + video recording.
- 📅 **Week 14:** Live exposition.

---

## License

This repository will be released under the **MIT License** at the end of the course (currently private during development).

---

## Acknowledgments

- [SigmaHQ](https://github.com/SigmaHQ/sigma) for the open Sigma rule format.
- [MITRE ATT&CK](https://attack.mitre.org/) for the threat taxonomy.
- [Wazuh](https://wazuh.com/) for the open-source SIEM/HIDS.
- [Atomic Red Team](https://github.com/redcanaryco/atomic-red-team) and [MITRE Caldera](https://github.com/mitre/caldera) for adversary emulation.
