# PROJECT BRIEF — ARGOS

**Adaptive Ransomware Guard with Orchestrated Surveillance**
*Curso: Tópicos Avanzados de Ciberseguridad · Universidad de Lima · 2026-1*

---

## Problema

Las empresas medianas y grandes no pueden costear EDRs comerciales (CrowdStrike, Defender XDR) que combinan reglas, ML y triage asistido por LLM, y los stacks open source actuales se quedan en una sola capa de detección — vulnerable a variantes de ransomware nuevas y con triage 100% manual.

## Solución

Sistema de detección y respuesta a ransomware con **defense-in-depth de 4 capas paralelas + SOAR + LLM triage**, todo OSS (excepto LLM API de bajo costo), desplegado en lab virtualizado y con demostración de ataque end-to-end con contención automatizada.

## Arquitectura — 4 capas de detección

1. **Capa 1 — Rule-Based:** Reglas Sigma mapeadas a MITRE ATT&CK (T1486, T1490, T1083, T1562) ejecutadas en Wazuh. Alta precisión.
2. **Capa 2 — ML Anomaly:** Isolation Forest + One-Class SVM sobre features de procesos (entropía, syscalls cripto, I/O patterns). Detecta variantes nuevas.
3. **Capa 3 — Deception:** Canary files con FIM whodata. Zero false-positive por diseño. Detección ultra-temprana.
4. **Capa 4 — LLM Triage:** FastAPI + mini-RAG (MITRE + NIST 800-61) + LLMClient vendor-agnostic (DeepSeek primary / Qwen fallback). Output estructurado con técnica, severidad, runbook.

**SOAR Decision Engine** clasifica alertas en 4 tiers (T0-T3) según confianza, fusiona scores y dispara contención automatizada para alta confianza, o solicita aprobación humana vía email para tiers medios. **Approval Workflow Console** visualiza decisiones multi-aprobador en tiempo real con resolución de split-brain por conservative-wins policy.

## Stack

Wazuh · OpenSearch · Sigma · Sysmon · auditd · Atomic Red Team · Caldera · scikit-learn · FastAPI · Streamlit · Redis · DeepSeek/Qwen API · JWT signing · Jinja2 templates · APScheduler

## Equipo y división

| Rol | Responsabilidad |
|-----|-----------------|
| **P1** Lead / LLM-SOAR | Capa 4, RAG, Decision Engine + tier classifier, Approval API, integración, coordinación |
| **P2** ML Engineer | Capa 2 completa: features, modelos, ensemble, evaluación |
| **P3** Detection Engineer | Capas 1+3: Sigma rules, MITRE mapping, deception, PRs upstream |
| **P4** Infra / UI / Eval | Lab, simulador de ataque, Streamlit + Approval Workflow Console, dashboards, métricas |

## Plan — 14 semanas con 3 gates

- **Gate 1 (sem 5):** Capa 1 end-to-end funcional.
- **Gate 2 (sem 7):** Capas 1+2+3 integradas con SOAR.
- **Gate 3 (sem 9):** Stack completo + Capa 4 LLM + Approval flow + métricas iniciales.
- **Sem 10-12:** PRs Sigma upstream, hardening, vídeo demo.
- **Sem 13-14:** Informe técnico, exposición.

## Resultados esperados

- **Demo en vivo:** ataque → detección multi-capa → análisis LLM → aprobación humana con split-brain (4 aprobadores) → contención por conservative-wins.
- **Approval Workflow Console** mostrando decisiones en tiempo real durante el demo.
- **Métricas:** time-to-detect, archivos afectados antes de contención, false positive rate, MITRE coverage matrix, P/R/F1 por capa, latencia de aprobación humana.
- **Bonus killer:** 2-4 reglas Sigma aceptadas en `SigmaHQ/sigma` upstream con autoría verificable.
- **Repo público al cierre del curso** con README enterprise-grade + vídeo demo de 3min.

## Resiliencia y manejo de fallos

El sistema está diseñado contra fallos del propio defensor. **El LLM nunca está en el path crítico de contención** — si alucina o falla, el SOAR sigue actuando desde Capas 1-3. **Si el atacante mata el agente Wazuh**, la desconexión es ella misma alerta crítica. **Conservative-wins policy** protege contra cuentas comprometidas que rechacen contenciones legítimas. Tres capas de detección independientes garantizan degradación gradual, no ceguera total. Threat model completo (STRIDE + FMEA + Risk Register, ~50 amenazas analizadas) en `THREAT_MODEL.md`. Decisiones arquitectónicas individuales en ADRs 0001 a 0007 (incluye ADR-0007: cadena de notificación multi-canal con escalación temporal).

## Por qué importa

Replica la arquitectura de productos comerciales de gama alta (Microsoft Defender XDR, CrowdStrike Falcon) con stack 100% open source. El cache profesional viene de la **calidad de ejecución y rigor del informe**, no de originalidad arquitectónica forzada. Proyecto apto para portafolio LinkedIn y referencia técnica en entrevistas blue team.

---
*v1.3 · Kickoff + Threat Model + HITL SOAR + multi-channel notification · Owner: P1*
