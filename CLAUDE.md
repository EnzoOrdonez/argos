# CLAUDE.md — memoria de arranque para ARGOS

> Auto-cargado al inicio de cada sesión. Es un ÍNDICE + bitácora de sesiones, NO el
> registro narrativo detallado — ese sigue siendo `MEMORIA_ARGOS.md` (formato del
> equipo, más granular). Si algo de acá y de `MEMORIA_ARGOS.md` se contradice, gana el
> más reciente por fecha; avisar y corregir ambos. Este archivo se mantiene vivo:
> actualizar al cierre de cada sesión de trabajo, no solo cuando se pida.

## Qué es ARGOS

XDR/SOAR multi-capa open-source (Sigma L1 + ML L2 + canary L3 + LLM L4 enrichment, más
un SOAR con HITL y tiers T0-T3) que defiende la base PostgreSQL del banco ficticio
**IntiBank**. Proyecto del curso "Tópicos Avanzados de Ciberseguridad" (Universidad de
Lima, 2026-1). Entregables: demo en vivo + informe técnico + exposición ~13 min.
**Fecha de entrega: 2026-07-01** (movida desde 28-jun, antes 13-jun).

## Jerarquía de autoridad (no inventar otra)

1. `argos_contracts/` v1.1.0 — **INMUTABLE**.
2. ADRs `Accepted` en `docs/decisions/` (orden de lectura abajo).
3. Código real en `soar/` (verificado con tests).
4. `docs/ARGOS_RUNBOOK_MAESTRO.html` — doc único de verdad operativa del equipo.
5. `MEMORIA_ARGOS.md` — bitácora cross-sesión narrativa, mantenida por Enzo/Claude Code.
6. `docs/PROJECT_STATUS.md` — "Last updated 2026-06-10", quedó atrás de
   `MEMORIA_ARGOS.md`/`PLAN_EJECUCION_1JUL.md` (2026-06-29) en varios puntos (ver tabla
   de estado abajo, reconciliada contra código real al 2026-07-01).
7. Manuales `docs/team/manual-*.md` — ilustrativos, desfasados por diseño (ADR-0011).

## Qué NO tocar sin permiso explícito de Enzo

- **`argos_contracts/`** (v1.1.0): contrato congelado entre las 4 capas + SOAR.
- **`soar/`**: "el cerebro", ~400+ tests, terminado y en review. Bug puntual autorizado
  explícitamente es la única excepción (ver Bugs conocidos).

## ADRs — orden de lectura recomendado

1. **ADR-0015** (real-prototype-realization): topología 3 VMs, Perfil A/B, fases A/B/C,
   active-response por OS. Enmienda 2026-06-26 confirma 3 VMs simultáneas (core Linux,
   víctima Windows, víctima Linux Debian+PostgreSQL).
2. **ADR-0012** (response-playbooks): `ResponseExecutor` (Simulated ↔ Wazuh AR real),
   catálogo de playbooks, por qué throttle+snapshot son pre-aprobación.
3. **ADR-0013** (soar-orchestration): consumer, correlación por host (`RoutingSignal`,
   doble índice Redis), scheduler (3 relojes), gate del hook LLM (T2 ∪ two-person).
4. **ADR-0010** (demo-operational-decisions): patrón ideal/mínimo por decisión (UC-05
   cameo, webapp UC-08, thresholds, timing HITL), triggers de fallback.
5. **ADR-0011** (soar-implementation-reconciliation): por qué el manual P1 quedó
   desfasado del contrato v1.1.0; jerarquía de autoridad formalizada.
6. `docs/decisions/OPEN_QUESTIONS_RESOLUTION.md` — Q5 (calibración thresholds, sin
   empezar), Q2 (criticidad por host).

## Mapa de carpetas — estado real al 2026-07-01 (verificado contra código, no contra READMEs)

| Carpeta | Estado real | Evidencia |
|---|---|---|
| `argos_contracts/` | Terminado, v1.1.0, congelado | 64 tests (corregido Ronda 9; ver nota más abajo) |
| `soar/` | Terminado (Fases 0-3) | tests verdes según docs del equipo — **no verificado en esta sesión**, ver nota pytest |
| `active-response/` | Terminado: 6 scripts Linux + 6 Windows + tests | `argos-{isolate,throttle,snapshot,kill,unisolate,unthrottle}` |
| `deception/` (canary L3) | Terminado | generator + fim-configs + wazuh-rules + tests |
| `detection/` (Sigma L1) | Reglas `.yml` escritas (10) pero **NO desplegadas** a Wazuh — no existe `local_rules.xml`, el provision del manager solo despliega `canary_rules.xml` (C18, ALTO IMPACTO, abierto) | `lab/provision/wazuh-manager.sh` |
| `detection/simulators/` | Existe y es real — `uc01_lockbit_like.py`, `uc06_ddos_controlled.py`, `uc08_sqli_controlled.py` (P3). Safety-gated: uc06/uc08 no ejecutan nada real sin `--i-confirm-this-is-my-lab`. **Esto ya es simulación de ataque funcional, aunque vive fuera de `attack-simulation/`** | `detection/simulators/README.md`, 541 líneas |
| `llm_triage/` | Cliente NVIDIA real, no solo scaffolding (esto contradice `PROJECT_STATUS.md` línea 56, que quedó vieja) | `llm_client/openai_client.py` |
| `ml/` | Librería + demo de consola; **sin daemon/consumer L2 corriendo en vivo** | `ml/soar_adapter.py` |
| `lab/` | **NO vacío** — Vagrantfile (90 líneas) + provisioning de **2 de 3 VMs** (core=Wazuh manager, linux-victim=Debian+PostgreSQL IntiBank) + `postgres/init.sql`+`seed.py` + 2 runbooks (1074 líneas totales). `vagrant validate` OK. **`vagrant up` nunca completó con éxito** (C19, ver Bugs). VM Windows víctima (Fase 1B) **diferida a propósito** (decisión Enzo 2026-06-29): no existe `victim-windows.ps1`, va como video |
| `attack-simulation/` | Vacío de verdad — solo README (146 líneas). Antes de escribir nada: decidir con Enzo si se reusa/mueve `detection/simulators/` o se construye aparte (evitar duplicar) |
| `evaluation/` | Vacío de verdad — solo README (183 líneas). Calibración de thresholds (Q5) no empezada; los valores en distintos docs no siempre coinciden entre sí (0.95/0.80/0.60/0.40 en `PROJECT_STATUS.md` vs. 0.80/0.74 en `PLAN_EJECUCION_1JUL.md`) — todos son placeholders, ninguno calibrado |
| `ui/` (Streamlit) | Existe, app + componentes + tests | fallback de la consola (Fase 6 es la principal, `:8080`) |
| `console/` | Consola web principal (`:8080`) | Fase 6 |
| `scripts/demo_injector.py` | **Los 8 UC están implementados** (uc01...uc08), con test dedicado para uc03 (`test_uc03_split_brain.py`) | 458 líneas, `_scenarios()` |
| `docker-compose.yml` (Track B) | Completo y verificado contra compose vivo (5 servicios healthy) | `docs/RUNBOOK_GRABACION_TRACKB.md` |

## Diagnóstico de partida de Enzo (prompt 2026-07-01) — verificado, no repetido

| # | Afirmación original | Veredicto |
|---|---|---|
| 1 | `lab/` — 0 líneas, solo README | **Falso.** 1074 líneas, 2/3 VMs provisionadas en código (falta boot real). |
| 2 | `attack-simulation/` — 0 líneas, solo README | Cierto para esa carpeta puntual, pero incompleto: `detection/simulators/` ya cubre UC-01/06/08 funcionalmente. |
| 3 | `evaluation/` — 0 líneas, thresholds sin calibrar | Confirmado sin cambios. |
| 4 | `demo_injector.py` cubre 5/8 UC, faltan UC-03/05/08 | **Falso** — los 8 están implementados y testeados. |
| 5 | Timeout 5s hardcodeado en `soar/`, backend deepseek-v4-pro | Timeout: **confirmado, sigue igual**. Backend: **desactualizado** — deepseek-v4-pro descartado hace semanas por latencia; actual es `gemma` (ver Bugs conocidos). |

**Hallazgo fuera del diagnóstico de partida:** hoy (2026-07-01) es la fecha de entrega
documentada en `PLAN_EJECUCION_1JUL.md`/`MEMORIA_ARGOS.md`. Hubo un checkpoint
**Go/No-Go el 2026-06-30 20:00** cuyo resultado esta sesión desconoce (ver Preguntas
abiertas). Sesiones previas de Claude Code ya construyeron Fase 0 + Fase 1A del lab
real y dejaron Track B (simulado) grabado y verificado como respaldo garantizado.

## Bugs conocidos y su estado

### BUG-1 — Timeout de 5s en el hook SOAR→llm_triage (activo, sin arreglar)

- **Dónde:** `soar/decision_engine/triage_hook.py:38` — `DEFAULT_TIMEOUT_SECONDS = 5.0`,
  default del `httpx.AsyncClient` de `TriageClient`. Constante Python; no lee ningún
  env var.
- **Síntoma:** si `llm_triage`/el backend tarda >5s en responder a `POST /triage`, el
  hook cae a `except Exception` → `Incident.llm_analysis = None` (fail-soft por diseño,
  invariante R-2 — no tumba la contención). Panel LLM sale vacío para ese incidente.
- **Ojo, dos timeouts distintos:** `LLM_REQUEST_TIMEOUT_SECONDS=120` (confirmado seteado
  en `.env`) se consume en otro punto de la cadena (`llm_triage` → NVIDIA/gemma), NO en
  `triage_hook.py`. Subir ese env var no mueve el corte de 5s del lado SOAR.
- **Mitigación existente (no es fix):** `DEMO_MODE` + cache en `demo/cached-responses/`
  (`T1078.json`/`T1083.json`/`T1190.json`) sirve respuesta cacheada casi instantánea
  para uc03/04/07/08. **Sin confirmar si `DEMO_MODE` sigue en `true` hoy** — el valor
  actual en `.env` no calza en longitud con `true` tal como se revisó el 2026-07-01;
  confirmar con Enzo antes de asumir que el cache sigue activo.
- **Backend real actual:** ya no es deepseek-v4-pro (descartado por latencia 15-21s).
  El valor de `OPENAI_MODEL` en `.env` es compatible con `google/gemma-4-31b-it` (pivote
  2026-06-30 tras problemas de key/créditos NVIDIA con `gpt-oss-120b`), pero no se leyó
  el string exacto en esta sesión.
- **Estado:** pendiente. Toca `soar/` → requiere autorización explícita de Enzo antes de
  tocarlo. Opciones sobre la mesa, ninguna elegida: (a) subir la constante, (b) leerla
  de un env var nuevo, (c) mejorar el fail-soft para distinguir "LLM lento" de "LLM caído".

### BUG-2 — C18: capa Sigma no desplegada (documentado por el equipo)

Los 10 `.yml` de `detection/sigma-rules/` no están convertidos a `local_rules.xml`;
`wazuh-manager.sh` solo despliega `canary_rules.xml`. En el lab real, solo canary (L3) +
active-response son reales; UC-01 "real" es solo por canary (no por la Sigma de
vssadmin); UC-04/06/07/08 dependen del injector para mostrarse en vivo. Diferido a P3
(`sigma-cli convert`), marcado ALTO IMPACTO por el propio equipo.

### BUG-4 — Telegram/Twilio: env vars del código no coinciden con `.env` (nuevo, 2026-07-01)

`soar/notifications/channels/telegram.py:111` lee `os.environ["TELEGRAM_CHAT_ID"]` y
`twilio_voice.py:52-53` leen `TWILIO_FROM_NUMBER`/`TWILIO_TO_NUMBER` — pero `.env`/`.env.example`
solo definen `TELEGRAM_APPROVER_CHAT_IDS` y `TWILIO_APPROVER_PHONES` (plural). Confirmado por
grep: ningún `.py` del repo lee las variables plural — quedaron huérfanas. Efecto: `TelegramChannel()`
instanciado sin args revienta con `KeyError`, y el gate de `scripts/demo_injector.py:_build_notifier()`
(chequea `TELEGRAM_CHAT_ID`) nunca construye el canal → Telegram nunca sale por el injector, con o
sin `TELEGRAM_BOT_TOKEN` válido. Mismo patrón en Twilio (`TWILIO_TO_NUMBER` vs `TWILIO_APPROVER_PHONES`).
**Fix de cero riesgo, no toca `soar/`:** agregar a `.env` `TELEGRAM_CHAT_ID=<mismo valor que
TELEGRAM_APPROVER_CHAT_IDS>` (y `TWILIO_TO_NUMBER=<uno de TWILIO_APPROVER_PHONES>` si se persigue
Twilio). Fix de fondo (renombrar en `soar/notifications/channels/*.py`) requiere autorización
explícita de Enzo — no tocado. Two-person con 2 chat_ids DISTINTOS sigue sin poder demostrarse
(`TELEGRAM_APPROVER_CHAT_IDS` tiene 1 solo id, y la clase de todos modos solo soporta un `chat_id`).

### BUG-3 — C19: `vagrant up` nunca completó (Hyper-V vs VirtualBox)

En la máquina de Enzo, Hyper-V (Docker Desktop/WSL2) le quita VT-x a VirtualBox →
`startvm` falla con `E_FAIL exit 1`. Runbook: `lab/RUNBOOK_BOOT_1A.md`. Decisión
registrada 2026-06-29: bootear en la máquina de Diego (sin Hyper-V). **Esta sesión no
tiene confirmación de si eso se ejecutó ni con qué resultado.**

## Conectividad / credenciales — revisado 2026-07-01 (solo SET/EMPTY, sin exponer valores)

| Canal | Estado | Nota |
|---|---|---|
| Telegram bot token | SET | — |
| Telegram chat IDs aprobadores | SET, pero longitud consistente con **un solo ID** (no ≥2) | two-person real por Telegram sigue sin poder demostrarse con identidades distintas |
| OPENAI_API_KEY (NVIDIA NIM) | SET | — |
| OPENAI_MODEL | SET | longitud compatible con `gemma`, no confirmado el string exacto |
| ARGOS_JWT_SECRET / JWT_SECRET | SET (mismo largo en ambas — posible duplicado del mismo valor) | no se puede saber desde acá si es secreto real o placeholder |
| POSTGRES_PASSWORD / VICTIM_PG_PASSWORD | SET | ídem, no se puede saber si es real o placeholder |
| TWILIO_ACCOUNT_SID / AUTH_TOKEN | SET pero con longitud que **no calza** con el formato real de Twilio (SID=34 chars, token=32) | probable placeholder |
| DISCORD_WEBHOOK_URL | SET pero de 1 solo carácter | efectivamente vacío/no funcional |
| DEMO_MODE | SET | longitud no calza con `true` — revisar con Enzo (ver BUG-1) |
| ARGOS_EXECUTOR | **EMPTY** | default runtime = `simulated`. Ejecutar contención real hoy requiere setearlo a `wazuh` explícitamente Y tener un manager Wazuh vivo y alcanzable — ninguna de las dos está dada ahora |
| WAZUH_API_URL/USER/PASSWORD | SET | sin manager real corriendo, no se puede confirmar si son credenciales válidas |

## Verificación de tests — limitación de este sandbox (2026-07-01)

Este sandbox Linux solo tiene **Python 3.10.12**; `pyproject.toml` exige `>=3.11`. El
`.venv` real del repo es de Windows (`.venv/Scripts/*.exe`) y no corre en este sandbox.
**No se pudo correr `pytest -q` en esta sesión.** Los números de tests citados en los
docs del equipo (420 → 427 → 441 según la fecha del doc) no están verificados de forma
independiente todavía. Antes de tocar cualquier código: correr `pytest -q` real (en el
`.venv` de Windows de Enzo, o instalar Python 3.11 en un sandbox) y anotar el resultado
acá.

## Preguntas abiertas — RESUELTAS en esta sesión (2026-07-01)

1. Go/No-Go 30-jun 20:00: **el lab real nunca booteó** (ni antes ni después). Igual que
   el 29-jun: solo `vagrant validate`, cero `vagrant up` exitoso.
2. Margen real: **horas** (la exposición es hoy). No días.
3. Máquina para el lab: iba a ser la de Enzo — **mismo C19 sin resolver**.
4. VM Windows: dada por **descartada para hoy** — no hay margen ni para completar la
   Fase 1A, mucho menos para greenfield de la víctima Windows.

**Decisión tomada con Enzo (2026-07-01):** dado el riesgo (reboot para Hyper-V→VBox
comparte máquina con Track B; `vagrant up` nunca completó ni una vez) vs. las horas
disponibles, **se prioriza asegurar Track B como demo en vivo**. El lab real (Track A)
queda fuera de alcance para hoy — no se intenta el boot. Retomar `lab/` es trabajo de
una sesión futura, sin la presión de un demo en horas.

## Estado de Track B verificado en esta sesión (sin poder correr docker desde el sandbox)

- `docker-compose.yml`: revisado, limpio. 5 servicios (redis/postgres-audit/soar/console/
  llm-triage) con healthcheck; `ARGOS_EXECUTOR` default `simulated`; perfiles `real` y
  `fallback` aparte.
- `.env`: **`DEMO_MODE=true` confirmado** (una inferencia mía anterior por longitud de
  string decía que podía haber vuelto a `false` — era incorrecta; ya se leyó directo).
- Cache LLM (`demo/cached-responses/`): **los 3 archivos existen y tienen contenido**
  (T1078→uc07, T1083→uc03, T1190→uc04). Con `DEMO_MODE=true` esto neutraliza el riesgo
  del timeout de 5s (BUG-1) para la corrida de hoy — uc01/02/05/06/08 no llaman al LLM
  de todas formas (R-2 gating).
- `docs/RUNBOOK_GRABACION_TRACKB.md`: runbook completo, verificado 2026-06-29 contra
  compose vivo, con timing exacto para ~13 min (uc02→uc01→uc06→uc04→uc07→uc03) y
  troubleshooting ya anticipado. **Usar este archivo tal cual para la corrida de hoy.**
- **No verificado en esta sesión** (requiere el compose real en la máquina de Enzo, que
  este sandbox no puede tocar): que los 5 servicios sigan healthy hoy, que el backend
  LLM (gemma) siga respondiendo si algún caso pega fuera de cache, que no haya rot de
  puertos/imágenes Docker desde el 29-jun.

## Decisiones tomadas en esta sesión (2026-07-01, sesión Cowork #1)

- Ningún archivo de `soar/`/`argos_contracts/` tocado. Se creó/actualizó únicamente
  este `CLAUDE.md`.
- Se corrigió el diagnóstico de partida de Enzo contra el código real (tabla arriba).
- Se recomendó explícitamente NO intentar el boot del lab real hoy (riesgo > beneficio
  dado C19 sin resolver + horas de margen); Enzo lo aceptó.
- `pytest` no se pudo correr en el sandbox (Python 3.10 vs. `>=3.11` requerido). Queda
  pendiente para una sesión sin presión de tiempo.
- Diagnosticado BUG-4 (env vars Telegram/Twilio) y arreglado vía workaround de cero
  riesgo en `.env` (alias `TELEGRAM_CHAT_ID`); Enzo lo aplicó y confirmó que funcionó.
- Enzo corrió uc03 en vivo contra el compose real: conservative-wins/EXECUTE_ISOLATION,
  LLM poblado desde demo-cache, audit trail completo. Track B confirmado funcional.

### HTML de presentación (`docs/use-cases/`) — copia de trabajo creada, original intacto

A pedido de Enzo (expo hoy 8pm), se mejoró el HTML de casos de uso para incluir CU-03 y
CU-05 (tenían CSS/JS completos pero nunca se habían conectado al grid visible — solo
existían 6 de 8 `.uc-card`). Regla explícita de Enzo: nunca tocar el original.

- **Original `argos_use_cases.html`: intacto.** Nunca recibió un solo `Edit`/`Write` en
  esta sesión — verificable por el historial de tool calls, no solo por hash (ver nota
  de sandbox abajo).
- **Copia de trabajo: `docs/use-cases/argos_use_cases_v2.html`** — es la que hay que usar
  para la demo/grabación de hoy. Cambios aplicados:
  1. Insertadas las cards CU-03 (centerpiece, comparte estrella con CU-04 — decisión de
     Enzo) y CU-05 (heartbeat/agent-kill), con narrativa calcada de la corrida real de
     Enzo (host WIN-WS-07, T1083, score 0.74, votos enzo=reject/p2=approve/p3=approve/
     p4=timeout).
  2. Corregido un bug semántico real en el JS dormido de CU-03: el código pre-existente
     (nunca ejecutado hasta ahora) marcaba a los que rechazaban como "ganadores" —
     al revés de conservative-wins real (gana approve, no reject). También tenía la
     ventana de consolidación hardcodeada en 180s (real: 60s, ADR-0006) y el texto de
     estado decía "EMPATE" (impreciso: es una resolución por política, no un empate).
     Las tres cosas quedaron corregidas.
  3. Agregada sección `.decision-legend` (tiers T0-T3 + conservative-wins vs.
     two-person-rule vs. R-2) justo antes del grid de casos de uso.
  4. Arreglados el array `cuIds` y el objeto `map` del mini-diagrama (JS), que solo
     cubrían 5 de los ahora-8 casos.
  5. Auditoría final (esta sesión): actualizado texto desactualizado que seguía diciendo
     "5 escenarios"/"cinco casos" en el hero, el chip de duración, el divisor de sección
     y el contador KPI — todos ahora dicen 8. Agregadas 3 filas (CU-06/07/08) a la
     "Matriz Resumen" que antes solo cubría CU-01-05, con datos verificados contra las
     cards reales (no inventados).
- **Gap conocido y NO arreglado a propósito:** la sección "Cobertura MITRE ATT&CK" (mitad
  de página) sigue con el marco viejo — dice "9 técnicas... 6 casos" y sus 9 celdas
  individuales listan tags para CU-01/02/04/06/07/08 nada más (ninguna celda referencia
  CU-03 ni CU-05; T1562.001 de CU-05 ni siquiera es una fila ahí). Arreglarlo bien
  requeriría agregar una 10ª técnica y recalcular 9 fracciones de cobertura — no se hizo
  por el riesgo de meter un número mal bajo presión de tiempo, y porque el runbook de
  grabación (`RUNBOOK_GRABACION_TRACKB.md`) nunca hace scroll hasta esa sección: es
  contenido de la página web, no parte de la demo de consola/injector. Si Enzo quiere,
  se puede arreglar en una sesión sin presión.
- **Hallazgo menor, pre-existente, no-bloqueante:** el JS de CU-04 tiene DOS definiciones
  de `window.playCU04` (una vieja, basada en `cu04Key1`/`cu04Key2` que no existen en el
  HTML real; otra correcta, basada en `cu04A1`-`cu04A4`, que es la que de verdad matchea
  el HTML). La segunda gana en tiempo de ejecución (JS sobrescribe), así que CU-04 anima
  bien — pero la primera es código muerto de una iteración anterior que nadie borró.
  Confirmado que ya estaba así en el original (no lo introduje yo). Cosmético, no requiere
  acción para hoy.
- **Nota de entorno importante:** el mount de este sandbox Linux hacia la carpeta de Enzo
  quedó con vistas obsoletas de tamaño/línea de archivo para este HTML específico
  (`wc -l`/`stat`/`tail` vía bash mostraban un archivo más corto y hasta truncado a mitad
  de palabra) mientras que la herramienta de lectura de archivos veía el contenido real y
  completo sin problema. Causó una falsa alarma (pensé que el archivo estaba truncado a
  ~4580 líneas cuando en realidad tiene ~5115). Si una sesión futura necesita correr
  `diff`/`wc`/`grep` por bash contra archivos grandes en `docs/use-cases/`, verificar
  primero con lectura directa antes de confiar en esos números.

### Tareas de esta sesión — estado final

- Tarea "Mejorar copia del HTML" → completada.
- Tarea "Auditoría final: listo para demo/grabación" → completada. Veredicto: **sí, listo
  para grabar**, con el gap del MITRE heatmap arriba explícitamente disclosed (no
  bloqueante, no visible en el flujo de grabación real).

### Ronda 2 (mismo día, a pedido de Enzo tras ver la v2): reorden + nueva escena 3D

Enzo pidió dos cosas sobre `argos_use_cases_v2.html` (el original sigue intacto, cero
cambios ahí):

1. **Reordenar las cards CU a orden numérico 01-08.** Antes salían 01,02,06,04★,07,03★,05,08
   (orden heredado de cuándo se insertó cada card históricamente, no un diseño intencional).
   Se movieron los bloques HTML completos a 01,02,03★,04★,05,06,07,08 — CU-03 y CU-04 quedan
   adyacentes, lo cual además tiene sentido (comparten estrella). Se corrigió también el
   array `cuIds` del mini-diagrama sticky (JS, `~línea 3567`), que mapea posición-en-DOM →
   config por índice; sin este fix el mini-diagrama hubiera iluminado las capas equivocadas
   al hacer scroll. El objeto `map` (colores/labels) no necesitaba cambios, solo `cuIds`.

2. **Nueva escena 3D de topología de red** ("como los demás, o mejor el diagrama de red
   planteado... asegurate de hacer una animación 3d impresionante"). Investigué primero:
   ya existían dos diagramas `.drawio` (`docs/architecture/network_diagram_v2.drawio`,
   2026-06-10, el vigente) con la topología real de 3 VMs — nunca se habían llevado al HTML.
   Pregunté a Enzo 3 cosas vía AskUserQuestion antes de tocar nada: qué vista (eligió
   **ambas combinadas**: física + overlay lógico de ataque), dónde ubicarla (eligió
   **sección propia nueva**, entre Arquitectura y Casos de Uso), y cómo tratar la VM
   Windows dado que nunca bootea (eligió **mostrarla con nota "diferida"**, no ocultarla).

   Resultado: nueva sección "02/07 · TOPOLOGÍA DE RED" (renumeré las 7 secciones
   existentes de x/06 a x/07). Escena Three.js (reusa r149 ya cargado, mismo patrón que
   `hero3d`/`flow3d`: WebGLRenderer+resize, paleta de colores, labels 2D proyectados,
   IntersectionObserver para pausar fuera de viewport):
   - 3 nodos "servidor" física (grid flotante en y=-1.3, plano 192.168.56.0/24):
     `argos-core` (.10, manager/SOAR/ML/LLM), `lin-victim-01` (.21, PostgreSQL,
     PRODUCTION-CRITICAL, badge "🔒 Regla 2 Personas"), `windows-victim` (.20, **ghost:
     wireframe sin relleno, sin partículas de telemetría, línea punteada, badge "◐ Fase
     1B · diferida hoy"** — la única VM que NO rota en el loop de animación, a propósito).
   - Overlay lógico (plano lógico IntiBank, existe solo en datos/reglas Sigma, no es red
     física — aclarado en el texto bajo la escena): nodo atacante (icosaedro,
     198.51.100.0/24) con arco de partículas rojas hacia `lin-victim-01`; nodo aprobadores
     (octaedro, canal HITL Telegram/Discord/Twilio) con línea punteada hacia `core`.
   - 4 anillos sensores (colores C1-C4, mismo esquema que `flow3d`) alrededor de
     `lin-victim-01` — callback visual a la sección de Arquitectura de arriba.
   - Cámara orbitando automáticamente, contador "PAQUETES DE ATAQUE" en vivo.

   **Verificación real (no solo lectura de código):** el sandbox bash tiene un mount
   obsoleto para este archivo específico (`wc`/`tail`/`diff` seguían devolviendo una
   versión vieja truncada — mismo problema que ya quedó documentado más abajo). Para
   evitar reportar "listo" sin probarlo: instalé el paquete real `three@0.149.0` (mismo
   que carga el HTML por CDN) en el sandbox y corrí un script Node que reconstruye TODA
   la lógica nueva de la escena (curvas Bezier, líneas punteadas + `computeLineDistances`,
   icosaedro/octaedro, pool de partículas viajando sobre curvas, proyección a pantalla)
   contra la librería real — los 11 checks pasaron sin excepciones. Esto no reemplaza ver
   el render real en un navegador (no tengo uno headless con WebGL en este sandbox), pero
   descarta con bastante confianza errores de API/sintaxis. **No verificado: cómo se ve
   realmente en pantalla (composición visual, que no se vea sobrecargado) — Enzo debería
   darle un vistazo rápido en su navegador antes de la expo.**

   CSS: reutilicé casi todo (`.flow3d-wrap/.card/.hdr/.stage/.labels/.foot`, `.f3-lbl`) —
   solo agregué `.f3-lbl.critical/.deferred/.attacker` y `.f3-lbl em` (línea de badge) y
   `.net3d-legend` (leyenda de colores física/ataque/HITL). Cero CSS nuevo para el
   contenedor visual.

   Gap conocido: el MITRE heatmap (sección ahora 04/07) sigue sin mencionar esta nueva
   sección de topología — no aplica realmente (esa sección es sobre técnicas ATT&CK, no
   sobre infraestructura), no requiere cambio.

### Ronda 3 (mismo día, feedback de Enzo tras ver la ronda 2): core dividido + flujos bidireccionales + Windows activa

Enzo pidió 3 cambios sobre la escena de topología de red (ronda 2), reabriendo una
decisión que él mismo había tomado antes (VM Windows) — la nueva decisión gana, se
documenta acá el cambio:

1. **`argos-core` dividido en sub-nodos.** Antes era una sola caja "ARGOS-CORE" con un
   badge de texto listando servicios. Ahora es un mini-clúster de 6 nodos reales dentro
   del mismo espacio físico (~192.168.56.10): **SOAR** (hub, rojo — el "cerebro"),
   **Wazuh Manager** (azul — hostea Sigma L1 + canary L3, es quien realmente tiene la
   conexión física a los agentes), **Redis**, **ML L2**, **LLM Triage**, **OpenSearch**
   — cada uno con su propio label 2D. Los labels de los 5 satélites son "minor" (solo
   nombre, compactos) para no competir visualmente con los 5 labels "major" (SOAR,
   lin-victim, windows-victim, atacante, aprobadores).

2. **Partículas bidireccionales (van y vuelven).** Antes cada conexión mandaba
   partículas en un solo sentido. Ahora hay un sistema genérico (`addBidiLine`/`addFlow`)
   donde CADA conexión — las 5 internas del clúster (SOAR↔cada servicio) y las 4
   externas (Wazuh↔lin-victim, Wazuh↔win-victim, SOAR↔aprobadores, atacante↔lin-victim)
   — manda partículas en ambos sentidos con colores/periodos propios por dirección (p.ej.
   Wazuh→víctima = active-response/azul, víctima→Wazuh = telemetría/color del host;
   atacante→víctima = ataque/rojo, víctima→atacante = respuesta/ámbar). Es más fiel a
   como funciona Wazuh en la realidad (agente reporta arriba, manager empuja
   active-response abajo), no solo más "bonito".

3. **Windows-victim pasa de fantasma a activa.** Revierte la decisión de la ronda 2
   (entonces Enzo eligió "mostrarla con nota diferida" = wireframe sin relleno, sin
   partículas). Ahora tiene el mismo tratamiento visual que lin-victim (nodo sólido,
   rota, con partículas de telemetría bidireccionales hacia Wazuh Manager), solo que
   conserva una nota chica en su label 2D ("◐ Fase 1B del lab — diferida hoy") y usa un
   color distinto (cyan) en vez del rojo de producción-crítica. La línea física
   Wazuh↔windows-victim pasó de punteada a sólida, igual que la de lin-victim.

   CSS: renombrado `.f3-lbl.deferred` → `.f3-lbl.note` (mantiene el borde punteado como
   señal visual, pero ya NO reduce opacidad — el nodo ahora está activo). Agregado
   `.f3-lbl.minor` (compacto, solo nombre, para los 5 sub-nodos del clúster).

   **Verificación (ronda 3, más rigurosa que la ronda 2):** no me conformé con probar
   solo la construcción de la escena — escribí un harness Node que mockea
   document/window/performance/requestAnimationFrame/IntersectionObserver lo mínimo
   indispensable, deja el `WebGLRenderer` real de three.js mockeado (es lo único que
   necesita GPU) y corre la función `loop()` REAL (la que vive tal cual en el HTML)
   durante 700 frames simuladas (~11.6s) contra `three@0.149.0`. Confirmé que: la escena
   construye sin excepciones, el loop corre 700 frames sin excepciones, y el contador de
   paquetes de ataque avanza (prueba de que el sistema de flujos con tags funciona de
   punta a punta, no solo en la construcción). Sigue sin ser un render visual real —
   Enzo debería darle un vistazo en su navegador antes de la expo, ahora con más razón
   porque el clúster interno tiene 6 nodos pequeños muy juntos y vale la pena confirmar
   que se lean bien a la distancia de cámara elegida.

### Ronda 4 (mismo día, feedback de Enzo con screenshot real): fix de solape de labels

Enzo mandó un screenshot real del render (primera confirmación visual que tuvimos de
esta escena — hasta acá todo era verificación por ejecución, nunca por ojo humano) y
tenía razón: labels y nodos claramente solapados — la caja grande de SOAR tapaba
WAZUH MGR/ML L2/REDIS, LLM TRIAGE se comía a OPENSEARCH, y WINDOWS-VICTIM se solapaba
con su propia geometría. Diagnóstico: el clúster de 6 sub-nodos de la ronda 3 estaba
demasiado apretado (radios de ~0.6-0.9 unidades) para la cantidad de labels que tiene
que soportar, y `.f3-lbl` usa `transform: translate(-50%,-50%)` (centrado exacto sobre
el punto proyectado, no flotando arriba), así que cualquier par de nodos cercanos en 3D
garantiza cajas de label superpuestas en pantalla.

Fix aplicado (solo posiciones/offsets, cero cambios de lógica):
- Clúster core reorganizado en forma de "pentágono" alrededor de SOAR (hub en el
  centro, y ahora más alto: 0,0.55,0) con radios de ~2.0 unidades en vez de ~0.9:
  wazuh (0,0.25,1.9) al frente, redis/ml (±2.0,-0.15,0.4) a los costados, llm/os
  (±1.4,1.6,-1.3) arriba-atrás. Víctimas empujadas de x=±2.7 a ±3.3 y z=1.5→1.8;
  atacante/aprobadores escalados proporcionalmente (~1.2x).
- Cada offset vertical de label recalculado contra el tamaño real del nodo (antes
  varios quedaban con el label centrado casi ENCIMA del borde superior de su propio
  nodo — ej. wazuh tenía solo 0.06 de despeje real). Ahora todos tienen 0.25-0.45 de
  despeje sobre su nodo.
- Cámara: radio de órbita 9→10.5, altura base 4.3→4.8, lookAt y 0.2→0.3 — un
  pull-back parcial (no proporcional al aumento de spacing) para que el aumento de
  distancia real entre nodos SÍ se traduzca en más separación en pantalla y no quede
  anulado por alejar la cámara en la misma proporción.

**Verificación cuantitativa (no solo "no tira excepción" — esta vez medí separación en
píxeles):** escribí un harness que proyecta los puntos ancla de cada label a través de
una `THREE.PerspectiveCamera` real (mismo FOV/aspect que la escena) y mide distancia en
píxeles entre los pares que se veían solapados en el screenshot. A un ángulo de cámara
"típico" fijo: la mayoría de los pares pasaron de 20-70px de separación a 70-140px
(mejoras de 1.4x a 3.9x). Extendí el chequeo a muestrear 12-36 ángulos a lo largo de
TODA la órbita de 360° (no solo un instante) para ver el peor caso real de la animación
— acá encontré algo importante que **no** escondo: el par soar-wazuh en particular
sigue teniendo un acercamiento fuerte (~12-13px) en cierto punto de la rotación, y no
mejora con más espaciado.

**Por qué no se puede arreglar solo espaciando más (limitación estructural, no un bug
mío):** SOAR está literalmente en el centro/eje de la órbita de la cámara (x=0,z=0).
Cualquier nodo que orbite alrededor de un punto que está sobre el propio eje de rotación
de la cámara va a tener, matemáticamente, al menos un instante por vuelta donde la
cámara mira "a través" de SOAR directo hacia ese nodo (colinealidad cámara-SOAR-nodo),
sin importar cuánta distancia real haya entre ellos — solo el tamaño del "espacio
libre" en ese instante depende de la separación en Y (altura), no en X/Z, porque la
cámara casi no varía en altura durante la órbita. Probé subirle más la altura a SOAR
para separarlo verticalmente de sus vecinos, y confirmé por qué no vale la pena forzarlo
más: ya subí SOAR de y=0.3 a y=0.55 (esto sí ayudó al resto de los pares), pero llevarlo
mucho más alto para "resolver" el caso puntual soar-wazuh empieza a romper la lectura
de "todos estos son un solo clúster/servidor" — es un trade-off, no algo que se arregle
gratis.

Decisión tomada (dado que hoy es el día de la expo, sin margen para seguir iterando
cámara/geometría): dejar el fix de spacing tal cual (mejora real y medida en el caso
típico, que es la mayor parte de cada vuelta de la órbita) y **no perseguir "cero
solape en absolutamente todos los instantes de una órbita de 360°"** — es un problema
distinto y más difícil que "sepáralos un poco", con retornos decrecientes. Si en la
práctica Enzo sigue viendo un parpadeo de solape puntual entre SOAR y WAZUH MGR durante
la rotación, la palanca que de verdad lo resolvería es limitar el arco de la cámara
(ej. oscilar ±45° en vez de dar la vuelta completa) en vez de seguir empujando nodos —
cambio de comportamiento de la animación que no se hizo hoy por no estar pedido y por
riesgo/tiempo.

Re-verifiqué ejecución completa (construcción + 1400 frames simuladas, más de una
órbita completa) contra `three@0.149.0` tras aplicar el fix: sin excepciones, contador
de ataque sigue avanzando. Sigue sin ser un render visual real de referencia — pero al
menos ahora la comparación antes/después está medida en píxeles, no solo "a ojo".

### Ronda 5 (mismo día, Enzo mandó screenshots reales tras la ronda 4): el fix de spacing NO alcanzó — algoritmo de anti-solape 2D real

Enzo mandó 5 screenshots reales del render (primera vez que vimos MÚLTIPLES ángulos,
no solo uno) y el solape seguía ahí — en algunos casos peor que el screenshot original
de la ronda 4 (texto de SOAR/WAZUH MGR/REDIS literalmente entrelazado carácter por
carácter en más de una captura). El diagnóstico de la ronda 4 (aumentar distancia 3D
entre nodos) era correcto pero insuficiente, y mi verificación de esa ronda tenía un
error real que reconozco: medí distancia entre PUNTOS-ancla de cada label (70-140px de
separación, lo reporté como "mejora clara") pero nunca comparé eso contra el tamaño real
de la CAJA de cada label — las "major" (con badge) miden ~190px de ancho. 70-140px entre
centros de dos cajas de ~190px de ancho sigue siendo solape garantizado; nunca fue
suficiente, sin importar cuánto más separe los nodos en 3D. Encima, con 5 servicios
orbitando alrededor de SOAR y una cámara que da la vuelta completa, hay casi siempre
algún servicio "detrás" de SOAR desde el punto de vista de la cámara — es una fracción
grande de cada vuelta, no el instante puntual que había estimado en la ronda 4.

**Conclusión: seguir moviendo coordenadas en 3D a mano no iba a resolver esto nunca —
hacía falta resolver el solape donde realmente ocurre, en 2D, después de proyectar.**

Fix real (algoritmo, no más tuning de posiciones):
1. Tras crear cada `<div>` de label (ya con su contenido real adentro), se mide su
   tamaño real una sola vez con `getBoundingClientRect()` → `labelSizes[key] = {w,h}`.
2. Cada frame, después de proyectar la posición 3D→2D de cada label (`rawPos`), corre
   una pasada de separación tipo SAT (Separating Axis Theorem, la técnica estándar de
   "label decluttering" en data-viz real): para cada par de cajas que se solapan tanto
   en X como en Y, se calcula la profundidad de solape en cada eje y se empujan ambas
   cajas separándolas a lo largo del eje de MENOR solape (el empuje mínimo que resuelve
   el choque). 10 iteraciones de esto por frame (10 labels → 45 pares → 450 chequeos/
   frame, insignificante para un browser).
3. Recién con las posiciones ya separadas se escribe `el.style.left/top`.

Esto es estructuralmente distinto a las rondas 3 y 4: ya no depende de que el spacing en
3D "alcance" para ningún ángulo de cámara — el anti-solape corre en 2D, sobre las
posiciones ya proyectadas, así que garantiza cero solape sin importar hacia dónde esté
mirando la cámara en ese instante.

**Verificación (mucho más rigurosa que rondas anteriores — mide el criterio de éxito
real, no un proxy):** las rondas 3-4 verificaban "¿la distancia entre puntos mejoró?"
— la pregunta equivocada. Esta vez el harness mide "¿las CAJAS de label se solapan,
sí o no, en píxeles reales?": mockeé `getBoundingClientRect()` de cada label con
tamaños representativos de la CSS real (major con badge ~188×64px, major sin badge
~150×33px, minor ~45+5.2×largo_del_texto ancho ×22px alto), corrí el `loop()` real
1600 frames simuladas (~26.6s, más de una órbita completa de sobra) contra
`three@0.149.0`, y en cada frame leí las posiciones FINALES que el propio código de
producción ya escribió en `style.left/top` (no una proyección paralela mía) y medí
solape real de caja contra caja para los 45 pares posibles. Primer resultado (10
iteraciones de empuje, +1px de margen): 27 pares-frame con solape residual, peor caso
1.3px de profundidad — ya casi nada, pero no cero. Subí a empuje +1.5px de margen:
**0px de solape en los 1600 frames, sin excepción.** Aplicado el mismo ajuste al HTML
real (`DECLUTTER_ITERS = 10`, margen `+1.5`).

**Lección para sesiones futuras (por qué la ronda 4 falló pese a "verificar"):** medir
que dos ANCLAS se alejan no prueba que dos CAJAS dejen de solaparse — hay que medir
contra el tamaño real del elemento que se va a renderizar, no contra un umbral arbitrario
inventado sin base (usé 55px como umbral en la ronda 4 sin chequear contra el ancho real
de ~190px de las cajas "major"; error mío, no del método de verificación en sí). La
lección más amplia: cuando el criterio de éxito es visual, verificar el proxy más
cercano posible al criterio real (solape de cajas, no distancia entre puntos) — y
cuando el usuario manda evidencia real (screenshot) que contradice la verificación
sintética, la evidencia real gana siempre, sin excusas ni relitigar la metodología vieja.

Sigue sin ser un render en navegador real (no hay WebGL headless en este sandbox), pero
esta vez la verificación mide exactamente la propiedad que le importa a Enzo (cero
solape de cajas), no un proxy indirecto — la confianza en el resultado es mucho más alta
que en rondas anteriores.

## Ronda 9 (13 días después de la entrega, 2026-07-14): transición a portafolio open-source

Curso terminado. Enzo pidió: (1) auditar si ARGOS "cumple lo que dice" para publicarlo como
herramienta real en GitHub (no solo demo de curso), (2) reescribir el texto del HTML de casos de uso
en tono humano (reglas anti-detección de IA que él mismo especificó: sin em dash, sin ciertas
palabras, variar longitud de oración, etc.), (3) corregir con rigor la tabla "ARGOS vs SIEMs
Comerciales" — el profesor (trabaja con Palo Alto Cortex XDR) dijo que está mal, "incorpora todo",
(4) extender esa misma verificación de honestidad a todo el resto del HTML, (5) volcar todo lo
investigado en un memoria.md privado, no commiteado. Decisiones tomadas antes de arrancar (vía
AskUserQuestion): diagnóstico primero (no ejecutar arreglos de código profundos sin que Enzo los
revise), créditos del equipo en sección discreta al final del README (pendiente de ejecutar),
portafolio open-source gratis sin intención comercial, solo lectura (no se optimiza para recibir
PRs externos).

**Hallazgo de Ronda 9 (ya gestionado):** el repo estuvo público con el `TELEGRAM_BOT_TOKEN`
filtrado (Ronda 7/8) recuperable desde el historial — resuelto en Ronda 11 (purgado vía
`git filter-repo`, bot y chat borrados por Enzo). La misma sesión encontró un hallazgo de
privacidad sobre un ex-integrante del equipo en el historial de git; gestionado directamente
por Enzo fuera de este archivo, sin detalle acá a propósito. Para cualquier sesión futura: si
algo en `git log --all` sugiere una identidad no acreditada públicamente en el proyecto, no
investigar ni documentar más — es terreno exclusivo de Enzo.

**Trabajo ejecutado hoy (no solo diagnóstico) en `docs/use-cases/argos_use_cases_v2.html`:**
investigación real (WebSearch) de capacidades 2026 de Microsoft Defender XDR / CrowdStrike Falcon /
Palo Alto Cortex XDR (los 3 tienen deception nativo o vía integración, y triage/acción autónoma vía
GenAI mucho más maduro de lo que la tabla vieja reconocía — Security Copilot, Charlotte AI,
Cortex AgentiX); tabla comparativa corregida con esos datos (Palo Alto deception ✗→½, los 3 en
LLM/GenAI triage ½→✓); **scorecard de "% cobertura" (100/75/75/62) eliminado por completo** — eran
números inventados a mano, no un cálculo real, y es exactamente el tipo de comparación que un
experto de industria rechaza; nota final "paridad funcional" reescrita a algo honesto. Todo el texto
de prosa sustancial (hero, topología, tiers, los 8 `uc-desc`, intros de MITRE/SIEMs/síntesis)
reescrito en tono humano. De paso se corrigieron: `argos_demo_prod` residual en CU-04 (debía ser
`app_prod`), `gpt-4o-mini` residual en CU-07 (backend viejo, ya no se nombra un modelo específico),
tres valores distintos para "cuántas técnicas MITRE" dentro del mismo HTML (9/Diez/6 → unificados a
9, el real), KPIs de síntesis ejecutiva etiquetados "TARGET" cuando ya son logros confirmados
(→ "CONFIRMADO", salvo tiempo de detección que sí es solo simulado, no medido en producción), y un
bug de HTML preexistente (línea 1989, `<span>` cerrado con `</b>` por error de tipeo de una edición
anterior — no introducido hoy). Verificado con `node --check` (JS) y un parser HTML real (0 errores
de balance de tags tras los cambios). No verificado: render visual real en navegador.

**Mismo patrón de sobreclaim encontrado fuera del HTML de casos de uso (diagnóstico, no corregido
hoy):** la frase "ARGOS replica la arquitectura de [Microsoft/CrowdStrike/Palo Alto]" aparece
prácticamente igual en README, PROJECT_BRIEF, CONTEXT, el SAD, y — más urgente — en
`EXPOSICION_ARGOS.html:183`, la sección de Introducción que se lee en voz alta al presentar. El SAD
y el THREAT_MODEL además describen el fallback LLM a Llama local como "testable claim, not
aspiration" pese a que `CLAUDE.md` ya documenta que nunca se cableó, y el THREAT_MODEL tiene una
contradicción interna real (T-030 descrito como "US-based" en una tabla y "China-based" en la sección
de riesgos aceptados, resto de una versión más vieja nunca sincronizada).

**Diagnóstico adicional de "qué falta para ser herramienta real de GitHub" (todo en
`MEMORIA_AUDITORIA_GITHUB.md`, no ejecutado):** no existe ningún CI/CD (`.github/` no existe), pese
a que la suite de tests ya está bien aislada de infraestructura externa (fakeredis, sin conexiones
reales en tests) y agregar un workflow sería barato; 47 tests reales (`ml/tests`, `ui/tests`,
`soar/response/forensics/tests`) quedan fuera de `testpaths` de `pytest.ini` sin que el README lo
explique; `soar/inventory.py` hardcodea IPs/criticidad del lab del curso en código de producción real
(no config), afectando directamente si un host requiere two-person rule; 8 archivos de andamiaje de
curso quedaron en la raíz trackeados en git sin seguir el patrón de `.gitignore` que ya existe para
sus hermanos; `docs/EVALUATION_CRITERIA.md` y `docs/CONTEXT.md` están enlazados desde el README como
si fueran onboarding pero son, en esencia, documentos de curso. LICENSE (MIT) está correcto y
completo, sin hallazgos. `.gitignore` en general está mejor cuidado que el promedio de un proyecto
OSS. El conteo "69 tests" que este mismo archivo citaba para `argos_contracts/` en rondas anteriores
está desactualizado — el conteo real verificado hoy por ejecución es **64** (el HTML ya lo tenía
correcto).

Se creó `MEMORIA_AUDITORIA_GITHUB.md` en la raíz y se agregó a `.gitignore` (verificado con Read que
la regla quedó escrita; no se pudo confirmar con `git check-ignore` en este sandbox por el mismo
problema de mount desincronizado ya documentado más abajo en este archivo — Enzo debería confirmar
con `git status` en su máquina que el archivo no aparece como untracked).

## Próximos pasos priorizados

**Hoy (horas):** Enzo corre `docker compose up -d` + smoke tests y sigue
`docs/RUNBOOK_GRABACION_TRACKB.md` para la corrida en vivo. Claude puede leer
salidas/errores que Enzo pegue, pero no puede ejecutar docker/vagrant directamente
(sandbox aislado del host de Enzo).

### Ronda 6 (mismo día, tras confirmar visualmente que la ronda 5 arregló el solape): 2 ajustes menores

Enzo confirmó (screenshot) que el anti-solape 2D funciona — pidió dos cambios puntuales:
1. Label de SOAR seguía grande (tenía sub "NÚCLEO DE DECISIÓN" + badge "Tier Router ·
   Playbooks · Notificaciones"). Vaciado a solo el nombre (`sub:'', badge:''`); el
   render condicional ya evita un `<b></b>` vacío. Con esto SOAR queda del mismo orden
   de tamaño que los labels "minor" sin perder su color/borde distintivo.
2. Pregunta legítima de Enzo: "¿el atacante no debería atacar también la máquina
   Windows?" — verificado contra el contenido real de las UC (no asumido): CU-03 ataca
   `WIN-WS-07` (split-brain) y CU-05 ataca `WIN-VICTIM-01` (agent-kill/T1562.001) — el
   diagrama solo tenía la línea atacante→lin-victim. Agregada línea bidireccional
   atacante↔windows-victim (mismo patrón que la de lin-victim, período distinto para
   diferenciar la señal, tagAB:'atk' para que sume al contador de paquetes).

Reverifiqué con el mismo harness de anti-solape (1600 frames, más de una órbita) tras
ambos cambios: sigue en 0px de solape. Chequeo adicional: el contador de ataque ahora
avanza más rápido (24 en 600 frames, 49 en 1200) porque suma las dos líneas de ataque,
confirmado por ejecución real, no solo lectura de código.

**Estado de la escena de topología de red al cierre de esta ronda:** core dividido en
6 componentes, flujos bidireccionales en las 9 conexiones internas/externas + 2 líneas
de ataque (lin-victim y windows-victim), anti-solape 2D en cero confirmado, SOAR
compacto. Enzo debería confirmar visualmente una vez más antes de la expo, aunque el
historial de esta sección sugiere que probablemente lo hará de cualquier forma.

## Ronda 7 (mismo día, 6h antes de la expo): auditoría de coherencia + guion + README + reproducibilidad

Enzo pidió una pasada final de 4 pasos secuenciales: (1) coherencia entre todos los
documentos del proyecto, (2) si eso está bien, revisar el guion de exposición, (3) si
el guion está bien, arreglar/mejorar el README, (4) si todo eso está bien, evaluar si
alguien que clona la repo puede reproducir esto aparte de conseguir sus propias API
keys. Se usaron 3 subagentes en paralelo (coherencia, guion, reproducibilidad) para
investigar, y luego se aplicaron los fixes de mayor valor dado el tiempo disponible.

### 🔴 Hallazgo más serio: secreto real filtrado a `.env.example` (ya corregido)

`.env.example` (versionado en git, público) tenía **el mismo `TELEGRAM_BOT_TOKEN` real**
que el `.env` privado de Enzo — confirmado por hash SHA-256 idéntico entre ambos
archivos, y confirmado por `git log -p` que un commit (`f1dc9a5`, "chore(env): .env.example
— IPs lab, modelo LLM y split postgres") pisó el placeholder original
(`replace-with-bot-token`) con el token real, probablemente por error al editar el
archivo equivocado. Esto es un secreto real en el historial de git de un proyecto de
ciberseguridad — irónico y con más urgencia que cualquier otro hallazgo de esta ronda.
**Enzo: rotar este bot token en @BotFather cuanto antes, independientemente de todo lo
demás** — arreglar `.env.example` hacia adelante no limpia el historial de git ya
existente. Revisé el resto de las variables "secret-like" (`WAZUH_API_PASSWORD`,
`OPENSEARCH_PASSWORD`, `POSTGRES_PASSWORD`, `JWT_SECRET`, `TWILIO_*`) y **todas son
placeholders genuinos** (`replace-with-...`) o secretos explícitamente de-solo-lab
(`VICTIM_PG_PASSWORD`, comentado como tal) — no hay otro caso igual.

Fix aplicado en `.env.example`: `TELEGRAM_BOT_TOKEN` vuelto a placeholder; de paso,
agregado el alias `TELEGRAM_CHAT_ID`/`TWILIO_TO_NUMBER` (BUG-4, antes solo estaba
parchado en el `.env` local de Enzo, así que un clone nuevo pisaba el mismo bug sin
saberlo); comentario aclarado en `DEMO_MODE` sobre que hay que ponerlo en `true` para
reproducir Track B.

### Coherencia entre documentos — 1 hallazgo grande, 3 menores (todos corregidos)

- **`docs/use-cases/USE_CASES.md` estaba truncado a media oración** (cortaba en
  "registra el caso en OpenSearch como False Positive con razón" — sin success
  criteria/narración de UC-07, sin UC-08 entero, sin changelog), pese a estar citado en
  el README como "TTPs completos". Completado: cerré la oración, agregué success
  criteria + demo narration de UC-07, escribí la sección UC-08 completa (mismo formato
  que las demás, datos ya establecidos en el guion: T1190 SQLi, `WIN-WEB-01`, T1
  auto-execute + block IP), agregué un Changelog al final.
- **Auto-contradicción en §2**: el texto decía "four demo scenarios... plus an optional
  fifth" mientras la tabla adyacente ya listaba 8 filas y el texto siguiente decía
  "Total demo runtime con 8 UCs". Corregido a "eight demo scenarios".
- **Identidad del activo defendido desactualizada en UC-04/UC-07**: usaban `argos_demo_prod`
  (schema inexistente en el código real), "PostgreSQL 15", y tablas `employees/payroll/
  invoices` — verificado contra `lab/postgres/init.sql` (schema real: `intibank`,
  database `app_prod`, tablas `customers/accounts/transactions`) y `docker-compose.yml`
  (`postgres:17.5-bookworm`). Corregido en ambos UCs a la terminología IntiBank real
  (ADR-0009), incluyendo el path `/var/lib/postgresql/15/main/` → `/17/main/`.
- Confirmado limpio (sin hallazgos nuevos): fecha de entrega, topología 3 VMs, backend
  LLM, conteos de tests, thresholds — todo ya cubierto por las tablas de este mismo
  archivo en sesiones previas.

### Guion de grabación (`GUION_GRABACION_TRACKB.html`) — contenido correcto, 2 bugs de ejecución reales (corregidos)

El contenido narrativo (8 UC, orden uc02→uc01→uc06→uc04→uc07→uc03, tiers, backend
`gpt-oss-120b`, honestidad real-vs-simulado, manejo correcto de la limitación de
Telegram con IDs sintéticos en vez de chat_ids reales) estaba bien y alineado con el
estado verificado. Pero:

1. **Los 10 bloques `<pre>` de comandos tenían `demo_reset.py` pegado sin salto de
   línea al comando siguiente** (ej. `demo_reset.py.venv\Scripts\python scripts\demo_injector.py
   uc02...`). El botón "copiar" del HTML hace `pre.innerText`, así que copiar y pegar
   en vivo durante la grabación hubiera fallado en el PRIMER comando. Corregido: salto
   de línea real entre cada comando, en los 10 bloques (uc01/02/03/04/05/06/07/08 +
   el bloque de audit SQL sink + el teardown).
2. **`%RU%` (sintaxis cmd.exe) usado en los 9 comandos del injector, pero el guion se
   declara en PowerShell** (nota propia de la sección 0) y nunca lo define — no se
   hubiera expandido. Como el propio guion ya dice en su intro de sección 5 que "no
   hace falta ninguna variable, los comandos no llevan --redis-url", directamente quité
   `--redis-url %RU%` de los 9 comandos — asi el código coincide con lo que el propio
   texto ya prometía.

Verificado con grep tras el fix: cero ocurrencias de `%RU%` o concatenaciones sin salto
de línea restantes en el archivo.

**2 documentos viejos marcados como superados** (con banner visible al abrirlos, para
que nadie los use por error hoy): `DEMO_RUNBOOK.md` (27-jun, 5 UC, menciona
`deepseek-v4-pro`) y `GUIA_VIDEO_DEMO.html` (26-jun, 3 UC, apunta a Streamlit `:8501`,
dice que `--live` "todavía no se construyó"). `GUIA_VIDEO_DEMO.pdf` no se tocó (es un
export, menor riesgo de que alguien lo abra por error hoy dado que ya está marcado el
HTML) — mencionar a Enzo si hace falta limpiarlo después.

### README.md — actualizado en varios puntos que quedaron atrás

Badge de fecha de entrega (28-jun → 1-jul), badge de tests (413 fijo y "passing" → ~441
con nota de "no re-verificado"), nombre de backend LLM (`deepseek-v4-pro`/`kimi-k2.6` →
`openai/gpt-oss-120b`, 3 lugares), tabla de "Estado actual" (fila de Lab: ya no dice
"pendiente-lab" sin matices, ahora explica que el código es real y que `vagrant up`
nunca completó por Hyper-V/VirtualBox — no por el código; fila de video demo: apunta al
guion y runbook vigentes, no a `DEMO_RUNBOOK.md` superado), sección "Prototipo real (3
VMs)" (ya no dice que `lab/` "es un stub" — tenía razón sobre el código real), sección
"Escenarios de demo" (decía "cinco escenarios" y solo listaba 5 UCs en la tabla — ahora
8, con UC-03 y UC-05/08 incluidos), sección "Hito siguiente" (triggers de fallback
vencidos desde hace semanas contra una fecha de entrega vieja — reemplazado por el
estado real de hoy), Quick Start (agregado el paso `cp .env.example .env` +
`DEMO_MODE=true` que faltaba antes de `docker compose up -d`, sin el cual Track B no
sale reproducible para alguien nuevo).

### Respuesta a la pregunta de reproducibilidad de Enzo

**¿Alguien que clone la repo puede replicar esto aparte de conseguir sus propias API
keys?** Con los fixes de esta ronda: **sí, para Track B** (`git clone` → `cp .env.example
.env` → completar `OPENAI_API_KEY` real + `DEMO_MODE=true` → `docker compose up -d` →
`demo_injector.py`). Antes de esta ronda la respuesta hubiera sido "no, silenciosamente"
por BUG-4 (Telegram nunca se hubiera armado, sin error visible). Track A (lab de 3 VMs)
NO es reproducible todavía por nadie — ni siquiera por Enzo en su propia máquina (C19,
Hyper-V vs VirtualBox) — eso es una limitación de entorno, no del repo, y ya estaba
disclosed. El cache LLM (`demo/cached-responses/`) está trackeado en git y sobrevive un
clone limpio, confirmado. Todo lo demás (Dockerfile, docker-compose.yml, schema.sql,
Vagrantfile) referencia archivos que existen — no hay pasos manuales ocultos adicionales
más allá de los ya corregidos.

### Hallazgo adicional (post-reporte inicial): `deploy/README.md` desincronizado + env vars huérfanas

Barrido final de coherencia encontró un documento que las 3 revisiones anteriores no habían
tocado: `deploy/README.md` (guía de deploy de Fase 5, distinta del README raíz). Tenía el mismo
problema de fondo que ya se había corregido en el README raíz — `OPENAI_MODEL=deepseek-ai/
deepseek-v4-pro` (backend descartado) — más uno nuevo y peor: instruía textualmente a copiar la
API key real desde `DeepSeek_V4_PRO_API_KEY`/`Kimi2_6_API_KEY` hacia `OPENAI_API_KEY`. Verificado
por grep en todo el repo: **ningún `.py` lee esas tres variables** (`MiniMax_M3_API_KEY`,
`Kimi2_6_API_KEY`, `DeepSeek_V4_PRO_API_KEY`) — solo aparecían en `.env.example` y en 3 docs.
`llm_client/openai_client.py:65` lee únicamente `OPENAI_API_KEY`. Son restos huérfanos de cuando
se evaluaban esos backends como primario, nunca limpiados tras el pivote a NVIDIA NIM. Corregido:
`deploy/README.md` actualizado (backend real + nota de que esas 3 vars no hacen falta);
`.env.example` las comentó con nota explicativa en vez de dejarlas como si hicieran falta
completarlas. `MEMORIA_ARGOS.md` y `docs/ARGOS_RUNBOOK_MAESTRO.html` también las mencionan pero
son bitácora narrativa/histórica — no se tocaron (regla existente: no reescribir historia).

## Ronda 8 (mismo día): token de Telegram confirmado filtrado + página nueva de exposición

Enzo confirmó por captura de pantalla que el `TELEGRAM_BOT_TOKEN` seguía visible en su editor
tal cual lo había diagnosticado la Ronda 7 (color resaltado = git aún lo ve como tracked/reciente).
Se le dieron los pasos concretos para rotarlo (@BotFather → `/mybots` → seleccionar el bot →
"API Token" → "Revoke current token" → pegar el nuevo valor en `.env` local, nunca en
`.env.example` → reiniciar el servicio `soar` si Track B está corriendo). **Acción pendiente del
lado de Enzo, no ejecutable desde acá.** Limpiar el historial de git (`git filter-repo`/BFG) se
deja explícitamente para después de la entrega — reescribe hashes de commits y rompe los clones
locales del resto del equipo.

### Hallazgo adicional de coherencia (barrido extra, no capturado en Ronda 7): `PROJECT_BRIEF.md` + nombre "Angeles" vs. "Nicole" Castillo

Al buscar contenido real para la nueva página de exposición se encontró que `docs/PROJECT_BRIEF.md`
— el "resumen 90 segundos" que el propio README linkea como puerta de entrada — había quedado
desactualizado desde v1.4: fecha de entrega vieja (13-jun en vez de 1-jul) y backend LLM viejo
(`GPT-4o-mini` / `ADR-0001 v2` en vez de NVIDIA NIM `openai/gpt-oss-120b` / ADR-0001 v3). Corregido
a v1.5.

Más serio: `README.md:163` y `docs/ARGOS_RUNBOOK_MAESTRO.html:157` decían **"Nicole Castillo"**
para P3, mientras que **"Angeles Castillo"** aparece 40+ veces en código real, tests (incluso hay
un `assert` en `detection/tests/test_rule_syntax.py:57` que verifica textualmente que el `author:`
de cada regla Sigma sea "Angeles Castillo"), ADRs, `docs/CONTEXT.md`, `docs/PROJECT_BRIEF.md` y
`docs/team/*`. "Nicole" era el valor incorrecto/desactualizado en exactamente esos 2 archivos —
corregido a "Angeles Castillo" en ambos. Este era el tipo de inconsistencia que la Ronda 7 debía
cazar y no cazó (los 3 subagentes no llegaron a `PROJECT_BRIEF.md` a fondo); quedó documentado acá
para que no se repita el gap.

### Nueva pieza: `EXPOSICION_ARGOS.html`

Sebastián pasó por chat la estructura clásica de sustentación (Introducción, Problemática,
Objetivos, Herramientas usadas, Recomendaciones/Conclusiones). Enzo pidió que fuera HTML con
animaciones — se preguntó explícitamente formato (PPTX vs. HTML) antes de construir nada; Enzo
confirmó HTML porque quiere animaciones al presentar. Se creó **`EXPOSICION_ARGOS.html`** en la
raíz (archivo nuevo y separado de `docs/use-cases/argos_use_cases_v2.html` — no se tocó ese
archivo): 7 secciones tipo slide con scroll-snap (Portada, Introducción, Problemática, Objetivos,
Herramientas, Conclusiones, Equipo/Cierre), misma paleta y tipografía que el HTML de casos de uso
(Orbitron/Exo 2/Share Tech Mono, verde `#00ffb3` sobre fondo casi negro) para consistencia visual,
pero **sin Three.js** — animaciones más simples y de menor riesgo: fondo de "digital rain" en
canvas 2D, contadores animados, dots de navegación lateral con sección activa, barra de progreso
de scroll, navegación por teclado (flechas/PageUp/PageDown), fade-in por `IntersectionObserver`.

Todo el contenido (problemática, objetivos, stack por capa, veredictos de conclusión) viene de
`docs/PROJECT_BRIEF.md` (ya corregido) + `README.md` + `CLAUDE.md` — nada inventado; los veredictos
de la sección de conclusiones distinguen explícitamente lo confirmado (Track B en vivo, diseño de
resiliencia) de lo pendiente (boot de Track A, calibración de thresholds), sin inflar resultados.

**Verificación (ejecución real, no solo lectura):** sintaxis JS confirmada con `node --check`.
Además se montó un harness Node con mocks de `document`/`window`/`canvas 2D context`/
`IntersectionObserver`/`requestAnimationFrame` y se corrió el único bloque `<script>` real del
archivo completo: el rain effect dibuja ~12k veces sin excepciones en 120 frames simulados y
respeta `document.hidden` (pausa/reanuda), la barra de progreso calcula el porcentaje correcto
(caso de prueba: 50% exacto), los 7 dots de navegación se crean con las etiquetas correctas, el
dot activo cambia según la sección "visible", los 4 contadores llegan exactamente a su valor
final (4/8/4/441) tras simular >1100ms de frames, y la navegación por teclado dispara
`scrollIntoView` sin lanzar errores. Balance de tags HTML verificado con un parser real
(`html.parser` de Python): 0 tags sin cerrar, 7 `<section>` = 7 `</section>`. Contenido re-grepeado
contra el archivo final para confirmar que no colaron fechas/nombres/backend viejos. Sigue sin ser
un render de navegador real — Enzo debería abrirlo una vez antes de presentar.

**Después de la entrega (sin presión de tiempo):**
1. Correr `pytest -q` real, línea base antes de tocar nada.
2. Retomar `lab/`: resolver C19 con calma (Hyper-V off + reboot fuera de una ventana de
   demo, o máquina dedicada sin Docker Desktop) y hacer el primer `vagrant up` real.
3. VM Windows víctima (Fase 1B) — decidir si vale la pena ahora que no hay presión.
4. `attack-simulation/`: decidir reusar/mover `detection/simulators/` vs. construir
   aparte.
5. Timeout LLM (BUG-1): requiere autorización explícita de Enzo, toca `soar/`.
6. `evaluation/`: calibración de thresholds, solo si sobra tiempo.
7. Rotar `TELEGRAM_BOT_TOKEN` en @BotFather (filtrado a `.env.example`, ver Ronda 7) —
   esto no requiere esperar, hacerlo apenas se pueda.
8. Considerar limpiar el historial de git del token filtrado (`git filter-repo` o
   similar) si el repo va a hacerse público al cierre del curso (el README dice
   "público al cierre") — requiere coordinación con el equipo, no es urgente para hoy.

## Ronda 10 (2026-07-15): prompt maestro para Claude Code — ejecución de la transformación OSS

Tras la Ronda 9 (auditoría completa, `MEMORIA_AUDITORIA_GITHUB.md`), Enzo pidió un prompt "completo,
auditable y proactivo" para dárselo a Claude Code (shell/git real, esta sesión de Cowork no tiene) y
que ejecute ahí la transformación: arreglos, mejoras, manejo de errores y una interfaz visual real.
Requisitos explícitos de Enzo: que el prompt obligue a Claude Code a revisar críticamente el plan
propuesto (no ejecutarlo ciego), a ser proactivo buscando fallas no listadas, a auditar/testear antes
y después de cada cambio, a dar contexto completo del proyecto, a preguntarle a él directamente ante
cualquier contradicción en vez de asumir, y a organizar el trabajo en fases (con libertad de proponer
más si las encuentra necesarias).

Antes de escribirlo se confirmaron 3 decisiones vía AskUserQuestion:
1. **Interfaz visual = modernizar `console/`** (FastAPI + `console/static/`, ya es la consola
   principal, :8080), no construir algo nuevo desde cero.
2. **`soar/`/`argos_contracts/` dejan de estar bloqueados para esta transformación** — autorización
   general, condicionada a que cada cambio lleve tests que pasen y quede documentado. La regla vieja
   de "nunca tocar sin permiso explícito" era para protegerlos *durante el curso*; ya no aplica tal
   cual, pero la disciplina de tests-antes-de-aplicar sí se mantiene.
3. **Checkpoints por fase** — Claude Code para al final de cada fase, resume, espera confirmación.

Se creó **`PROMPT_CLAUDE_CODE_TRANSFORMACION_OSS.md`** (raíz, gitignored — mismo tratamiento que
`MEMORIA_AUDITORIA_GITHUB.md`, nunca commitear/pushear) con 8 fases (0-7): auditoría propia + crítica
del plan → seguridad/honestidad de bajo riesgo → CI/CD → tests faltantes + `soar/inventory.py`
config-driven + BUG-1 (timeout LLM, ahora en alcance dado el punto 2 de arriba) → honestidad del resto
de la documentación (el patrón "replica la arquitectura", más urgente en `EXPOSICION_ARGOS.html:183`,
nunca corregido) → modernización de `console/` → limpieza cosmética/portafolio (SECURITY.md, créditos
discretos, andamiaje suelto en `.gitignore`) → verificación final + cierre en formato "Ronda N" acá
mismo. El prompt remite a leer `CLAUDE.md` y `MEMORIA_AUDITORIA_GITHUB.md` completos en vez de
duplicar su contenido (evita desincronización), con líneas rojas explícitas (nunca el HTML original,
nunca reescribir historia de git sin confirmación en el momento, nunca tocar la identidad de la
compañera expuesta, nunca rotar secretos).

**No ejecutado en esta sesión** — el propio pedido de Enzo es que la ejecución de código la haga
Claude Code, no Cowork. Las 8 fases siguen pendientes en su totalidad. Próxima sesión (de Claude Code,
no de acá): empezar por la Fase 0 del prompt.

## Ronda 11 (mismo día, 2026-07-15): historial de git reescrito — token de Telegram purgado

Mientras Claude Code ejecutaba el prompt maestro (Fase 0 y Fase 1 completadas, ver más abajo), Enzo
resolvió el riesgo funcional del `TELEGRAM_BOT_TOKEN` filtrado borrando el bot y el chat en Telegram
directamente ("por mientras"). Preguntó, desde esta sesión de Cowork, si además se podía purgar el
string del token del historial de git — hasta ahora esto había quedado deliberadamente pendiente en
todas las rondas anteriores ("requiere coordinación con el equipo, no por sorpresa").

**Recomendación dada:** esperar y coordinar con Yohamin/Diego/Angeles antes de reescribir, ya que el
bot ya invalidado resuelve el riesgo real (nadie puede usar ese token para nada) y lo que queda es
cosmético. Enzo, informado de que esto rompe los clones locales de los tres, decidió explícitamente
**proceder de todas formas** vía `AskUserQuestion` ("Proceder ahora, asumo el riesgo").

### Ejecución

1. Backup completo antes de tocar nada: `git bundle create ... --all` (20 refs, verificado con
   `git bundle verify`), guardado fuera del repo.
2. Token real localizado con precisión en el historial (valor omitido a propósito de esta bitácora —
   este archivo SÍ se commitea, a diferencia de `MEMORIA_AUDITORIA_GITHUB.md`; escribirlo acá habría
   re-filtrado exactamente lo que se estaba purgando), presente en un único commit (`f1dc9a5`,
   introducido) y revertido a placeholder en `8b0f431` — exactamente la cronología que ya documentaba
   la Ronda 7.
3. **Primer intento (desde el sandbox de Cowork) falló** — no por error de comando, sino porque el mount
   de este sandbox sobre el filesystem real de Windows de Enzo no tiene permisos para hacer `unlink` sobre
   archivos dentro de `.git/refs/` y `.git/logs/refs/` (mismo tipo de desincronización de mount ya
   documentado en rondas anteriores, pero esta vez bloqueando una escritura real, no solo dando falsos
   positivos de lectura). `git-filter-repo --force` abortó a mitad de camino con `fatal: unable to unlink
   ...git update-ref failed`. Diagnóstico posterior confirmó que ningún ref se movió (todos los hashes
   intactos) — el intento dejó basura "dangling" inofensiva y varios `.lock` huérfanos, pero no corrupción.
   **Lección:** operaciones de escritura pesada sobre `.git/` (no solo lectura) no son seguras desde este
   sandbox contra el mount de Enzo; deben ejecutarse directo en su máquina.
4. Enzo limpió los `.lock` huérfanos él mismo (confirmando antes, en el Administrador de Tareas, que no
   había ningún proceso git corriendo), instaló `git-filter-repo` vía `pip` en su Windows, y corrió la
   purga directo en su Git Bash.
5. **Casi-incidente real, detectado a tiempo:** el primer intento de Enzo de correr `git filter-repo` se
   ejecutó en la terminal equivocada — el prompt mostraba `~/Projects/Agentwatch/arqui261-grupo3
   (seccion8-limitacion-rollback)`, un repositorio de otro curso/equipo, no ARGOS. El comando falló solo
   porque `replacements.txt` no existía ahí (`FileNotFoundError`), no por ninguna protección real — con
   `--force`, si el archivo hubiera existido, se habría reescrito el historial de ese otro proyecto sin
   ningún motivo. Detectado por revisión directa del prompt de la terminal antes de reintentar. **Lección
   para cualquier operación destructiva futura: pedir `pwd` confirmado en texto antes de cada comando de
   riesgo, nunca asumir que la terminal activa es la esperada cuando hay múltiples proyectos abiertos.**
6. Confirmado el directorio correcto (`/c/Users/enziz/Projects/argos`), la purga corrió limpia:
   `git filter-repo --replace-text replacements.txt --force` → 111 commits parseados, reescritos en 0.8s,
   repack sin errores. `HEAD` de `chore/oss-transformation` pasó de `cca8ba0` a `d830a0b` (incidentalmente
   también aplicó el `--replace-text` de forma correcta sobre `main` y `feature/lab/p4-lab-real`).
7. Verificación real antes de cualquier push: `git log --all -p | grep "<prefijo numérico del bot ID>"`
   → vacío (cero apariciones del token real en todo el historial reescrito, ni siquiera su prefijo).
   `grep "REDACTED_TELEGRAM_BOT_TOKEN"` → 2 apariciones, exactamente en los 2 commits que correspondían.
8. `filter-repo` había removido el remote `origin` (comportamiento de seguridad por diseño de la
   herramienta). Re-agregado, y `git push origin --force --all` + `--force --tags` aplicado.

### Resultado y efecto secundario a resolver

Push exitoso: `chore/oss-transformation` (→`d830a0b`), `feature/lab/p4-lab-real` (→`27cc7dd`) y `main`
(→`9a97ea9`) quedaron con `forced update` en GitHub — el historial público ya no contiene el token real
en ningún commit alcanzable.

**Efecto secundario no buscado, detectado tras el push:** `--force --all` empujó también 9 ramas que
hasta ahora eran puramente locales de Enzo y nunca se habían compartido a `origin` (`chore/finalizacion-
readme-limpieza`, `feat/demo-polish`, `feature/fase-1-live-mode` a `-6-console`, `feature/p4/approval-
console`) — el push las reporta como `[new branch]`. Son checkpoints del propio desarrollo de ARGOS (no
contenido ajeno), y ya pasaron por el mismo `--replace-text` que limpió `main`, así que no reintroducen
el token. Pendiente confirmar con Enzo si las deja públicas (son historia real del proyecto, consistente
con ya ser un repo público) o prefiere borrarlas de `origin` (`git push origin --delete <rama>`) por no
haber sido una decisión explícita.

**Nota técnica pendiente de que Enzo entienda, no accionable:** GitHub puede seguir sirviendo el commit
viejo (`f1dc9a5`, con el token real) por hash directo durante un tiempo, hasta que su propio garbage
collector interno lo recolecte — un force-push cambia qué es *alcanzable* desde las ramas, no borra
instantáneamente objetos huérfanos del lado de GitHub. Irrelevante en la práctica porque el bot ya está
borrado (el string no sirve para nada), pero no es "cero rastro inmediato".

**Acción pendiente de Enzo, urgente:** avisar a Yohamin, Diego y Angeles que sus clones locales de ARGOS
quedaron con historial divergente — necesitan **re-clonar**, no `git pull` (un pull/merge normal sobre
historial reescrito genera conflictos masivos o reintroduce commits viejos con el token).

**Sección 1.2 de `MEMORIA_AUDITORIA_GITHUB.md` queda resuelta** (token purgado del historial, no solo
del working tree) — no editado ese archivo todavía para reflejarlo, pendiente de una pasada de
consolidación.

## Ronda 12 (2026-07-15): ejecución completa del prompt maestro de transformación OSS (Fases 0-7)

Esta ronda la ejecutó **Claude Code** (shell/git real, no Cowork), corriendo el
`PROMPT_CLAUDE_CODE_TRANSFORMACION_OSS.md` (Ronda 10) de punta a punta. Las 8 fases (0-7) quedaron
**cerradas**, cada una en su propio PR a `main`, cada PR con **CI real verde** en el runner de GitHub
antes de mergear. Trabajo sobre el branch `chore/oss-transformation`.

### Qué se hizo, fase por fase

- **Fase 0 — auditoría + crítica del plan.** Primera sesión que corrió la suite de verdad:
  línea base **488 items verdes** (441 del default + 47 de ml/ui/forensics). Se confirmó que "441"
  era correcto (350 funciones `def test_` expanden a 441 por parametrización). Crítica al plan del
  prompt aplicada (Fase 6 mal especificada — gitignore no basta; `datetime.UTC` no rompe en 3.11+;
  console/ ya más maduro de lo asumido; +hallazgos fuera del prompt como `ui/README.md`).
- **Fase 1 — honestidad de bajo riesgo.** "Repositorio privado durante el curso; público al cierre"
  corregido en 7 sitios (el repo ya era público). Copyright del README alineado con LICENSE.
- **Fase 2 — CI/CD (primer pipeline del repo).** `.github/workflows/ci.yml`: test matrix ubuntu
  py3.11/3.12 + lint (ruff + `mypy argos_contracts`). **Ruff baseline**: 157 auto-fixes + 52 triados
  a mano (UP042 ignore repo-wide por los enums `str,Enum` del contrato; per-file-ignores acotados;
  noqa justificados). `testpaths` completado (ml/ui/forensics ahora en un solo `pytest`). Badge real.
- **Fase 3 — portabilidad + BUG-1 (toca `soar/`, con tests).** `inventory.py` config-driven
  (`ARGOS_HOST_INVENTORY`, fail-loud, boot-time validation). BUG-1: timeout del hook LLM configurable
  (`LLM_TRIAGE_TIMEOUT_SECONDS`) + fail-soft diferenciado por causa (R-2 intacto). Suite 488→507.
- **Fase 3.5 — el CI real cazó un bug que lo local no.** El primer run en GitHub falló:
  `ui/streamlit_app/lib/` (código real: config/incident_loader/view_model) estaba tragado por el
  patrón `.gitignore` `lib/` sin anclar → **nunca se había commiteado**, nadie que clonara podía
  correr la UI. Fix: anclar `/lib/` `/lib64/` + commitear los 4 huérfanos. Tres runs hasta verde.
- **Fase 4 — honestidad de la documentación (20 archivos, docs-only).** Framing "replica/mirrors la
  arquitectura" → "toma el patrón a escala de laboratorio". Backend `gpt-4o-mini` stale → NVIDIA NIM
  en 10 docs activos; fallback Llama marcado diferido/no-cableado en todos lados. THREAT_MODEL
  (T-030 US/China resuelto, Week 13 no realizada), SAD (CI real vs Atomic Red Team no-corrido,
  heartbeat 60s, 0.74 preliminar), EXPOSICION chips INFRA, PROJECT_STATUS banner, ui/README roadmap.
- **Fase 5 — consola web (toca `soar/audit/`, con tests).** Tabla `audit_events` append-only + write
  genérico en `PostgresSink.emit()` (los agregados perdían el historial evento-por-evento). Consola:
  timeline de auditoría navegable (endpoint opcional, nunca 503, degrada solo-Redis), ráfaga
  multi-capa, indicador de staleness, columnas Rol/Respondió. Verificado con harness node+jsdom
  sobre el `app.js` real (16 checks del DOM). Suite 507→519.
- **Fase 6 — limpieza de portafolio.** `SECURITY.md` (GitHub Private Vulnerability Reporting);
  `git rm --cached` de 6 andamiajes de curso; README a tono portafolio (badge Deadline fuera, equipo
  → sección Créditos discreta, framing de curso aligerado); CONTEXT/EVALUATION_CRITERIA marcados
  "histórico del curso".
- **Fase 7 — verificación final + cierre (esta ronda).** Suite completa **519 passed**. Barrido de
  secretos sobre todo lo agregado en las 6 fases (limpio). Confirmado que los 3 archivos privados
  gitignoreados no entraron a ningún commit. Este cierre.

### Fuera de alcance (a propósito, documentado)

Artefactos de curso marcados "ilustrativos/desfasados por diseño" (ADR-0011): la narrativa profunda
OpenAI+Ollama de `manual-p1/p2.md`, las líneas de backend de los 4 HTMLs de equipo salvo la del
patrón, el ADR-0001 mismo (registro versionado), los diagramas `.drawio`, y los changelogs históricos
(se agregan filas nuevas, no se reescribe historia). Track A (lab de 3 VMs) sigue sin bootear (C19) —
es una limitación de entorno, no del código, ya documentada.

### Nota sensible (decisión explícita de Enzo)

El párrafo "🔴 Hallazgo más serio" de la Ronda 9 se **suavizó** por decisión directa de Enzo: ya no
menciona ningún detalle identificable del hallazgo de privacidad sobre un ex-integrante. El tema
queda gestionado por Enzo fuera de este archivo; sesiones futuras: no investigar ni documentar más
sobre identidades no acreditadas públicamente en el historial de git — es terreno exclusivo de Enzo.

### En manos de Enzo al cierre

- Habilitar **Private Vulnerability Reporting** en Settings→Security del repo (lo que promete
  `SECURITY.md`).
- Mergear el PR de Fase 7.
- Las acciones de la Ronda 11 que siguen siendo suyas (9 ramas force-pusheadas, aviso de re-clone al
  equipo, `replacements.txt`).

**Estado final: el prompt maestro completo (Fases 0-7) está ejecutado.** El repo pasó de tarea de
curso a pieza de portafolio open-source con CI real verde, código y documentación honestos, consola
funcional y limpieza de andamiaje — sin reescribir historia de git (más allá de la purga del token de
la Ronda 11, que fue de Enzo) y sin tocar las líneas rojas.
