# ADR-0006: Split-brain resolution — conservative-wins policy

**Estado:** Aceptado
**Fecha:** Semana 1
**Autores:** P1 (Enzo)
**Revisores:** Equipo completo

---

## Contexto

ADR-0003 introduce aprobación humana para tiers T2/T3. ADR-0005 introduce notificación a múltiples destinatarios (multi-recipient). Esto produce un problema clásico en sistemas distribuidos: **¿qué pasa si dos aprobadores dan respuestas contradictorias?**

Ejemplo: Email enviado a Enzo, P2, P3, P4. Enzo click "reject — false positive". P2 click "approve isolation". El sistema debe decidir.

Este es el **split-brain decision problem**, formalmente equivalente a problemas de consenso distribuido (Paxos, Raft, etc.) pero con humanos como nodos.

## Decisión

**Implementar conservative-wins policy con ventana de consolidación de 60 segundos para acciones reversibles, y two-person rule para acciones irreversibles.**

## Reglas concretas

### Para acciones reversibles (host isolation, process kill)

1. **First positive response sets initial decision.**
   - Primer click en "approve" → estado: `PENDING_EXECUTION`. Se inicia ventana de consolidación de 60s.
   - Primer click en "reject" → estado: `PENDING_REJECTION`. Se inicia ventana de consolidación de 60s.

2. **Durante la ventana de 60s:**
   - Si llegan respuestas adicionales del mismo signo → confirmación, estado se mantiene.
   - Si llega respuesta del signo opuesto → conflicto detectado, **conservative-wins se aplica al cierre de la ventana**.

3. **Conservative-wins logic:**
   - En contención, *conservative* = aislar (más restrictivo).
   - Si hay cualquier "approve isolation" en la ventana → ejecuta isolation, regardless del número de rejects.
   - Si todas las respuestas son "reject" → no ejecutar.

4. **Cierre de la ventana:**
   - Sistema ejecuta la decisión final.
   - Email final a todos los aprobadores con audit summary: *"Action: ISOLATED. Decisions: 2 approve, 1 reject, 1 timeout. Policy: conservative-wins."*
   - Aprobadores que querían reject pueden ver justificación en el dashboard.

### Para acciones irreversibles (account deletion, disk wipe)

1. **Two-person rule estricto.**
   - Requiere DOS aprobaciones explícitas de distintos aprobadores.
   - UN SOLO rechazo cancela la acción permanentemente.
   - No hay timeout escalation hacia execute.

2. **Ningún destructive action en ARGOS v1 cae en esta categoría.**
   - Por diseño, todas las acciones automatizadas son reversibles (isolation, kill, snapshot).
   - Two-person rule queda documentado para futuras extensiones.

## Justificación

### Por qué conservative-wins en lugar de majority vote

- **Asimetría de costos:** un host aislado por error tiene costo bajo (ticket de TI, restauración). Un host NO aislado siendo atacado tiene costo alto (data loss, breach).
- **Speed:** majority vote requiere quorum, que es lento o inviable fuera de horario.
- **Security mindset:** ante incertidumbre, escoger la opción más restrictiva es el default correcto.

### Por qué ventana de 60s y no first-response-wins puro

- **Protege contra clicks descuidados:** primer aprobador que lee email rápido y click "reject" sin analizar no debe poder cerrar el caso.
- **Permite que respuestas posteriores corrijan:** si segundo aprobador analiza más cuidadosamente y discrepa, el sistema lo escucha.
- **60s es trivial en términos de seguridad** (ataque ya progresó N segundos antes de que llegara el primer email).

### Por qué first response inicia la ventana, no se espera quorum

- **Quorum-based systems son lentos** y inviables a las 3 AM con un solo aprobador disponible.
- **Single positive response es suficiente** para iniciar acción si la confianza del tier ya pasó el threshold automático parcial.

## Audit trail obligatorio

Cada decisión multi-aprobador genera un audit log estructurado:

### Política de gestión del secreto JWT (per Q6 OPEN_QUESTIONS_RESOLUTION)

Los botones de aprobación/rechazo en los emails llevan un token JWT firmado HS256 con un secreto compartido:

- **v1 (proyecto académico):** secreto estático en archivo `.env` (modo 0600, `.gitignore` enforced). Rotación manual únicamente ante sospecha de leak.
- **v2 (deployment productivo, fuera de scope):** secreto en gestor dedicado (Azure Key Vault / AWS Secrets Manager / HashiCorp Vault) con rotación automática cada 90 días, acceso por identidad IAM + policy, audit log de cada lectura.
- **Propiedades del token actuales:** expira a los 5 minutos, single-use (invalidado tras la primera respuesta válida), bound al `incident_id` específico, transporte TLS-only.

Una rotación del secreto JWT en v1 invalida todos los tokens en vuelo; los emails enviados antes de la rotación quedan inservibles. El equipo asume este costo durante operación normal porque la frecuencia de rotación es muy baja.



```json
{
  "incident_id": "INC-2026-04-29-001",
  "tier": "T2",
  "alert_summary": "Suspicious file enumeration on host WIN-VICTIM-01",
  "approvers_notified": ["enzo@demo.local", "p2@demo.local", "p3@demo.local", "p4@demo.local"],
  "responses": [
    {"responder": "enzo@demo.local", "decision": "reject", "timestamp": "2026-04-29T15:32:14Z", "latency_ms": 18000},
    {"responder": "p2@demo.local", "decision": "approve", "timestamp": "2026-04-29T15:32:31Z", "latency_ms": 35000},
    {"responder": "p3@demo.local", "decision": "approve", "timestamp": "2026-04-29T15:32:48Z", "latency_ms": 52000},
    {"responder": "p4@demo.local", "decision": "timeout", "timestamp": "2026-04-29T15:33:14Z"}
  ],
  "conflict_detected": true,
  "consolidation_window_seconds": 60,
  "policy_applied": "conservative-wins",
  "final_decision": "EXECUTE_ISOLATION",
  "execution_timestamp": "2026-04-29T15:33:15Z",
  "execution_status": "success"
}
```

Este audit log es:
- Visible en Streamlit Approval Workflow Console.
- Almacenado en OpenSearch index `argos-audit-decisions`.
- Incluido en el informe post-incidente automático.

## Visualización en Approval Workflow Console

El Streamlit dashboard muestra durante el incidente:

- **Decision Matrix** con un row por aprobador, status visual (pending / approved / rejected / timeout) actualizándose en tiempo real.
- **Conflict indicator:** banner amarillo cuando se detecta primer signo opuesto, con countdown de 60s visible.
- **Final decision banner:** verde "EXECUTED: ISOLATED" o rojo "REJECTED: NO ACTION" al cierre, con justificación textual ("conservative-wins policy applied: 2 approve, 1 reject").
- **Action timeline:** cronología horizontal de eventos (alert → emails sent → first response → conflict → window closed → execution).

## Alternativas consideradas

### First-response-wins puro

- ✅ Velocidad máxima.
- ❌ Sin protección contra clicks descuidados.
- ❌ Aprobador rápido define todo, los demás no cuentan.
- **Veredicto:** rechazado.

### Majority vote con quorum

- ✅ Decisión robusta.
- ❌ Lento, inviable sin quorum.
- ❌ Contradice "tiempo es valioso".
- **Veredicto:** rechazado.

### Hierarchical authority (rangos)

- ✅ Refleja realidad organizacional.
- ❌ Requiere modelo de roles formalizado, fuera de scope v1.
- ⚠️ Documentado como future work para v2.
- **Veredicto:** rechazado para v1.

### Veto absoluto desde rechazo

- "Cualquier reject cancela la acción".
- ❌ Da poder excesivo a un solo aprobador (especialmente atacante con cuenta comprometida).
- ❌ Asimetría hacia inacción contradice security mindset.
- **Veredicto:** rechazado.

## Consecuencias

### Positivas

- Resuelve split-brain con política explícita y defendible.
- Audit trail completo para compliance / informe.
- **Demo material excepcional:** escenificar split-brain en vivo con 4 aprobadores y conservative-wins resolution es prácticamente único entre proyectos universitarios.
- Vocabulario de Site Reliability Engineering aplicado a security — el profesor lo reconoce.

### Negativas

- Complejidad: state machine en Redis con timeouts y consolidación.
- Falsos positivos potenciales: si conservative-wins ejecuta sobre 1 approve / 3 reject, se ejecuta una acción que la mayoría no quería. Aceptable porque la acción es reversible.

## Vector de ataque mitigado

**T-NEW-01 (a documentar en threat model):** atacante con cuenta de email comprometida da "reject" a contención de su propio ataque.
- Mitigación: conservative-wins. Si solo otro aprobador da "approve", la contención ejecuta de todas formas.
- Esto convierte una potencial vulnerabilidad (cuenta comprometida puede deshabilitar defensa) en un costo limitado (atacante necesita comprometer la mayoría de cuentas para vetar todas las contenciones).

## Revisión

A re-evaluar si en testing se observa que conservative-wins genera demasiados aislamientos no deseados. Si la ratio "rejected by majority but executed anyway" supera 10% de los conflictos, ajustar política (posiblemente a "supermajority required to reject").

## Actualizaciones posteriores

- **Semana 2:** se añade la política de gestión del secreto JWT (Q6 de `OPEN_QUESTIONS_RESOLUTION.md`) — sección "Audit trail obligatorio" actualizada.
