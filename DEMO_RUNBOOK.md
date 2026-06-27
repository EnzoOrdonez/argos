# ARGOS — Runbook del demo y del video

Cómo correr ARGOS de punta a punta y grabar el video de la exposición. Dos caminos:

- **Fase A — demo simulado (este documento).** Corre en una sola PC, sin lab, con `SimulatedExecutor`. Es el **respaldo garantizado** y la base del video (ADR-0010 backup narrative).
- **Fase B/C — prototipo real.** Sobre VMs (Windows + DB server Debian) con Wazuh active-response. Ver **ADR-0015** (`docs/decisions/0015-real-prototype-realization.md`).

---

## 0. Prerrequisitos

- **Python 3.11** (el entorno canónico; `pydantic-core` no compila en 3.14).
- **Docker** (para correr Redis). Alternativa sin Docker: Memurai o Redis en WSL.
- (Opcional) **Bot de Telegram** (token + chat id) y/o **webhook de Discord** para que las notificaciones salgan de verdad. Si no hay credenciales, el inyector las omite (fail-soft).

## 1. Setup (una sola vez)

```powershell
cd C:\Users\enziz\Projects\argos
.\.venv\Scripts\Activate.ps1
pip install -e ".[soar,llm,dev,ui]"
```

## 2. Fase A — correr el demo simulado

`scripts/demo_injector.py` corre **todo el flujo de P1 en un solo proceso** (consumer → tier router → playbooks simulados → notificaciones → HITL → audit) y deja el incidente en Redis para que la consola lo muestre. **No hace falta levantar el Approval API ni el consumer aparte.**

**Terminal 1 — Redis real** (la consola necesita verlo; `--in-process` usa un fakeredis aislado que la consola NO ve):

```powershell
docker run --rm -p 6379:6379 redis:7
```

**Terminal 2 — la consola** (mismo Redis):

```powershell
cd C:\Users\enziz\Projects\argos ; .\.venv\Scripts\Activate.ps1
$env:REDIS_URL = "redis://localhost:6379/0"
streamlit run ui\streamlit_app\app.py
```

Abre en `http://localhost:8501`.

**Terminal 3 — inyectar los UC** (mismo Redis, **NO** `--in-process`). Las notificaciones salen de verdad solo si seteás las credenciales:

```powershell
cd C:\Users\enziz\Projects\argos ; .\.venv\Scripts\Activate.ps1
# opcional — notificaciones reales:
$env:TELEGRAM_BOT_TOKEN = "..."
$env:TELEGRAM_CHAT_ID   = "..."
$env:DISCORD_WEBHOOK_URL = "..."

.\.venv\Scripts\python.exe scripts\demo_injector.py uc01 --redis-url redis://localhost:6379/0
.\.venv\Scripts\python.exe scripts\demo_injector.py uc04 --redis-url redis://localhost:6379/0
.\.venv\Scripts\python.exe scripts\demo_injector.py uc07 --redis-url redis://localhost:6379/0
.\.venv\Scripts\python.exe scripts\demo_injector.py uc02 --redis-url redis://localhost:6379/0
.\.venv\Scripts\python.exe scripts\demo_injector.py uc06 --redis-url redis://localhost:6379/0
```

Cada inyección imprime un trace en la terminal (UC, votos HITL, tier, decisión, política, acciones simuladas, audit) y deja el incidente en Redis; la consola lo lista en el sidebar al refrescar (~1.5s).

## 2-bis. Variante docker-compose (Fase 5, Perfil A)

Todo el core en contenedores en vez de los 3 terminales manuales. Detalle completo en `deploy/README.md`.

```powershell
# raíz del repo; .env con POSTGRES_PASSWORD (+ OPENAI_API_KEY si querés el LLM real)
docker compose up -d                    # redis, postgres, soar, console, llm-triage
docker compose ps                       # esperar (healthy)
python scripts\demo_injector.py uc04 --redis-url redis://localhost:6379/0
# consola web: http://localhost:8080    (Streamlit fallback: docker compose --profile fallback up -d  ->  :8501)
```

Camino real (Wazuh instalado en la VM core): `ARGOS_EXECUTOR=wazuh docker compose --profile real up -d`
(suma el `bridge`, que tailea `/var/ossec/logs/alerts`). Swap simulado↔real = `ARGOS_EXECUTOR` + el perfil
`real`. La consola web (Fase 6, `:8080`) reemplaza a la Streamlit; ambas leen el mismo Redis.

## 3. Qué muestra cada UC

| UC | Escenario | Host | Desenlace | Política |
|----|-----------|------|-----------|----------|
| `uc01` | Ransomware en 3 capas casi simultáneas (T1486) | `WIN-VICTIM-01` (endpoint) | `EXECUTE_ISOLATION` (T0 auto) | auto-execute |
| `uc02` | Canary sola (Capa 3), zero-FP | `WIN-VICTIM-01` | `EXECUTE_ISOLATION` (T0 auto) | auto-execute |
| `uc04` | Ataque a la DB del banco (L1+L2) | `LIN-VICTIM-01` (DB Debian, production-critical) | `EXECUTE_ISOLATION` | **two-person-rule** (2 aprueban) |
| `uc06` | DDoS volumétrico (T1498), fast-path | `EDGE-FW-01` | `EXECUTE_ISOLATION` (T0 auto) | auto-execute |
| `uc07` | SELECT masivo legítimo (falso positivo) | `LIN-VICTIM-01` | `NO_ACTION` (el humano rechaza) | two-person-rule |

> Nota: `demo_injector` casta los votos del escenario y resuelve en ~1s, así que la consola muestra cada incidente **ya resuelto** (ideal para un recorrido). Para el teatro en vivo (reloj de 60s corriendo + aprobar en el momento) usar el **modo `--live`** (§5).

## 4. Grabar el video

- **Rápido (built-in Windows 10):** Xbox Game Bar — `Win+Alt+R` arranca/para; graba la ventana activa; se guarda en `Vídeos\Capturas`.
- **Recomendado para la expo:** OBS Studio (gratis) — pantalla completa con terminal + consola lado a lado + micrófono para narrar.

**Guion sugerido** (mapea a la rúbrica "recursos/simulaciones" + "dominio del tema"):

1. Intro (10s): ARGOS = XDR multivector que defiende a IntiBank; 4 capas + SOAR con aprobación humana.
2. `uc01` — ransomware en 3 capas → T0 auto-aislamiento sub-segundo (fast-path).
3. `uc04` — ataque a la DB (production-critical) → two-person rule, 2 aprueban; mostrar la matriz de decisión en la consola.
4. `uc07` — SELECT masivo legítimo → el humano **rechaza** → `NO_ACTION` (el HITL atrapa un falso positivo).
5. Cierre: el audit trail + aclarar que es la corrida **demo-safe** (`SimulatedExecutor`, ADR-0010) y que el prototipo real corre sobre VMs (ADR-0015). Esa honestidad técnica suma.

## 5. Modo en vivo (`--live`) y aprobación por Telegram

El modo `--live` inyecta la alerta **sin** castear los votos y deja el incidente en `AWAITING_APPROVAL` (la ventana de 60s arranca con el **primer** voto, no en la inyección), para aprobar en vivo y ver a la consola resolver en tiempo real. Dos mecanismos: **trigger local** (un script, sin internet — la red de seguridad) y **Telegram real** (vía ngrok). El executor de la contención lo elige `ARGOS_EXECUTOR` (default `simulated`; ver `.env.example`).

### 5.1 Trigger local (sin internet — la red de seguridad)

Inyectá en vivo y aprobá/rechazá desde otra terminal, sin Telegram ni ngrok (mismo Redis que la consola):

```powershell
# 1. Inyectar dejando el incidente EN ESPERA (uc04 = two-person; uc07 = el humano rechaza):
.\.venv\Scripts\python.exe scripts\demo_injector.py uc04 --live --redis-url redis://localhost:6379/0
#    -> imprime el incident_id (INC-YYYY-MM-DD-NNN) y queda en AWAITING_APPROVAL

# 2. Aprobar/rechazar (two-person: 2 approves DISTINTOS ejecutan; 1 reject cancela):
.\.venv\Scripts\python.exe scripts\live_approve.py --latest --decision approve --email telegram:soc-lead
.\.venv\Scripts\python.exe scripts\live_approve.py --latest --decision approve --email telegram:dba
#    o, para rechazar:  --decision reject --email telegram:compliance
```

`--latest` toma el último incidente del día; o pasá `--incident INC-...`. La consola refleja cada voto y la decisión final al refrescar (~1.5s). Para usar el active-response real en vez del simulado: `$env:ARGOS_EXECUTOR = "wazuh"` (degrada a simulated si faltan las `WAZUH_API_*`). Si además corrés el Approval API (camino Telegram de §5.2), él dueña el reloj de la ventana → agregá `--no-wait`.

### 5.2 Telegram + ngrok (setup, una sola vez para todo el equipo)

> **Fase 1 = modo legacy (sin JWT):** `demo_injector` arma el `TelegramChannel` sin `ApprovalSigner`, así que los botones viajan como `approve:{incident}` sin token firmado. Para que el callback los acepte, corré el Approval API **sin** `ARGOS_JWT_SECRET` en el entorno. El API ejecuta la contención con `SimulatedExecutor` (el swap a `wazuh` del lado del API es Fase 3/5). El trigger local (§5.1) es independiente de esto.

El bot de Telegram es **uno solo, compartido**. `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` van en el entorno de quien manda las notificaciones; con eso ya **salen** (bot → aprobadores). El chat id se saca con @userinfobot o de `getUpdates` (`message.chat.id`).

Para **recibir** el click del botón de vuelta hace falta exponer el Approval API con ngrok, **solo en la máquina que corre el Approval API**:

```powershell
# (el authtoken ya quedó guardado con: ngrok config add-authtoken <token>)

# 1. Approval API corriendo (Redis arriba + REDIS_URL seteado). Usá el Python del venv:
$env:REDIS_URL = "redis://localhost:6379/0"
.\.venv\Scripts\python.exe -m uvicorn soar.approval_api.main:app --port 8003

# 2. En otra terminal, exponé el 8003
ngrok http 8003
#    -> copiá la URL "Forwarding  https://XXXX.ngrok-free.app -> http://localhost:8003"

# 3. Registrá el webhook del bot a esa URL + /telegram/callback (abrir en el navegador):
#    https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://XXXX.ngrok-free.app/telegram/callback
#    -> {"ok":true,"result":true,"description":"Webhook was set"}

# 4. Verificar:   https://api.telegram.org/bot<TOKEN>/getWebhookInfo
#    Reset/quitar: https://api.telegram.org/bot<TOKEN>/deleteWebhook
```

**Ojo:** la URL de ngrok **cambia cada vez que reiniciás ngrok** → repetí el paso 3 con la URL nueva. El webhook es excluyente con `getUpdates`. Esto solo hace falta para la aprobación **en vivo**; el video y el trigger local NO lo necesitan.

### 5.3 Quién hace qué en el prototipo real (equipo)

- **Telegram/ngrok:** NO lo repite cada uno. El bot se crea **una vez** (lo hizo P1); ngrok corre en **una sola máquina** (la del Approval API). Los compañeros que **aprueban** solo tienen que estar en el chat/grupo de Telegram y tocar el botón — no instalan ni configuran nada.
- **Infra por máquina (ADR-0015 Perfil B):** lo que SÍ es por máquina es levantar los servicios/containers asignados (Docker, apuntando a las IPs compartidas) y, en las **víctimas** (VM Windows / DB Debian), instalar el agente Wazuh + los scripts active-response. Eso lo cubre el runbook del prototipo real que genera CC + ADR-0015.

En una frase: **un bot, un ngrok, un Approval API; los demás solo aprueban o levantan su parte de infra.**

## 6. Fase B/C — prototipo real (resumen)

El prototipo real conmuta los **bordes** por entorno, sin tocar `soar/` ni el contrato: feeder `demo_injector` ↔ `bridge` (tail de `alerts.json`), executor `SimulatedExecutor` ↔ `WazuhActiveResponseExecutor` (`ARGOS_EXECUTOR=simulated|wazuh`). Víctimas: **VM Windows 10** (endpoint, UC-01/02/05) y **DB server Debian + PostgreSQL** (production-critical, UC-04/07/08). Detalle completo en **ADR-0015**.

## 7. Troubleshooting

- **`docker` no instalado** → Memurai / Redis en WSL, o `--in-process` (pero la consola no lo verá).
- **Consola vacía** → confirmá que el inyector corrió con `--redis-url` (NO `--in-process`) apuntando al **mismo** `REDIS_URL` que la consola.
- **`BUSYGROUP ... already exists`** en logs → inofensivo; o resetear: `redis-cli XGROUP DESTROY events:normalized soar-router ; redis-cli XGROUP CREATE events:normalized soar-router 0 MKSTREAM`.
- **`UnicodeEncodeError: charmap`** (en simuladores de P3, no en `demo_injector`) → `$env:PYTHONUTF8 = "1"`.
