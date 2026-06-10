# ADR-0012 — Response playbooks: modelo de ejecución e interfaz

| Campo | Valor |
|-------|-------|
| Status | 🟡 Proposed · 2026-05-30 (pendiente review P1 antes de implementar) |
| Deciders | P1 (Enzo) — toca a P3 (Wazuh AR) y P4 (lab) |
| Related | ADR-0003 (tiers + reversibilidad), ADR-0006 (Sit.B throttle-and-wait), ADR-0010 §2.1 (UC-05 agent-kill), ADR-0011 §3 (dependencias Fase 3), SAD §6.3, `argos_contracts` v1.1.0 (`ActionType`, `ProposedAction`, `FinalDecision`) |
| Doc-first | Se documenta el diseño **antes** de implementar (`soar/playbooks/`) para no re-tocar doc a mitad de Fase 3. |

---

## 1. Contexto

La Fase 2 entregó **decisión** (tier router + HITL) y **notificación**. Falta la **ejecución**: los _playbooks_ que materializan la `FinalDecision` y disparan las acciones protectoras inmediatas. ADR-0011 §3 los marcó como dependencia bloqueante de Fase 3, en particular `process_throttle` + `disk_snapshot`, que son los que **vuelven segura la espera del production-critical** (ADR-0006 Situación B: el host crítico no se auto-aísla por timeout; el throttle + snapshot acotan el daño mientras se espera al 2º aprobador — decidido con P1 el 2026-05-30).

Lo que **ya está decidido** y este ADR sólo referencia:
- **Mecanismos** por OS (ADR-0003 §Reversibilidad + SAD §6.3): throttle = `cpulimit`/`ionice` (Linux) / rate-limit de Process Mitigation (Windows); snapshot = `dd` (Linux) / VSS (Windows); isolation = `iptables` / Wazuh AR / `NetFirewallRule`; kill = `SIGKILL` / `Stop-Process`.
- **Cuándo disparan** (ADR-0003 + ADR-0006 + ADR-0011 §3).
- **El contrato `argos_contracts` v1.1.0 ya soporta resultados de ejecución** (`ProposedAction.{type,target,reversible,parameters}`, `FinalDecision.{execution_status,executed_at}`). No se toca.

Lo que este ADR **decide** es el **modelo de ejecución** (cómo el SOAR actúa sobre la VM víctima) y la **interfaz** de los playbooks.

## 2. Decisión

### 2.1 Modelo de ejecución — `ResponseExecutor` (abstracción) + Wazuh active-response

El SOAR **no ejecuta acciones directamente sobre las VMs**. Las delega a un `ResponseExecutor` (interfaz), con dos implementaciones:

1. **`WazuhActiveResponseExecutor` (real, XDR-estándar):** el SOAR ordena, el **agente Wazuh ejecuta** la acción en la VM vía active-response. Es el patrón de los XDR reales (Defender/CrowdStrike: el manager orquesta, el sensor actúa) y coincide con `manual §3.4` ("Wazuh active-response aísla el host"). Validación: lab Vagrant de P4.
2. **`SimulatedExecutor` (demo-safe):** loguea la acción que ejecutaría y marca el resultado, **sin tocar VMs**. Uso: tests del sandbox (sin lab), ensayos, y **fallback del video-backup** (ADR-0010 §2.1/§backup narrative).

Razón de la abstracción: desacopla el SOAR del mecanismo, lo hace testeable sin lab (mismo patrón que las notificaciones con `respx`), y permite conmutar real/simulado por entorno sin cambiar la lógica de decisión.

### 2.2 Catálogo de playbooks — `ActionType` × cuándo disparan

| Playbook | `ActionType` | Cuándo dispara | Destructivo | Reversible |
|----------|--------------|----------------|:-----------:|:----------:|
| `process_throttle` | `PROCESS_THROTTLE` | **Inmediato** al clasificar T2 / production-critical, **pre-aprobación** | No | Sí (quitar límite) |
| `disk_snapshot` | `DISK_SNAPSHOT` | **Inmediato** junto al throttle, pre-aprobación | No | N/A (no-op de revert) |
| `host_isolation` | `HOST_ISOLATION` | Al resolverse `EXECUTE_ISOLATION` (T0/T1 auto; T2 aprobado; two-person con quórum) | No | Sí (reconectar) |
| `process_kill` | `PROCESS_KILL` | Junto a isolation en el playbook de contención full | No (servicio se relanza) | Sí-ish |
| `audit_logger` | — (no es acción) | En **toda** acción y decisión | No | — |

`process_throttle` + `disk_snapshot` son la clave de ADR-0006 Sit.B: **disparan antes de cualquier aprobación** y acotan el daño durante la espera. Sin ellos, la espera del production-critical está desprotegida (hueco detectado y aceptado por P1).

### 2.3 Contrato e integración (no se toca v1.1.0)

- Cada playbook opera sobre una `ProposedAction` (`type`, `target` = host/proceso, `reversible`, `parameters`).
- El resultado se escribe en `FinalDecision.execution_status` ∈ `{success, failed, partial}` + `FinalDecision.executed_at`.
- El **orquestador** (Fase 3, consumer/scheduler) es quien: dispara throttle+snapshot al crear el incidente T2; y al resolverse `EXECUTE_ISOLATION`, corre el playbook de contención y actualiza `execution_status`.

### 2.4 Reversibilidad, idempotencia, fail-soft

- **REVERTED:** el botón "Revert if false alarm" (ADR-0003 T0/T1) invoca `host_isolation.revert()` → `FinalOutcome = REVERTED`.
- **Idempotencia:** re-ejecutar una acción ya aplicada es no-op (aislar un host ya aislado no falla).
- **Fail-soft:** un playbook que falla setea `execution_status = "failed"`/`"partial"` y se loguea; **nunca** tumba al orquestador (mismo principio que los canales de notificación). Un throttle que falla no bloquea la espera ni la decisión.

### 2.5 Interfaz (borrador, a confirmar en review)

```text
class ResponseExecutor(Protocol):
    def run(self, action: ProposedAction) -> ExecutionResult: ...
    def revert(self, action: ProposedAction) -> ExecutionResult: ...

# ExecutionResult: dataclass local a soar/ (no contrato): {action_id, status: Literal[success|failed|partial], detail, latency_ms}
# Playbooks = funciones puras de "qué ProposedAction construir" + el executor las corre.
#   build_throttle(host, pid) -> ProposedAction(type=PROCESS_THROTTLE, ...)
#   build_snapshot(host) -> ProposedAction(type=DISK_SNAPSHOT, ...)
#   build_isolation(host) -> ProposedAction(type=HOST_ISOLATION, reversible=True, ...)
#   build_kill(host, pid) -> ProposedAction(type=PROCESS_KILL, ...)
```

Patrón: los playbooks **construyen** la `ProposedAction` (puro, testeable) y el `ResponseExecutor` la **ejecuta** (mockeable). El SOAR nunca shell-ea directo a una VM.

## 3. Dependencias cross-team (para que todos estén al tanto)

- **P3 (Wazuh/Sigma):** define los comandos/scripts de **active-response** en Wazuh (su dominio). Sin ellos, `WazuhActiveResponseExecutor` no tiene qué invocar (sólo corre `SimulatedExecutor`).
- **P4 (lab):** habilita active-response en el lab Vagrant + expone las VMs víctima (Win/Linux) con el agente Wazuh configurado.
- **P1 (yo):** `ResponseExecutor` + los playbooks (`build_*`) + el wiring en el orquestador + tests con `SimulatedExecutor`.

## 4. Scope POC / demo

- **Real:** `WazuhActiveResponseExecutor` en el lab para UC-01 (isolation visible — "la audiencia ve el host aislarse").
- **Sandbox/tests/ensayo/video:** `SimulatedExecutor` (sin VMs). Mismo código de decisión; sólo cambia el executor inyectado.
- UC-05 (Wazuh agent-kill, ADR-0010 §2.1) es un cameo aparte; este ADR cubre los playbooks de respuesta, no la auto-defensa del agente.

## 5. Alternativas consideradas

| Alternativa | Veredicto |
|-------------|-----------|
| **SSH-exec directo desde el SOAR a las VMs** | ❌ Acopla el SOAR a credenciales SSH de cada víctima; menos XDR-estándar; más superficie de ataque. |
| **Acción local en el agente sin pasar por el manager** | ❌ Pierde la orquestación central y el audit trail unificado. |
| **Sólo simulado (nunca real)** | ❌ El profesor quiere ver acción real en el demo (UC-01). Se mantiene como fallback, no como único modo. |
| **`ResponseExecutor` + Wazuh AR real + Simulated fallback** | ✅ XDR-estándar, desacoplado, testeable sin lab, con fallback de demo. |

## 6. Consecuencias

### Positivas
- El SOAR queda **desacoplado** del mecanismo de ejecución y **testeable sin lab** (`SimulatedExecutor` + mocks).
- La espera del production-critical (ADR-0006 Sit.B) queda **acotada** una vez implementados throttle+snapshot — cierra el hueco de seguridad detectado.
- Encaja en el contrato v1.1.0 sin tocarlo.

### Negativas
- Crea dependencia explícita en P3 (AR scripts) y P4 (lab) para el modo real; mitigado con `SimulatedExecutor` para no bloquear a P1.
- El paridad real/simulado hay que mantenerla (que el simulado refleje fielmente lo que el real haría) para que el ensayo sea representativo.

## 7. Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 (Proposed) | 2026-05-30 | Initial — modelo de ejecución (ResponseExecutor: Wazuh AR + Simulated), catálogo de playbooks, contrato, reversibilidad/fail-soft, deps cross-team. Pendiente review de P1 antes de implementar. | P1 |
