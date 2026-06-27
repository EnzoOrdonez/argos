# ADR-0015 — Prototipo real: active-response, topología Wazuh manager-only + VM Windows, y conmutación simulado ↔ real

| Campo | Valor |
|-------|-------|
| Status | ✅ Accepted · 2026-06-24 |
| Deciders | P1 (Enzo). Toca a P2 (bridge/ML publisher), P3 (scripts AR + reglas), P4 (compose/Wazuh/VM). |
| Related | ADR-0010 (demo ideal/mínimo + backup narrative), ADR-0012 (ResponseExecutor + playbooks), ADR-0014 (spec del bridge), `argos_contracts` v1.1.0 (inmutable), `soar/playbooks/wazuh.py` |

---

## 1. Contexto

Hoy ARGOS corre **todo en una PC, simulado**: `scripts/demo_injector.py` publica `NormalizedAlert` al stream y `SimulatedExecutor` finge la contención. El objetivo del proyecto es **ver el ataque en una red real**. Quedan dos blockers de código (el **bridge** ADR-0014 y los **scripts active-response**) y el **entorno** (lab). Restricciones reales: una laptop de **16 GB**, y una **VM Windows 10 en VirtualBox** ya disponible.

Se decide un esquema de **dos caminos**: un **VIDEO garantizado** (simulado, sin código nuevo — ADR-0010 backup narrative) y un **PROTOTIPO REAL** como upgrade por fases.

## 2. Decisión

### 2.1 Dual-path con swap de bordes (el SOAR no cambia)
El cerebro (`soar/`) y el contrato no se tocan. Se conmuta por entorno:
- **Feeder:** `demo_injector` (simulado) ↔ **bridge** (real).
- **Executor:** `SimulatedExecutor` ↔ `WazuhActiveResponseExecutor` (`ARGOS_EXECUTOR=simulated|wazuh`).

Esto ya es posible por la abstracción `ResponseExecutor` (ADR-0012) y el injector dual-track.

### 2.2 Bridge (realiza ADR-0014)
Servicio nuevo que **tailea `alerts.json` del Wazuh manager** y por cada alerta del proyecto publica un `NormalizedAlert`:
- `group` → `source_layer` (`argos_layer1`→L1, `argos_layer3`→L3).
- `technique_mitre` desde `detection/mitre-mapping.yaml` (respeta el whitelist).
- `severity_score` = fórmula `rule.level` (0–15)→(0.0–1.0); canary 12-13 → ≥0.95.
- `host_id` del agente. Publica `XADD events:normalized * payload <json>`. Fail-soft ante rotación/líneas parciales.
- **+ publisher ML:** `ml.soar_adapter` ya arma el `NormalizedAlert`; solo se le suma el `XADD`.

### 2.3 Active-response
Scripts `argos-{isolate,throttle,snapshot,kill}` (+ reverts `argos-{unisolate,unthrottle}`) en el agente + bloques `<command>`/`<active-response>` en el `ossec.conf` del manager. El `WazuhActiveResponseExecutor` ya los invoca por nombre (`soar/playbooks/wazuh.py`). Implementados en `active-response/` para los **dos OS del lab** (Windows + Linux; ver Enmienda 2026-06-26 al pie):
- **Linux (víctimas Debian — bash):** `iptables -I/-D` para aislar, `kill -9`/`pkill` para kill, `tar` para snapshot, `renice`+`ionice`+`cpulimit` para throttle. FIM/whodata vía `auditd`.
- **Windows (endpoint — PowerShell):** `netsh advfirewall` para aislar, `Stop-Process` para kill, `Copy-Item` para snapshot, `PriorityClass` para throttle.
- **REGLA CRÍTICA (ambos OS):** `argos-isolate` **debe whitelistear la IP del manager (puertos 1514/1515) ANTES del block-all**; si corta TODA la red, mata el canal agente↔manager y el manager no puede revertir ni confirmar (auto-brick). Si falta la IP del manager, el script **aborta** en vez de aislar a ciegas.

### 2.4 Topología — dos perfiles de despliegue

El indexer y el dashboard **sí son parte de un Wazuh real y deben estar en el prototipo final**. El "manager-only" es una restricción de **RAM**, no de arquitectura.

**Perfil A — "demo-lite" (una laptop de 16 GB, todo + la VM encima).** Wazuh **manager-only** (sin indexer ni dashboard). ARGOS tailea `alerts.json` y tiene su propia consola (Streamlit) + audit, así que el indexer no es necesario para el end-to-end y es justo lo que consume la RAM (el stack completo pide ≥6 GB y no entra cómodo con la VM Windows de ~4.8 GB + el host Windows en 16 GB). Servicios en Docker: `wazuh-manager`, `redis`, `soar`, `bridge`, `ml`, `llm-triage`, `console`. Víctima = VM Windows 10 (VirtualBox, red host-only): host (servicios + atacante) y VM (víctima) = dos nodos en una red real sobre una sola PC.

**Perfil B — "full" (prototipo final, distribuido o con más RAM).** Wazuh **completo: manager + indexer + dashboard** — el despliegue fiel de un SIEM/XDR real, y **es lo que el prototipo final debe tener** (el indexer almacena/busca alertas; el dashboard es la UI nativa de Wazuh). No entra en una sola laptop de 16 GB junto con las VMs víctima, así que el perfil full **requiere distribuir entre máquinas del equipo**: una caja para el stack Wazuh (manager+indexer+dashboard, ≥8 GB), las víctimas en máquinas/VMs aparte, los servicios ARGOS en otra. Coincide con el objetivo "ver el ataque entre PCs". Pasar de A→B = sumar los servicios `wazuh-indexer` + `wazuh-dashboard` al compose y repartir por IP; el resto no cambia.

### 2.5 Víctimas y alcance por fases

El activo que ARGOS protege es la **data sensible del banco (PII)**, que en la realidad vive en un **server Linux (Debian) con PostgreSQL** — ese es el host **production-critical** (el que dispara la two-person rule, ADR-0006/0009). Las víctimas no son intercambiables:
- **DB server Debian + PostgreSQL** = el activo crítico, blanco de UC-04 (ataque a la DB), UC-07 (SELECT masivo) y UC-08 (SQLi). Es el victim **central**, no un bonus.
- **Endpoint Windows 10** = la estación de trabajo, blanco de UC-01 (ransomware vssadmin/wmic), UC-02 (canary) y UC-05 (agent-kill).

Fases (el orden es pragmático por lo que ya existe, no por importancia):
- **Fase A (comprometida):** video simulado (cero código nuevo; no usa Wazuh).
- **Fase B (prototipo real, parte 1):** la **VM Windows 10** que ya tenés, como endpoint — ransomware, canary, agent-kill reales.
- **Fase C (prototipo real, parte 2):** el **DB server Debian + PostgreSQL/pgAudit** como host production-critical — UC-04/07/08 reales. Cierra la narrativa del banco; se hace apenas la Fase B esté estable.

### 2.6 Snapshot demo-safe
Copia/tar del dir del canary, **no** VSS real (ADR-0012).

## 3. Alternativas consideradas

| Alternativa | Veredicto |
|-------------|-----------|
| Wazuh full stack (manager+indexer+dashboard) | ❌ ~6 GB+, no entra cómodo con la VM en 16 GB, y ARGOS no usa el indexer. |
| Un contenedor por persona (5 dockers) | ❌ Los contenedores siguen la arquitectura, no el organigrama. |
| Bridge vía `integrator` de Wazuh | 🟡 Más nativo pero más config; tail de `alerts.json` es más simple/robusto para el demo. |
| Solo simulado (sin prototipo real) | ❌ No cumple el objetivo del proyecto. Se mantiene como Fase A garantizada, no como único modo. |

## 4. Consecuencias

**Positivas:** el SOAR y el contrato no se tocan (swap por env); el video queda garantizado sin código nuevo; la VM Windows da el UC estrella (ransomware) real + el "ataque entre máquinas" en una sola laptop.

**Negativas:** el prototipo real son varias piezas a 3 días (bridge + AR + config Wazuh + red de la VM) → por eso es Fase B/C, no la apuesta única. RAM al límite (mitigado con manager-only). `argos-isolate` mal hecho se auto-brickea (mitigado con whitelist del manager).

## 5. Verificación

- **Fase A:** el stack simulado corre end-to-end y el video queda grabado.
- **Fase B:** la VM Windows enrolada al manager; un ataque real dispara alerta → bridge → SOAR → aprobación (Telegram real) → `argos-isolate` aísla la VM **sin perder el agente** → audit lo registra. El swap simulado↔real queda documentado en el runbook.

---

## Enmienda (2026-06-26) — OS y topología del lab confirmados

El equipo confirmó el lab real: **3 VMs corriendo a la vez** (Diego las hostea y ejecuta el ataque),
con **dos sistemas operativos**. Esto enmienda §2.3 y §2.4 (Status sigue **Accepted**):

- **§2.3 — active-response es Windows *y* Linux** (no solo Windows). Los scripts viven en
  `active-response/{linux,windows}/`: bash (`iptables`/`kill`/`tar`/`renice`) para las víctimas Linux,
  PowerShell (`netsh`/`Stop-Process`/`Copy-Item`/`PriorityClass`) para la víctima Windows. La regla
  crítica del whitelist del manager (1514/1515 antes del block-all) aplica a los dos.
- **§2.4 — topología de 3 VMs** (en vez de "una laptop de 16 GB + 1 VM Windows"):
  1. **Core** — 1 VM **Linux**: Wazuh manager + los servicios ARGOS (`redis`, `soar`, `bridge`, `ml`,
     `llm-triage`, `console`).
  2. **Víctima endpoint** — 1 VM **Windows**: ransomware (UC-01), canary (UC-02), agent-kill (UC-05).
  3. **Víctima crítica** — 1 VM **Linux Debian + PostgreSQL** (production-critical): ataque a la DB
     (UC-04), SELECT masivo (UC-07), SQLi (UC-08).

  Sigue siendo el Perfil A (manager-only por RAM); el indexer/dashboard (Perfil B) quedan para el
  prototipo final distribuido. Coherente con la canary (`deception/wazuh-rules/canary_rules.xml`, auditd
  + rutas `/canary/...`) y el victim production-critical Debian de §2.5.
