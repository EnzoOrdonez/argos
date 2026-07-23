# deploy/ — docker-compose Perfil A (Fase 5, ADR-0015)

Empaqueta los servicios core de ARGOS en la VM Linux core. Las víctimas (Windows endpoint + Linux
Debian/PostgreSQL `app_prod`) son **VMs externas**, no servicios de acá. Wazuh manager se instala en la
VM core (systemd); el `bridge` montea su `alerts.json`. El `postgres` de acá es para `argos_audit` (el log
de ARGOS), **separado** del `app_prod` de la víctima.

El `docker-compose.yml` y el `Dockerfile` viven en la **raíz** (para `docker compose up` sin `-f`).

## Prerrequisitos
- Docker + docker compose v2.
- `.env` en la raíz (gitignored, `cp .env.example .env` y completar): `POSTGRES_PASSWORD`; para el LLM
  real: `OPENAI_API_KEY` (una nvapi key de NVIDIA), `OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1`,
  `OPENAI_MODEL=openai/gpt-oss-120b` (backend actual — `deepseek-ai/deepseek-v4-pro` fue descartado por
  latencia, ver `CLAUDE.md`), `OPENAI_FALLBACK_MODEL=moonshotai/kimi-k2.6`; opcional `ARGOS_JWT_SECRET`,
  `TELEGRAM_*`. **`openai_client.py` solo lee `OPENAI_API_KEY`** — ignorar cualquier variable
  `MiniMax_M3_API_KEY`/`Kimi2_6_API_KEY`/`DeepSeek_V4_PRO_API_KEY` que aparezca en `.env.example`: son
  restos huérfanos de backends anteriores, ningún código las lee. Para reproducir sin depender del LLM
  real (Track B tal como se demuestra hoy), poner `DEMO_MODE=true` — usa las respuestas cacheadas en
  `demo/cached-responses/`. `ENVIRONMENT` y `ARGOS_EXECUTOR` son obligatorios: use
  `development + simulated` para demo local; staging/production solo aceptan `wazuh`.
  Si se habilita `ARGOS_AUDIT_SQL_DSN`, el sink conecta de forma lazy con
  `ARGOS_AUDIT_SQL_CONNECT_TIMEOUT_SECONDS` (default 5, rango 1..60), registra cada
  evento no persistido y reintenta en el evento siguiente.
  'ARGOS_EXECUTION_SQL_DSN' es obligatorio para Approval API, consumer y scripts
  live; el journal falla cerrado y no comparte la degradacion fail-soft del audit.

## Migracion PR-01B2

Una instalacion nueva aplica 'soar/audit/schema.sql' al inicializar PostgreSQL.
Para un volumen existente, antes de iniciar procesos capaces de ejecutar:

    docker compose up -d postgres
    docker compose exec -T postgres psql -U argos -d argos_audit -f /docker-entrypoint-initdb.d/01-argos-audit.sql

La migracion solo agrega 'argos_audit.execution_journal' y un indice. Para
rollback, detener 'soar' y 'soar-consumer', restaurar la version anterior y
conservar la tabla como evidencia; no es necesario ni recomendable borrarla.

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
# En .env: ENVIRONMENT=staging (o production), ARGOS_EXECUTOR=wazuh
docker compose --profile real up -d   # + bridge (tailea /var/ossec/logs/alerts del host)
# atacar la víctima -> alerta Wazuh -> bridge -> events:normalized -> SOAR -> aprobación (Telegram) ->
#   argos-isolate aísla la víctima SIN perder el manager (whitelist 1514/1515) -> audit
```

## Swap simulado ↔ real
- `ARGOS_EXECUTOR=simulated` solo con `ENVIRONMENT=development|test`; nunca es fallback.
- `ENVIRONMENT=staging|production` exige `ARGOS_EXECUTOR=wazuh`; cualquier error bloquea el arranque.
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
- PostgreSQL persiste audit cuando 'ARGOS_AUDIT_SQL_DSN' esta configurado y es
  autoridad fail-closed del journal para rutas de ejecucion. Esto no implica
  HA, TLS, backup/restore ni readiness productivo.
- **Sin OpenSearch** (Perfil A manager-only). Los 3 dashboards SOC = Perfil B (F7, diferido).
- `ml` no es servicio (librería; vive en la imagen para el bridge Camino B).
- **Secretos solo en `.env`** (gitignored). El `docker-compose.yml` no tiene ningún secreto literal (un test lo verifica).
