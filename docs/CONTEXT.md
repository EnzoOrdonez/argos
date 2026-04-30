# SOC-in-a-Box

**Stack defensivo por capas con triage asistido por LLM para detección y contención automatizada de ransomware**

> Proyecto del curso **Tópicos Avanzados de Ciberseguridad** — Universidad de Lima — Semestre 2026-1
> Integrantes: Enzo Cáceres + 3 compañeros

---

## 1. Visión del proyecto

Construir un sistema de detección y respuesta a ransomware que combine cuatro capas defensivas independientes (rule-based, ML, deception y LLM-assisted triage), todas open source o costo mínimo, desplegado en un lab virtualizado, con demostración de un ataque end-to-end y contención automatizada en tiempo real.

**Inspiración arquitectónica:** Microsoft Defender XDR, CrowdStrike Falcon, Palo Alto Cortex XDR. No inventamos nada nuevo — replicamos la arquitectura comercial de gama alta con stack OSS y la documentamos rigurosamente. El cache profesional viene de la **calidad de ejecución**, no de originalidad arquitectónica.

---

## 2. Motivación y relevancia

### Por qué este proyecto

- **Ransomware sigue siendo el problema número uno** de empresas medianas y grandes en LATAM y Europa. Cualquier proyecto de defensa contra ransomware tiene relevancia inmediata.
- **Defense in depth** es el patrón estándar de la industria. Demostrar que entendemos y construimos múltiples capas defensivas, cada una con sus trade-offs, es lo que diferencia un perfil senior de uno junior.
- **LLM-assisted triage** es el bleeding edge comercial (Microsoft Security Copilot, CrowdStrike Charlotte AI lanzaron en 2024). Estamos alineados con la frontera, no rezagados.

### Qué buscamos como equipo

1. **Buena nota en el curso** — implementación funcional + demo impactante.
2. **Proyecto de portafolio LinkedIn-worthy** — README enterprise-grade, vídeo demo, métricas concretas, repo público al cierre del curso.
3. **Contribuciones verificables open source** — al menos 2-4 reglas Sigma aceptadas en `SigmaHQ/sigma` upstream.
4. **Aprendizaje real** — cada integrante domina su capa al punto de defenderla en entrevista técnica.

### Qué NO buscamos

- Originalidad arquitectónica forzada ("disruptivo porque sí").
- Métricas estadísticas de paper académico (no es una tesis).
- Sustituir un EDR comercial completo (scope acotado y honesto).

---

## 3. Arquitectura: 4 capas + SOAR

Ver diagrama completo en `docs/architecture/soc_in_a_box_architecture_v2.mermaid`.

### Capa 1 — Rule-Based Detection (Sigma + Wazuh)

Reglas Sigma escritas en YAML, convertidas a formato Wazuh con `sigma-cli`. Mapeadas explícitamente a técnicas MITRE ATT&CK. Detectan patrones conocidos de ransomware.

**Técnicas objetivo (mínimo):** T1486 (Data Encrypted for Impact), T1490 (Inhibit System Recovery / shadow copy deletion), T1083 (File and Directory Discovery), T1562.001 (Disable Defender), T1021 (Lateral Movement SMB/RDP), T1071 (C2 channels).

**Trade-off:** alta precisión, recall limitado contra variantes nuevas. Por eso existen las otras capas.

### Capa 2 — ML Anomaly Detection (Isolation Forest + One-Class SVM)

Modelos no supervisados entrenados sobre baseline benigno (~2 semanas de actividad normal). Detectan desviaciones que las reglas no captan.

**Features por proceso/ventana 60s:**
- Tasa de file writes
- Entropía promedio de archivos escritos
- Ratio de extensiones modificadas
- Llamadas a CryptoAPI (CryptEncrypt, BCryptEncrypt en Windows; openssl/libsodium hooks en Linux)
- Conexiones de red salientes nuevas
- CPU/IO burst patterns

**Pipeline:** Wazuh alerts → Redis stream → Python consumer → modelo → score → alerta enriquecida de vuelta a Wazuh.

**Trade-off:** mayor recall en variantes nuevas, mayor false positive rate. Requiere baseline limpio.

### Capa 3 — Deception (Canary Files + FIM)

Archivos-cebo con nombres atractivos (`financials_Q4_2025.xlsx`, `passwords.txt`, `db_backup.sql`) en ubicaciones donde un usuario legítimo nunca tocaría. FIM (File Integrity Monitoring) con Sysmon whodata (Windows) o auditd (Linux) captura QUÉ proceso accedió.

**Lógica:** primera modificación/lectura/rename de un canary = alerta crítica con confianza máxima. Por diseño, FP rate ≈ 0.

**Trade-off:** detección ultra-temprana pero acotada (atacante sofisticado puede evadir si conoce los canaries). Por eso es complemento, no reemplazo.

### Capa 4 — LLM-Assisted Triage & Enrichment

Cuando cualquier capa 1-3 dispara, un servicio FastAPI recibe el contexto completo (alerta + logs + process tree + network connections últimos 5min) y construye una respuesta estructurada usando RAG sobre corpus de seguridad + LLM.

**Corpus RAG:**
- MITRE ATT&CK STIX bundle (técnicas, mitigaciones, detecciones)
- Sigma rules documentation
- NIST SP 800-61r2 (Computer Security Incident Handling Guide)
- SANS IR playbooks públicos
- Post-mortems propios de ataques simulados en el lab

**Pipeline:** BM25 + BGE-large embeddings + RRF + cross-encoder. Reutilizado del proyecto CloudRAG (~70% del código), corpus 100% nuevo.

**LLM backend (vendor-agnostic):**
- **Primary:** DeepSeek-V3 (vía API OpenAI-compatible)
- **Fallback:** Qwen2.5-72B-Instruct
- Implementado tras `LLMClient` interface — swap en una variable de entorno.

**Output estructurado:** `{tecnica_mitre, confianza, severidad, runbook_aplicable, accion_recomendada, indicadores_correlacionar}`.

### SOAR — Decision Engine + Response Automation

Lógica de fusión de scores con reglas explícitas:

| Capas que disparan | Acción |
|--------------------|--------|
| Capa 3 sola | Aislamiento inmediato (canary = zero-FP) |
| Capa 1 + Capa 2 | Aislamiento + disk snapshot |
| Solo Capa 2 | Monitoreo reforzado + análisis LLM al analista |
| Solo Capa 1 | Alerta estándar con contexto LLM |

**Acciones automatizadas:**
- Host isolation vía iptables (Linux) / PowerShell firewall rules (Windows)
- Process kill por PID
- Disk snapshot (VSS en Windows, `dd` en Linux)
- Notificación email + Slack webhook
- Captura forense: process tree, network connections, hashes de archivos modificados

---

## 4. Stack tecnológico

### Open Source (mayoría del stack)

| Componente | Licencia | Función |
|------------|----------|---------|
| Wazuh | GPLv2 | SIEM/HIDS core |
| OpenSearch + Dashboards | Apache 2.0 | Backend de logs + visualización |
| Sysmon for Linux + auditd | GPL | Telemetría endpoint |
| Atomic Red Team | MIT | Simulación de TTPs MITRE |
| Caldera (MITRE) | Apache 2.0 | Cadenas de ataque automatizadas |
| Sigma rules + sigma-cli | DRL 1.1 / LGPL | Detection engineering |
| scikit-learn | BSD | Isolation Forest, One-Class SVM |
| FastAPI | MIT | API service Capa 4 |
| Streamlit | Apache 2.0 | Analyst UI |
| Redis | BSD | Stream entre Wazuh y ML consumer |
| BGE-large embeddings | MIT | Retrieval en RAG |
| Vagrant / Terraform | MPL / MPL | IaC del lab |

### Componentes de bajo costo (no OSS pero costo-beneficio justificado)

| Componente | Costo aprox | Justificación |
|------------|-------------|---------------|
| DeepSeek-V3 API | ~$0.14 / 1M tokens input | Razonamiento estructurado a 1/30 del costo de GPT-4 |
| Qwen2.5-72B API | Comparable | Fallback con context window largo |

**Política de vendor lock-in:** todos los componentes propietarios pasan por interfaces abstractas. El sistema completo es swappeable a Claude API, GPT-4, o Llama local con cambio de configuración, sin tocar lógica.

### Sysmon (Windows) — nota especial

Sysmon es freeware Microsoft, no OSS estricto. Lo usamos porque es el estándar de facto en blue teams y los Sigma rules upstream asumen Sysmon. Alternativa OSS es Sysmon for Linux (sí es OSS); para Windows no hay equivalente OSS de calidad comparable. Esto se documenta honestamente en el informe.

---

## 5. División de trabajo

| Persona | Rol | Responsabilidades principales |
|---------|-----|-------------------------------|
| **P1 — Enzo (Lead)** | LLM / SOAR / Coordinación | Capa 4 (FastAPI + RAG + LLMClient), Decision Engine, integración entre capas, coordinación general |
| **P2** | ML Engineer | Capa 2 completa: feature extraction, entrenamiento Isolation Forest + OC-SVM, ensemble, evaluación, integración con Wazuh vía Redis |
| **P3** | Detection Engineer | Capa 1 (reglas Sigma + mapping MITRE) + Capa 3 (canary files + FIM rules), PRs upstream a SigmaHQ |
| **P4** | Infra / Attack Sim / UI | Lab provisioning (Vagrant/Terraform), Wazuh + OpenSearch deployment, simulador de ransomware, Streamlit dashboard, dashboards Kibana/OpenSearch, métricas |

**Regla operativa crítica:** cada integrante debe poder defender SU módulo en exposición. No se permite que P1 haga el trabajo de otros con Claude Code — P1 puede ayudar con dudas, no escribir código por ellos.

**Claude Code:** P1 tiene Claude Code Max y lo usa intensivo en Capa 4 + integración. Otros pueden usar la versión gratuita o pedir ayuda puntual a P1.

---

## 6. Plan de 14 semanas

Checkpoints del curso confirmados en **semanas 5, 7 y 9**.

| Sem | P1 (LLM/SOAR) | P2 (ML) | P3 (Rules+Deception) | P4 (Infra+UI+Eval) | Gate |
|-----|---------------|---------|----------------------|---------------------|------|
| 1 | Setup repo, README, ADR inicial | Research papers ML anomaly | Lectura SigmaHQ + research gaps | VMs lab + red aislada | — |
| 2 | LLMClient interface + prompts | Spec features + dataset baseline | Reglas Sigma v1 (5 reglas core) | Wazuh + agentes + Sysmon | — |
| 3 | Mini-RAG: ingesta MITRE + NIST | Recolección baseline benigno | Atomic Red Team test reglas v1 | Caldera + primer ataque logged | — |
| 4 | RAG funcional + eval retrieval | Feature extraction pipeline | Sigma v2 + scaffolding canaries | Ransomware simulator + canary gen | Pre-Gate 1 |
| **5** | LLM client DeepSeek + Qwen fallback | Isolation Forest + métricas inicial | Capa 1 completa (10+ reglas) | Demo Capa 1 end-to-end | 🚩 **Gate 1 curso** |
| 6 | Decision Engine v1 | OC-SVM + ensemble | Canaries + FIM whodata | Pipeline Wazuh→Redis→ML | — |
| **7** | Integración Capa 4 con SOAR | ML en producción real-time | Capa 3 funcional | Streamlit v1 (analyst view) | 🚩 **Gate 2 curso** |
| 8 | Playbooks SOAR | Tuning thresholds + FP rate | **PR Sigma #1** + research #2 | OpenSearch dashboards + IaC | — |
| **9** | LLM enriquece UI + runbook | Eval full P/R/F1 por capa | **PR Sigma #2** + ajustes | Coverage matrix + FP testing | 🚩 **Gate 3 curso** |
| 10 | Hardening + edge cases | Ablation: rules vs ML vs ensemble | **PR Sigma #3** | Vídeo demo v1 raw | — |
| 11 | Refinamiento prompts + structured validation | Reporte ML + ROC curves | **PR Sigma #4** + runbooks NIST | Demo rehearsal #1 | — |
| 12 | Decision Engine + logging forense | Métricas finales | Reglas finales + Sigma follow-up | Vídeo demo v2 editado | — |
| 13 | Informe: secciones LLM/SOAR/arch | Informe: secciones ML/eval | Informe: detection/deception/MITRE | Informe: infra/UI/métricas | — |
| 14 | Slide visión + rehearsal x10 | Slides ML | Slides detection | Slides infra + recording final | 🎯 **Exposición** |

---

## 7. Gates de abandono (críticos)

Si en un gate la condición no se cumple, **se sacrifica scope, no calidad**:

- **Gate 1 (sem 5):** si Capa 1 no end-to-end, P2 pausa ML y ayuda a P3 hasta arreglar. No se construye sobre fundación rota.
- **Gate 2 (sem 7):** si Capa 2 ML no funciona mínimamente, **se abandona Capa 4 LLM** y se pivota a versión simplificada (Capas 1+3+SOAR). Sigue defendible.
- **Gate 3 (sem 9):** si stack no integrado, se sacrifican PRs Sigma de semanas 10-11 para enfocar todo en el demo.

**Regla de oro:** mejor 3 capas pulidas que 4 chapuceras.

---

## 8. Métricas (3 categorías separadas)

### A. Demo headline (3 métricas para slide de exposición)

1. **Time-to-detect (TTD)** — segundos desde inicio del ataque hasta primera alerta válida.
2. **Archivos afectados antes de contención** — cuántos archivos reales se encriptaron antes del aislamiento del host.
3. **False positive rate** — sobre 24-48h de actividad benigna baseline.

### B. Forensia / Incident Response Timeline (para informe NIST + auditoría)

- Event chain completo cronológico (cada evento Wazuh con timestamp, host, proceso, técnica MITRE inferida).
- Process tree del proceso ofensor.
- Network connections del proceso (origen, destino, puerto, protocolo).
- User actions correlacionadas (login, comandos ejecutados).
- Hashes SHA256 de todos los archivos modificados.
- Command-line completo del proceso ofensor.

Todo capturado nativamente por Wazuh + OpenSearch — no es trabajo extra, solo decidir qué se reporta.

### C. Evaluación del sistema (para informe técnico)

- Precision / Recall / F1 por capa individual.
- MITRE ATT&CK coverage matrix (técnicas detectadas vs no detectadas).
- Latencia por capa (Capa 1 vs 2 vs 3 vs 4).
- Throughput de eventos procesados por segundo.
- Comparación ablation: solo reglas vs solo ML vs ensemble.

---

## 9. Estrategia de demo

**El demo es lo más importante para la nota.** Reglas:

1. **Guion narrativo escrito en semana 11.** 4-5 minutos máximo. Estructura: setup (1min) → ataque (1min) → detección + LLM analysis (1.5min) → contención automatizada (1min) → forensia post-mortem (30s).
2. **Ataque scriptado y reproducible.** Nada improvisado en vivo.
3. **Vídeo de respaldo grabado** por si algo falla en el momento.
4. **Cada integrante tiene su minuto** explicando su capa con la pantalla específica.
5. **Rehearsal mínimo 10 veces** en semanas 13-14.

**Inspiración visual:** las demos de CrowdStrike y SentinelOne en YouTube. Pantalla dividida: ataque a la izquierda, dashboard a la derecha.

---

## 10. Bonus killer: contribuciones Sigma upstream

Cada integrante intenta contribuir 1 regla Sigma al repo `SigmaHQ/sigma` aceptada por mantenedores. Esto queda forever en el commit history con tu nombre como `author`.

**Estrategia:**
- Identificar gaps específicos no cubiertos en el repo actual (ej. técnicas evasivas de shadow copy deletion, canary file access patterns, ransomware específicos 2025-2026).
- Escribir regla con referencias a threat reports / papers.
- Pasar tests locales: `python tests/test_rules.py`.
- PR con descripción clara del threat scenario.
- Iterar feedback de mantenedores (1-3 semanas review típico).

**Costo:** ~4-6h por regla (research + escritura + tests + PR).
**Reward:** contribución open source verificable con nombre propio. Muy raro en perfiles estudiantiles.

Si un PR es rechazado, no es drama — se documenta el aprendizaje y la regla queda en el repo del proyecto.

---

## 11. Convenciones del equipo

### Repo

- **Privado durante el curso, público al cierre.**
- Branch principal: `main`. PRs obligatorios para merge (al menos 1 review).
- Branches feature: `feature/<persona>/<descripcion>` (ej. `feature/p2/isolation-forest-baseline`).
- Commits convencionales: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.
- `.gitignore` incluye: `.env`, `*.pcap`, `models/*.pkl`, `data/raw/`, logs sensibles.
- Secretos vía `.env.example` (template) + `.env` (gitignored).

### Sync semanal (no negociable)

- **Lunes 30min — Standup:** qué hice, qué voy a hacer, bloqueos, dependencias.
- **Viernes 30min — Demo interno:** cada uno muestra su avance al grupo.
- Plantilla de standup en `docs/standup-template.md`.

### Decisiones arquitectónicas

- Toda decisión arquitectónica significativa va en `docs/adr/NNNN-titulo.md` (Architecture Decision Record).
- Formato simple: contexto, decisión, alternativas consideradas, consecuencias.

### Documentación viva

- `README.md` siempre refleja estado actual del proyecto.
- Cada capa tiene su propio `README.md` en su carpeta.
- Demo de capa = vídeo o GIF de 30s en `docs/demos/`.

---

## 12. Estructura del repo

```
soc-in-a-box/
├── README.md                  # Entry point: visión, demo gif, instalación
├── LICENSE                    # MIT (definir en sem 1)
├── .gitignore
├── .env.example
│
├── docs/
│   ├── architecture/
│   │   ├── soc_in_a_box_architecture_v2.mermaid
│   │   └── README.md (explica el diagrama)
│   ├── adr/                   # Architecture Decision Records
│   │   ├── 0001-llm-vendor-agnostic.md
│   │   └── 0002-...
│   ├── runbooks/              # Playbooks NIST
│   ├── demos/                 # GIFs y vídeos
│   └── standup-template.md
│
├── lab/
│   ├── vagrant/               # VirtualBox lab provisioning
│   ├── terraform/             # IaC opcional Azure
│   └── README.md
│
├── detection/
│   ├── sigma-rules/           # Reglas custom (algunas para upstream)
│   ├── wazuh-rules/           # Reglas convertidas para Wazuh
│   ├── mitre-mapping.yaml     # Matriz cobertura MITRE
│   └── README.md
│
├── ml/
│   ├── features/              # Feature extraction
│   ├── models/                # Entrenamiento Isolation Forest, OC-SVM
│   ├── consumer/              # Redis consumer integrado con Wazuh
│   ├── notebooks/             # EDA + experimentos
│   └── README.md
│
├── deception/
│   ├── canary-generator/      # Script Python para generar canaries
│   ├── fim-configs/           # Configs FIM Wazuh
│   └── README.md
│
├── soar/
│   ├── decision-engine/       # Lógica fusion + reglas
│   ├── playbooks/             # Acciones de respuesta
│   └── README.md
│
├── llm-triage/
│   ├── api/                   # FastAPI service
│   ├── rag/                   # Mini-RAG: ingesta, retrieval, eval
│   ├── llm-client/            # LLMClient interface + DeepSeek + Qwen
│   ├── prompts/               # Templates Jinja2
│   └── README.md
│
├── ui/
│   ├── streamlit-app/         # Analyst dashboard
│   ├── opensearch-dashboards/ # JSON exports de dashboards
│   └── README.md
│
├── attack-simulation/
│   ├── ransomware-simulator/  # Script Python custom
│   ├── atomic-red-team/       # Configs y wrappers
│   ├── caldera-operations/    # Operations definidas
│   └── README.md
│
└── evaluation/
    ├── metrics/               # Scripts cálculo métricas A/B/C
    ├── datasets/              # Ground-truth manual + baseline
    ├── reports/               # Reportes finales
    └── README.md
```

---

## 13. Próximos pasos inmediatos (semana 1)

1. **Crear repo privado en GitHub** con esta estructura — owner: P1, colaboradores: P2, P3, P4.
2. **Push inicial:** este `CONTEXT.md`, README skeleton, diagrama, ADR-0001.
3. **Primer standup lunes:** validar plan con todo el equipo.
4. **Validar scope con el profesor del curso** antes de empezar — confirmar que la Capa 4 LLM no sale del dominio del curso.
5. **P4 inicia provisioning del lab** — VMs deben estar listas semana 2.
6. **P1 inicia LLMClient interface y skeleton FastAPI.**
7. **P2 hace research papers.** Sugerencias iniciales:
   - "Ransomware Detection Using Machine Learning" — surveys recientes en IEEE
   - Datasets: CIC-IDS2018, BODMAS, MalwareBazaar
8. **P3 hace audit del repo SigmaHQ** — identificar 4 gaps potenciales para PRs.

---

## 14. Referencias clave

- **MITRE ATT&CK:** https://attack.mitre.org/
- **SigmaHQ:** https://github.com/SigmaHQ/sigma
- **Wazuh docs:** https://documentation.wazuh.com/
- **NIST SP 800-61r2:** https://csrc.nist.gov/pubs/sp/800/61/r2/final
- **Atomic Red Team:** https://github.com/redcanaryco/atomic-red-team
- **Caldera:** https://github.com/mitre/caldera
- **DeepSeek API docs:** https://platform.deepseek.com/
- **Qwen API docs:** https://help.aliyun.com/zh/dashscope/

---

**Última actualización:** Semana 1 (kickoff)
**Owner del documento:** P1 (Enzo)
**Estado:** Draft inicial — aprobado por equipo en standup semana 1
