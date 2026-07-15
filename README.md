<div align="center">

# ARGOS

### Adaptive Response Guard with Orchestrated Surveillance

*Plataforma multi-vector de detección y respuesta (XDR-style) con defensa en profundidad, SOAR y aprobación humana asistida por LLM. Énfasis primario en ransomware; extendida a Network DoS y Application Abuse per ADR-0008.*

[![Status](https://img.shields.io/badge/status-prototipo%20F1--F6%20completo-brightgreen)](docs/ARGOS_RUNBOOK_MAESTRO.html)
[![Contracts](https://img.shields.io/badge/argos__contracts-v1.1.0-blue)](argos_contracts/)
[![CI](https://github.com/EnzoOrdonez/argos/actions/workflows/ci.yml/badge.svg)](https://github.com/EnzoOrdonez/argos/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

**Activo defendido:** 🛡 PostgreSQL Production DB

</div>

---

## ¿Qué es ARGOS?

ARGOS toma el patrón arquitectónico de los XDR/EDR comerciales (Microsoft Defender XDR, CrowdStrike Falcon, Palo Alto Cortex XDR) y lo construye **a escala de laboratorio académico** usando **exclusivamente componentes open source** más una API LLM de bajo costo para la capa de triage — sin la telemetría de producción, el threat intel comercial ni los años de tuning de esos productos. Cuatro capas de detección en paralelo, contención automatizada con flujo de aprobación humana, y resolución visible de split-brain — todo reproducible en un lab virtualizado.

> 📄 **Resumen en 90 segundos:** [`docs/PROJECT_BRIEF.md`](./docs/PROJECT_BRIEF.md)
> 🎨 **Flujo visual con asignación por integrante:** [`docs/architecture/argos_flow.html`](./docs/architecture/argos_flow.html)
> 🏗️ **Arquitectura completa (SAD):** [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](./docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md)

---

## Por qué importa

| | |
|---|---|
| 🆓 **Patrón de EDR comercial, a escala de lab** | Mismas primitivas arquitectónicas que los productos pagos (multi-capa + SOAR + LLM triage), sin su telemetría de producción ni su threat intel comercial. Stack 100% OSS excepto una API LLM con budget tope (~\$5/día). Reproducible en cualquier laptop con Vagrant. |
| 👥 **HITL automation con consenso anti-split-brain** | Decisiones multi-aprobador resueltas por *conservative-wins policy* explícita (ADR-0006), no por improvisación. Visible en tiempo real en la Approval Workflow Console. |
| 🤖 **ML contra variantes novel** | Ensemble Isolation Forest + One-Class SVM detecta ransomware que no matchea ninguna regla — el caso donde las defensas signature-only se quedan ciegas. |
| 🍯 **Capa de deception con propiedad zero-FP** | Canary files con FIM whodata atrapan al atacante *antes* de que toque datos reales. Por diseño: un usuario legítimo nunca toca un honeypot. |
| 🌐 **Soberanía de datos** | El dato va a **NVIDIA NIM** (jurisdicción US) vía `openai/gpt-oss-120b` (pivote 2026-06-30 desde `deepseek-v4-pro`, descartado por latencia 15-21s): procedencia del modelo ≠ jurisdicción del dato. + data sintética + sanitizer T-030. Fallback Ollama (diferido) = zero-egress real (ADR-0001 v3). |

---

## Arquitectura de un vistazo

Cuatro capas de detección paralelas alimentan un SOAR Decision Engine que clasifica alertas en cuatro tiers de confianza (T0–T3) y las enruta a contención automática o a flujo de aprobación humana:

```mermaid
flowchart TD
    subgraph DET["🔍 Capas de detección (paralelas)"]
        L1["<b>Capa 1</b><br/>Sigma + Wazuh<br/><i>rule-based</i>"]
        L2["<b>Capa 2</b><br/>Isolation Forest + OC-SVM<br/><i>ML anomalía</i>"]
        L3["<b>Capa 3</b><br/>Canary + FIM whodata<br/><i>deception</i>"]
        L4["<b>Capa 4</b><br/>FastAPI + RAG + LLM<br/><i>triage (enrichment-only)</i>"]
    end

    DE[["⚙️ SOAR Decision Engine<br/>tier classifier"]]

    L1 --> DE
    L2 --> DE
    L3 --> DE
    L4 -. enriquece .-> DE

    DE --> T0["🟥 T0<br/>≥ 0.95"]
    DE --> T1["🟧 T1<br/>0.80–0.95"]
    DE --> T2["🟨 T2<br/>0.60–0.80"]
    DE --> T3["🟦 T3<br/>0.40–0.60"]

    T0 --> A1["⚡ Auto-isolate<br/>+ snapshot"]
    T1 --> A1
    T2 --> A2["⏱ Throttle + snapshot<br/>luego 3-min approval<br/>(split-brain →<br/>conservative-wins)"]
    T3 --> A3["📨 Notificación<br/>LLM-enriched"]
```

> Thresholds 0.95 / 0.80 / 0.60 / 0.40 son **valores preliminares** pendientes de calibración empírica (ver [Q5 protocol](./docs/decisions/OPEN_QUESTIONS_RESOLUTION.md)).
> Para el flujo completo con asignación por integrante: [`docs/architecture/argos_flow.html`](./docs/architecture/argos_flow.html).

---

## Automatización por tier de confianza (T0–T3)

ADR-0003 hace que la profundidad de automatización sea función de **confianza de detección** × **reversibilidad de la acción**. La misma pipeline de alerta produce cuatro outcomes muy distintos:

| Tier | Disparado por | Acción | Aprobación |
|:----:|---------------|--------|-----------|
| 🟥 **T0** | Canary solo, o capas 1+2+3 corroboran | Aislamiento inmediato + snapshot | Post-facto con botón "Revertir" |
| 🟧 **T1** | Capa 1 + Capa 2 corroboran (sin canary) | Aislamiento inmediato + snapshot | Post-facto con botón "Revertir" |
| 🟨 **T2** | Capa sola con high score | **Throttle + snapshot ahora**, aislamiento full pendiente de aprobación 3-min | Pre-ejecución con timeout |
| 🟦 **T3** | Corroboración baja | Solo notificación enriquecida con LLM | Revisión manual del analista |

**Por qué T2 es interesante.** Ransomware moderno cifra ~25,000 archivos/min. El throttle aplicado durante la ventana de aprobación corta esa tasa ≥80% (objetivo validado en EV-03), acotando el daño incluso si el humano no responde. Si el timeout expira sin respuesta, el sistema auto-ejecuta — no hay escenario donde el atacante le gane al reloj.

**Split-brain (conflicto multi-aprobador)** se resuelve con *conservative-wins policy* + ventana de consolidación de 60s: cualquier "approve" gana sobre rechazos, excepto para acciones irreversibles que requieren two-person rule. Ver [ADR-0006](./docs/decisions/0006-split-brain-resolution.md).

---

## Resiliencia por diseño

ARGOS asume que el atacante apuntará al defensor mismo:

- **El LLM nunca está en el path crítico de containment (R-2).** Si el backend LLM cae, alucina, o el endpoint responde basura, las capas 1–3 + el SOAR siguen funcionando (fail-soft a `None`). El LLM Triage solo enriquece la vista del analista.
- **Inferencia local como fallback genuino (diferido).** Llama 3.1 8B vía Ollama mantendría el análisis activo aun en deployment air-gapped (zero-egress real para PII); aún no cableado (ADR-0001 v3).
- **El disconnect del agente es señal en sí mismo.** Si un atacante mata el Wazuh agent (T1562.001), la pérdida de heartbeat dispara una alerta crítica dentro de ~60s y activa aislamiento de red — el silencio los delata (R-04).
- **Tres capas de detección independientes.** Sigma rules, ML anomaly y canaries fallan independientemente. No hay un solo componente cuya caída produzca ceguera total.
- **Conservative-wins en conflicto multi-aprobador.** Una cuenta de aprobador comprometida no puede vetar unilateralmente una contención legítima — cualquier otro "approve" sobrescribe el "reject" (ADR-0006).

Threat model STRIDE + FMEA completo con ~50 amenazas analizadas: [`docs/architecture/THREAT_MODEL.md`](./docs/architecture/THREAT_MODEL.md).

---

## Stack tecnológico

<table>
<tr>
<td valign="top" width="50%">

**🔍 Detección & SIEM**
- Wazuh 4.7 · OpenSearch · Sigma
- Sysmon · auditd

**🎯 Simulación de ataque multi-vector**
- Atomic Red Team · Caldera
- Custom ransomware simulator (Python)
- DDoS: hping3 · slowhttptest (per UC-06)
- SQL injection: sqlmap (per UC-08)
- pgAudit para query patterns (per UC-07)

**🤖 Machine Learning**
- scikit-learn (Isolation Forest, One-Class SVM)
- scipy (Shannon entropy)

</td>
<td valign="top">

**⚙️ Backend services**
- FastAPI · Redis · APScheduler · Pydantic v2 · PyJWT

**🛡 LLM Triage** (per ADR-0001 v3)
- NVIDIA NIM (SDK OpenAI) — `openai/gpt-oss-120b` (pivote 2026-06-30 tras problemas de key/créditos con el backend anterior)
- Sanitizer T-030 + MITRE whitelist (anti-alucinación)
- Ollama (Llama 3.1 8B local) = fallback zero-egress, diferido

**📺 UI**
- Consola web (FastAPI, `:8080`) + Streamlit (fallback, `:8501`)
- OpenSearch Dashboards = Perfil B (diferido)

**🏗 Infra**
- Vagrant · VirtualBox · Terraform (opcional Azure)

</td>
</tr>
</table>

---

## Estado actual

Prototipo **F1–F6 completo** (~441 tests per docs de equipo; no re-verificado en un sandbox limpio esta sesión). Leyenda: ✅ hecho (testeado) · 🟡 simulado (corre demo-safe sin lab) · 🔧 pendiente-lab (necesita las VMs).

| Componente | Estado | Notas |
|---|:---:|---|
| 📐 Arquitectura & diseño (SAD, threat model, **15 ADRs**, contracts spec, use cases) | ✅ | Completo |
| 📦 [`argos_contracts/`](./argos_contracts/) — Pydantic v2 cross-team | ✅ | **v1.1.0** · inmutable · contratos sellados |
| ⚙️ SOAR completo (decision engine, tiers, two-person, consolidación, notificaciones, audit, Approval API) | ✅ | ~250 tests · ADR-0011/0012/0013 |
| 🌐 F1 · Live mode (Telegram/ngrok/trigger local) | ✅ | `--live` + `scripts/live_approve.py` |
| 🤖 F2 · Bridge de normalización (`events:normalized`) | ✅🔧 | Camino A Wazuh→`payload` + Camino B publisher ML (ADR-0014). **Scorer ML en vivo = pendiente (P2)** |
| 🛡 F3 · Active-response (Windows + Linux) | ✅🔧 | Scripts `argos-{isolate,throttle,snapshot,kill}` listos; instalación en agentes = pendiente-lab |
| 🧠 F4 · Capa 4 LLM Triage (NVIDIA NIM) | ✅ | `POST /triage` · `openai/gpt-oss-120b` · sanitizer T-030 · fail-soft (R-2) |
| 🐳 F5 · docker-compose Perfil A | ✅ | Core en la VM Linux core · ADR-0015 · `deploy/README.md` |
| 📺 F6 · Consola web + Streamlit fallback | ✅ | `:8080` (web) / `:8501` (streamlit) · read-only |
| 🔍 Capa 1 (Sigma) · 🍯 Capa 3 (Canary FIM) | ✅🔧 | Reglas + simuladores listos; despliegue/auditd en el lab = pendiente-lab |
| 🏗 Lab 3 VMs + ataque real (Track A) | 🔧 | Código real (Vagrantfile + provisioning de 2/3 VMs, `vagrant validate` OK) — `vagrant up` nunca completó con éxito en la máquina de prueba (conflicto Hyper-V/VirtualBox, no es un problema de código). Diferido; Track B es el confirmado para la entrega. |
| 🎬 Video demo + exposición (Track B) | ✅ | Docker-compose confirmado funcional y corrido en vivo. Runbook de grabación: [`docs/RUNBOOK_GRABACION_TRACKB.md`](./docs/RUNBOOK_GRABACION_TRACKB.md) |

> **Manual maestro del equipo (la fuente de verdad):** [`docs/ARGOS_RUNBOOK_MAESTRO.html`](./docs/ARGOS_RUNBOOK_MAESTRO.html) · **status detallado:** [`docs/PROJECT_STATUS.md`](./docs/PROJECT_STATUS.md)

---

## Quick start

El prototipo F1–F6 corre hoy, demo-safe, sin lab.

```bash
git clone https://github.com/EnzoOrdonez/argos.git
cd argos
pip install -e ".[soar,llm,dev,ui,ml]"
pytest -q                          # suite completa (CI corre esto mismo en cada push/PR)
```

**Correr el demo (Track B — docker-compose, confirmado funcional):**

```bash
cp .env.example .env
# completar credenciales propias (OPENAI_API_KEY de NVIDIA NIM como mínimo; el resto
# es opcional — Telegram/Discord/Twilio se omiten fail-soft si faltan)
# poner DEMO_MODE=true en .env (usa las respuestas LLM ya cacheadas en demo/cached-responses/,
# evita depender del backend real durante la demo)

docker compose up -d                                          # redis, postgres, soar, console, llm-triage
python scripts/demo_injector.py uc04
# consola web -> http://localhost:8080
```

> ⚠ Si usás notificaciones Telegram/Twilio reales: revisar `TELEGRAM_CHAT_ID`/`TWILIO_TO_NUMBER`
> en `.env.example` (BUG-4 en `CLAUDE.md`) — el código lee esos nombres, no
> `TELEGRAM_APPROVER_CHAT_IDS`/`TWILIO_APPROVER_PHONES`.

> 📘 **Runbook de grabación (comandos + troubleshooting):** [`docs/RUNBOOK_GRABACION_TRACKB.md`](./docs/RUNBOOK_GRABACION_TRACKB.md)
> 📕 **Manual maestro del equipo (estado, comandos, trampas):** [`docs/ARGOS_RUNBOOK_MAESTRO.html`](./docs/ARGOS_RUNBOOK_MAESTRO.html)

<details>
<summary><b>Prototipo real (3 VMs)</b></summary>

`lab/` **sí tiene código real**: Vagrantfile + provisioning de 2 de las 3 VMs (`core` = Wazuh
manager, `lin-victim-01` = Debian + PostgreSQL 17.5 + pgAudit), más `postgres/init.sql` + `seed.py`
y runbooks de boot. `vagrant validate` pasa. La VM Windows víctima (Fase 1B) está diferida a
propósito. **`vagrant up` nunca completó con éxito** — conflicto Hyper-V (Docker Desktop/WSL2)
vs. VirtualBox en la máquina de prueba, no un problema del código (ver `lab/RUNBOOK_BOOT_1A.md`
y `CLAUDE.md`). Para la entrega se usa Track B (docker-compose, arriba) como demo garantizada;
Track A queda para retomar sin presión de tiempo. Swap simulado↔real con `ARGOS_EXECUTOR=wazuh` +
`docker compose --profile real up -d` una vez que el lab bootee.

```bash
cp .env.example .env    # completar valores reales (gitignored)
```

</details>

<details>
<summary><b>Variables de entorno requeridas</b> (ver <code>.env.example</code> completo)</summary>

Agrupadas por componente:

- **Wazuh:** `WAZUH_API_URL`, `WAZUH_API_USER`, `WAZUH_API_PASSWORD`
- **OpenSearch:** `OPENSEARCH_URL`, `OPENSEARCH_USER`, `OPENSEARCH_PASSWORD`
- **Redis:** `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- **PostgreSQL (activo defendido):** `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- **LLM Triage (ADR-0001 v3):** `LLM_BACKEND`, `OPENAI_API_KEY` (key NVIDIA), `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_FALLBACK_MODEL`
- **Approval flow:** `JWT_SECRET`, `APPROVAL_T2_TIMEOUT_SECONDS=180`, `APPROVAL_CONSOLIDATION_WINDOW_SECONDS=60`
- **Notificaciones (ADR-0007 v2):** `TELEGRAM_BOT_TOKEN`, `DISCORD_WEBHOOK_URL`, `TWILIO_ACCOUNT_SID`, `SMTP_*` (post-facto)
- **Lab:** `LAB_VICTIM_WINDOWS_IP`, `LAB_VICTIM_LINUX_IP`, `LAB_MANAGER_IP`

</details>

---

## Escenarios de demo

Ocho escenarios end-to-end de ataque (6 núcleo + 2 opcionales) diseñados para la exposición en vivo (~13 min el set núcleo). TTPs completos, guiones de narración y criterios de éxito en [`docs/use-cases/USE_CASES.md`](./docs/use-cases/USE_CASES.md); orden y timing exacto de grabación en [`docs/RUNBOOK_GRABACION_TRACKB.md`](./docs/RUNBOOK_GRABACION_TRACKB.md).

| UC | Escenario | Tier | Desenlace | Foco del demo |
|:--:|-----------|:----:|-----------|--------------|
| `uc01` | Ransomware en 3 capas casi simultáneas (T1486) | T0 | EXECUTE_ISOLATION (auto, sub-seg) | Fast-path full-stack |
| `uc02` | Canary sola (Capa 3), zero-FP | T0 | EXECUTE_ISOLATION (auto) | Detección ultra-temprana · **zero archivos cifrados** |
| `uc03` ★ | Variante novedosa (ML sola) → split-brain | T2 | EXECUTE_ISOLATION (conservative-wins) | **Centerpiece:** HITL con desacuerdo real entre 4 aprobadores, resuelto por política |
| `uc04` | Ataque a la DB de IntiBank (L1+L2) | T1 | EXECUTE_ISOLATION | **two-person rule** · four-eyes · host production-critical |
| `uc05` (opcional) | Agent-kill sigiloso (T1562.001) | T0 | EXECUTE_ISOLATION (auto) | Resiliencia: silencio del agente como señal |
| `uc06` | DDoS volumétrico (T1498), fast-path | T0 | EXECUTE_ISOLATION (auto) | Contención en el edge |
| `uc07` | SELECT masivo legítimo | T1 | **NO_ACTION** (el humano rechaza) | El HITL atrapa un **falso positivo** |
| `uc08` (opcional) | SQL injection contra app web (T1190) | T1 | EXECUTE_ISOLATION (auto, block IP) | OWASP Top 10 #1 · Initial Access |

**Técnicas MITRE ATT&CK en alcance:** T1486 (ransomware) · T1490 (inhibit recovery) · T1498 (DDoS) · T1190 (SQLi) · T1078 (valid accounts / FP) · T1562 (agent-kill) · T1083 (discovery). Detalle por UC en [`docs/use-cases/USE_CASES.md`](./docs/use-cases/USE_CASES.md).

---

## Documentación

| 📂 | Topic | Documento |
|:--:|-------|-----------|
| 📄 | Resumen 90 segundos | [`docs/PROJECT_BRIEF.md`](./docs/PROJECT_BRIEF.md) |
| 👥 | Contexto del proyecto *(histórico del curso)* | [`docs/CONTEXT.md`](./docs/CONTEXT.md) |
| 🏗 | Arquitectura completa (SAD) | [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](./docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) |
| 🎨 | Flujo + asignación por integrante | [`docs/architecture/argos_flow.html`](./docs/architecture/argos_flow.html) · [`.drawio`](./docs/architecture/argos_flow.drawio) |
| 📐 | Cross-team contracts spec | [`docs/architecture/CONTRACTS_SPECIFICATION.md`](./docs/architecture/CONTRACTS_SPECIFICATION.md) |
| 🛡 | Threat model (STRIDE + FMEA) | [`docs/architecture/THREAT_MODEL.md`](./docs/architecture/THREAT_MODEL.md) |
| 🔒 | LLM data handling + sanitization | [`docs/data-handling.md`](./docs/data-handling.md) |
| 📋 | Rúbrica + deliverables *(histórico del curso)* | [`docs/EVALUATION_CRITERIA.md`](./docs/EVALUATION_CRITERIA.md) |
| 📊 | Status honesto (shipped vs documentado) | [`docs/PROJECT_STATUS.md`](./docs/PROJECT_STATUS.md) |
| 🧠 | Architecture decisions (15 ADRs) | [`docs/decisions/`](./docs/decisions/) |
| 🎬 | Use cases & escenarios demo | [`docs/use-cases/USE_CASES.md`](./docs/use-cases/USE_CASES.md) |

---

## Estructura del repo

<details>
<summary><b>Click para expandir</b></summary>

```
argos/
├── README.md                  # Este archivo
├── LICENSE                    # MIT
├── .env.example               # Plantilla de variables
├── pyproject.toml             # Metadata + extras por módulo + tooling
├── docker-compose.yml         # F5 · core Perfil A (+ perfiles real/fallback)
├── Dockerfile                 # Imagen única de los servicios
│
├── argos_contracts/           # Cross-team Pydantic v2 contracts (inmutable · v1.1.0)
├── llm_triage/                # Capa 4 — FastAPI + LLM client (NVIDIA NIM) + sanitizer T-030
│   ├── api/                   #     POST /triage endpoint
│   ├── llm_client/            #     OpenAI SDK -> NVIDIA (gpt-oss-120b) + Ollama stub (ADR-0001 v3)
│   ├── prompts/               #     Jinja2 templates
│   └── rag/                   #     BM25 + BGE-large + RRF
│
├── soar/                      # SOAR completo: decision engine, tiers, Approval API, audit, forensics
├── bridge/                    # F2 · Wazuh/ML -> events:normalized (ADR-0014)
├── detection/                 # Capa 1 · Sigma rules + simuladores de ataque (P3)
├── active-response/           # F3 · scripts argos-* (linux/ bash + windows/ PowerShell)
├── ml/                        # Capa 2 · ML pipeline (scorer en vivo pendiente)
├── deception/                 # Capa 3 · canary generator + FIM/auditd configs
├── console/                   # F6 · consola web read-only (FastAPI + SPA)
├── ui/                        # Consola Streamlit (fallback)
├── deploy/                    # F5 · runbook del compose + tests estructurales
├── scripts/                   # demo_injector, live_approve, triage_stub
│
├── docs/                      # Documentación arquitectónica
│   ├── ARGOS_RUNBOOK_MAESTRO.html  # Manual maestro del equipo (fuente de verdad)
│   ├── architecture/          #     SAD, threat model, flujo + ownership
│   └── decisions/             #     15 ADRs + OPEN_QUESTIONS_RESOLUTION
│
├── lab/                       # Vagrantfile + provisioning real (2/3 VMs); vagrant up nunca completó (ver README)
├── attack-simulation/         # Wrappers de emulación adversaria
└── evaluation/                # Métricas, datasets, reportes
```

</details>

---

## Hito siguiente

🎯 **Entrega final: 1 de julio de 2026** (fecha movida desde 28-jun, antes 13-jun): informe técnico + demo en vivo + presentación (~13 min). Decisión tomada el mismo día de entrega: se prioriza Track B (docker-compose, confirmado funcional y corrido en vivo) como demo garantizada; Track A (lab real de 3 VMs) queda diferido — `vagrant up` nunca completó con éxito (conflicto Hyper-V/VirtualBox), sin relación con la calidad del código del lab. Retomar Track A es trabajo post-entrega, sin presión de calendario.

Detalle completo del estado real (verificado contra código, no solo contra READMEs) en [`CLAUDE.md`](./CLAUDE.md).

---

## Créditos

ARGOS nació como proyecto del curso **Tópicos Avanzados de Ciberseguridad** (Universidad de Lima, 2026-1) y hoy se mantiene como pieza de portafolio open-source. Equipo original:

| | Integrante | Rol | Alcance principal |
|:--:|---|---|---|
| 🟣 | **Enzo Ordoñez** | P1 · Líder · LLM/SOAR | `argos_contracts`, Capa 4 LLM Triage (NVIDIA), motor SOAR + Tier Classifier, Approval API con JWT, notificaciones multi-canal, consola web + Streamlit, bridge/live mode, docker-compose, coordinación general |
| 🔵 | **Sebastian Montenegro** | P2 · Ingeniero ML | Capa 2 (Isolation Forest + One-Class SVM), feature extraction, calibración de thresholds, métricas A/B/C (P/R/F1, MITRE coverage), captura forense |
| 🟠 | **Angeles Castillo** | P3 · Detección · Engaño | Capa 1 (Sigma rules mapeadas a MITRE), Capa 3 (canary FIM + whodata), active-response Win+Linux, validación con Atomic Red Team y Caldera |
| 🟢 | **Diego Jara** | P4 · Infraestructura · UI | Lab de 3 VMs + Wazuh manager, PostgreSQL `app_prod`/`argos_audit` con datos sintéticos, ejecución del ataque, grabación del video demo |
| 🟡 | **Yohamin Pimentel** | Apoyo P2 · Forense | Integración forense con **Velociraptor** (`soar/response/forensics/`, recolección post-incidente), apoyo a la Capa 2 |

> Detalle visual con asignación por componente: [`docs/architecture/argos_flow.html`](./docs/architecture/argos_flow.html)

---

## Licencia

MIT — © 2026 Enzo Ordoñez Flores and ARGOS project contributors (ver [`LICENSE`](./LICENSE)). Repositorio público en GitHub desde julio de 2026.

---

## Agradecimientos

[SigmaHQ](https://github.com/SigmaHQ/sigma) por el formato Sigma abierto · [MITRE ATT&CK](https://attack.mitre.org/) por la taxonomía de amenazas · [Wazuh](https://wazuh.com/) por el SIEM/HIDS open-source · [Atomic Red Team](https://github.com/redcanaryco/atomic-red-team) y [MITRE Caldera](https://github.com/mitre/caldera) por adversary emulation · [Ollama](https://ollama.com/) por inferencia local accesible.
