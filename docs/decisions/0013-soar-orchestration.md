# ADR-0013 — Orquestación SOAR Fase 3: consumer, correlación, scheduler, LLM hook, audit

| Campo | Valor |
|-------|-------|
| Status | 🟡 Proposed · 2026-05-30 (pendiente review P1 antes de implementar) |
| Deciders | P1 (Enzo) — toca a P2 (LLM Triage), P3 (alertas en `events:normalized`), P4 (audit DB/OpenSearch) |
| Related | `argos_contracts` v1.1.0, ADR-0003/0006/0011 (decisión), ADR-0012 (playbooks), ADR-0009 §2.6 (matriz capa×UC), SAD §6.5/§7, OPEN_QUESTIONS Q4 (schema Incident) |
| Doc-first | Se documenta el diseño del orquestador **antes** de implementar (`soar/decision_engine/consumer.py` + hook + audit), para cerrar la doc de Fase 3 y no re-tocarla. |

---

## 1. Contexto

La Fase 2 entregó los bloques: tier router (§2.1), notificación (§2.2-2.5), HITL/consolidación (§2.6-2.8). ADR-0012 fijó los playbooks. Falta el **orquestador** que conecta todo end-to-end: el **consumer** del stream `events:normalized`, el **hook** al LLM Triage, y el **audit**.

El `manual §3.1-3.4` describe esto pero con los **mismos desfases de contrato** que ADR-0011 corrigió: usa `NormalizedEvent`, `IncidentState.NEW`, `Incident.llm_verdict`, y un modelo **"un evento = un incidente"** con `num_layers_fired` pre-cocido. Eso es incorrecto en v1.1.0: el stream lleva `NormalizedAlert` **por capa** (una alerta por cada capa que dispara), y el `tier_router` (§2.1) necesita `fired_layers` — que **no viene en una sola alerta**. Por lo tanto el orquestador debe **correlacionar** varias alertas del mismo host en un incidente. Este ADR diseña eso.

## 2. Decisión

### 2.1 Pipeline del consumer (orden de operaciones)

```
events:normalized (Redis Stream, grupo "soar-router")
   │  cada entry = un NormalizedAlert (layer_origin=sigma|ml|canary|llm)
   ▼
1. correlacionar por host_id dentro de una ventana corta  → RoutingSignal
2. route(RoutingSignal) → Tier                            (§2.1, ADR-0003/SAD §6.2)
3. construir/actualizar Incident (id INC-…, host+criticidad, alert representativo)
4. si T2/production-critical: disparar throttle+snapshot YA (ADR-0012, pre-aprobación)
5. si tier ∈ {T2}: hook LLM Triage → Incident.llm_analysis (no bloqueante, R-2)
6. dispatch_for_tier(incident) → notificaciones (§2.2-2.5)
7. si requiere espera humana: lanzar consolidation_task (scheduler, §2.8)
8. al resolverse FinalDecision=EXECUTE_ISOLATION: correr playbook contención (ADR-0012)
9. audit de cada paso (OpenSearch + Postgres)
   └─ XACK al stream sólo si el procesamiento no lanzó (si lanza, la entry se reintenta)
```

### 2.2 Correlación de alertas → `RoutingSignal` (la decisión clave)

El stream lleva una `NormalizedAlert` por capa. El orquestador agrupa por **`host_id`** dentro de una **ventana de correlación corta** (`CORRELATION_WINDOW_SECONDS`, propuesto **5s**) y produce **un** `RoutingSignal` con `fired_layers` = el conjunto de capas que alertaron sobre ese host en la ventana.

Modelo elegido — **enriquecimiento incremental** (streaming, estándar SIEM/XDR):
- Llega una alerta para `host_id`:
  - Si **no hay incidente abierto** para ese host dentro de la ventana → **crear** Incident con `RoutingSignal` de 1 capa.
  - Si **ya hay** uno abierto (creado < ventana, sin `final_decision`) → **enriquecer**: agregar `source_layer` a `fired_layers`, actualizar `corroboration_confidence` (combinación de los `severity_score`), **re-rutear** con `route()`. Si el tier **escala** (p. ej. L1-sola T2 → L1+L2 T1, o aparece canary → T0), actualizar el Incident y mandar notificación de escalación.
- **Fast-path sin esperar correlación** (ADR-0011 §2.2 / SAD §6.2): si la alerta es de **Capa 3 (canary)** o trae una **técnica AUTO_T0** (`T1485/86/90/1498/99`) → el `tier_router` ya devuelve T0; se procesa inmediato sin esperar la ventana (no hay ambigüedad que correlacionar).

Estado de correlación: un índice `corr:{host_id}` en Redis con TTL = ventana, apuntando al `incident_id` abierto. Esto evita un buffer en memoria que se pierda si el consumer reinicia.

### 2.3 Construcción del `Incident`

- **`incident_id`:** patrón `INC-YYYY-MM-DD-NNN` con contador **diario** vía `INCR incident:counter:{YYYY-MM-DD}` en Redis (SAD §6.5 / OPEN_QUESTIONS Q4.1).
- **`host` + `criticality`:** la `NormalizedAlert` trae `host_id`, no criticidad. El orquestador resuelve la criticidad con un **inventario estático** (`soar/inventory.py` o config): los hosts de la **DB IntiBank** (la Linux VM con PostgreSQL, IPs `10.10.50.x` per ADR-0009 §2.7) = `PRODUCTION_CRITICAL`; el resto = `STANDARD`. Esto alimenta `requires_two_person` (§2.7). Alternativa: leer el label `criticality` del agente Wazuh si P3 lo expone en `raw_data` (preferible a futuro).
- **`alert`:** el `NormalizedAlert` **representativo** (el de mayor `severity_score`, o el primero). El detalle multi-capa vive en el `RoutingSignal` (no se persiste un conteo, per ADR-0011).
- **`proposed_actions`:** se arman según el tier/decisión (ADR-0012 `build_*`).
- **`created_at`/`updated_at`:** tz-aware; **`state`** inicial `RECEIVED` → `AWAITING_APPROVAL` si requiere humano.

### 2.4 Acciones protectoras inmediatas

Si el incidente es T2 / production-critical, el orquestador dispara **throttle + snapshot** (ADR-0012, vía `ResponseExecutor`) **antes** de notificar y antes de cualquier espera. Es lo que acota el daño durante la ventana (ADR-0006 Sit.B / ADR-0011 §3).

### 2.5 Hook al LLM Triage (Layer 4 de P2)

- Sólo para **T2** (donde el contexto ayuda a la decisión humana; ADR-0009 §2.6: el LLM **no** aplica a DDoS).
- El orquestador arma un `AlertContext` (contrato `triage.py`: `incident_id`, `created_at`, `host: HostInfo`, `alert_summary: AlertSummary`, `recent_telemetry`) y llama al servicio de P2 (`POST /triage`).
- Respuesta = `TriageResponse` → se guarda en **`Incident.llm_analysis`** (no `llm_verdict`).
- **No bloqueante (invariante R-2):** si el LLM falla/timeout/cae → `llm_analysis = None` y el flujo sigue. El LLM **nunca** está en el camino crítico de contención (el tier ya se decidió con Capas 1-3).

### 2.6 Scheduler de la ventana de consolidación

Por cada incidente que entra en espera humana (T2 / production-critical), el orquestador **lanza `consolidation_task`** (§2.8) con **APScheduler** (en `soar/README` stack). Es lo que materializa los 60s (ADR-0006) y, en su caso, el failsafe / la espera de Sit.B.

### 2.7 Contención al resolverse la decisión

Cuando `build_final_decision_if_ready` o `close_window` fijan `FinalDecision = EXECUTE_ISOLATION`, el orquestador corre el **playbook de contención** (isolation + kill, ADR-0012) vía `ResponseExecutor` y escribe `FinalDecision.execution_status` + `executed_at`. `NO_ACTION` → no corre playbook (throttle/snapshot se revierten). `REVERTED` → un-isolate.

### 2.8 Audit

- **OpenSearch `argos-audit-decisions`** (primario, SAD §6.5 + ADR-0006): timeline completo por incidente (alertas, responses, conflicto, política, decisión final, ejecución).
- **PostgreSQL** (`audit_incidents` / `audit_responses`, lo arma P4): vista SQL para el demo. **Con los valores reales del contrato** (`final_outcome ∈ {EXECUTE_ISOLATION, NO_ACTION, REVERTED}`, `final_policy ∈ {two-person-rule, conservative-wins, …}`) — NO los `"execute"/"block"` del manual.
- Audit es **fail-soft**: si un sink cae, se loguea y el flujo sigue (no se pierde la contención por un fallo de auditoría).

## 3. Dependencias cross-team

- **P2:** expone `POST /triage` que acepta `AlertContext` y devuelve `TriageResponse`; y emite alertas ML/LLM a `events:normalized` como `NormalizedAlert` (no `NormalizedEvent`).
- **P3:** emite alertas Sigma/Canary a `events:normalized` como `NormalizedAlert` con `source_layer` correcto; idealmente expone `criticality` del host.
- **P4:** crea las tablas `audit_incidents`/`audit_responses` (con los Literals reales) + el índice OpenSearch.

## 4. Scope POC / demo

- Consumer + correlación + scheduler + hook + audit: implementables y **testeables sin lab** (fakeredis para el stream/estado, `respx` para el `/triage` de P2, `SimulatedExecutor` para playbooks).
- El end-to-end real (UC-01..UC-08) se valida en el lab de P4 con todos los servicios.
- Correlación: la ventana de 5s es suficiente para los ataques scripted del demo (las capas disparan casi simultáneas).

## 5. Alternativas consideradas

| Alternativa | Veredicto |
|-------------|-----------|
| **Un evento = un incidente** (modelo del manual) | ❌ Imposible en v1.1.0: una `NormalizedAlert` es de una sola capa; el `tier_router` necesita `fired_layers`. Sin correlación no hay fusión multi-capa (SAD §6.2). |
| **Buffer en memoria** para correlacionar | ❌ Se pierde si el consumer reinicia; rompe el "estado en Redis" del diseño. |
| **Ventana larga (30-60s)** de correlación | ❌ Demasiada latencia para ransomware; el fast-path de canary/AUTO_T0 ya evita esperar en los casos sin ambigüedad. |
| **Enriquecimiento incremental con índice `corr:{host}` en Redis (TTL=ventana) + fast-path** | ✅ Estándar streaming, sobrevive reinicios, baja latencia, fusión multi-capa correcta. |

## 6. Consecuencias

### Positivas
- Cierra el end-to-end de Fase 3 sobre el contrato v1.1.0, **testeable sin lab**.
- La correlación hace que la fusión multi-capa del `tier_router` (§2.1) funcione de verdad (no con un conteo ficticio).
- Audit con los Literals reales → coherente con ADR-0011, defendible ante el profesor.

### Negativas
- El enriquecimiento incremental + re-ruteo + notificación de escalación agrega complejidad (re-notificar cuando el tier sube). Mitigable: para el demo, los ataques scripted disparan las capas casi juntas, así que el caso común es 1 sola construcción de incidente.
- Dependencia en P2 (`/triage`) y P4 (audit). Mitigado: el hook es no-bloqueante y el audit fail-soft, así que P1 no se bloquea si esos servicios no están.

## 7. Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 (Proposed) | 2026-05-30 | Initial — diseño del orquestador Fase 3: consumer + correlación incremental por host, construcción de Incident (INC-id, criticidad por inventario), acciones inmediatas, hook LLM no-bloqueante, scheduler, contención, audit dual con Literals reales. Pendiente review de P1. | P1 |
