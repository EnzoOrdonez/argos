# ADR-0013 — Orquestación SOAR Fase 3: consumer, correlación, scheduler, LLM hook, audit

| Campo | Valor |
|-------|-------|
| Status | ✅ Accepted · 2026-06-10 (review P1 con correcciones, ver §7; Proposed desde 2026-05-30) |
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

## 7. Review P1 (2026-06-10): correcciones al diseño

Review contra contrato v1.1.0, ADR-0009 y el código de Fase 2. Estas correcciones mandan sobre el texto de arriba donde difieran; el histórico queda intacto como registro del borrador.

1. **§2.1, `layer_origin` no existe.** El campo del contrato es `source_layer` y el enum `Layer` v1.1.0 solo define `layer_1|layer_2|layer_3`. La Capa 4 (LLM) no emite `NormalizedAlert`: es enriquecimiento (invariante R-2), no detección. P2 publica al stream únicamente alertas ML (`layer_2`).
2. **Formato de entry del stream (faltaba fijarlo):** cada entry de `events:normalized` lleva un campo `payload` con `NormalizedAlert.model_dump_json()`. Es el contrato operativo para P2/P3.
3. **§2.2, la ventana fija de 5s se reemplaza por dos índices.** `corr:{host_id}` con TTL 5s deslizante (agrupa la ráfaga; cada alerta del host refresca el TTL) + `corr:open:{host_id}` apuntando al incidente sin `final_decision` (se borra al decidir; TTL de seguridad 600s). Lookup: `corr` → `corr:open` → crear incidente. Una alerta tardía (al segundo 6, o al 90) enriquece y re-rutea mientras el incidente siga sin decidir; si ya se decidió, se anexa al audit y a la vista de capas sin re-ejecutar ni re-notificar. Motivo: con 5s fija, la alerta del segundo 6 creaba un incidente duplicado y la re-notificación por escalación quedaba inútil frente al timer de 3 min del T2.
4. **§2.3, el inventario no va por rango `10.10.50.x`.** ADR-0009 §2.7 define `10.10.50.0/24` como servidores de aplicación (red ficticia para reglas Sigma sobre `ip_address`), no el host DB. La criticidad se resuelve por `host_id` en `soar/inventory.py`: `LIN-VICTIM-01` (10.0.0.22, host PostgreSQL per OPEN_QUESTIONS Q2 y `.env`) y `LIN-DB-01` (alias que usa el conftest de Fase 2) son `PRODUCTION_CRITICAL`; `WIN-VICTIM-01` y `LAB-MANAGER` son `STANDARD`; host desconocido cae a `STANDARD`. Deuda con P4: unificar el nombre canónico del host DB.
5. **§2.5, gate del hook LLM corregido a "espera humana":** llama a `/triage` cuando `tier == T2` **o** `requires_two_person(incident)` (production-critical), excluyendo `T1498/T1499` (ADR-0009 §2.6). Motivo: UC-04 rutea T1 (L1+L2 corroboradas) sobre host crítico y ahí el LLM es "decisivo" per ADR-0009 §2.6; el gate "solo T2" lo dejaba sin contexto.
6. **§2.6, asyncio puro en lugar de APScheduler**, consistente con `consolidation_task` de Fase 2 (los jobs son efímeros en memoria igual; tests deterministas con sleep inyectable). Y son **tres** relojes, no uno: (A) consolidación de 60s desde el **primer voto** (ADR-0006), poblando `Incident.consolidation_window`; (B) timeout T2 de 180s desde la notificación (ADR-0003): cero votos en host estándar cierra con `timeout-escalation`, cero votos en production-critical sigue esperando (Sit.B), y con votos el timer no actúa porque la ventana manda; (C) escalación Twilio a t=60s sin respuesta (ADR-0007 v2, `escalate_to_voice` ya existe).
7. **XACK y poison guard:** una entry que falla queda sin ACK y se reintenta; a la tercera delivery (XPENDING) se ACKea y se registra `poison_discarded` en el audit, para que un mensaje malformado no cicle infinito.
8. **Contador diario** `incident:counter:{YYYY-MM-DD}` con EXPIRE 48h para no acumular claves.
9. **Botones de aprobación por espera humana, no por tier:** el canal Telegram muestra Approve/Reject cuando el incidente espera humano (T2 o two-person), no solo en T2. UC-04 es T1 + crítico y necesita botones.
10. **`corroboration_confidence` = noisy-OR** de los `severity_score` de las capas que dispararon (`1 - prod(1 - s_i)`), documentado en el consumer. Con L1=0.85 y L2=0.90 da 0.985 ≥ 0.80, así UC-04 rutea T1 como espera el demo.

## 8. Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 (Proposed) | 2026-05-30 | Initial — diseño del orquestador Fase 3: consumer + correlación incremental por host, construcción de Incident (INC-id, criticidad por inventario), acciones inmediatas, hook LLM no-bloqueante, scheduler, contención, audit dual con Literals reales. Pendiente review de P1. | P1 |
| 1.1 (Accepted) | 2026-06-10 | Review P1 con 10 correcciones (§7): source_layer sin capa LLM, formato de entry, correlación con dos índices, inventario por host_id, gate LLM T2 ∪ two-person, asyncio + tres relojes, poison guard, EXPIRE del contador, botones por espera humana, noisy-OR. Status a Accepted. | P1 |
