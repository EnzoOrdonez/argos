# HANDOFF · Brief para continuar el proyecto ARGOS en sesión nueva

> Documento creado el 2026-05-30, actualizado el 2026-06-10. Si la fecha actual es > 2026-06-28, este handoff está **expirado**: la entrega final ya pasó.

---

## Quién soy y cuál es el contexto

Soy **Enzo Ordoñez Flores** (P1, líder técnico) del equipo ARGOS. ARGOS es un proyecto de fin de curso para *Tópicos Avanzados de Ciberseguridad* — Universidad de Lima, ciclo 2026-1. **Entrega final: sábado 28 de junio de 2026** (prórroga del profesor anunciada el 2026-06-10; los docs que aún digan 13-jun están desactualizados en ese punto). Tres deliverables: informe técnico (~30 % peso), demo en vivo (~40 %), presentación oral (~20 %).

El proyecto es una plataforma **multi-vector XDR** (Extended Detection and Response) llamada **Adaptive Response Guard with Orchestrated Surveillance**. Defiende una DB bancaria ficticia (**Banco Inti S.A.A.** / brand **IntiBank**) contra ransomware, DDoS, SQL injection y false positives, usando 4 capas (Sigma + Wazuh / ML / Canary FIM / LLM Triage) más un SOAR con HITL multi-canal.

Equipo: P1 Enzo (líder · SOC Lead ficticio), P2 Sebastian Montenegro (ML · DBA ficticio), P3 Angeles Castillo (Detection + Sims · Infra Lead ficticio), P4 Diego Jara (Infra + UI · Compliance Officer ficticio).

---

## ANTES DE RESPONDER NADA — leé estos archivos en este orden

1. `docs/team/manual-equipo.md` — contexto operacional, flujo del demo, convenciones
2. `docs/decisions/README.md` — índice de ADRs
3. `docs/decisions/0008-multi-vector-scope-expansion.md` — qué UCs entran al demo
4. `docs/decisions/0009-intibank-scenario.md` — escenario empresarial (schema bancario, roles, umbrales, branding, compliance)
5. `docs/decisions/0010-demo-operational-decisions.md` — 11 decisiones operacionales con patrón ideal/mínimo
6. `docs/team/manual-p1-enzo.md` — manual operativo del líder (Fases 1-4)
7. `docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md` §6 — las 4 capas

Si **no** has leído esos 7 archivos, **no me ayudes con nada de implementación todavía** — me dices "voy a leer primero" y los lees. Si yo te pido que avances sin leerlos, **dime que no** y forzá la lectura primero. Hacer eso me ahorra horas de re-decidir.

---

## Estado actual del repo (a 2026-05-30, último commit local `aeb7d4f`)

- **Documentación cerrada.** ADRs 0001-0010 cubren todas las decisiones arquitectónicas y operacionales. Cada cambio requiere ADR nuevo.
- **Fase 1 de los manuales individuales cerrada** (prereqs, cuentas externas Telegram/Discord/Twilio/OpenAI, repo + venv, .env). Cada integrante debería estar listo para arrancar Fase 2.
- **69 tests pasando** (`pytest -q` global).
- **8 commits locales pendientes de push** (yo los pusheo manualmente desde mi máquina). Estado: `git log --oneline -10` de la raíz del repo.
- **HTMLs interactivos** (`docs/use-cases/argos_use_cases.html`, `docs/team/html/argos-manual-p*.html`) y **PDFs** generados y validados.
- **Diagramas drawio**: `docs/architecture/network_diagram.drawio` + `docs/architecture/use_cases_diagrams.drawio` (5 páginas por UC).

---

## Reglas estrictas — no las rompas

1. **NUNCA modifiques un ADR ya aceptado.** Si descubres que un ADR está mal, propón un ADR nuevo que lo supersede. Inmutabilidad post-aceptación es la regla.
2. **NUNCA cambies `argos_contracts` v1.1.0.** Es la API pública entre componentes; cambiarla rompe a P2/P3/P4 en paralelo.
3. **`pytest -q` debe seguir verde (≥ 69 passed) después de cada cambio.** Si tu cambio rompe tests, o el cambio es malo o los tests están mal — investigá ambas opciones antes de ajustar el test.
4. **NO regeneres los HTMLs ni PDFs de los manuales** salvo que yo te lo pida explícitamente. Son artefactos pesados, regenerarlos por cualquier ajuste menor es churn y la diff es ruido en git.
5. **NUNCA toques la versión de PostgreSQL pinneada.** ADR-0010 §4.5 fija `postgres:17.5-bookworm`. Las menciones históricas a "PostgreSQL 15" en docs y HTMLs son ruido, NO autoridad — la autoridad es el ADR.
6. **El patrón ideal/mínimo de ADR-0010 NO se discute.** Si un trigger de fallback se cumple (T-7 / T-10 / T-14 / T-21 días según decisión), el fallback aplica automáticamente. No "esperemos un día más".

---

## Lo que sigue (próximos pasos en orden, sin ambigüedad)

### Inmediato (esta semana)
- **P4 Diego**: arrancar Fase 2 de `docs/team/manual-p4-diego.md` — Vagrant + PostgreSQL 17.5-bookworm + pgAudit, schema desde ADR-0009 §2.2, seed con Faker(es_PE).
- **P3 Angeles**: arrancar Fase 2 de `docs/team/manual-p3-angeles.md` — Sigma rules DB usando umbrales de ADR-0009 §2.5 + rule MFA flag de ADR-0010 §4.1.
- **P2 Sebastian**: actualizar `ml/data/synthetic_generator.py` con día simulado (ADR-0010 §2.3 ideal — 30 días × 24h, distribución horaria por rol). Si T-21 días sin esto, fallback a data plana per §2.3 mínimo.
- **P1 (yo)**: arrancar Fase 2 de `docs/team/manual-p1-enzo.md` — SOAR Tier Router, Notification Service (Telegram + Discord + Twilio), Approval API, Two-Person Rule, 60s Consolidation.

### Mediano (próximas 2 semanas)
- Integración real entre capas (Fase 3 de cada manual).
- UC-04 end-to-end con 4 aprobadores HITL.
- Webapp dummy para UC-08 (P4 — ADR-0010 §2.2 ideal Flask 60-80 líneas).

### Final (1 semana antes del demo)
- UC-05 Wazuh kill mini-cameo (P4 — ADR-0010 §2.1 ideal).
- JWT signing en Approval API (P1 — ADR-0010 §4.4 ideal).
- Rehearsals con timer audible (P4 dirige — ADR-0010 §2.4).
- Video respaldo grabado.
- Informe técnico final.

---

## Cómo me tienes que tratar — no soy frágil

- **Sin adulación.** No me digas "buena pregunta" o "excelente idea". Solo respondé.
- **Crítica explícita.** Si ves que mi razonamiento tiene un hueco, decímelo directamente: "lo que pedís tiene este problema X, lo verificaste?". No suavices.
- **Reta mis suposiciones.** Si yo te pido algo que viola un ADR sin que yo lo note, parame y mostrame qué ADR estoy violando antes de ejecutar.
- **No inventes hechos.** Si no sabés algo del repo, leelo. Si después de leer no está claro, decimelo en lugar de improvisar.
- **Bullet points solo si tiene sentido.** Prefiero prosa concisa.
- **Sin emojis salvo que yo los use primero.**

---

## Protocolo cuando detectes un problema en lo que pido

Caso típico: yo pido "X" pero X contradice un ADR o un manual.

**Respuesta correcta:**
> "Lo que pedís contradice ADR-XXXX §Y.Z que dice [cita literal]. Antes de ejecutar necesito que confirmes uno de tres caminos:
>
> 1. Cambié de opinión sobre la decisión — entonces abrimos ADR nuevo que supersede.
> 2. El ADR está mal interpretado por mí — corrige mi lectura.
> 3. Vamos a violar el ADR esta vez — necesito justificación explícita."

**Respuesta incorrecta:** ejecutar X sin avisar, o ejecutar X y después decir "ojo, eso violaba ADR".

---

## Tooling crítico que debes saber existe

| Tool | Para qué |
|------|----------|
| `pytest -q` | tests globales, debe pasar siempre |
| `sigma check detection/sigma/rules/` | valida reglas Sigma antes de cargar a Wazuh |
| `docs/team/_build/build_manual.py` | regenera HTMLs+PDFs de manuales (NO correr salvo pedido explícito) |
| `make demo-up` / `make demo-down` / `make demo-reset` | controla el lab Vagrant (lo arma P4 en su Fase 2) |
| `mcp__workspace__bash` | shell sandbox Linux donde tú vives — paths mapean según el system prompt |

---

## Verificación obligatoria al arrancar

Cuando empieces, corre estos checks y reporta el resultado en una línea cada uno:

```bash
# 1. Estado git
git log --oneline -5

# 2. Tests pasando
pytest -q 2>&1 | tail -3

# 3. ADRs presentes (debe listar 0001 .. 0010 + README + OPEN_QUESTIONS)
ls docs/decisions/

# 4. Manuales generados (4 PDFs + 4 HTMLs + 1 intro + 1 equipo)
ls docs/team/pdf/ docs/team/html/

# 5. Diagramas drawio (3 archivos)
ls docs/architecture/*.drawio
```

Si algo de eso falla o difiere de lo descrito en este handoff, **paráme antes de seguir**. Probablemente el repo está en un estado intermedio inconsistente.

---

## Última cosa — el push pendiente

A 2026-05-30 hay commits locales que no he pusheado a GitHub. Si querés validar contra el remoto, mi último commit local es `aeb7d4f`. Si `git rev-parse HEAD` te da algo más nuevo, yo o alguien del equipo avanzó. Si te da algo más viejo o un hash distinto, alguien hizo rebase y conviene preguntarme antes de tocar nada.

---

**Empezá leyendo los 7 archivos del bloque superior. No respondas con planes ni código hasta que hayas leído al menos los ADRs 0008, 0009 y 0010 — son las decisiones más recientes y las que más probablemente afectan lo que voy a pedir.**


---

## Actualizacion — 2026-05-30 (post implementacion Fase 2 SOAR · P1)

> Esta seccion refleja el estado **despues** de implementar la Fase 2 del SOAR. Lo de arriba
> (commit `aeb7d4f`, "69 tests", "arrancar Fase 2") es el estado previo; lo de aca manda.

**Fase 2 del SOAR (manual P1 §2.1-§2.8) implementada y en verde:** tier router, Notification
Service + canales (Telegram/Discord/Twilio), Approval API, two-person + conservative-wins,
ventana de 60s. `pytest -q` global = **166 passed**; cobertura `soar` 99% (`tier_router.py` 100%).

**Doc nueva — LEER ANTES DE TOCAR SOAR (se suma a los 7 archivos de arriba):**

1. `decisions/0011-soar-implementation-reconciliation.md` (✅ Accepted) — **fuente de verdad**:
   reconcilia el manual con `argos_contracts` v1.1.0. Los snippets de `manual-p1-enzo.md`
   §Fase 2-3 quedaron **superseded** (el manual lleva banner). Si vas a tocar SOAR, lee esto PRIMERO.
2. `decisions/0012-response-playbooks.md` (🟡 Proposed) — diseno de playbooks
   (ResponseExecutor: Wazuh AR + SimulatedExecutor; throttle/snapshot/isolation/kill).
3. `decisions/0013-soar-orchestration.md` (🟡 Proposed) — diseno del consumer + correlacion
   por host + scheduler + hook LLM + audit de Fase 3.

**Regla actualizada:** la autoridad SOAR es `argos_contracts` v1.1.0 (inmutable) + ADRs + el
codigo en `soar/`. Los snippets del manual son ilustrativos, NO fuente de verdad (ADR-0011 §2.1).

**Proximo paso P1 — Fase 3 (tras review de ADR-0012/0013):** orden (1) ResponseExecutor +
throttle/snapshot, (2) consumer + correlacion, (3) hook LLM + audit. Todo testeable sin lab
(fakeredis / respx / SimulatedExecutor).

**Deuda team-wide** registrada en ADR-0011 §7: `manual-p2-sebastian.md` usa `NormalizedEvent`/
`llm_verdict` (real: `NormalizedAlert` / `Incident.llm_analysis: TriageResponse`) — ya tiene banner.

**Nota git:** durante la sesion el mount del sandbox corrompio `.git/HEAD` (rama trunca `featu`)
y dejo un `.git/index.lock` huerfano; los commits, las ramas `feature/p1/fase2-*` y `main`
(→ `eccd882`) estan intactos. Recuperar en maquina real: `rm -f .git/index.lock` y, si HEAD
quedo roto, `git symbolic-ref HEAD refs/heads/main`.

---

## Actualizacion — 2026-06-10 (cierre Fase 3 SOAR · P1)

> Esta seccion manda sobre la de Fase 2. Entrega movida al **28-jun** (prorroga del profesor);
> los triggers de ADR-0010 §5 se recalculan contra esa fecha (T-14 = 14-jun, T-10 = 18-jun,
> T-7 = 21-jun; T-21 ya vencio el 7-jun).

**Fase 3 del SOAR entregada y en verde.** `pytest -q` global = **250 passed** (eran 166).
Cobertura `soar/` **97%**, `tier_router.py` **100%**, cada modulo nuevo ≥ 93% (piso ADR-0011 §4 = 80%).

**Lo implementado (todo testeable sin lab: fakeredis / respx / SimulatedExecutor):**

1. `soar/playbooks/` — ResponseExecutor (Protocol), SimulatedExecutor, WazuhActiveResponseExecutor, builders. ADR-0012.
2. `soar/decision_engine/consumer.py` + `soar/inventory.py` — consumer de `events:normalized`, correlacion por host con dos indices, fast-path, throttle+snapshot pre-aprobacion, poison guard. ADR-0013.
3. `soar/decision_engine/containment.py` — apply_decision para los tres outcomes (idempotente, fail-soft).
4. `soar/decision_engine/scheduler.py` — tres relojes asyncio (60s / 180s / voz 60s).
5. `soar/decision_engine/triage_hook.py` + `scripts/triage_stub.py` — hook LLM no bloqueante (R-2), gate T2 ∪ two-person sin DDoS.
6. `soar/audit/` — audit dual fail-soft (MemorySink + OpenSearch) + `schema.sql` para P4.
7. `scripts/demo_injector.py` — inyector por UC (uc01/02/04/06/07), modo `--in-process`.
8. `soar/approval_api/jwt_signer.py` — JWT HS256 single-use, verificacion en el callback de Telegram. Cierra el trigger T-10 (18-jun) antes de tiempo.

**ADR-0012 y ADR-0013 pasaron a ✅ Accepted** tras el review de P1 del 2026-06-10 (seccion §7 de cada uno,
con las correcciones incorporadas como texto nuevo, sin reescribir el historico).

**Wiring de Fase 2 que cambio:** el callback del Approval API (`soar/approval_api/main.py`) ahora,
tras cada voto, arranca la ventana de consolidacion con el primer voto, ejecuta la contencion al
fijarse la decision y audita; los colaboradores (executor, scheduler, audit, signer) son opcionales
para que el API degrade a Fase 2 si no se inyectan. Los snippets del manual P1 §Fase 3 siguen
superseded por ADR-0011/0013, no por este handoff.

**Frontera de P1 respetada:** no se toco `llm_triage/`, `ml/`, `detection/`, `deception/`, `lab/`,
`ui/`, `attack-simulation/`. El inyector y el stub viven en `scripts/` (carpeta nueva sin owner;
`attack-simulation/` es de P4 per CONTEXT.md §5). Capa 4: P1 solo escribio el hook desde `soar/`.

**Deuda anotada:** unificar el nombre canonico del host DB (hoy `LIN-VICTIM-01` y `LIN-DB-01`
conviven en el inventario, coordinar con P4); el corpus RAG cita NIST 800-61 r2 y ya existe la
r3 (abril 2025), cambiarlo es decision de P2.
