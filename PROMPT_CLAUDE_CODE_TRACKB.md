<!--
  PROMPT PARA CLAUDE CODE — dejar Track B corrible y grabable end-to-end. Entrega 1-jul-2026.
  Tooling de equipo, NO es entregable. Pega TODO lo que esta debajo de la linea como primer
  mensaje en Claude Code, con el repo abierto. Sigue vigente el marco de PROMPT_CLAUDE_CODE_1JUL.md.
-->

---

Sos ingeniero senior de seguridad en ARGOS. Consultor crítico, no asistente complaciente. Auditás antes y después, parás y me preguntás (Enzo) ante cualquier contradicción, no tocás `argos_contracts` v1.1.0, no metés el LLM en el path de contención (R-2), validás todo en `.venv`, commits convencionales, y mantenés `MEMORIA_ARGOS.md` al día. El marco completo está en `PROMPT_CLAUDE_CODE_1JUL.md` §0-§3 y §5-§7. Re-aterrizá leyendo `MEMORIA_ARGOS.md` antes de actuar.

## Contexto y objetivo

Decisión de Enzo (modelo de demo del 1-jul): **Track B en vivo + lab real grabado.** Track B es `docker compose` + `scripts/demo_injector.py` corriendo los UC por el pipeline real (tiers, correlación, quorum, scheduler, LLM, audit, consola), executor `simulated`, en la laptop de Enzo con Docker (Hyper-V ON). El lab VirtualBox NO es esta sesión (lo bootea Diego en otra máquina; acá no se puede por C19).

Objetivo de esta sesión: dejar Track B 100% corrible y GRABABLE end-to-end, con todos los módulos y partes conectadas, para grabar una corrida limpia que sirva de demo y de respaldo en video.

Estado: el injector cubre 5 UC (uc01/02/04/06/07). UC-03 (centerpiece split-brain), UC-05 y UC-08 NO tienen escenario en el injector. compose Perfil A existe. LLM `openai/gpt-oss-120b` ~0.9s. Consola read-only en `:8080`. `demo_reset` hace FLUSHDB. `DEMO_MODE`/`DEMO_CACHE_PATH` existen.

## Tareas, en orden

1. **REPORTE DE ENTRADA + levantar Track B y verificar que TODO está conectado.** `docker compose up -d` (redis, postgres-audit, soar, console, llm-triage); confirmá que cada servicio queda healthy, que la consola `:8080` renderiza, que `/triage` responde de verdad contra gpt-oss, y que el audit escribe. Si algo no levanta en esta máquina (Hyper-V/Docker), reportá y pará. No asumas que el compose corre limpio solo porque "es el camino garantizado".

2. **Corré los 5 UC del injector (uc01/02/04/06/07) end-to-end, con `demo_reset` entre cada uno.** Por cada UC confirmá la cadena completa: alerta → `events:normalized` (campo `payload`) → tier correcto → decisión esperada → la consola muestra el incidente → el audit lo registra → el enriquecimiento LLM aparece. Reportá cualquier UC que no dé el desenlace esperado, con la causa.

3. **Construí el escenario `uc03` en `demo_injector` (CENTERPIECE, prioridad alta).** Split-brain real: alerta ML-only T2 → throttle + snapshot proactivos → 4 votos por el quorum/scheduler REALES (2 approve, 1 reject, 1 timeout) → ventana de consolidación → conservative-wins → EXECUTE_ISOLATION. Usá la lógica real de `soar` (handlers/scheduler), sin tocar el contrato. La consola tiene que mostrar el conflicto y la resolución. Agregá tests del escenario y dejá `pytest -q` verde.

4. **Opcional, solo si 1-3 están verdes y sobra tiempo:** escenarios `uc05` (agent-kill: stop-service + agent-offline → T0 → isolate) y `uc08` (SQLi Sigma → T1 → block IP) en el injector. Si no entran en el tiempo, se narran o se graban aparte; avisame, no los fuerces.

5. **LLM a prueba de cámara.** Generá la cache de respuestas (`DEMO_CACHE_PATH`) corriendo el triage real de cada UC una vez, y dejá `DEMO_MODE=true` para la grabación. gpt-oss es rápido (~0.9s), pero la cache elimina cualquier blip de red en vivo. R-2 intacto: el LLM nunca bloquea la contención, aunque la cache falle.

6. **Telegram en la grabación = injector-cast, sin ngrok.** Los votos de uc03/uc04 los castea el injector de forma determinista. No dependas del callback real de Telegram para la grabación (es lo más frágil). Si Enzo quiere un momento Telegram real, que sea un paso opcional y aparte, no el camino de la grabación.

7. **RECORDING RUNBOOK** (`docs/RUNBOOK_GRABACION_TRACKB.md`): la secuencia exacta para grabar una corrida limpia. Orden de UCs, comando por UC, `demo_reset` entre cada uno, qué mostrar en pantalla (consola `:8080`, terminal del injector, panel LLM, audit), timing sugerido por UC para caber en ~13 min, y los puntos de narración. Que cualquiera del equipo pueda grabar siguiéndolo sin improvisar.

## No hagas

No toques `argos_contracts`. No metas el LLM en contención. No dependas de ngrok ni del Telegram real para la grabación. No construyas el lab VirtualBox (es de Diego, y esta máquina tiene Hyper-V ON). No fuerces uc05/uc08 si comprometen los 5 que ya andan + uc03.

## Cierre

REPORTE DE SALIDA: qué levantaste y verificaste conectado, qué UC quedan grabables y cuáles no (y por qué), qué es real vs simulado en la corrida, tests en verde, y auto-crítica (lo más débil, qué se rompe contra lo real, qué supuesto puede ser falso). Mantené `MEMORIA_ARGOS.md` al día. Ante cualquier contradicción o duda, pará y preguntame con opciones concretas.
