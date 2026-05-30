# HANDOFF · Brief para continuar el proyecto ARGOS en sesión nueva

> Documento creado el 2026-05-30. Si la fecha actual es > 2026-06-13, este handoff está **expirado** — la entrega final ya pasó.

---

## Quién soy y cuál es el contexto

Soy **Enzo Ordoñez Flores** (P1, líder técnico) del equipo ARGOS. ARGOS es un proyecto de fin de curso para *Tópicos Avanzados de Ciberseguridad* — Universidad de Lima, ciclo 2026-1. **Entrega final: sábado 13 de junio de 2026.** Tres deliverables: informe técnico (~30 % peso), demo en vivo (~40 %), presentación oral (~20 %).

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
