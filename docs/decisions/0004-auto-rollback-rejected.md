# ADR-0004: Auto-rollback "dead man's switch" — REJECTED

**Estado:** Rechazado (decisión documentada para futura referencia)
**Fecha:** Semana 1
**Autores:** P1 (Enzo)
**Revisores:** Equipo completo

---

## Contexto

Patrón considerado: si el sistema ejecuta una contención automática (aislamiento de host) y nadie del equipo confirma "sí, era ataque real" en X minutos, el sistema **automáticamente revierte** la acción.

Justificación del patrón en industria: si nadie está disponible para confirmar a las 3 AM, probablemente el host aislado es un servicio que la empresa necesita más que la incertidumbre del ataque.

## Decisión

**Rechazado. NO implementar auto-rollback.**

## Razones

### 1. Contradice el principio de "containment fails closed"

ADR-0003 y la sección de Resilience del SAD (R-3) establecen que el sistema **falla cerrado, no abierto**. Auto-rollback hace exactamente lo opuesto: si el equipo no responde, la contención se deshace silenciosamente.

Para un atacante esto sería un beneficio explícito: "espera 30 min, el host se reconecta solo, continúa el ataque". Convierte una fortaleza arquitectónica en debilidad.

### 2. Premisa incorrecta sobre incentivos

El patrón asume: *"si nadie respondió, probablemente era falso positivo y el host es importante"*.

La premisa correcta es: *"si nadie respondió a las 3 AM, no sabemos si era ataque o falso positivo, y el host sigue aislado hasta que alguien decida con información"*.

Asumir benignidad en ausencia de información es lo opuesto a security mindset.

### 3. Mejor solución existe: escalación

Si el problema es "nadie responde a las 3 AM", la solución profesional es **escalación a otro canal o persona**, no auto-rollback:
- Email no respondido en N min → SMS / llamada vía PagerDuty.
- SMS no respondido → escalation manager.
- Y así sucesivamente.

Esto mantiene "fails closed" mientras resuelve el problema operacional real.

### 4. Caso de uso real: ataques low-and-slow

Algunos ataques (APTs sofisticados, ransomware con dwell time) están explícitamente diseñados para activarse en ventanas donde el SOC no está pendiente. Auto-rollback es regalo perfecto para este patrón: el atacante solo necesita esperar la ventana de 30 min para que la contención se deshaga.

## Alternativas consideradas

### Auto-rollback con confirmación explícita ("disable auto-rollback per host")

- Se permite auto-rollback solo en hosts no-críticos.
- ⚠️ Mejora el patrón pero mantiene el principio inverso (asumir benignidad).
- **Veredicto:** rechazado por la misma razón.

### Escalación multi-canal (sin auto-rollback)

- Email → SMS → call → escalation manager.
- ✅ Resuelve el problema real (humano no disponible) sin sacrificar seguridad.
- **Veredicto:** documentado como future work en ARGOS, fuera de scope v1 (requiere integraciones adicionales).

### Notificación a múltiples destinatarios desde el inicio

- Mitigación parcial: si N personas reciben el email simultáneamente, probabilidad de que al menos una responda es mayor.
- ✅ Implementado en ADR-0005 (multi-recipient) y resuelto en ADR-0006 (split-brain).
- **Veredicto:** este es el camino correcto.

## Consecuencias

### Positivas

- Mantiene principio "containment fails closed".
- No introduce ventana de oportunidad explotable por atacante.
- ADR rechazado documentado: el equipo evaluó la opción y la descartó por razones explícitas. Esto es importante en informe técnico — muestra rigor de pensamiento, no descarte por ignorancia.

### Negativas (aceptadas)

- En escenarios reales sin SOC 24/7, host puede quedar aislado más tiempo del óptimo. Aceptable: "isolated longer than necessary" >> "reconnected during ongoing attack".

## Mensaje para la defensa académica

Si en exposición un evaluador pregunta *"¿qué pasa si nadie responde al email a las 3 AM?"*, la respuesta es:

> "El host queda aislado hasta que alguien revise. Consideramos auto-rollback explícitamente y lo rechazamos: ver ADR-0004. Argumentamos que en seguridad asumir benignidad sin información es un anti-pattern. La solución correcta al problema operacional es escalación multi-canal, documentada como future work."

Esta respuesta demuestra que el equipo:
1. Evaluó alternativas.
2. Tiene principios de diseño claros y consistentes.
3. Distingue entre problemas resueltos y problemas reconocidos pero out-of-scope.

## Referencias

- ADR-0003: Confidence-tiered automation.
- ADR-0006: Split-brain resolution.
- THREAT_MODEL.md, sección "Resilience by Design", propiedad R-3.
