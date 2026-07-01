<!--
  PLAN DE EJECUCION — entrega 1-jul-2026. Tooling de equipo, no es entregable.
  Lo genero P1 (Enzo) con apoyo del arquitecto. Borrar antes del push publico si no se versiona.
  Fuente de verdad sigue siendo: argos_contracts v1.1.0 > ADRs > codigo en soar/ > ARGOS_RUNBOOK_MAESTRO.html > manuales.
-->

# PLAN DE EJECUCION — ARGOS, entrega 1-jul-2026

## Actualización 2026-06-29 (post Fase 0)

Claude Code corrió este plan por el flujo auditar → construir → auditar y cerró la **Fase 0** (contradicciones + fixes): branch `feature/lab/p4-lab-real`, 6 commits, **420 tests verdes**, contracts intactos, en review. La auditoría corrigió tres cosas que yo había puesto mal o de menos, y eso es el proceso funcionando:

- **C3 era falsa premisa.** La key LLM ya estaba cableada; el bug real era el modelo (`gpt-oss-120b` sin prefijo `openai/` daba 404). Resuelto (C10).
- **C5 ya estaba bien en código.** `handlers.py` deduplica por identidad; el gap real es un solo chat_id de Telegram. Sin fix de SOAR.
- **C1 es runtime-safe.** La criticidad se resuelve por `host_id`, no por IP, así que cambiar la subnet no toca el routing del SOAR. Menos riesgo del que temía.
- **C11 (nueva):** los `POSTGRES_*` servían el audit-DB y el víctima a la vez. Separados (`POSTGRES_*`=audit, `VICTIM_PG_*`=víctima).
- **LLM:** primario ahora `openai/gpt-oss-120b` (~0.9s) + fallback kimi. A 0.9s desaparece el riesgo de latencia del panel LLM en vivo.

**Conectividad al 29-jun:** verde el app-core y el LLM. Amarillo Telegram (envío sí, interactivo necesita ngrok + 2 chat_ids) y JWT (sin firma, secreto en placeholder). Rojo Twilio (la llamada, credenciales placeholder), Discord (vacío), Wazuh y la DB víctima (greenfield, Fase 1 sin arrancar).

**Fase 1A (core + víctima Linux) escrita y commiteada; boot real en curso.** El registro canónico cross-sesión vive en `MEMORIA_ARGOS.md`.

**Honestidad sobre qué es real en el lab (C18, ALTO IMPACTO):** la capa Sigma (L1) NO está desplegada — los 10 `.yml` no están convertidos a formato Wazuh (no existe `local_rules.xml`) y el provision del manager solo despliega `canary_rules.xml`. Por eso, en el lab, **solo el canary (L3) y el active-response son reales**. UC-02 es el único end-to-end totalmente real; UC-01 dispara por canary (no por Sigma vssadmin); UC-04/06/07/08 van por **injector** (pipeline real de tiers/HITL/audit, detección simulada). **Fase 1B (víctima Windows) DIFERIDA** — va como video; su valor único eran reglas Sigma que igual no dispararían.

---

## 0. Veredicto, sin vueltas

Elegiste correr los 8 UC sobre 3 VMs reales con active-response en vivo. Tu propio `docs/ARGOS_RUNBOOK_MAESTRO.html` (el documento unico de verdad del equipo) dice lo contrario: la demo garantizada es `docker compose` local, 5 UC, sin Telegram en vivo, sin ngrok, sin internet, con la consola web auto-refrescando. El `lab/` no existe en codigo, es un README. Vas a construir infraestructura greenfield completa en 3 dias, y a apostar la nota a que corra limpia en vivo.

No te pido que cambies la decision. Te armo el plan para cumplirla. Pero el plan tiene dos pistas y un punto de corte, porque cualquier ingeniero senior que monta un Wazuh real de 3 VMs en 3 dias mantiene el camino simulado como respaldo. Si el lab real no esta verde la noche del 30, salis con el simulado. Esa no es una concesion mia, es lo que tu runbook ya recomienda.

- **Track A (lab real):** lo que elegiste. Critical path = infraestructura. Riesgo alto.
- **Track B (spine simulado):** ya existe y funciona. Tu demo garantizada. Costo de mantenerlo: ensayarlo.
- **Go/No-Go: 30-jun 20:00.** Criterios abajo. Pase lo que pase, Track B queda grabado como backup en video.

## 1. Estado real (no el del PROJECT_STATUS vencido)

F1-F6 estan commiteados y son reales, no scaffolding. Lo verifique contra el git log y el codigo.

Funciona hoy, sin lab:
- `docker compose up` Perfil A: redis, postgres (argos_audit 17.5), soar, console, llm-triage.
- `scripts/demo_injector.py` con 5 UC (uc01, uc02, uc04, uc06, uc07) por el pipeline real (tiers, correlacion, audit) con `SimulatedExecutor`.
- Consola web read-only en `:8080`, auto-refresh ~1.5s.
- Cliente NVIDIA real (`/triage`), bridge de normalizacion, scripts AR Windows+Linux, los tres canales de notificacion en codigo.

No existe (greenfield):
- Todo el `lab/`: sin Vagrantfile, sin provisioning.
- El scorer ML L2 en vivo (solo existe el primitivo de publicacion).
- Postgres victima `app_prod` + data IntiBank (el DDL esta en ADR-0009, el `init.sql` no).
- Simulador de UC-03 (variante WMIC que evade Sigma) y app Flask vulnerable de UC-08.

## 2. Las 7 contradicciones que hay que resolver ANTES de construir

Estas son las que Claude Code te va a preguntar (no las va a asumir). Te doy mi recomendacion para que llegues decidido. Resolverlas mal arruina el provisioning entero.

| # | El choque | Impacto | Mi recomendacion |
|---|-----------|---------|------------------|
| C1 | **Subnet del lab.** `.env`/`inventory.py` dicen `10.0.0.0/24`; el runbook maestro dice `192.168.56.0/24` y aclara que 10.x son solo fixtures de test | Si no se fija una sola, nada se conecta en el lab | Lab real = `192.168.56.0/24` (default host-only de VirtualBox): mgr .10, win .20, lin .21. Actualizar `.env` e `inventory.py` o separar fixtures explicitamente |
| C2 | **OS victima Windows:** `inventory.py:50` dice Windows 11; ADR-0015 y el HTML dicen Windows 10 | Cosmetico, pero rompe el provisioning si el box no coincide | Windows 10 (box mas liviano y estable en Vagrant). Corregir `inventory.py` |
| C3 | **`.env`: la key LLM esta mal nombrada.** El cliente lee `OPENAI_API_KEY`, pero la key real esta en `OPENAI_API_KEY_DeepSeek` | El LLM real NO levanta hasta copiarla | Copiar el valor a `OPENAI_API_KEY`. Trivial y bloquea el demo. Hacerlo ya |
| C4 | **8 UC especificados vs 5 implementados.** El injector cubre uc01/02/04/06/07. UC-03, UC-05, UC-08 no tienen camino reproducible | No podes correr los 8 end-to-end hoy | Nucleo en vivo = los 5 del injector. UC-03 por injector en modo simulado (la logica split-brain es real). UC-05/08 grabados. Ver seccion 5 |
| C5 | **Two-person rule cuenta por status, no por identidad.** Y el `.env` tiene un solo `chat_id` de Telegram | No demostras two-person genuino con un solo aprobador | Cablear >=2 chat_ids en un grupo de Telegram. Evaluar un fix chico en SOAR para contar identidades distintas (sin tocar el contrato) |
| C6 | **Thresholds de tier sin calibrar** (`policies.py`: 0.80, 0.74 marcados preliminares, calibracion Q5/D-1 pendiente) | Los numeros no son empiricos | Aceptar los preliminares para el demo. Declararlo en el informe como calibracion pendiente. No bloquea |
| C7 | **`detection/mitre-mapping.yaml` incompleto** (falta T1485, que la canary emite) | Menor; el bridge ya valida contra `MITRE_WHITELIST` del contrato | Agregar T1485 al yaml. Bajo esfuerzo |

## 3. Seguridad (hacelo hoy, antes que nada)

El `.env` tiene secretos vivos en cleartext: la key de NVIDIA (`nvapi-...`, repetida en varias variables) y el `TELEGRAM_BOT_TOKEN` real. Esta gitignored, pero:

1. Confirma que `.env` nunca entro al historial: `git log --all -- .env` y `git grep nvapi- $(git rev-list --all)`. Si aparece, las claves estan comprometidas para siempre.
2. Rota la key de NVIDIA y el token de Telegram antes de hacer el repo publico. Ya salieron de tu maquina.
3. Limpia el naming: una sola `OPENAI_API_KEY`, sin duplicados confusos.

## 4. Critical path Track A (lab real) por owner

El bloqueante es P4. Nada de detection/SOAR real corre hasta que las VMs y Wazuh esten arriba. Orden y dependencias:

**P4 — infraestructura (dia 1, bloquea a todos)**
1. Resolver C1 (subnet). Sin esto no se provisiona.
2. `lab/Vagrantfile`: 3 VMs (core Ubuntu 22.04, victima Windows 10, victima Debian) en `192.168.56.0/24`.
3. `lab/provision/`: install Wazuh manager systemd en core, enrolar los 2 agentes, red host-only.
4. Postgres `app_prod` en la Debian victima + `init.sql` con schema IntiBank (DDL en ADR-0009) + seed sintetico + `pg_dump` a `/var/backups/postgres/` + pgAudit.
5. `docker compose --profile real up -d` en la core, montando el `alerts.json` real del manager.

**P3 — deteccion y AR (dia 1-2, depende de P4.3)**
6. Desplegar reglas Sigma + canary al manager; FIM `ossec.conf` en los agentes.
7. Instalar scripts AR en los agentes (`argos-isolate/throttle/snapshot/kill`) + `argos-ar.conf` con la IP del manager (sin esa IP, `argos-isolate` aborta por diseno, no aisla a ciegas).
8. Mapeo `host_id -> agent_id` de Wazuh (el executor pasa el target como `agents_list`).
9. UC-03: construir el simulador de variante WMIC que evade Sigma (greenfield), o decidir que UC-03 va por injector simulado.

**P2 — ML y bridge real (dia 2, depende de P4.5)**
10. Scorer ML L2 en vivo (Isolation Forest + OC-SVM) publicando al stream via `ml_publisher`.
11. Validar el bridge tailando el `alerts.json` real (codigo existe, falta probar contra Wazuh real).

**P1 — HITL real y swap (dia 2-3, depende de P4 + P3.7)**
12. Multi-aprobador: grupo Telegram + >=2 chat_ids + ngrok + setWebhook + Approval API publica. C5.
13. Twilio voz (opcional, fragil): cargar credenciales reales o aceptar que la escalacion a t=60s no corre.
14. Swap `ARGOS_EXECUTOR=wazuh` y correr cada UC como ataque real, no por injector.

## 5. Alcance UC realista contra el reloj de 13 min

Los 8 UC son 19-20 min segun tu `USE_CASES.md`. La exposicion es ~13. No entran. Aun si el lab estuviera listo, tenes que cortar. Propuesta:

- **REAL en el lab (Fase 1A):** canary L3 + active-response sobre la víctima Linux. **UC-02** = único end-to-end totalmente real (canary → bridge → SOAR → `argos-isolate`). **UC-01** dispara **por canary**, no por la Sigma de vssadmin (C18, no desplegada).
- **Por injector (pipeline real tiers/HITL/audit, detección simulada):** UC-01 (variante Sigma), UC-04 (two-person), UC-06 (DDoS), UC-07 (FP cancelado). El injector ya los corre determinista; el lab NO los detecta porque la Sigma no está en el manager (C18).
- **UC-03 (centerpiece split-brain):** es tu mejor pieza, pero no tiene simulador y necesita 4 aprobadores. Corrértelo por injector en modo simulado muestra la logica real de split-brain y conservative-wins sin depender del ataque en VM. Recomiendo esto, no construir el simulador WMIC en 3 dias.
- **UC-05 y UC-08:** grabados en video, narrados en 1 min cada uno si sobra tiempo.

Comprimi como dice tu propio `USE_CASES.md` §2: UC-02 a 1 min, UC-06 a 1.5 min, y dale el tiempo a UC-04 y UC-07 que son los que muestran HITL.

## 6. Go/No-Go y backup

**Checkpoint 30-jun 20:00.** El lab real pasa si, y solo si:
- Las VMs del lab (core + víctima Linux) levantan con `vagrant up` limpio y el agente reporta al manager (`agent_control -l` Active).
- **UC-02 (canary)** corre end-to-end real (canary FIM -> bridge -> SOAR -> `argos-isolate` ejecuta en la VM) una vez, repetible. (UC-01 "real" = solo canary; la Sigma vssadmin no está desplegada, C18 → va por injector.)
- El `demo_reset` deja el estado limpio entre corridas.

Si falla cualquiera: salis con Track B (simulado). Sin discusion, sin improvisar a las 2am.

**Backup obligatorio, pase lo que pase:** graba una corrida completa de Track B (los 5 UC por `docker compose` + injector + consola) el 30 a la tarde. Es tu seguro contra cualquier fallo en vivo el 1.

## 7. Riesgo, dicho de frente

Montar Wazuh real de 3 VMs, con active-response funcionando, ML en vivo, multi-aprobador y 8 UC, en 3 dias, partiendo de un `lab/` vacio, y correrlo limpio frente al evaluador: la probabilidad de que salga sin un fallo visible es baja. El valor de ARGOS no esta en que el iptables corra en una VM real. Esta en la arquitectura: 4 capas, tiers T0-T3, HITL con conservative-wins, audit, R-2. Todo eso lo demostras igual de bien por el camino simulado, que es determinista y no depende de que ngrok o el agente Wazuh cooperen a las 9am. Mi consejo sigue siendo: Track B como demo principal, una VM real para UC-01 como prueba de que el camino real existe, y el resto grabado. Vos decidis.
