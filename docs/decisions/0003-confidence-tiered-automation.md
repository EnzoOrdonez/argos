# ADR-0003: Confidence-tiered automation with Human-in-the-Loop SOAR

**Estado:** Aceptado
**Fecha:** Semana 1
**Autores:** P1 (Enzo)
**Revisores:** Equipo completo

---

## Contexto

La pregunta es: ¿toda detección dispara contención automática inmediata, o se requiere aprobación humana?

Dos lecturas opuestas de "el tiempo es valioso en un incidente":
- **Lectura A:** automatizar todo, eliminar al humano del loop.
- **Lectura B:** preparar al humano para que decida en segundos en vez de minutos.

La industria converge en una lectura mixta donde el grado de automatización depende de la **confianza en la detección** y la **reversibilidad de la acción**.

## Decisión

**Implementar automatización en cuatro tiers según confianza, con email + botón de aprobación para tiers de confianza media-baja.**

## Esquema de tiers

| Tier | Disparado por | Confianza | Acción | Email |
|------|---------------|-----------|--------|-------|
| **T0 — Critical confirmed** | Capa 3 (canary) sola, o Capas 1+2+3 simultáneas | ≥0.95 | Auto-isolate inmediato | Post-facto con botón "Revertir" |
| **T1 — High confirmed** | Capa 1 + Capa 2 corroboran (sin canary) | 0.80–0.95 | Auto-isolate inmediato | Post-facto con botón "Revertir" |
| **T2 — Medium uncertain** | Capa 1 sola con regla high-fidelity, o Capa 2 sola con score muy alto | 0.60–0.80 | Pendiente con countdown 3 min | Pre-aprobación con botones |
| **T3 — Low uncertain** | Capa 2 score medio, Capa 1 con regla experimental | 0.40–0.60 | Solo notificación, sin acción | Análisis LLM al analista, sin botón ejecutar |

## Lógica de ejecución por tier

### T0 / T1 — Auto + email post-facto

1. Decision Engine detecta tier T0 o T1.
2. Ejecuta playbook de contención inmediatamente (aislamiento, kill, snapshot).
3. Envía email al equipo con: análisis LLM, comandos ejecutados, timestamp, **botón "Revert if false alarm"** (token JWT firmado).
4. Si analista hace click "Revert": sistema reconecta el host y registra reversión en audit log.

### T2 — Pre-aprobación con timeout 3 min

1. Decision Engine detecta tier T2.
2. Estado: `AWAITING_APPROVAL` en Redis con TTL 3 min.
3. **Inmediatamente** se aplican dos acciones protectoras no destructivas:
   - **Throttle del proceso ofensor:** CPU/IO limits para reducir velocidad de cifrado de ~25K archivos/min a ~100-500 archivos/min.
   - **Snapshot proactivo de disco:** preserva evidencia forense y provee punto de recuperación.
4. Email al equipo con análisis LLM, comandos propuestos, **botones "Approve isolation" / "Reject — false positive"**.
5. Si llega aprobación dentro del timeout: ejecuta isolation completa. Throttle y snapshot ya están en su lugar.
6. Si llega rechazo: estado `REJECTED`, throttle removido, snapshot descartado.
7. **Si timeout sin respuesta a los 3 minutos:** **auto-execute isolation inmediato**. No hay re-broadcast ni esperas adicionales.

**Razón del timeout corto sin escalación:** ransomware moderno cifra a 25,000 archivos/minuto. Esperas largas son incompatibles con la naturaleza del ataque. El throttle + snapshot durante el countdown bound el daño incluso en escenarios de "humano no disponible". Ver Q9 en `OPEN_QUESTIONS_RESOLUTION.md` para análisis completo.

### T3 — Notificación informativa

1. Email con análisis, sin botones de acción.
2. Analista revisa en Streamlit dashboard, marca como benigno o escala manualmente.

## Reversibilidad

Cada acción se categoriza como:

| Acción | Reversibilidad | Tier mínimo para auto |
|--------|----------------|----------------------|
| Host isolation (firewall) | Reversible en segundos | T0/T1 auto, T2 con approval |
| Process kill | Reversible (proceso se relanza si era servicio) | T0/T1 auto, T2 con approval |
| Disk snapshot | No destructivo | Cualquier tier auto |
| Account password reset | Reversible pero molesto | T2 mínimo con approval |
| Account deletion | Irreversible | Two-person rule (ADR-0006 split-brain) |
| Disk wipe | Irreversible | Out of scope ARGOS v1 |

### Override por criticidad del host (per Q2 OPEN_QUESTIONS_RESOLUTION)

Independientemente del tier asignado por confianza, el Decision Engine enruta la contención de cualquier host etiquetado en Wazuh como `criticality=production-critical` a través del flujo de **two-person rule** (dos aprobaciones explícitas requeridas antes de ejecutar; un solo rechazo cancela). Esto se aplica incluso a tiers T0/T1 que normalmente serían auto-execute. Razón: el costo de aislar erróneamente un activo de producción crítico (downtime de servicio facturable, cascada de dependencias) supera el costo del delay de aprobación. Ver UC-04 en `USE_CASES.md` para el escenario demo correspondiente.

Throttle y disk snapshot siguen disparándose inmediatamente sin esperar aprobación (no destructivos), por lo que la ventana de espera mantiene el daño acotado por la misma propiedad descrita en la sección T2 de este ADR.

## Alternativas consideradas

### Toda acción 100% automática

- ❌ Vulnerable a falsos positivos en Capas 2/3 con baja confianza.
- ❌ Defensive DoS por alertas falsas (T-043 en threat model).
- ✅ Velocidad máxima.
- **Veredicto:** rechazado para tiers T2/T3.

### Toda acción 100% manual

- ❌ Inviable a las 3 AM o fines de semana sin SOC 24/7.
- ❌ Tiempo medio de respuesta excesivo en escenarios de alta confianza.
- ✅ Cero falsos positivos por automatización errónea.
- **Veredicto:** rechazado.

### Two-tier (automático vs manual sin gradación)

- ⚠️ Más simple pero pierde matiz.
- ⚠️ La decisión binaria fuerza thresholds rígidos.
- **Veredicto:** rechazado en favor del esquema 4-tier que permite sintonización.

## Consecuencias

### Positivas

- Patrón industrial estándar (Microsoft Sentinel, Splunk SOAR, Tines).
- Defensible ante profesor: "el tiempo es valioso → reducimos tiempo de decisión humana, no eliminamos al humano".
- Demo material rico: 4 tiers permite escenificar 4 escenarios distintos.
- Adaptable: thresholds entre tiers son configurables sin redeployment.

### Negativas

- Mayor complejidad de implementación: state machine en Redis, email templates por tier, lógica de timeout y escalación.
- Más vectores de ataque (token interception, replay attacks) — cubiertos en threat model expandido.
- Aprobaciones por email requieren JWT firmado, expiración corta, auditoría.

## Implicaciones técnicas

### Componentes nuevos

1. **`approval_service.py`:** state machine de aprobaciones en Redis.
2. **`notification_channel/email.py`:** envío de emails con templates Jinja2 + JWT en URLs.
3. **FastAPI endpoint:** `POST /approval/{token}` valida JWT + actualiza state.
4. **Scheduler:** `apscheduler` para timeouts y escalación.

### Componentes existentes modificados

- **Decision Engine:** clasifica alertas en tiers antes de enrutar.
- **Streamlit Analyst UI:** muestra Approval Workflow Console con estado en tiempo real.

### Time estimate

~1 semana de trabajo de P1 sobre el plan original. Cabe en sem 7-8 sin sacrificar otros componentes.

## Revisión

A re-evaluar en Gate 2 (semana 7) cuando los thresholds entre tiers se calibren con datos reales del lab. Protocolo de calibración cerrado en `OPEN_QUESTIONS_RESOLUTION.md` §Q5.

## Actualizaciones posteriores

- **Semana 2:** se incorpora override por criticidad del host (Q2 de `OPEN_QUESTIONS_RESOLUTION.md`) — los hosts `production-critical` se enrutan a two-person rule independientemente del tier. Sección "Reversibilidad" actualizada en consecuencia.
