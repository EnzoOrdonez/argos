# deploy/ — docker-compose Perfil A (Fase 5, ADR-0015)

Empaqueta los servicios core de ARGOS en la VM Linux core. Las víctimas (Windows endpoint + Linux
Debian/PostgreSQL `app_prod`) son **VMs externas**, no servicios de acá. Wazuh manager se instala en la
VM core (systemd); el `bridge` montea su `alerts.json`. El `postgres` de acá es para `argos_audit` (el log
de ARGOS), **separado** del `app_prod` de la víctima.

El `docker-compose.yml` y el `Dockerfile` viven en la **raíz** (para `docker compose up` sin `-f`).

## Prerrequisitos
- Docker + docker compose v2.
- `.env` en la raíz (gitignored) con al menos: `POSTGRES_PASSWORD`; para el LLM real: `OPENAI_API_KEY`
  (una nvapi key de NVIDIA), `OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1`,
  `OPENAI_MODEL=deepseek-ai/deepseek-v4-pro`, `OPENAI_FALLBACK_MODEL=moonshotai/kimi-k2.6`;
  opcional `ARGOS_JWT_SECRET`, `TELEGRAM_*`. **Ojo:** hoy la key real está bajo
  `DeepSeek_V4_PRO_API_KEY`/`Kimi2_6_API_KEY` — copiala a `OPENAI_API_KEY` para que el servicio la use.

## Camino simulado (garantizado, el del video)
```bash
docker compose up -d            # redis, postgres, soar, console, llm-triage
docker compose ps               # esperar (healthy)
python scripts/demo_injector.py uc04 --redis-url redis://localhost:6379/0   # inyectar desde el host
# consola web:  http://localhost:8080      (Streamlit fallback: docker compose --profile fallback up -d -> :8501)
```

## Camino real (Wazuh + víctimas)
Requiere Wazuh manager instalado en la VM core (systemd) — ver `detection/p3_deployment_guide.md`.
```bash
ARGOS_EXECUTOR=wazuh docker compose --profile real up -d   # + bridge (tailea /var/ossec/logs/alerts del host)
# atacar la víctima -> alerta Wazuh -> bridge -> events:normalized -> SOAR -> aprobación (Telegram) ->
#   argos-isolate aísla la víctima SIN perder el manager (whitelist 1514/1515) -> audit
```

## Swap simulado ↔ real
- `ARGOS_EXECUTOR=simulated` (default) → `SimulatedExecutor` (no toca VMs). `=wazuh` → active-response real.
- Feeder: sin `--profile real`, el demo se alimenta con `demo_injector`; con `--profile real`, con el `bridge`.

## Servicios / puertos / health
| Servicio | Puerto | Health | Perfil |
|---|---|---|---|
| redis | 6379 | `redis-cli ping` | core |
| postgres (`argos_audit`) | 5432 | `pg_isready` | core |
| soar (Approval API) | 8003 | `/healthz` | core |
| console (web) | 8080 | `/health` | core |
| llm-triage | 8002 | `/health` | core |
| bridge | — | (tailer, sin HTTP) | `real` |
| streamlit (fallback) | 8501 | — | `fallback` |

## Notas
- **postgres provisto pero no escrito** por el SOAR hoy (usa `MemorySink`); queda listo (schema `argos_audit`,
  `soar/audit/schema.sql`) para cuando P4 cablee el sink. No bloquea el demo.
- **Sin OpenSearch** (Perfil A manager-only). Los 3 dashboards SOC = Perfil B (F7, diferido).
- `ml` no es servicio (librería; vive en la imagen para el bridge Camino B).
- **Secretos solo en `.env`** (gitignored). El `docker-compose.yml` no tiene ningún secreto literal (un test lo verifica).
