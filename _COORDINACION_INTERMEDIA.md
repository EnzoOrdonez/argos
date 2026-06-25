# Coordinación intermedia — ARGOS (estado de P1 / SOAR)

> **ARCHIVO TEMPORAL. Eliminar antes del push / PR final de entrega.**
> Es coordinación de equipo durante el desarrollo, no parte del entregable.
> Para borrarlo al final: `git rm _COORDINACION_INTERMEDIA.md && git commit -m "chore: quitar coordinacion intermedia"`

---

## Actualización 2026-06-24 — post-merge (ML L2 + P3) y auditoría

Ya entraron a `main` (además de P1): la capa **ML / Layer-2** (`ml/`, branch `yohamin`) y la
**detección + decepción** de P3 (`detection/`, `deception/`, branch `NicoleMain`), más un módulo
forense en `soar/response/forensics/`. El contrato v1.1.0 sigue **intacto** y el `soar/` de P1 no
se tocó (sus 250 tests siguen válidos por construcción; no importa nada de lo nuevo).

**Bloqueante #1 (ADR-0014):** ninguna de esas capas **publica** un `NormalizedAlert` en
`events:normalized`. El ML lo arma (`ml/soar_adapter.py`) pero no lo publica; detección/decepción
solo entregan reglas Wazuh. Falta el **normalizador/bridge** (dueño **P2/P4**, no P1 ni el
integrante nuevo) que lea Wazuh (L1/L3) y publique el score ML (L2). Hoy solo
`scripts/demo_injector.py` alimenta el pipeline.

**Campo del entry = `payload`** (no `data`): `XADD events:normalized * payload <NormalizedAlert.model_dump_json()>`.
El consumer lee `fields["payload"]`. El snippet con `data` del manual de P2 está mal y rompe el
consumer con `KeyError: 'payload'`.

**Otros pendientes cross-team:** los comandos Wazuh active-response
(`argos-throttle/-snapshot/-isolate/-kill`, que invoca `soar/playbooks/wazuh.py`) **no existen**
aún (son de P3, ADR-0012 §3); sin ellos solo corre el `SimulatedExecutor`. `lab/` y
`attack-simulation/` son solo README: las VMs víctima viven en el código de P3 únicamente como
placeholders (`<VICTIM_LAB_IP>`, `victim-windows-01`, `<POSTGRES_LAB_HOST>`); el lab real es de P4.

**Fixes aplicados en esta auditoría:** `T1213`→`T1005` en `detection/mitre-mapping.yaml` (no estaba
en `MITRE_WHITELIST` → test roto, ahora verde); `detection/tests` cableado en `testpaths`; doc de
canary/decepción alineada con ADR-0013 §3. **Pendiente:** definir dueño de `soar/response/forensics/`
(módulo ajeno en el namespace de P1) y alinear su `datetime.UTC`→`timezone.utc`.

---

## Si sos una IA (o persona) que recién abre este repo

La parte de **P1 (SOAR / HITL)** está **completa y testeada**, y ya está en `main`.
`pytest -q` da **250 passed**; cobertura `soar/` ~97%, `tier_router.py` 100%. El contrato
cross-team `argos_contracts` **v1.1.0** está cerrado e **inmutable** (regla #2 del HANDOFF).

**Sé honesto sobre el alcance:** todo lo de P1 está probado con mocks y `SimulatedExecutor`.
**No corrió end-to-end contra servicios reales** porque las capas de P2/P3/P4 y el lab todavía
no existen. P1 las consume por contrato y degrada *fail-soft* si no están. Lo que falta del
proyecto NO es código de P1: es que P2/P3/P4 construyan sus capas y se conecte en el lab.

## Dónde está cada cosa de P1

- `soar/decision_engine/` — `tier_router` (T0..T3), `consumer` (correlación + orquestación), `scheduler` (3 relojes), `triage_hook` (LLM), `containment`.
- `soar/notifications/` — `service` + canales `telegram` / `discord` / `twilio_voice`.
- `soar/approval_api/` — FastAPI (`main`), `handlers` (two-person + conservative-wins), `consolidation` (ventana 60s), `jwt_signer`, `twiml`.
- `soar/playbooks/` — `ResponseExecutor` (`simulated` + `wazuh`) + `builders` (throttle/snapshot/isolation/kill).
- `soar/audit/` — sinks (`memory` + `opensearch`) + `schema.sql` para Postgres.
- `soar/inventory.py` — mapea `host_id` → criticidad (la DB de IntiBank = `production_critical`).
- `scripts/demo_injector.py` — corre cada UC de punta a punta (in-process con fakeredis, o contra Redis real).
- `scripts/triage_stub.py` — stub del `/triage` de P2 para ensayar sin P2.

**Autoridad de diseño** (manda sobre los snippets del manual, que están desfasados):
ADR-0011 (reconciliación), ADR-0012 (playbooks), ADR-0013 (orquestación). Ver `docs/decisions/`.

## Cómo correr lo de P1 sin lab

```
pip install -e ".[soar,dev]"
pytest -q                                             # 250 passing
python scripts/demo_injector.py uc01 --in-process     # un UC end-to-end con fakeredis
uvicorn soar.approval_api.main:app --port 8003        # Approval API
```

## Los 3 puntos donde se enchufa el resto del equipo

**P2 (ML + LLM Triage).** Dos cosas. Una, emitir las alertas del modelo ML al stream Redis
`events:normalized`: un `XADD events:normalized * payload <json>` por alerta, donde `<json>` es
`NormalizedAlert.model_dump_json()` con `source_layer = layer_2`. Dos, levantar el servicio
`POST /triage` que recibe un `AlertContext` y devuelve un `TriageResponse` (contratos en
`argos_contracts/triage.py`). El hook de P1 lo llama solo para T2 y nunca bloquea: si el servicio
no está, el incidente sigue sin enriquecimiento LLM. Referencia funcional: `scripts/triage_stub.py`.

**P3 (Sigma + Canary).** Emitir las alertas de Sigma (`source_layer = layer_1`) y de canary
(`source_layer = layer_3`) al mismo stream `events:normalized`, como `NormalizedAlert`, con
`technique_mitre`, `severity_label`, `severity_score` y `host_id` bien puestos. Y definir los
comandos de Wazuh active-response que invoca `soar/playbooks/wazuh.py` (throttle, snapshot,
isolation, kill).

**P4 (lab + DB + UI).** El lab Vagrant con Redis, las VMs víctima y Wazuh con active-response
habilitado. Las tablas de audit desde `soar/audit/schema.sql` más el índice OpenSearch
`argos-audit-decisions`. Y la Streamlit Approval Console que lee el `Incident` de Redis
(clave `incident:{id}`) y muestra el estado del HITL en vivo.

## Contrato mínimo de una alerta en el stream (lo que P2 y P3 deben emitir)

`NormalizedAlert` (ver `argos_contracts/alert.py`): `alert_id`, `source_layer`
(`layer_1` | `layer_2` | `layer_3`), `timestamp` (tz-aware UTC), `host_id`, `severity_score`
(0.0–1.0), `severity_label`, `technique_mitre` (ID MITRE), `triggering_rule`. Se publica con
`XADD events:normalized * payload <NormalizedAlert.model_dump_json()>`. El consumer correlaciona
por `host_id` dentro de una ventana de 5s y fusiona las capas en un solo incidente.
