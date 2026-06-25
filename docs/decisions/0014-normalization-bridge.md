# ADR-0014 — Bridge de normalización: alertas Wazuh / scores ML → `NormalizedAlert` en `events:normalized`

| Campo | Valor |
|-------|-------|
| Status | 🟡 Proposed · 2026-06-24 (auditoría post-merge P1/P2/P3) |
| Deciders | P1 (Enzo) **propone**; dueño de implementación: **P2** (publisher) + **P4** (fuente Wazuh del lab). **NO P1, NO el integrante nuevo.** |
| Related | ADR-0013 §3 (P1 solo consume, no normaliza crudo), `argos_contracts` v1.1.0 (`NormalizedAlert` en `alert.py`, inmutable), `manual-p2-sebastian.md` §3.1 (bridge `events:raw_wazuh`→`events:normalized`, diseño previo), `detection/mitre-mapping.yaml` (P3, L1), `deception/wazuh-rules/canary_rules.xml` (P3, L3), `ml/soar_adapter.py` (P2/ML, L2) |

---

## 1. Contexto

La auditoría del 2026-06-24 (tras mergear ML/Layer-2 y detección/decepción de P3) encontró el **hueco de integración #1**: **ninguna capa publica un `NormalizedAlert` en `events:normalized` en código.**

- **L2 (ML):** `ml/soar_adapter.py` **construye** un `NormalizedAlert` correcto (`source_layer=LAYER_2`, `process_info`, etc.), pero nadie lo **publica** al stream. Solo se ejercita en `ml/demo/` y tests.
- **L1 (Sigma) y L3 (canary):** `detection/` y `deception/` solo entregan reglas Wazuh. No hay código que lea las alertas Wazuh y emita `NormalizedAlert`. Asumen un "bridge" que solo existía en el diagrama de red (`tail alerts.json → Redis XADD`).

Además había un **choque de diseño**: comentarios de `canary_rules.xml` y `deception/README.md` decían que *"el Decision Engine (`soar/`) construye el `NormalizedAlert`"*. Eso contradice **ADR-0013 §3** (P1 **solo consume**, no normaliza crudo). Este ADR cierra esa contradicción y fija quién y cómo construye el `NormalizedAlert`.

## 2. Decisión

### 2.1 Existe un componente normalizador (bridge), separado del SOAR

El SOAR (P1) **no** se toca: sigue leyendo `NormalizedAlert` de `events:normalized` (ADR-0013 §3). El bridge es un componente aparte cuyo dueño es **P2** (con P4 exponiendo la fuente Wazuh del lab). El bridge tiene dos caminos:

**Camino A — Wazuh → NormalizedAlert (L1 Sigma + L3 canary).** Un proceso lee las alertas del Wazuh manager (`alerts.json` o el stream `events:raw_wazuh`) y, por cada alerta del proyecto, construye un `NormalizedAlert` y lo publica:

- `source_layer`: del `group` de la regla (`argos_layer1` → `LAYER_1`, `argos_layer3` → `LAYER_3`).
- `technique_mitre`: vía `detection/mitre-mapping.yaml` (la **autoridad** del mapeo regla→técnica), **no** el tag crudo del `.yml`. Solo IDs en `MITRE_WHITELIST` (ver ADR sobre T1213 abajo).
- `severity_score`: fórmula `rule.level` Wazuh (0–15) → `0.0–1.0`. Para canary L3, level 12/13 → `>= 0.95` (zero-FP, ADR-0003). **La fórmula vive aquí, no en `soar/`.**
- `host_id`: del `agent_name`/inventario; `process_info`/`file_info` desde los campos `audit.*`/`syscheck.*`.

**Camino B — ML score → NormalizedAlert (L2).** Un publisher delgado toma la salida de `ml.soar_adapter.ml_score_to_normalized_alert()` (que ya produce el objeto correcto) y solo hace el `XADD`. No hay que reescribir nada del adapter; falta únicamente el paso de publicación.

### 2.2 Formato del entry del stream (autoridad: el consumer de P1)

Cada entry de `events:normalized` lleva **un campo llamado `payload`** con `NormalizedAlert.model_dump_json()`:

```python
await r.xadd("events:normalized", {"payload": alert.model_dump_json()})
```

> ⚠️ **Corrección de coherencia.** El consumer de P1 lee `fields["payload"]` (`soar/decision_engine/consumer.py`), y `scripts/demo_injector.py` publica con `payload`. Pero `manual-p2-sebastian.md` §3.1 usa `{"data": ...}` — **está mal**: con `data` el consumer revienta con `KeyError: 'payload'` y la alerta nunca se procesa. El nombre de campo correcto es **`payload`**. Hay que corregir ese snippet del manual de P2.

### 2.3 Lo que el bridge NO hace

- **No fija criticality.** La criticidad del host la resuelve el consumer de P1 por `soar/inventory.py` (ADR-0013). El bridge solo pone `host_id`.
- **No correlaciona.** La correlación por host (ventana 5s, noisy-OR, fast-path) es del consumer de P1. El bridge emite una alerta por evento.

## 3. La técnica T1213 (relacionado, ya corregido)

`detection/mitre-mapping.yaml` mapeaba `T1213` ("Data from Information Repositories"), que **no** está en `MITRE_WHITELIST` v1.1.0 (contrato congelado). Esto rompía `detection/tests/test_mitre_mapping.py`. Fix aplicado: el mapeo contract-facing usa la técnica de Collection más cercana del whitelist, **`T1005`** ("Data from Local System"); el tag `attack.t1213` del `.yml` se conserva como referencia ATT&CK. El bridge debe tomar la técnica de `mitre-mapping.yaml`, no del tag crudo, justamente para no emitir un ID fuera del whitelist (que el validador de `TriageResponse` rechazaría).

## 4. Alternativas consideradas

| Alternativa | Veredicto |
|-------------|-----------|
| P1 normaliza el crudo Wazuh dentro de `soar/` | ❌ Contradice ADR-0013 §3; acopla el SOAR a los formatos de Wazuh; ensucia el consumer. |
| Cada capa publica su propio `NormalizedAlert` en su propio proceso | 🟡 Viable para L2 (ML ya está en Python). Para L1/L3 igual hay que leer Wazuh, así que conviene un bridge único que cubra ambos. |
| Bridge único (este ADR) | ✅ P1 intacto, contrato intacto, una sola pieza que lee Wazuh + publica ML, dueño claro (P2/P4). |

## 5. Consecuencias

- **Positivo:** destraba el end-to-end (hoy solo `demo_injector` alimenta el stream); P1 y el contrato no se tocan; el dueño queda explícito (P2/P4, no P1 ni el nuevo).
- **Negativo / pendiente:** es trabajo nuevo de P2/P4 que aún no existe. Mientras no esté, la demo real depende del `SimulatedExecutor` + `demo_injector` (que ya funcionan). Es el bloqueante #1 para que las capas L1/L2/L3 lleguen de verdad al SOAR.
- **Dependencia hermana:** los comandos Wazuh active-response (`argos-throttle/-snapshot/-isolate/-kill` que invoca `soar/playbooks/wazuh.py`) tampoco existen aún — son de P3 (ADR-0012 §3). Sin ellos solo corre el `SimulatedExecutor`. No es parte de este ADR pero bloquea el mismo end-to-end.
