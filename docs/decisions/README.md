# Architecture Decision Records (ADRs)

This directory contains the architectural decisions made for ARGOS, following the [ADR pattern popularized by Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

Each ADR is a short document that captures:
- **Context:** what problem we faced.
- **Decision:** what we chose to do.
- **Alternatives considered:** what else we evaluated and why we rejected it.
- **Consequences:** trade-offs accepted, both positive and negative.

Rejected decisions are documented too — they show that the team evaluated alternatives rigorously rather than ignoring them.

---

## Index

| # | Title | Status | Summary |
|---|-------|--------|---------|
| [0001](./0001-llm-vendor-agnostic.md) | LLM vendor-agnostic via LLMClient interface (v2) | ✅ Accepted | Abstract LLM behind interface; OpenAI GPT-4o-mini primary (US-based) + Llama 3.1 8B local fallback (zero-egress). v2 reasignó primario por soberanía de datos. Swap via env var. |
| [0002](./0002-heartbeat-default-60s.md) | Wazuh agent heartbeat — keep default 60s | ✅ Accepted | Reject lowering heartbeat interval; alert fatigue cost outweighs marginal detection improvement. |
| [0003](./0003-confidence-tiered-automation.md) | Confidence-tiered automation with HITL SOAR | ✅ Accepted | 4-tier classification (T0-T3); auto-execute high confidence, human approval for medium-uncertain. T2 timeout 3min with throttle+snapshot during countdown. |
| [0004](./0004-auto-rollback-rejected.md) | Auto-rollback "dead man's switch" | ❌ Rejected | Rejected. Contradicts "fails closed" principle. Documented to show the team considered and consciously rejected the option. |
| [0005](./0005-notification-channel-abstraction.md) | Notification channel abstraction | ✅ Accepted | Strategy pattern for notification channels. Foundation para ADR-0007; canales concretos definidos allí. |
| [0006](./0006-split-brain-resolution.md) | Split-brain resolution — conservative-wins policy | ✅ Accepted | When approvers disagree, conservative-wins policy with 60s consolidation window. In containment context, conservative = isolate. |
| [0007](./0007-notification-multichannel-escalation.md) | Multi-channel notification escalation chain (v2) | ✅ Accepted | Telegram (primario) + Discord (visibilidad del equipo) en paralelo a t=0; Twilio Voice (DTMF) como escalación a t=60s; email degradado a notificación post-facto. v2 reemplazó ntfy.sh y Slack (canales que el equipo no usa) por Discord. |
| [0008](./0008-multi-vector-scope-expansion.md) | Multi-vector scope expansion (XDR-style) | ✅ Accepted | Expansión de scope ransomware-only a multi-vector. Rebrand "Adaptive Ransomware Guard" → "Adaptive Response Guard" (mantiene acrónimo ARGOS). Añade UC-06 DDoS, UC-07 SELECT masivo legítimo (T2 false positive cancelado por humano), UC-08 SQL injection. MITRE expandido con T1498, T1499, T1078. Política Claude Code: cada integrante puede usarlo en su propia parte. |
| [0009](./0009-intibank-scenario.md) | Banco Inti S.A.A. (IntiBank) — escenario empresarial concreto | ✅ Accepted | Define el activo defendido: schema PostgreSQL bancario de 7 tablas (customers, accounts, cards, transactions, transfers, internal_users, audit_log), 6 roles con separation of duties, umbrales Sigma combinados (MIN_ABSOLUTE + MIN_PERCENT por tabla), matriz capa × UC, branding dual Banco Inti SAA / IntiBank, IPs ficticias, referencias compliance reales (SBS, ISO 27001, SOC 2, PCI). Desbloquea P2/P3/P4 para Fase 2 con datos concretos. |
| [0010](./0010-demo-operational-decisions.md) | Decisiones operacionales del demo (ideal vs mínimo) | ✅ Accepted | 11 decisiones consolidadas con patrón ideal/mínimo: UC-05 mini-cameo, Flask webapp para UC-08, ML temporal, HITL coordination, TP/FP benchmarks, retraining, DNI checksum, backup narrative, MFA flag, statement_timeout, professor kit. Política de fallback explícita con triggers temporales (T-7/T-14/T-21 días) y dueños por decisión. |
| [0011](./0011-soar-implementation-reconciliation.md) | Reconciliacion de implementacion SOAR (manual P1 ↔ argos_contracts v1.1.0) | ✅ Accepted | Formaliza las correcciones de Fase 2: el manual §Fase 2-3 estaba desfasado del contrato v1.1.0 y de ADR-0003/0006 (conservative-wins, two-person por criticidad, T3 notifica, tier fusion + fast-path DDoS, FinalDecision/ApproverState reales). Resuelve el mismatch SAD §6.5 (PENDING_SECOND_APPROVAL no esta en el enum → usar AWAITING_APPROVAL). Fija dependencias de Fase 3 (throttle/snapshot/scheduler, consumer sobre NormalizedAlert). |
| [0012](./0012-response-playbooks.md) | Response playbooks — modelo de ejecucion e interfaz | ✅ Accepted | Diseno (doc-first) de los playbooks de respuesta: ResponseExecutor abstracto (Wazuh active-response real + SimulatedExecutor demo-safe), catalogo ActionType×cuando-disparan (throttle+snapshot inmediatos pre-aprobacion = clave de ADR-0006 Sit.B; isolation+kill en EXECUTE_ISOLATION), contrato ProposedAction/execution_status, reversibilidad/idempotencia/fail-soft. Deps cross-team: P3 (Wazuh AR), P4 (lab). Review P1 2026-06-10 con ajustes (§7): Accepted. |
| [0013](./0013-soar-orchestration.md) | Orquestacion SOAR Fase 3 — consumer, correlacion, scheduler, LLM hook, audit | ✅ Accepted | Diseno (doc-first) del orquestador: consumer de events:normalized con **correlacion incremental** de NormalizedAlerts por host_id (ventana 5s + fast-path canary/AUTO_T0) → RoutingSignal; construccion de Incident (INC-id daily counter, criticidad por inventario); throttle+snapshot inmediatos; hook LLM no-bloqueante (AlertContext→TriageResponse en Incident.llm_analysis); scheduler de la ventana; contencion al resolver; audit OpenSearch+Postgres con Literals reales. Corrige el 'un evento = un incidente' del manual §3.1. Review P1 2026-06-10 con 10 correcciones (§7: correlacion con dos indices, inventario por host_id, gate LLM T2 ∪ two-person, asyncio con tres relojes, poison guard): Accepted. |
| [0014](./0014-normalization-bridge.md) | Bridge de normalizacion: Wazuh (L1/L3) + score ML (L2) -> `NormalizedAlert` en `events:normalized` | 🟡 Proposed | Cierra el hueco #1 de la auditoria post-merge (2026-06-24): ninguna capa publicaba al stream. Normalizador separado del SOAR (dueño P2/P4, NO P1 ni el nuevo): camino A Wazuh->NormalizedAlert (source_layer por group, MITRE por mitre-mapping.yaml, level->severity_score); camino B publisher del ml.soar_adapter. Fija el campo del entry = `payload` (corrige el `data` del manual de P2 que rompia el consumer con KeyError). Relacionado: fix T1213->T1005 (no estaba en MITRE_WHITELIST). |
| [0015](./0015-real-prototype-realization.md) | Prototipo real: active-response, Wazuh manager-only + VM Windows, swap simulado↔real | ✅ Accepted | Dos caminos: VIDEO simulado garantizado (demo_injector + SimulatedExecutor, cero codigo nuevo) y PROTOTIPO REAL por fases, conmutado por env (feeder demo_injector↔bridge; executor Simulated↔Wazuh) SIN tocar soar/ ni el contrato. Bridge = tail de alerts.json→NormalizedAlert (realiza ADR-0014) + publisher ML. AR = scripts argos-{isolate,throttle,snapshot,kill} + ossec.conf; isolate DEBE whitelistear la IP del manager (1514/1515) o se auto-brickea. Dos perfiles: A demo-lite (1 laptop 16GB, Wazuh manager-only por RAM) y B full (manager+indexer+dashboard, distribuido = lo que el prototipo final debe tener). Victima central = DB server Debian+PostgreSQL (activo PII production-critical, UC-04/07/08); endpoint Windows 10 (UC-01/02/05). Fases: A video, B VM Windows, C DB server Debian. |

---

## Closure document

| Document | Purpose |
|----------|---------|
| [OPEN_QUESTIONS_RESOLUTION.md](./OPEN_QUESTIONS_RESOLUTION.md) | Resolves 9 minor open questions in batch (Q1-Q9), including the corrected T2 timeout behavior with throttle and proactive snapshot during countdown. |

---

## Conventions

- ADRs are **immutable once accepted**. Changes happen via new ADRs that supersede earlier ones, OR via in-place version bumps (v2, v3) when the same decision needs to be revisited honestly — preserving the original rationale and the new one side-by-side.
- New ADR number = max existing + 1.
- Status values: `Proposed`, `Accepted`, `Rejected`, `Superseded by ADR