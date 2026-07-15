<!--
  MEMORIA DE PROYECTO — ARGOS. Registro cross-sesion para re-aterrizar rapido.
  Tooling de equipo, NO es entregable. Mantener actualizado al cierre de cada sesion.
  Fuente de verdad del codigo: argos_contracts v1.1.0 > ADRs > soar/ > ARGOS_RUNBOOK_MAESTRO.html > manuales.
-->

# MEMORIA — Proyecto ARGOS

**Última actualización:** 2026-06-29 · **Entrega:** 2026-07-01 (movida desde 28-jun, antes 13-jun).

## Qué es ARGOS

XDR multi-capa open-source que defiende la base PostgreSQL del banco ficticio IntiBank. Cuatro capas de detección (Sigma L1, ML L2, canary L3, LLM L4 enrichment) más un SOAR con respuesta y aprobación humana (HITL) y tiers T0-T3. Proyecto de Tópicos Avanzados de Ciberseguridad, Universidad de Lima, 2026-1. Entregables: demo en vivo, informe técnico, exposición de ~13 min.

## Equipo

Enzo Ordoñez (P1, líder): SOAR/HITL, LLM, argos_contracts, Approval API JWT, consola, coordinación. Sebastian (P2): ML. Angeles (P3, en docs aparece "Angeles"; el brief inicial decía "Nicole", confirmar nombre): Sigma + canary + comandos Wazuh active-response. Diego (P4): lab, infra, video. Yohamin: apoyo P2 + forense.

Cómo trabajamos: Enzo decide. El arquitecto (esta sesión) planifica y critica. Claude Code codea con el prompt crítico (auditar → construir → auditar, parar y preguntar ante contradicción). Tanto el arquitecto como Claude Code tienen el MCP de Docker, que es automatización de navegador (Playwright) + gestión de catálogo MCP, NO control de contenedores del host. El despliegue real lo corre Claude Code o Enzo en la máquina.

## Decisión estratégica central

Enzo eligió correr la demo del 1-jul sobre un lab real de 3 VMs con active-response en vivo, en contra de la recomendación del runbook maestro y del arquitecto (que recomendaban la demo simulada local). Forma final: híbrido. Windows 10 en VM desechable con snapshot (víctima), manager y víctima Linux en VM. El harness simulado (Track B) queda como red de seguridad obligatoria y se graba como backup el 30-jun. Go/No-Go el 30-jun 20:00: si el lab real no levanta limpio, se sale con Track B.

**Modelo final del demo (decidido 29-jun, post-C19):** Track B en vivo desde la laptop de Enzo (Docker, Hyper-V ON) + el lab real (canary + AR) como **clip grabado** desde la máquina de Diego (Hyper-V OFF). En una sola máquina, Track A (VirtualBox) y Track B (Docker) son mutuamente excluyentes, así que el respaldo en vivo es un **video, no un switch**. Track B ya está completo, verificado y con guion de grabación.

Por qué containers no reemplazan todo: la víctima Windows no corre en container Linux (UC-01/02/05 son Windows nativos), y un endpoint con agente Wazuh real + auditd + FIM whodata es más fácil y fiel en VM que en container. Containers sirven para los servicios Linux (manager sin indexer, víctima Postgres).

## Decisiones tomadas (con fecha)

- **Lab real 3 VMs híbrido** (29-jun). Track B simulado = backup grabado obligatorio.
- **Subnet 192.168.56.0/24** (29-jun): mgr .10, win .20, lin .21. Windows 10 (no 11).
- **Alcance UC** (29-jun, RECONCILIADO post-C18): lo REAL en el lab = **canary L3 + active-response**. UC-02 = único end-to-end totalmente real; UC-01 dispara por canary (no por Sigma vssadmin). UC-01(Sigma)/04/06/07/08 por **injector** (pipeline real tiers/HITL/audit, detección simulada — la Sigma NO está desplegada). UC-03 injector simulado; UC-05/08 grabados. **Fase 1B (Windows) DIFERIDA → video.** Comprimir narración ~13 min (USE_CASES §2).
- **Modelo de demo** (29-jun, post-C19): Track B en vivo + lab grabado. El respaldo es un video, no un switch a vivo (C19).
- **Guion de grabación** (29-jun): `GUION_GRABACION_TRACKB.html`, español, narrador por UC (Enzo=decisión, Sebastian=ML, Angeles=detección, Diego=opera), comandos copiables, salida esperada fiel al injector, verificación (smoke 8 UC `--in-process` + pytest 441), y encuadre honesto del dual-path de uc03.
- **Two-person** (29-jun): por injector (castea 2 identidades, el código ya deduplica por email) + Telegram real opcional si ngrok levanta.
- **LLM** (29-jun, ADR-0001 v3.1): primario `openai/gpt-oss-120b` (~0.9s, fiable) + fallback `moonshotai/kimi-k2.6`. deepseek-v4-pro descartado por latencia (15-21s, un timeout a 40s). El id NVIDIA requiere prefijo `openai/` o da 404. **Actualización 30-jun:** la key Qx4J quedó revocada/sin créditos y el endpoint gratis de NVIDIA resultó inestable (gpt-oss timeout, kimi 429). Modelo de trabajo final para el demo = `google/gemma-4-31b-it` (su free endpoint estaba disponible). Cache LLM de los 3 UC que llaman al LLM (T1078/T1083/T1190) generada con gemma y guardada en `demo/cached-responses/`; `DEMO_MODE=true` en `.env` para la grabación → el demo sirve la cache y no toca la API. Lección: el script `gen_llm_cache.py` NO lee el `.env` (hay que exportar las `OPENAI_*` en la sesión), y los archivos de cache se acumulan entre runs (no hace falta 3/3 en una sola corrida). Drift a reconciliar: ADR-0001 v3.1 dice gpt-oss primario, pero el que funciona es gemma.
- **Thresholds de tier**: preliminares aceptados para el demo, declarados pendientes en el informe (calibración Q5/D-1).
- **argos_contracts v1.1.0**: INMUTABLE. No se toca.

## Contradicciones C1-C11 (estado al 29-jun)

| # | Qué era | Resolución | Estado |
|---|---------|-----------|--------|
| C1+C8 subnet/IPs | código 10.0.0.x vs runbook 192.168.56.x, octetos en conflicto | Fijado 192.168.56.0/24 (.10/.20/.21). Reescrito inventory.py + .env + diagrama | ✅ resuelta |
| C2 OS Windows | inventory.py Win11 vs ADR Win10 | Win10, + test lock | ✅ resuelta |
| C3 key LLM | yo asumí key mal nombrada → LLM no levanta | FALSA PREMISA: la key ya estaba cableada. El bug real era el modelo (C10) | ✅ refutada |
| C4 alcance UC | injector 5, UC-03/05 sin camino, UC-08 solo atacante | live 5 + UC-03 injector + UC-05/08 grabados | ✅ decidida |
| C5 two-person | yo asumí que contaba por status | PARCIAL FALSA: handlers.py ya deduplica por identidad. Gap real = 1 solo chat_id | ✅ aclarada, sin fix de código |
| C6 thresholds | 0.80/0.74 preliminares | aceptados, declarados pendientes | ✅ decidida |
| C7 T1485 | faltaba en mitre-mapping.yaml | agregada fila al canary XML; ya estaba en MITRE_WHITELIST | ✅ resuelta (cosmético) |
| C9 stream drift | p3_deployment_guide dice events:raw_wazuh; real es events:normalized | PENDIENTE: handoff a P3, corregir la guía o la detección no llega al SOAR | ⚠️ abierta |
| C10 modelo LLM | .env corría gpt-oss-120b sin prefijo = 404 | gpt-oss-120b con prefijo openai/ primario + kimi fallback. ADR-0001 v3.1 | ✅ resuelta |
| C11 POSTGRES (nueva) | POSTGRES_* servía audit y víctima a la vez | separados: POSTGRES_*=audit (compose pinneado) / VICTIM_PG_*=víctima | ✅ resuelta |
| C12 rol PG (nueva) | Claude Code inventó VICTIM_PG_USER=intibank_app en Fase 0 | corregido a `inti_app` (ADR-0009 §2.4); init.sql crea los 6 roles inti_* | ✅ resuelta |
| C13 lab/README (nueva) | README decía argos_demo_prod/PG15 | actualizado a app_prod/intibank + layout lab/postgres/ | ✅ resuelta |
| C14 layout seed (nueva) | README provision/postgres-seed.sql vs ADR-0009 lab/postgres/{init.sql,seed.py} | gana ADR: init.sql + seed.py (Faker es_PE) | ✅ decidida |
| C17 reglas DB (nueva) | faltan pg_mass_read(rows_returned_pct)/pg_balance_update_offhours/pg_sqli_pattern + el bridge no computa rows_returned_pct | DEFERIDO P3/P1; UC-04/07 van por injector | ⚠️ abierta |
| C18 Sigma sin desplegar (nueva) | los 10 .yml Sigma no están convertidos a Wazuh (no existe local_rules.xml); el provision del manager solo despliega canary_rules.xml | DEFERIDO P3 (sigma-cli convert). CONSECUENCIA de alto impacto: en el lab SOLO canary L3 + active-response son reales. UC-02 es el único end-to-end totalmente real; UC-01 dispara por canary (no por Sigma vssadmin); UC-05 parcial (regla 502 nativa sí, Sigma stop-service no); UC-06 necesita su regla desplegada o no detecta; UC-04/07/08 por injector | ⚠️ abierta — ALTO IMPACTO |
| C19 Hyper-V vs VirtualBox (nueva) | en la máquina de Enzo, `vagrant up` falla en `startvm` (E_FAIL exit 1): Hyper-V activo (Docker Desktop/WSL2, vmcompute+vmms running) le quita VT-x a VirtualBox 7.1.4 | BLOCKER host-level (no bug del Vagrantfile, que valida OK). Track A (VBox, Hyper-V OFF) y Track B (docker compose host, Hyper-V ON) son MUTUAMENTE EXCLUYENTES en una sola máquina → alternar = reboot. **DECIDIDO 29-jun: el lab se bootea en OTRA máquina sin Hyper-V (Diego/spare/host Linux); la máquina de Enzo queda para Track B.** Runbook listo (`lab/RUNBOOK_BOOT_1A.md`). Boot real = handoff a Diego (Claude Code no puede correrlo en la máquina de Enzo). | ✅ decidida — boot pendiente en otra máquina |

## Estado de build

- **Fase 0 (contradicciones + fixes): COMPLETA.** Branch `feature/lab/p4-lab-real`, 6 commits, 420 tests verdes, contracts intactos. En review de Enzo.
- **Fase 1A (core + linux-víctima): ESCRITA + commiteada, `vagrant validate` OK. Boot real INTENTADO 29-jun → FALLÓ por C19 (Hyper-V).** ~10 commits. `lab/Vagrantfile`, `provision/wazuh-manager.sh`, `provision/victim-linux.sh` (anti-brick argos-ar.conf), `lab/postgres/init.sql` (schema intibank + 7 tablas + 6 roles inti_*), `lab/postgres/seed.py` (Faker es_PE seed=42, self-check), `lab/inventory.yaml`, `lab/RUNBOOK_BOOT_1A.md`. El box ubuntu/jammy64 descargó/importó OK; `startvm` murió por Hyper-V (C19). **Boot real sigue PENDIENTE** (otra máquina sin Hyper-V o apagar Hyper-V+reboot). Docs honestos: lo real en el lab = canary L3 + AR; resto por injector (C18).
- **Hardening victim-linux pre-boot (29-jun, review Enzo, 4 commits):** F1 **canary paths** — el FIM/auditd vigilaban `/opt/argos/canary` + `passwords.csv`, que NO matchea la regla 100100 (regex por filename) → **UC-02, el único UC totalmente real, no habría disparado.** Corregido a los 4 paths canónicos de `deception/canary-generator/config.yaml` + syscheck de `fim-configs/ossec-linux.conf`. F2 enrolamiento robusto (espera authd 1515 + agent-auth fail-loud + verifica "Connected to the server"). F3 `init.sql` idempotente. F4 guard de egress. F5 `inventory.py` os→Debian 12 + runbook valida con `inti_dba` (no `inti_app`, que ve 5 tablas por GRANTs). pytest 420 verde.
- **Fase 1B (windows-víctima): DIFERIDA — va como video.** NO se escribe `victim-windows.ps1`. Decisión de Enzo (29-jun): su valor único eran reglas Sigma que igual no dispararían (C18).
- **Track B grabable: COMPLETO + VERIFICADO contra compose vivo (29-jun, 4 commits, 427 tests).** `docker compose up -d` levanta los 5 servicios healthy en la laptop (Docker/Hyper-V — el compose SÍ corre acá, a diferencia del lab VBox). Los 6 UC dan el desenlace esperado: uc01/02/06 T0-auto, uc04 two-person 2-approve, uc07 NO_ACTION, **uc03 (CENTERPIECE) split-brain → conservative-wins EXECUTE + conflict_detected + P4 TIMEOUT**, LLM poblado en uc03/04/07. **uc03 nuevo** en `demo_injector` (camino window-close, lógica real de soar). **Cache LLM DEMO_MODE** implementada (`cached_client.py` + `gen_llm_cache.py`, montada ro en el compose; el id del modelo `openai/gpt-oss-120b` requiere prefijo). **Runbook** `docs/RUNBOOK_GRABACION_TRACKB.md`. LLM solo uc03/04/07/(no uc05/08) por R-2. **Opcionales hechos (Enzo, "ambos"):** **uc05** (agent-kill: L1 stop-service + L3 canary → T0 auto) + **uc08** (SQLi: L1+L2 T1190 → T1 auto) en el injector → **8 UC inyectables**, smoke parametrizado. **SQL sink `PostgresSink`** (audit → `argos_audit`, fail-soft, gated por `ARGOS_AUDIT_SQL_DSN`) — **fila real verificada** contra el Postgres del compose (audit_incidents + audit_responses). +psycopg en pyproject. **441 tests verde.** (Ojo: si el volume postgres es viejo, `down -v` para re-inicializar el rol `argos`.)

App-core real y testeado: argos_contracts, soar/ completo (consumer events:normalized campo `payload`, policies, quorum, playbooks/wazuh), active-response/{linux,windows} (6+6 scripts, anti-brick real), Sigma L1 (11 reglas), canary L3, llm_triage (cliente NVIDIA real), demo_injector (5 UC), compose Perfil A.

Greenfield: todo `lab/`, victim Postgres app_prod + seed IntiBank, simulador UC-03 (WMIC), app Flask víctima UC-08, daemon ML L2 en vivo (existe librería + demo de consola, no servicio continuo).

## Conectividad de canales (al 29-jun, leído del .env)

| Canal | Estado | Detalle |
|-------|:------:|---------|
| LLM gpt-oss-120b | 🟢 verde | key OK, probe 200 a 0.9s. Smoke /triage end-to-end en curso. 0.9s < corte SOAR de 5s, mata el riesgo de latencia que temía el runbook |
| App-core / SOAR / injector | 🟢 verde | 420 tests, demo_injector 5 UC determinista |
| Telegram | 🟡 amarillo | token real, 1 solo chat_id. Envío sí; aprobación interactiva necesita URL pública (ngrok) + setWebhook; two-person necesita ≥2 chat_ids |
| JWT botones | 🟡 amarillo | ARGOS_JWT_SECRET placeholder → corre sin firma (legacy). Setear secreto si querés mostrar firma real |
| Email | 🟡 amarillo | MailHog local, post-facto, nunca en path crítico |
| Twilio (la llamada) | 🔴 rojo | credenciales placeholder, sin número, sin teléfonos. La escalación de voz a t=60s NO suena sin setup. Trial exige verificar números |
| Discord | 🔴 rojo | webhook y role vacíos. No dispara |
| Wazuh | 🔴 rojo | todo greenfield (Fase 1). Bridge y anti-brick en código OK. C9 (drift de stream) a corregir |
| Victim DB IntiBank | 🔴 rojo | greenfield (Fase 1.5). DDL en ADR-0009. Data sintética (sin PII real). Usar seed mínimo (~10k filas), no el volumen completo (3GB/10min = timeout) |

## Seguridad

`.env` nunca entró al historial de git (verificado), la key real `nvapi-Qx4J...` nunca leakeó (solo el placeholder en history). Igual, antes de hacer el repo público: rotar la key NVIDIA y el token Telegram, y limpiar el naming (3 variables con el mismo valor de key: OPENAI_API_KEY, DeepSeek_V4_PRO_API_KEY, y la duplicada). POSTGRES_PASSWORD y ARGOS_JWT_SECRET siguen en placeholder.

## Riesgos clave y mitigaciones

- **VM Windows = poste largo.** Box pesado, WinRM frágil en Vagrant, 3 VMs en 16GB sin headroom (ADR-0015 eligió manager-only por RAM). Mitigar: `vagrant up` + snapshot dorado pre-demo, nunca cold boot en vivo. UC-01/02/05 grabados como fallback.
- **Anti-brick depende de un side-effect.** Sin `argos-ar.conf` (MANAGER_IP) en cada agente, `argos-isolate` no-opea silencioso. Escribirlo como paso asertado en ambos provision.
- **Twilio y Telegram interactivos son lo más frágil en vivo.** El runbook puso Twilio Voice último en el orden de sacrificio. No depender de la llamada real en vivo; injector + grabado.
- **Go/No-Go 30-jun 20:00.** Pasa solo si las 3 VMs levantan, ambos agentes reportan, y UC-01 corre end-to-end real repetible con reset limpio. Si no, Track B.

## Invariantes que no se tocan

argos_contracts sellado. Stream `events:normalized` campo `payload` (no `data`). `source_layer` = layer_1/2/3. `technique_mitre` en `MITRE_WHITELIST`. `argos-isolate` whitelistea la IP del manager (192.168.56.10) antes del block-all o aborta. R-2: el LLM nunca bloquea la contención. Todo se valida en `.venv` (el Python del sistema no tiene las deps). Comandos AR: argos-throttle/snapshot/isolate/kill.

## Pendientes (handoffs y deudas)

- **C9 (P3):** corregir `events:raw_wazuh` → `events:normalized` en `detection/p3_deployment_guide.md`, o la detección no llega al SOAR.
- **Smoke /triage real** contra gpt-oss end-to-end (validar parseo de TriageResponse, no solo el probe pelado). En curso.
- ~~VICTIM_PG_USER=intibank_app~~ → corregido a `inti_app` (C12, ADR-0009 §2.4). ✅
- **C17/C18 (P3/P1):** reglas Sigma DB + `rows_returned_pct` en el bridge + `sigma-cli convert`→`local_rules.xml`. Condicionan UC-04/07 *live*; por ahora van por injector.
- **`vagrant up` real de Fase 1A → HANDOFF a Diego en máquina sin Hyper-V** (decidido 29-jun, C19). Seguir `lab/RUNBOOK_BOOT_1A.md`: boot core+linux, pasar gates (agente Active, DB app_prod, canary→events:normalized, anti-brick). Reportar qué se rompe de verdad (provision no testeado contra Wazuh/PG reales).
- ~~Fase 1B~~ → DIFERIDA a video (no se construye).
- **Rotar/limpiar .env** pre-público.
- **Memoria de Claude Code** `project_deadline_28jun` quedó stale (la entrega es 1-jul).
- **uc03 dual-path (defender en la exposición):** el motor real ejecuta al primer approve (conservative-wins); uc03 se conduce por el cierre de ventana para mostrar el conflicto + el TIMEOUT (lógica real `finalize_after_window`). Aclarar en una frase de ADR-0006 + el informe cuál camino es canónico. Tener lista la respuesta a "si uno solo aprueba, ¿espera o actúa?".

## Documentos de referencia en el repo

`PLAN_EJECUCION_1JUL.md` (plan de ejecución), `PROMPT_CLAUDE_CODE_1JUL.md` (prompt para Claude Code), `docs/ARGOS_RUNBOOK_MAESTRO.html` (doc único de verdad del equipo), `docs/decisions/` (ADRs, sobre todo 0001 v3.1, 0003, 0006, 0007, 0009, 0010, 0011, 0012, 0013, 0014, 0015), `docs/use-cases/USE_CASES.md`, `argos_contracts/` v1.1.0, `docs/RUNBOOK_GRABACION_TRACKB.md` (runbook de grabación Track B), `GUION_GRABACION_TRACKB.html` (guion narrado por UC para la grabación y la exposición).
