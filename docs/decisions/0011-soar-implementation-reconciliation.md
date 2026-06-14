# ADR-0011 — Reconciliación de implementación SOAR (manual P1 ↔ argos_contracts v1.1.0)

| Campo | Valor |
|-------|-------|
| Status | ✅ Accepted · 2026-05-30 |
| Deciders | P1 (Enzo) — confirmado en la implementación de Fase 2 |
| Related | `argos_contracts` v1.1.0 (inmutable), ADR-0003 (tiers), ADR-0005 (canales), ADR-0006 (split-brain), ADR-0007 v2 (escalación), ADR-0009/0010 (escenario/ops), `manual-p1-enzo.md` §Fase 2-3, SAD §6 |
| Supersedes / amends | No supersede ningún ADR. **Reconcilia y supersede los snippets de código de `manual-p1-enzo.md` §Fase 2-3**, que quedaron desfasados del contrato. |

---

## 1. Contexto

Al implementar la Fase 2 del SOAR (§2.1–§2.8 del manual P1) se detectó que **los snippets de código del manual fueron escritos contra un diseño previo del contrato** (`Incident`/`NormalizedEvent` "planos"), que fue refactorizado a la forma **v1.1.0** en el commit `3da6216` (TD-01 `Incident.host → HostInfo`; TD-02 tipos `Literal`; canales notificación v2; bump a v1.1.0) **antes** de que el manual se redactara (`ea4fe9d`, `c638996`), pero el manual nunca se actualizó. Además, algunos snippets **contradecían ADRs aceptados** (ADR-0006 conservative-wins; ADR-0003 tier T3).

La implementación real de Fase 2 siguió la autoridad correcta: el **contrato inmutable `argos_contracts` v1.1.0** (regla #2 del HANDOFF) + los ADRs. Resultado: 8/8 secciones implementadas, **166 tests** en verde, cobertura `soar` 99% (`tier_router.py` 100%).

Este ADR **formaliza la reconciliación** para que el equipo trabaje sobre una fuente de verdad única, haya coherencia total y se minimicen los cambios futuros de documentación. También fija el contrato correcto para Fase 3 (cuyos snippets en el manual tienen el mismo desfase).

## 2. Decisión

### 2.1 Fuente de verdad (jerarquía de autoridad)

Para todo lo que es SOAR, la autoridad, en orden:

1. **`argos_contracts` v1.1.0** — formas de datos. Inmutable (regla #2 HANDOFF).
2. **ADRs aceptados** (0003, 0005, 0006, 0007 v2, 0009, 0010 y este 0011) — decisiones.
3. **Código real en `soar/`** — implementación verificada con tests.

Los **snippets de código de `manual-p1-enzo.md` §Fase 2-3 son ilustrativos del flujo, NO la fuente de verdad del contrato.** Quedan superseded por el código de `soar/` y por este ADR. El manual lleva un banner que lo indica.

### 2.2 Mapeo de correcciones (manual → implementación real)

| Sección | El manual decía | Real en v1.1.0 / implementado | Autoridad |
|---------|-----------------|-------------------------------|-----------|
| §2.1 | `from argos_contracts.incident import NormalizedEvent`; `event.severity/mitre_technique/num_layers_fired/confidence_score` | `NormalizedEvent` **no existe**. El router consume un `RoutingSignal` (dataclass local a `soar/`) derivado de `NormalizedAlert` (`source_layer`, `severity_label`, `severity_score`, `technique_mitre`, `host_id`) | contrato `alert.py` |
| §2.1 | `AUTO_T0_TECHNIQUES` incluía `T1561` | `T1561` **no está** en `MITRE_WHITELIST` → excluida. Set final: `{T1485, T1486, T1490, T1498, T1499}` (ransomware-destrucción + DoS) | `_mitre_data.py`, ADR-0008 |
| §2.2 | `TIER_CHANNELS[T3] = []` | `T3` **sí notifica** (Telegram+Discord, sin botón) | ADR-0003 §Esquema de tiers |
| §2.3-2.5 | `incident.host.hostname`, `incident.mitre_technique/num_layers_fired/confidence_score`, id `"inc-smoke-001"` | `host.id` (HostInfo no tiene `hostname`); datos desde `incident.alert.*`; id con patrón `^INC-\d{4}-\d{2}-\d{2}-\d{3}$`. `num_layers_fired` **no se persiste** (el `Incident` guarda un `NormalizedAlert` representativo, no un conteo) | contrato `incident.py`/`triage.py` |
| §2.6 | `<Gather action="/voice/dtmf">` sin `incident` | El `incident` viaja en la action URL (`/voice/dtmf?incident=<id>`), si no el endpoint nunca lo recibe | fix de correctitud |
| §2.7 | `FinalDecision(outcome="execute"/"block", policy_applied="conservative_wins"/"two_person_approve", approved_count=…)`; `ApproverState(approver_id=…, responded_at=time.time())` | `FinalDecision` con `Literal` reales (`outcome ∈ {EXECUTE_ISOLATION, NO_ACTION, REVERTED}`, `policy_applied ∈ {auto-execute, unanimous-approve, conservative-wins, two-person-rule, timeout-escalation}`) + `rationale` obligatorio; **sin** campos `*_count`. `ApproverState` con `email`+`role` y `responded_at` datetime tz-aware | contrato `incident.py` |
| §2.7 | `conservative-wins` etiquetaba un **bloqueo** ante conflicto | `conservative-wins` = **aislar** (cualquier approve gana). El bloqueo por conflicto es de la **two-person-rule** (un reject cancela). Son políticas distintas | ADR-0006 §"Reglas concretas" |
| §2.8 | finaliza siempre con `outcome="block"`, `policy_applied="no_quorum_timeout"` | Valores inexistentes. Cierre de ventana: production-critical **no auto-ejecuta** (espera, ADR-0006 Sit.B); estándar reversible → `NO_ACTION` si hubo reject, `EXECUTE_ISOLATION`/`timeout-escalation` si nadie respondió (failsafe ADR-0003) | ADR-0006 Sit.B + ADR-0003 |
| §1.3 / §3.1 | `pip install -r soar/requirements.txt`; consumer con `NormalizedEvent`, `IncidentState.NEW`, `Incident.llm_verdict` | `soar/requirements.txt` no existe → extras de `pyproject` (`.[soar]`, `.[dev]`). Fase 3 consumer debe usar `NormalizedAlert`, estados reales del enum (no `NEW`), y `Incident.llm_analysis: TriageResponse` (no `llm_verdict`/`LLMVerdict`) | contrato + `pyproject.toml` |

### 2.3 Lógica de decisión HITL (la pieza más sensible)

Dos políticas, elegidas por contexto vía `requires_two_person(incident)`:

- **Two-person rule** — host `Criticality.PRODUCTION_CRITICAL` (la DB de IntiBank) **o** acción irreversible (ADR-0006 Situación A/B + override ADR-0003): requiere **2 aprobaciones**; **1 rechazo cancela**. Sin auto-execute por timeout (Situación B: espera al 2º aprobador).
- **Conservative-wins** — acciones reversibles en host estándar (ADR-0006 §"acciones reversibles"): **cualquier approve → `EXECUTE_ISOLATION`**, sin importar cuántos rejects; solo-reject → `NO_ACTION`; nadie responde → `EXECUTE_ISOLATION`/`timeout-escalation` (failsafe).

Mapeo a UCs: **UC-04** (ataque a la DB, 2 aprueban) → execute/two-person-rule. **UC-07** (falso positivo en la DB, alguien rechaza) → no-action/two-person-rule. **UC-03** (split-brain en host estándar) → conservative-wins.

### 2.4 SAD §6.5 — `PENDING_SECOND_APPROVAL` no está en el enum v1.1.0

El SAD §6.5 menciona el estado `PENDING_SECOND_APPROVAL`, pero el enum `IncidentState` de v1.1.0 **no lo incluye** (tiene `RECEIVED, AWAITING_APPROVAL, PENDING_EXECUTION, PENDING_REJECTION, EXECUTING, EXECUTED, REVERTED, REJECTED, TIMEOUT_ESCALATED`).

**Resolución (sin tocar el contrato inmutable):** el estado de espera del 2º aprobador (production-critical) usa **`AWAITING_APPROVAL`**. La condición "needs-escalation" (incidente esperando > 30 min, per ADR-0003 §"Edge case 3 AM") se **deriva en la UI** (Streamlit, P4) por la antigüedad del incidente en `AWAITING_APPROVAL` con `final_decision == null`, no por un estado dedicado. Agregar `PENDING_SECOND_APPROVAL` sería un cambio de contrato (futuro `argos_contracts` v1.2), fuera de scope del POC. La mención del SAD queda como aspiracional documentada acá.

### 2.5 Identidad de aprobadores

`ApproverState.email` se llena hoy con `"<canal>:<id>"` (p. ej. `telegram:42`) como identificador único. El mapeo al **roster bancario ficticio** (ADR-0009 §2.8: SOC Lead / DBA / Infra / Compliance) es refinamiento de Fase 3 (tabla canal→aprobador). No bloquea la regla de quórum, que cuenta aprobaciones/rechazos por `email` distinto.

## 3. Dependencias de Fase 3 (bloqueantes para que el HITL sea seguro)

La Fase 2 entregó los **bloques de decisión y notificación**. La **orquestación** es Fase 3, y estas piezas son condición para que el comportamiento "esperar" del production-critical sea seguro (decidido con P1 el 2026-05-30):

1. **Playbooks `soar/playbooks/process_throttle.py` + `disk_snapshot.py`** — disparan **inmediato, sin aprobación**, al clasificarse un T2/production-critical. Frenan el ataque (~25.000 → ~100-500 archivos/min) y dejan punto de recuperación. **Sin esto, la espera del production-critical está desprotegida.** Prioridad #1.
2. **Scheduler de la ventana** — APScheduler lanza `consolidation_task` por cada incidente que entra en espera (la ventana de 60s).
3. **Timer de 3 min del T2 estándar** (ADR-0003) — distinto de la ventana de 60s de consolidación (ADR-0006). El flujo completo necesita ambos.
4. **Consumer `events:normalized`** (§3.1) — adaptado a `NormalizedAlert` (no `NormalizedEvent`); construye `Incident` válido (id `INC-…`, `alert`, `host` con `criticality`, `proposed_actions`); correlaciona capas para el `RoutingSignal`.
5. **Hook LLM Triage** (§3.3) — escribe `Incident.llm_analysis: TriageResponse | None`; nunca bloquea el flujo si el LLM falla (invariante R-2).

## 4. Convención de calidad (confirmada)

- **`tier_router.py` 100%** de cobertura (pieza crítica); resto de `soar` ≥ 80% (logrado: 99% global).
- `pytest -q` verde tras cada cambio (testpaths incluye `soar/**/tests`).
- **Deuda de lint conocida y aceptada:** `ruff` marca `UP017` (`datetime.UTC`) en los archivos que usan `datetime.now(timezone.utc)`. Se mantiene `timezone.utc` por **consistencia con el repo existente** (`argos_contracts/tests` ya lo usa) y portabilidad 3.10/3.11; no se aplica `datetime.UTC` (3.11-only). El gate del proyecto es `pytest`, no `ruff`.
- **Cambios de config (no contrato, no ADR):** `pyproject.toml` ganó `testpaths` de `soar`, `coverage.source += soar`, `flake8-bugbear.extend-immutable-calls` (FastAPI `Depends`/`Form`), y `python-multipart` en extras `[soar]` (lo exige `Form()` de FastAPI).

## 5. Alternativas consideradas

| Alternativa | Veredicto |
|-------------|-----------|
| Reescribir todos los snippets del manual §Fase 2-3 con el código real | ❌ Churn masivo en un doc de 2000+ líneas; duplicar código en doc garantiza drift futuro. Mejor apuntar al código real. |
| Cambiar `argos_contracts` para matchear el manual (forma plana) | ❌ Viola inmutabilidad (regla #2) y rompe a P2/P3/P4 que ya consumen v1.1.0. |
| No documentar y seguir corrigiendo ad-hoc | ❌ Es justo la fricción que causó re-trabajo en toda la Fase 2. |
| **ADR-0011 (registro autoritativo) + banner en el manual** | ✅ Fuente única de verdad, coherencia, mínimo churn, errores corregidos formalmente. |

## 6. Consecuencias

### Positivas

- **Fuente de verdad única** para SOAR; el equipo deja de tropezar con snippets desfasados.
- Las correcciones quedan **formalizadas y auditables** (defendible ante el profesor).
- **Minimiza cambios futuros de doc**: la doc apunta al código + contrato, que son los que evolucionan con tests.
- Deja explícitas las **dependencias de Fase 3** para que el HITL sea seguro.

### Negativas

- El manual P1 §Fase 2-3 queda con snippets **ilustrativos no-ejecutables** (mitigado con banner + puntero al código real y a este ADR).
- Los HTML/PDF de los manuales quedan desfasados hasta que se regeneren (rule #4: no se regeneran salvo pedido explícito; se hará al final con el build script).

## 7. Acciones derivadas

- `docs/decisions/README.md`: agregar ADR-0011 al índice.
- `manual-p1-enzo.md`: banner "superseded by ADR-0011" en §Fase 2 y §Fase 3; fix §1.3 (`pip install -e ".[soar,dev]"`).
- `docs/contracts/CONTRACTS_SPECIFICATION.md` y SAD §6.5: revisar contra v1.1.0 en Fase 3 si se usan como referencia (posible deuda residual — fuera de scope de este ADR salvo el §6.5 ya resuelto arriba).
- **Deuda team-wide (para que todos esten al tanto):** `manual-p2-sebastian.md` usa `NormalizedEvent` y `llm_verdict` (real: `NormalizedAlert` + `Incident.llm_analysis: TriageResponse`) — afecta el trabajo ML/LLM de P2. `num_layers_fired` aparece en los manuales p2/p3/p4 y en ADR-0009, pero es **conceptual** (que capas disparan por UC, no un campo del contrato; lo computa el `RoutingSignal`) — no requiere correccion. `docs/contracts/CONTRACTS_SPECIFICATION.md` **no existe** (referencia muerta en el manual §3.1). Banner por owner queda a criterio de P1/equipo.

## 8. Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 | 2026-05-30 | Initial — reconcilia manual P1 §Fase 2-3 con `argos_contracts` v1.1.0 + ADRs tras implementar Fase 2; resuelve SAD §6.5; fija dependencias de Fase 3. | P1 |
