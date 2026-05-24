# ARGOS — Documentación

**Adaptive Response Guard with Orchestrated Surveillance**

Sistema de detección y respuesta a ransomware con defensa en profundidad: detección por reglas (Sigma + Wazuh), detección de anomalías ML, engaño (canary files) y triage asistido por LLM con SOAR human-in-the-loop.

> Tópicos Avanzados de Ciberseguridad · Universidad de Lima · 2026-1
> **Entrega final: 13 de junio de 2026**

---

## Por dónde empezar

| Si eres... | Lee esto primero |
|------------|------------------|
| Evaluador con 90 segundos | [`PROJECT_BRIEF.md`](./PROJECT_BRIEF.md) |
| Integrante del equipo (onboarding) | [`CONTEXT.md`](./CONTEXT.md) |
| Arquitecto revisando el diseño | [`architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](./architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) |
| Revisor de postura de seguridad | [`architecture/THREAT_MODEL.md`](./architecture/THREAT_MODEL.md) |
| Buscando una decisión arquitectónica específica | [`decisions/README.md`](./decisions/README.md) |
| Quieres ver el sistema visualmente | [`architecture/argos_flow.html`](./architecture/argos_flow.html) o [`architecture/argos_flow.drawio`](./architecture/argos_flow.drawio) |
| Quieres entender qué muestra el demo | [`use-cases/USE_CASES.md`](./use-cases/USE_CASES.md) |
| Quieres ver responsabilidades por integrante | [`architecture/argos_flow.html`](./architecture/argos_flow.html) |

---

## Mapa de la documentación

### Nivel superior

- **`PROJECT_BRIEF.md`** — Resumen ejecutivo de una página. La forma más rápida de entender qué es ARGOS y por qué importa.
- **`CONTEXT.md`** — Onboarding completo del equipo: visión, alcance, stack, división del trabajo, plan, convenciones, estructura del repo.
- **`PROJECT_STATUS.md`** — Snapshot honesto de qué está realmente entregado vs. qué prometen los demás documentos. Cierra la brecha de "procesos mandatados sin evidencia de ejecución".

### Arquitectura

- **`architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`** — Solution Architecture Document (SAD). Especificación técnica completa de cada componente, interacción y preocupación transversal. La referencia canónica para "cómo funciona ARGOS".
- **`architecture/argos_flow.html`** y **`architecture/argos_flow.drawio`** — Flujo del sistema con asignación visible por integrante. Pieza de presentación.
- **`architecture/THREAT_MODEL.md`** — Análisis STRIDE (~50 amenazas), FMEA de fiabilidad, Risk Register del proyecto y 10 propiedades de resiliencia verificables.

### Decisiones

- **`decisions/README.md`** — Índice de todos los Architecture Decision Records (ADRs) con estado y resumen.
- **`decisions/0001`** a **`0007`** — ADRs individuales que documentan cada decisión arquitectónica con racional, alternativas consideradas y consecuencias.
- **`decisions/OPEN_QUESTIONS_RESOLUTION.md`** — Documento de cierre que resuelve preguntas menores en lote (Q1-Q9), incluyendo el comportamiento corregido del timeout T2.

### Casos de uso

- **`use-cases/USE_CASES.md`** — Escenarios demo (UC-01 a UC-05) con guiones de narración + escenarios de evaluación (EV-01 a EV-07) para pruebas de robustez del sistema.

### Cumplimiento del curso

- **`EVALUATION_CRITERIA.md`** — Rúbrica del curso (Informe Final Técnico + Presentación + Implementación Funcional + checkpoints) con mapeo de cada sección requerida a artefactos del repo.
- **`data-handling.md`** — Política de manejo de datos sensibles que cruzan a APIs externas: qué se sanitiza, qué se audita, qué constituye violación.

### Equipo

- **`team/standup-template.md`** — Plantilla para standups semanales de lunes.

---

## Equipo y responsabilidades

| Rol | Integrante | Responsabilidades principales |
|-----|------------|-------------------------------|
| **P1 · Líder · LLM/SOAR · Coordinación** | **Enzo Ordoñez Flores** | `argos_contracts` (entregado), Capa 4 LLM Triage completa (FastAPI + RAG + cliente vendor-agnostic), Motor SOAR + Tier Classifier, máquina de estados, Approval API con JWT, notificaciones multicanal, política conservative-wins y two-person rule, Consola de Aprobación en Streamlit, simulador de ransomware reproducible, playbooks de containment, heartbeat externo, coordinación general |
| **P2 · Ingeniero ML** | **Sebastian Montenegro** | Capa 2 ML completa (Isolation Forest + One-Class SVM ensemble), feature extraction ventana 60s, recolección de baseline benigno, pipeline Redis consumer, calibración de thresholds (Q5 protocol), métricas A/B/C (P/R/F1 por capa, MITRE coverage, ablation), captura forense (process tree, hashes, command-line), modelo de datos de dashboards OpenSearch |
| **P3 · Detección y Engaño** | **Angeles Castillo** | Capa 1: reglas Sigma YAML mapeadas a MITRE, conversión a Wazuh vía `sigma-cli`, uso del campo Sigma `level:` para clasificación de fidelidad. Capa 3: generador de canary files, configuración FIM whodata (Windows) y auditd (Linux). Validación 1-a-1 con Atomic Red Team y cadenas Caldera. Objetivo bonus: 2-4 PRs upstream aceptados en `SigmaHQ/sigma` |
| **P4 · Infraestructura · UI base · Demo** | **Diego Jara** | Vagrantfile reproducible en menos de 30 min, despliegue de Wazuh Manager + OpenSearch + Redis, setup de Windows VM (Sysmon) y Linux VM (auditd), provisioning de PostgreSQL con datos sintéticos (activo defendido), UI base Streamlit (Alert Inspection + Audit & Forensics; la Consola de Aprobación la entrega P1), grabación y edición del video demo, coordinación de rehearsals |

Cada integrante debe poder defender su capa en exposición. Regla operativa: P1 no escribe código de otros con Claude Code — puede ayudar con dudas, no escribir código por ellos (per `CONTEXT.md` §5).

---

## Estado del proyecto

Snapshot detallado en [`PROJECT_STATUS.md`](./PROJECT_STATUS.md).

| Componente | Estado |
|------------|--------|
| Diseño arquitectónico (SAD, threat model, 7 ADRs, contracts spec, use cases) | Completado |
| `argos_contracts` (Pydantic v2 cross-team, 69 tests) | Entregado · v1.1.0 |
| Capa 1 (Sigma + Wazuh) | Pendiente |
| Capa 2 (ML anomalía) | Pendiente |
| Capa 3 (Canary FIM) | Pendiente |
| Capa 4 (LLM Triage) | Esqueletos + TODOs |
| Motor SOAR + Approval API | Pendiente |
| Lab Vagrant + Wazuh deployment | Pendiente |
| Simulador de ransomware | Pendiente |
| UI Streamlit + Approval Console | Pendiente |
| Evaluación + métricas | Pendiente |
| Video demo + exposición | Pendiente |

---

## Quick stats

- **Arquitectura:** 4 capas de detección + SOAR + LLM triage + Approval Workflow Console.
- **Stack:** Wazuh, OpenSearch, Sigma, Sysmon, auditd, Atomic Red Team, Caldera, scikit-learn, FastAPI, Streamlit, Redis, GPT-4o-mini (primario) + Llama 3.1 local (fallback).
- **Activo defendido:** PostgreSQL Production DB sobre Linux VM (criticality = production-critical).
- **Documentación:** completa para fase de diseño antes de cualquier código escrito.
- **Amenazas analizadas:** ~50 vía STRIDE + FMEA.
- **Decisiones arquitectónicas:** 7 ADRs (6 aceptados, 1 rechazado) + 9 resoluciones de cierre.

---

## Licencia

MIT — copyright Enzo Ordoñez Flores (ver `LICENSE`). Repositorio privado durante el curso, público al cierre.
