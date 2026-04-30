# ADR-0002: Wazuh agent heartbeat — keep default 60s interval

**Estado:** Aceptado
**Fecha:** Semana 1
**Autores:** P1 (Enzo)
**Revisores:** Equipo completo

---

## Contexto

El intervalo de heartbeat del agente Wazuh determina la latencia de detección del escenario "atacante deshabilita el agente en la víctima". Default Wazuh: `notify_time=10s` con `time-reconnect=60s` → desconexión efectiva detectada en ~60-90 segundos.

Discutida la opción de bajar a 15-20s para reducir esta ventana ante ransomware veloz que mate el agente.

## Decisión

**Mantener configuración default (60s effective).**

## Trade-offs aceptados

### Si bajamos a 15-20s

| Costo | Magnitud lab | Magnitud producción |
|-------|--------------|---------------------|
| Tráfico de red | Insignificante (~5 KB/min) | 14 MB/min con 5K agentes |
| CPU manager | Invisible | Medible, manejable |
| **False positives por desconexión transitoria** | **Frecuentes** | **Frecuentes** |
| **Alert fatigue sobre rule 502** | **Alta** | **Alta** |
| Confianza degradada en la señal | Alta | Alta |

### Lo que NO ganamos al bajar

1. No detectamos más rápido el ataque inicial — eso es trabajo de Capas 1, 2 y 3.
2. No detenemos el ataque — eso es SOAR.
3. Solo reducimos la ventana entre "agente muerto" y "manager se entera".

### Defensa real contra "atacante mata agente"

No es detectar que el agente murió — es detectar el ataque ANTES de que escale a privilegios para matar el agente.
- **Capa 3 (canary)** detecta en segundos sin necesitar agente sano.
- **Capa 1 (Sigma rules)** detecta T1562.001 (Disable or Modify Tools) que precede al kill del agente.
- **Capa 2 (ML anomaly)** detecta el patrón de privilege escalation.

Bajar el heartbeat protege contra un escenario raro (atacante sofisticado, ataque rápido, agente sano hasta el final) a costo de degradar una señal de uso frecuente.

## Alternativas consideradas

### Bajar a 15s permanentemente

- ❌ Alert fatigue inevitable en operación normal.
- ❌ Aparta del default industrial sin justificación fuerte.
- ✅ Mejora ventana en escenario raro.
- **Veredicto:** rechazado.

### Bajar solo durante demo

- ✅ Ventaja narrativa puntual ("detectamos en 20s").
- ❌ Apartarse de default en demo + volver a default en repo público requiere justificar inconsistencia.
- ⚠️ Posible si hace falta narrativa específica del demo, documentado como excepción.
- **Veredicto:** opcional, decidir en semana 13 si la narrativa lo requiere.

### Tuning adaptativo (heartbeat dinámico según contexto)

- ✅ Teóricamente óptimo.
- ❌ Complejidad operacional alta.
- ❌ Out of scope Wazuh OSS (requiere customización).
- **Veredicto:** documentado como future work, no implementado.

## Consecuencias

### Positivas

- Configuración estándar industrial defendible.
- Confianza alta en rule 502 cuando dispara.
- Documentación auditable: "we explicitly evaluated and chose the default".

### Negativas

- Ventana teórica de 60-90s entre kill de agente y detección. Documentada como riesgo residual T-050 en threat model.
- Si en evaluación final demostramos escenario "agent killed, no detection until heartbeat", el TTD de ese ataque específico se reporta honestamente (no maquillamos).

## Revisión

Re-evaluar en Gate 2 (semana 7) si la evaluación experimental sugiere que la ventana de 60s es problemática para escenarios específicos del demo. La decisión queda abierta a cambio si los datos lo justifican.
