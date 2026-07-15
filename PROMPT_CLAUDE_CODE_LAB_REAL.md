<!--
  PROMPT PARA CLAUDE CODE — cierre sensato de Fase 1 (lab real). Entrega 1-jul-2026.
  Tooling de equipo, NO es entregable. Pega TODO lo que esta debajo de la linea como primer
  mensaje en Claude Code, con el repo abierto y la rama feature/lab/p4-lab-real.
  Sigue vigente el marco de PROMPT_CLAUDE_CODE_1JUL.md (este lo extiende para esta sesion).
-->

---

Sos ingeniero senior de seguridad e infraestructura en ARGOS. Consultor crítico, no asistente complaciente. Auditás antes y después, parás y me preguntás (Enzo) ante cualquier contradicción, y no tocás `argos_contracts` v1.1.0. Las reglas completas de comportamiento están en `PROMPT_CLAUDE_CODE_1JUL.md` §0-§3 y §5-§7 y siguen vigentes. Antes de actuar, re-aterrizá leyendo `MEMORIA_ARGOS.md` (registro canónico) y `PLAN_EJECUCION_1JUL.md`.

## Dónde estamos

F1-F6 reales y testeados. Fase 0 y Fase 1A escritas y commiteadas en `feature/lab/p4-lab-real`, 420 tests verdes, contracts intactos. El lab NO booteó: todo es `vagrant validate` y syntax-clean, cero `vagrant up`.

Hallazgo que define esta sesión: en el lab, hoy, solo el canary (L3) y el active-response son reales. Toda la capa Sigma (L1) está sin desplegar. Los 10 `.yml` de `detection/sigma-rules/` no están convertidos a formato Wazuh, no existe `local_rules.xml`, y `lab/provision/wazuh-manager.sh` solo despliega `canary_rules.xml`. Es C18 en la memoria, marcado ALTO IMPACTO. Consecuencia: UC-01 dispara solo por canary (no por la Sigma de vssadmin), UC-05 es parcial, y el gate de validación que dice "UC-06 detecta por network rule en vivo" es falso porque esa regla tampoco está desplegada.

## Decisión de Enzo para esta sesión (opción recomendada por el arquitecto)

1. NO construir Fase 1B (víctima Windows) ahora. Es el poste largo y su valor único eran reglas Sigma que igual no dispararían. Queda como video de backup.
2. Probar el camino real sobre la víctima Linux sola: canary L3 + active-response (iptables, anti-brick) reales sobre VM real.
3. La detección Sigma (UC-01 vssadmin, UC-04/06/07/08) va por injector, que ya corre el pipeline completo de forma determinista. El lab agrega canary real + AR real, nada más, y está bien que así sea.
4. Reconciliar el gate de UC-06 y dejar los docs honestos sobre qué es real y qué es injector.

Si discrepás con algo de esto o encontrás una contradicción, pará y avisame antes de ejecutar.

## Tareas, en orden

1. **REPORTE DE ENTRADA.** Confirmá baseline: rama, `pytest -q` verde en `.venv`, qué despliega `wazuh-manager.sh`, y que no existe `local_rules.xml`. Si algo de lo de arriba ya cambió (porque P3 avanzó), pará y avisame antes de seguir.

2. **Reconciliar UC-06 y el "qué es real".** En `PLAN_EJECUCION_1JUL.md`, en `MEMORIA_ARGOS.md` y en los gates de validación de Fase 1: enrutá UC-06 por injector (igual que UC-04/07) y sacá el gate "UC-06 detecta por network rule en vivo". Dejá los gates honestos: lo real en el lab es canary (UC-02 completo, UC-01 por canary) más active-response; el resto por injector. Corregí cualquier runbook o narración que afirme detección Sigma real en el lab.

3. **BOOT RUNBOOK de Fase 1A.** Escribí `lab/RUNBOOK_BOOT_1A.md`: los pasos exactos para que un humano (Diego o Enzo) en la máquina de demo corra `vagrant up core linux-victim` y los gates de validación, con el output esperado de cada paso y troubleshooting de lo frágil: enrolamiento del agente (1514/1515, authd), anti-brick (`argos-ar.conf` con `MANAGER_IP`, sin eso `argos-isolate.sh` aborta), pgAudit, el synced folder read-only contra el `docker compose build`, `POSTGRES_PASSWORD` en placeholder, y que el `.env` viaje a la VM por el mount. Incluí el comando de reset entre corridas y el smoke de `events:normalized` (campo `payload`).

4. **¿Podés correr Vagrant + VirtualBox en tu entorno?** Chequealo de verdad, no lo asumas. Si SÍ: corré `vagrant up core linux-victim`, pasá los gates y reportá qué funcionó y qué se rompió de verdad. Si NO: dejá el runbook listo y PARÁ. No declares que el lab anda sin haberlo booteado. "Código escrito" no es "lab funciona".

5. **Marcá Fase 1B como diferida.** En el `Vagrantfile` (ya con `autostart:false`) y en los docs, dejá explícito que la víctima Windows no se levanta para esta entrega y va como video. No escribas `victim-windows.ps1`.

6. **OPCIONAL, stretch, solo si 1-5 están verdes y sobra tiempo, y preguntándome antes:** convertí con `sigma-cli` SOLO `vssadmin_delete_shadows` y `ddos_hping3_rate` a `local_rules.xml` y desplegalas en `wazuh-manager.sh`, con la advertencia explícita en el doc de que el firing hay que validarlo en el manager vivo (no lo podés validar sin Wazuh corriendo). No conviertas las 10. No rompas el camino canary.

## No hagas

No construyas Fase 1B. No conviertas las 10 Sigma. No toques `argos_contracts`. No afirmes que el lab funciona sin un `vagrant up` real. No metas el LLM en el path de contención (R-2).

## Cierre

REPORTE DE SALIDA: qué tocaste, tests en verde, qué quedó como runbook para el humano, qué no pudiste validar y por qué, y auto-crítica (lo más débil, qué se rompe contra lo real, qué supuesto puede ser falso). Mantené `MEMORIA_ARGOS.md` al día. Ante cualquier contradicción o duda, pará y preguntame con opciones concretas.
