# ARGOS — Instalación del vector SSH brute-force (genérico)

> Documento único de instalación end-to-end para el vector v1 de ARGOS: detección y
> respuesta a **fuerza bruta SSH (MITRE T1110 / T1021.004)** contra un host Linux que vos
> configurás — no una VM de laboratorio, no una base de datos de banco. Objetivo: de cero a
> la primera detección real siguiendo solo este documento (RNF-5).

## Qué levanta

`docker compose --profile real up -d` corre, en tu máquina, el core de ARGOS **más** un Wazuh
manager contenido:

| Servicio | Rol | Puerto |
|---|---|---|
| `wazuh-manager` | Manager Wazuh (manager-only, sin indexer/dashboard). Recibe eventos del agente, aplica la regla SSH y escribe `alerts.json`. | 1514/1515 (agentes), 55000 (API) |
| `bridge` | Tail-ea el `alerts.json` del manager (volumen compartido) → normaliza → `events:normalized` en Redis | — |
| `redis` | Cola de eventos | 6379 |
| `soar-consumer` | **Daemon que drena el stream**: correlación + tier router + respuesta | — |
| `soar` | Approval API (callbacks de aprobación: Telegram/consola) | 8003 |
| `console` | Consola web (incidentes en vivo) | 8080 |
| `postgres` | Auditoría append-only (`argos_audit`) | 5432 |
| `llm-triage` | Enriquecimiento LLM (no decide; R-2) | 8002 |

El core (redis/postgres/soar/soar-consumer/console/llm-triage) corre siempre; `wazuh-manager`
y `bridge` solo con `--profile real`.

## Requisitos

- Docker + Docker Compose.
- Un **host Linux de destino** con `sshd`, donde vas a instalar un agente Wazuh (puede ser un
  contenedor descartable — ver la validación end-to-end).
- (Opcional) Una API key de NVIDIA NIM para el enriquecimiento LLM. Sin ella, ARGOS funciona
  igual; el panel LLM queda vacío (fail-soft, R-2).

## Paso 1 — Configuración

```bash
git clone <repo> argos && cd argos
cp .env.example .env
```

Editá `.env` y seteá, como mínimo:

- `POSTGRES_PASSWORD` — password de la DB de auditoría.
- `CONSOLE_BASIC_USER` / `CONSOLE_BASIC_PASS` — credencial de la consola web (RF-7). Sin ambas, la
  consola corre **sin** auth (solo aceptable en localhost).
- `WAZUH_API_URL=https://wazuh-manager:55000`, `WAZUH_API_USER`, `WAZUH_API_PASSWORD`,
  `WAZUH_AGENT_MAP={"asset-id":"001"}` y `WAZUH_API_TIMEOUT_SECONDS=5` — configuración
  fail-closed del manager, mapping uno-a-uno y timeout acotado.
- `ARGOS_EXECUTOR=wazuh` — activa el active-response REAL (default `simulated` no toca el host).
- `ARGOS_REQUIRE_APPROVAL=true` — (default) ninguna contención se auto-ejecuta sin aprobación humana.
- (Opcional) `OPENAI_API_KEY` para el LLM; `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` para aprobar
  desde Telegram.

> **Límite PR-01B3a:** una aceptación HTTP del manager no confirma el efecto en el endpoint y se
> registra como `ambiguous`. No hay rollback remoto ni soporte E2E Windows/Linux validado hasta
> PR-01B3b. Este camino no está listo para producción (ADR-0019).

Inventario del host defendido (decide la criticidad / two-person rule):

```bash
cp config/host_inventory.example.json config/host_inventory.json
```

Editá `config/host_inventory.json`: la **clave** debe ser el **nombre del agente Wazuh** de tu host
(el `host_id` que ARGOS ve = `agent.name`). Ejemplo:

```json
{ "my-linux-server": { "criticality": "standard", "ip": "10.0.0.10", "os": "Ubuntu Server 24.04" } }
```

Y en `.env`: `ARGOS_HOST_INVENTORY=config/host_inventory.json`.

## Paso 2 — Levantar ARGOS

```bash
docker compose --profile real up -d
docker compose ps          # todos healthy; wazuh-manager tarda ~1-2 min en arrancar
```

La regla SSH brute-force de ARGOS (`detection/wazuh-rules/ssh_bruteforce_rules.xml`, T1110, level 12)
ya va montada como `local_rules.xml` del manager.

## Paso 3 — Enrolar el agente en el host de destino

En tu host Linux de destino, instalá el agente Wazuh apuntando al manager (`<IP-del-host-docker>`,
puerto 1515 para enrolar, 1514 para reportar). El `agent.name` debe coincidir con la clave de
`config/host_inventory.json`. (Guía oficial: *Wazuh agent enrollment*.)

## Paso 4 — Active response en el agente (para la contención real)

La contención la dispara el SOAR vía `PUT /active-response` del manager; el comando corre en el
**agente**. Para eso, en el host de destino:

1. Copiá los scripts AR de `active-response/linux/*.sh` a `/var/ossec/active-response/bin/` del agente
   (nombres sin extensión: `argos-isolate`, `argos-throttle`, `argos-kill`, `argos-snapshot`,
   `argos-unisolate`, `argos-unthrottle`), con permiso de ejecución.
2. Registrá los comandos AR en el `ossec.conf` del **manager** agregando los bloques de
   `active-response/ossec/argos-ar-commands.conf` + `argos-ar-active-response.conf`, y reiniciá el
   manager (`docker compose restart wazuh-manager`).

> **Nota de honestidad:** este paso 4 (registro AR en el manager + deploy de los AR bin al agente) y el
> enrolamiento del paso 3 se **validan de punta a punta en la corrida real** (ver abajo). El resto de
> la tubería (regla → bridge → Redis → consumer → tier → notificación → aprobación) está cubierto por
> tests automatizados.

## Paso 5 — Validación end-to-end (la vara)

Con todo arriba, un intento de fuerza bruta SSH **real** contra el host de destino debe:

1. Disparar la regla nativa de Wazuh (multiple auth failures) → la regla hija de ARGOS la etiqueta
   `argos_layer1` + T1110 → `alerts.json`.
2. El bridge la publica → el `soar-consumer` crea el incidente en **Tier 2** (aprobación requerida).
3. Aparece en la consola (`http://localhost:8080`, con tu credencial) y/o llega la notificación.
4. Al **aprobar** (consola o Telegram), el `WazuhActiveResponseExecutor` real ejecuta la contención.
5. Un segundo intento desde la IP atacante **falla**.

El simulador de ataque seguro vive en `detection/simulators/` (construye el comando `hydra`/`medusa`,
lo imprime, y solo lo ejecuta con `--i-confirm-this-is-my-lab` contra un host que vos designes — nunca
por default, nunca contra IPs públicas).

## Modo demo (sin host real)

Para ver el flujo sin montar nada real: `docker compose up -d` (sin `--profile real`) +
`scripts/demo_injector.py` inyecta alertas simuladas. `ARGOS_EXECUTOR=simulated` no toca ningún host.
