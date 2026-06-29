# RUNBOOK — Grabación Track B (demo garantizada, 1-jul-2026)

Secuencia exacta para grabar una corrida limpia de **Track B**: `docker compose` Perfil A
+ `scripts/demo_injector.py` corriendo los UC por el **pipeline real** (tiers, correlación,
quorum, scheduler, LLM, audit, consola), executor **`simulated`**. Corre en la laptop de
Enzo (Docker Desktop). Cualquiera del equipo puede grabar siguiendo esto sin improvisar.

> **Verificado 2026-06-29:** los 5 UC del injector + el centerpiece uc03 dan el desenlace
> esperado contra el compose vivo. Servicios healthy: console `:8080`, llm-triage `:8002`
> (gpt-oss), soar `:8003`, redis, postgres.

---

## Qué es REAL y qué es SIMULADO (honestidad para la narración)

| Real (motor de verdad) | Simulado (demo-safe) |
|---|---|
| Pipeline P1: correlación, `tier_router`, quorum/two-person, scheduler, ventana de consolidación, conservative-wins, audit | **Executor `simulated`** (no toca hosts; loguea las acciones) |
| Decisión HITL: `handlers.py`/`consolidation.py` (la misma lógica que el lab usaría) | **Votos casteados por el injector** (sin Telegram real; ver §Telegram) |
| LLM real gpt-oss (o cache, ver §LLM) en uc03/04/07 | **uc03** conduce el cierre de ventana para *visualizar* el split-brain (la lógica de decisión es real) |
| Alertas `NormalizedAlert` por `events:normalized` (campo `payload`) | El ataque no ocurre: el injector publica las alertas que el lab generaría |

- **El LLM enriquece SOLO uc03/04/07** (T2 o two-person). uc01/02/06/05/08 NO llaman al LLM por diseño (R-2 gating, `triage_hook.should_call_triage`). No es un bug — narrarlo así.
- **El audit se ve por el stdout del injector** (sink en memoria) **y, opcionalmente, como fila real en Postgres** `argos_audit` si activás el SQL sink (ver §Audit SQL). Sin el DSN, solo stdout.
- **8 UC inyectables:** uc01/02/03/04/05/06/07/08. Los 8 dan su desenlace por el pipeline real. La grabación de ~13 min entra cómoda con 6; uc05/uc08 son beats cortos opcionales.

---

## 0. Prerrequisitos (una vez)
- Docker Desktop corriendo. `.env` presente con `POSTGRES_PASSWORD` seteado.
- `.venv` del repo (el injector corre en el host): `\.venv\Scripts\python`.

## 1. Cache LLM a prueba de cámara (recomendado para grabar)
gpt-oss responde ~0.9s, pero a veces pasa los 5s del hook y el panel LLM queda vacío. La
cache lo elimina:
```bash
# genera demo/cached-responses/ corriendo el triage real por UC (uc03/04/07):
.venv\Scripts\python scripts\gen_llm_cache.py
# activar la cache para la grabación:
#   en .env -> DEMO_MODE=true   (DEMO_CACHE_PATH=./demo/cached-responses ya está)
```
El servicio `llm-triage` monta `./demo` read-only; con `DEMO_MODE=true` sirve la cache
(re-estampa incident_id/generated_at). Miss o cache vacía → cae al gpt-oss real (R-2 intacto).

## 2. Levantar Track B
```bash
docker compose up -d --build
docker compose ps                 # los 5 servicios -> healthy (~30s)
# smoke:
curl http://localhost:8080/health   # {"ok":true,"redis":true}
curl http://localhost:8002/health   # {"ok":true,"backend": ...}
curl http://localhost:8003/healthz  # {"ok":true,"redis":true}
```
Abrir la **consola en http://localhost:8080** (auto-refresh ~1.5s). Es la estrella visual.

---

## 3. Secuencia de grabación (~13 min)

Patrón por UC: `demo_reset` → inyectar → narrar mirando la consola + el stdout del injector.
`RU=redis://localhost:6379/0`.

```bash
.venv\Scripts\python scripts\demo_reset.py --redis-url %RU%        # entre CADA UC
.venv\Scripts\python scripts\demo_injector.py <uc> --redis-url %RU%
```

Orden sugerido (cierra en el centerpiece) y timing para entrar en ~13 min:

| # | UC | Comando (tras `demo_reset`) | Tier / desenlace | ~min | Qué mostrar / narrar |
|---|----|------|------|---|------|
| 1 | **uc02** | `demo_injector.py uc02` | T0 auto · canary | 1.0 | Detección ultra-temprana, zero-FP. Cero archivos reales tocados |
| 2 | **uc01** | `demo_injector.py uc01` | T0 auto · ransomware 3 capas | 1.5 | Las 3 capas casi simultáneas → auto-aislar sin HITL (alta confianza) |
| 3 | **uc06** | `demo_injector.py uc06` | T0 fast-path · DDoS | 1.0 | Saturación de red → contención inmediata; el LLM NO aporta acá (sin ambigüedad) |
| 4 | **uc04** | `demo_injector.py uc04` | T1 two-person · 2 approve | 2.5 | DB IntiBank production-critical → **dos personas aprueban**; panel LLM poblado; vocabulario de compliance |
| 5 | **uc07** | `demo_injector.py uc07` | T1 · **NO_ACTION** (reject) | 2.0 | Falso positivo: el humano **cancela**; conservative no atropella al reject en two-person; panel LLM poblado |
| 6 | **uc03** ⭐ | `set APPROVAL_CONSOLIDATION_WINDOW_SECONDS=5 && demo_injector.py uc03` | **T2 · split-brain · conservative-wins** | 4.0 | **CENTERPIECE** (ver §uc03) |

> `set APPROVAL_CONSOLIDATION_WINDOW_SECONDS=5` (Windows `cmd`) o `$env:...=5` (PowerShell)
> hace visible el countdown de la ventana en la consola. Sin él, default 60s.

### §uc03 — el centerpiece (narración)
Lo que la consola muestra, en orden, durante la corrida:
1. **Tier T2** (ML sola, score 0.74) — "Sigma no la matchea, el canary no está en su camino; solo el ML la ve por comportamiento".
2. **Throttle + Snapshot** proactivos (antes de cualquier humano) — "acotamos el daño y preservamos forense mientras esperamos, pero esperamos seguro".
3. **Matriz de aprobadores**: Enzo **Reject** (rojo) → P2 **Approve** (verde) → banner **⚠ CONFLICTO DETECTADO · SPLIT-BRAIN** → P3 **Approve** → P4 **sin responder**.
4. **Clock de consolidación** (countdown ~5s).
5. Al cerrar: **EXECUTING — 2 approve · 1 reject · 1 timeout · conservative-wins** (P4 queda **TIMEOUT**).
6. **Panel LLM**: variante ransomware, técnica WMIC, confianza ~0.78.
Cierre: "El desacuerdo se resolvió por política (conservative-wins), no por jerarquía. El throttle ya había contenido el daño. El ML atrapó lo que las firmas no."

Verificación rápida del estado en redis (opcional, fuera de cámara):
```bash
docker compose exec redis redis-cli KEYS 'incident:INC-*'
# el incidente tiene tier=T2, final_decision conservative-wins, conflict_detected=true,
# approvers: enzo=rejected, p2/p3=approved, p4=timeout
```

---

### Beats opcionales — uc05 / uc08 (si sobra tiempo)
```bash
# uc05 — agent-kill sigiloso: L1 stop-service + L3 canary -> T0 auto-isolate
.venv\Scripts\python scripts\demo_injector.py uc05 --redis-url %RU%
# uc08 — SQL injection web: L1 firmas SQLi + L2 patron -> T1 auto, block IP
.venv\Scripts\python scripts\demo_injector.py uc08 --redis-url %RU%
```
Narrar uc05 = "matar el agente ES la señal: el host se aísla solo". uc08 = "OWASP #1; firma + anomalía de patrón se corroboran → T1 automático, block IP".

## §Audit SQL — fila real en Postgres (opcional)
Por defecto el audit se ve por el **stdout del injector**. Para mostrar una **fila real**
con un query (cierra el beat de compliance), activá el SQL sink antes de inyectar:
```bash
# DSN al Postgres argos_audit del compose (host -> localhost:5432). PW = POSTGRES_PASSWORD del .env.
set ARGOS_AUDIT_SQL_DSN=postgresql://argos:<POSTGRES_PASSWORD>@localhost:5432/argos_audit
.venv\Scripts\python scripts\demo_injector.py uc04 --redis-url %RU%
# mostrar la fila:
docker compose exec postgres psql -U argos -d argos_audit -x -c ^
  "SELECT incident_id,tier,state,final_outcome,final_policy,execution_status FROM argos_audit.audit_incidents;"
docker compose exec postgres psql -U argos -d argos_audit -c ^
  "SELECT approver_email,status,channel FROM argos_audit.audit_responses;"
```
Fail-soft: sin el DSN (o sin DB) el sink no-opea y el audit sigue por stdout (R-2: nunca
bloquea). Si el rol `argos` no existe, recreá el volume: `docker compose down -v && docker compose up -d`.

## §Telegram — injector-cast (sin ngrok)
Los votos de uc03/uc04/uc07 los **castea el injector de forma determinista** (in-proceso,
vía `record_approval_response`). **NO se usa ngrok ni el callback real de Telegram** para la
grabación: es lo más frágil en vivo. Si Enzo quiere un momento Telegram real, que sea un paso
**opcional y aparte** (ver `DEMO_RUNBOOK.md` §5.2), nunca el camino de la grabación.

## §Reset entre tomas y teardown
```bash
.venv\Scripts\python scripts\demo_reset.py --redis-url redis://localhost:6379/0   # FLUSHDB
docker compose down                # al terminar
```
Ojo (correlación por host_id): si inyectás varios UC sin reset, los que comparten host se
correlacionan en un mismo incidente. **Resetear entre cada UC** evita confusión en cámara.

## Troubleshooting
- **Panel LLM vacío en uc03/04/07:** gpt-oss pasó los 5s del hook. Solución: `DEMO_MODE=true`
  + `gen_llm_cache.py` (§1), recrear `docker compose up -d llm-triage`. (uc01/02/06 vacíos es **correcto**, no llaman LLM.)
- **uc03 tarda 60s:** falta `APPROVAL_CONSOLIDATION_WINDOW_SECONDS=5` antes del comando.
- **`POSTGRES_PASSWORD ... must be set`:** setealo en `.env` antes de `up`.
- Más detalle de setup/3-terminales/`--live`/Telegram real: `DEMO_RUNBOOK.md`.
