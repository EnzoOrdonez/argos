# PROJECT BRIEF — ARGOS

**Adaptive Response Guard with Orchestrated Surveillance**
*Curso: Tópicos Avanzados de Ciberseguridad · Universidad de Lima · 2026-1*

---

## Problema

Las empresas medianas y grandes no pueden costear EDRs comerciales (CrowdStrike, Defender XDR) que combinan reglas, ML y triage asistido por LLM, y los stacks open source actuales se quedan en una sola capa de detección — vulnerable a variantes de ransomware nuevas y con triage 100% manual.

## Solución

Plataforma multi-vector de detección y respuesta (XDR-style per ADR-0008) con **defense-in-depth de 4 capas paralelas + SOAR + LLM triage**. Énfasis primario en ransomware; extendida a Network DoS y Application Abuse. Todo OSS (excepto LLM API de bajo costo), desplegado en lab virtualizado y con demostración end-to-end de 3 vectores de ataque con contención automatizada y false positive cancellation por humano.

## Arquitectura — 4 capas de detección

1. **Capa 1 — Rule-Based:** Reglas Sigma mapeadas a MITRE ATT&CK (T1486, T1490, T1083, T1562) ejecutadas en Wazuh. Alta precisión.
2. **Capa 2 — ML Anomaly:** Isolation Forest + One-Class SVM sobre features de procesos (entropía, syscalls cripto, I/O patterns). Detecta variantes nuevas.
3. **Capa 3 — Deception:** Canary files con FIM whodata. Zero false-positive por diseño. Detección ultra-temprana.
4. **Capa 4 — LLM Triage:** FastAPI + mini-RAG (MITRE + NIST 800-61) + LLMClient vendor-agnostic (NVIDIA NIM `openai/gpt-oss-120b` primary / Llama 3.1 8B local vía Ollama como fallback zero-egress, diferido — per ADR-0001 v3). Output estructurado con técnica, severidad, runbook.

**SOAR Decision Engine** clasifica alertas en 4 tiers (T0-T3) según confianza, fusiona scores y dispara contención automatizada para alta confianza, o solicita aprobación humana vía notificación multi-canal (Telegram + Discord + Twilio Voice, per ADR-0007 v2) para tiers medios. **Approval Workflow Console** visualiza decisiones multi-aprobador en tiempo real con resolución de split-brain por conservative-wins policy.

## Stack

Wazuh · OpenSearch · Sigma · Sysmon · auditd · Atomic Red Team · Caldera · scikit-learn · FastAPI · Streamlit · Redis · NVIDIA NIM (`openai/gpt-oss-120b`) + Llama 3.1 local vía Ollama (diferido) · JWT signing · Jinja2 templates · APScheduler · PostgreSQL (activo defendido)

## Equipo y división

| Rol | Integrante | Responsabilidad |
|-----|-----------|-----------------|
| **P1** Lead / LLM-SOAR | Enzo Ordoñez Flores | Capa 4, RAG, Decision Engine + tier classifier, Approval API, simulador, playbooks, coordinación |
| **P2** ML Engineer | Sebastian Montenegro | Capa 2 completa: features, modelos, ensemble, evaluación, métricas, captura forense |
| **P3** Detection Engineer | Angeles Castillo | Capas 1+3: Sigma rules, MITRE mapping, deception, validación con ART/Caldera, PRs upstream |
| **P4** Infra / UI / Demo | Diego Jara | Lab Vagrant + Wazuh deployment + PostgreSQL, UI Streamlit base, video demo |

## Plan — 3 gates antes de la entrega

- **Gate 1:** Capa 1 end-to-end funcional.
- **Gate 2:** Capas 1+2+3 integradas con SOAR.
- **Gate 3:** Stack completo + Capa 4 LLM + Approval flow + métricas iniciales.
- **Entrega final:** 1 de julio de 2026 (movida desde 28-jun, antes 13-jun) — informe técnico + demo en vivo + presentación (~13 min).

## Resultados esperados

- **Demo en vivo:** ataque → detección multi-capa → análisis LLM → aprobación humana con split-brain (4 aprobadores) → contención por conservative-wins.
- **Approval Workflow Console** mostrando decisiones en tiempo real durante el demo.
- **Métricas:** time-to-detect, archivos afectados antes de contención, false positive rate, MITRE coverage matrix, P/R/F1 por capa, latencia de aprobación humana.
- **Bonus killer:** 2-4 reglas Sigma aceptadas en `SigmaHQ/sigma` upstream con autoría verificable.
- **Repo público en GitHub** (público desde julio de 2026) con README enterprise-grade + vídeo demo de 3min.

## Resiliencia y manejo de fallos

El sistema está diseñado contra fallos del propio defensor. **El LLM nunca está en el path crítico de contención** — si alucina o falla, el SOAR sigue actuando desde Capas 1-3. Si el primario OpenAI cae, fallback automático a Llama 3.1 local (zero-egress) — el sistema sigue funcionando sin internet. **Si el atacante mata el agente Wazuh**, la desconexión es ella misma alerta crítica. **Conservative-wins policy** protege contra cuentas comprometidas que rechacen contenciones legítimas. Tres capas de detección independientes garantizan degradación gradual, no ceguera total. Threat model completo (STRIDE + FMEA + Risk Register, ~50 amenazas analizadas) en `THREAT_MODEL.md`. Decisiones arquitectónicas individuales en ADRs 0001 a 0008.

## Por qué importa

Replica la arquitectura de productos comerciales de gama alta (Microsoft Defender XDR, CrowdStrike Falcon) con stack 100% open source. El cache profesional viene de la **calidad de ejecución y rigor del informe**, no de originalidad arquitectónica forzada. Proyecto apto para portafolio LinkedIn y referencia técnica en entrevistas blue team.

---
*v1.5 · Sync 2026-07-01: backend LLM (NVIDIA NIM gpt-oss-120b, ADR-0001 v3) + fecha de entrega (1-jul) ·
Owner: P1 (Enzo Ordoñez Flores)*
