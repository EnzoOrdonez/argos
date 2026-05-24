# ADR-0008: Multi-vector scope expansion — from ransomware-only to broader XDR

**Estado:** Aceptado
**Fecha:** 2026-05-24
**Autores:** P1 (Enzo Ordoñez Flores)
**Revisores:** Equipo completo
**Relacionado con:** `PROJECT_BRIEF.md`, `SOLUTION_ARCHITECTURE_DOCUMENT.md` §5, `USE_CASES.md`, `THREAT_MODEL.md`

---

## Contexto

El kickoff del proyecto definió ARGOS como **Adaptive Ransomware Guard**, con foco exclusivo en el kill chain de ransomware (T1486 Data Encrypted for Impact, T1490 Inhibit System Recovery, T1083 File Discovery, T1562 Impair Defenses, T1021 Remote Services, T1071 Application Layer Protocol). Toda la arquitectura — features ML, reglas Sigma, canary deception, simulador — está diseñada para ese tipo de ataque.

En la revisión de Semana 7 (calendario) con el profesor del curso, al ver únicamente escenarios de ransomware reaccionó con sorpresa ("¿esto es todo lo que será?"). El proyecto se presenta a sí mismo en `README.md` como réplica arquitectónica de productos XDR comerciales (Microsoft Defender XDR, CrowdStrike Falcon, Palo Alto Cortex XDR) — y ninguno de esos productos está limitado a un único TTP family. Mantener el alcance ransomware-only contradice la promesa del README, debilita el argumento de "réplica XDR profesional" en defensa, y deja sin demostrar la principal propiedad del HITL: cómo el sistema maneja decisiones bajo incertidumbre con ataques de naturalezas distintas.

El proyecto no necesita cobertura exhaustiva multi-vector — eso requeriría rediseño completo. Lo que necesita es **cobertura mínima representativa** que demuestre que la arquitectura de 4 capas + SOAR + HITL es genuinamente adaptativa.

## Decisión

**Expandir el alcance de ARGOS de "ransomware-only" a "multi-vector EDR/XDR con énfasis primario en ransomware, extendido a Network Denial of Service y Application Abuse".** Concretamente:

1. **Rebrand del acrónimo:** "Adaptive Ransomware Guard" → "**Adaptive Response Guard**". Mantiene el acrónimo ARGOS, mantiene la URL `EnzoOrdonez/argos`, mantiene LICENSE. El nuevo "R" refleja que el sistema responde a múltiples categorías de amenazas, no solo a una.

2. **Añadir 3 use cases nuevos** al demo en vivo, cubriendo categorías MITRE distintas al kill chain de ransomware:
   - **UC-06 — DDoS volumetric:** ataque de red contra PostgreSQL VM. Detección rate-based via reglas Sigma de frecuencia nativas en Wazuh. Tactic: Impact (T1498 Network DoS). Tier T0 si rate excede umbral. Demuestra que el sistema cubre ataques de red, no solo endpoint.
   - **UC-07 — SELECT masivo legítimo (false positive escenario T2):** usuario ejecuta `SELECT *` que devuelve 100K filas en horario no laboral. ML detecta anomalía en query patterns (rows_returned, duration, hour_of_day), clasifica como T2, lanza countdown 3 minutos, aprobadores reciben contexto LLM, reconocen que es legítimo, **cancelan la contención**. Demuestra la pieza más valiosa del HITL: cómo el sistema maneja incertidumbre y cómo el humano puede prevenir daño cuando ML acierta-pero-equivocadamente. Tactic: Valid Accounts (T1078).
   - **UC-08 — SQL injection:** ataque contra app web dummy delante de PostgreSQL via `sqlmap`. Detección via reglas Sigma sobre patrones SQL injection en logs HTTP. Tactic: Initial Access (T1190 Exploit Public-Facing Application). Tier T1. Cubre OWASP Top 10 #1 (Injection).

3. **Expandir `argos_contracts.MITRE_WHITELIST`** con las 4 técnicas nuevas: T1498, T1499, T1078, T1190 (este último ya estaba presente).

4. **Documentar sub-categorías dentro de las capas existentes:**
   - Capa 1 (Sigma rules) tendrá sub-directorios: `detection/sigma-rules/ransomware/`, `detection/sigma-rules/network/`, `detection/sigma-rules/database/`, `detection/sigma-rules/webapp/`.
   - Capa 2 (ML) tendrá modelos especializados por dominio: `ml/models/ransomware_ensemble.pkl`, `ml/models/query_pattern_anomaly.pkl`, `ml/models/network_traffic_anomaly.pkl`. Comparten el pipeline pero tienen features distintas. Esto NO añade una "Capa 5" — sigue siendo 1 capa ML con múltiples modelos.
   - Capa 3 (canary) permanece estrictamente ransomware-specific (es una primitiva especializada para defensa contra encriptación; documentado como tal).
   - Capa 4 (LLM Triage) ya es agnóstico al tipo de alerta — sin cambios.

5. **Política sobre uso de Claude Code por integrantes:** cada integrante (P2, P3, P4) puede usar Claude Code como asistente para acelerar SU propia parte. La regla `CONTEXT.md §5` se reinterpreta: P1 no escribe código de otros con Claude Code; pero cada integrante es libre de usar Claude Code (o cualquier asistente de IA) en su propio módulo, siempre que entienda lo que produce y pueda defenderlo en viva.

## Alternativas consideradas

### A — Mantener ransomware-only estricto

- ✅ Cero cambios de scope, sprint actual no se mueve.
- ❌ El proyecto se contradice a sí mismo: se vende como XDR pero solo cubre un TTP family.
- ❌ Debilita el argumento profesional al evaluador.
- ❌ El T2 ambiguous solo tiene escenarios ransomware-like, narrativa débil.
- **Veredicto:** rechazado.

### B — Pivote completo a XDR multi-vector (cobertura exhaustiva)

- ✅ Argumento profesional más fuerte.
- ❌ Requiere reescribir SAD, threat model, todos los ADRs, todos los UCs.
- ❌ Implica agregar Capa 5 (Network Detection con Suricata + Zeek), Capa 6 (App Security con OWASP ModSecurity), etc.
- ❌ 4-6 semanas de redesign + implementación. No hay tiempo.
- **Veredicto:** rechazado.

### C — Expansión mínima representativa (esta decisión)

- ✅ Cobertura de 3 categorías MITRE distintas: Impact (ransomware + DDoS), Valid Accounts (FP legítimo), Initial Access (SQL injection).
- ✅ Argumento XDR defendible: "nuestro sistema demuestra arquitectura adaptativa con 3 vectores representativos; añadir más vectores sigue el mismo patrón".
- ✅ ~3-4 días-persona de trabajo adicional, cabe en el sprint con re-priorización.
- ✅ No requiere rediseño de capas — solo expansión dentro del framework existente.
- **Veredicto:** aceptado.

## Consecuencias

### Positivas

- El proyecto cumple lo que promete en el README (réplica XDR profesional).
- El demo cubre 3 vectores distintos en 13-15 minutos, ganando densidad narrativa.
- UC-07 demuestra la pieza más valiosa del HITL: cancelación de contención por aprobador humano. Esta es la diferenciación clave frente a SIEMs sin SOAR.
- MITRE coverage matrix crece de 6 técnicas a 10 técnicas, en 4 tactics (Impact, Valid Accounts, Initial Access, Defense Evasion).
- El informe técnico tiene argumento más fuerte para defender "adaptabilidad arquitectónica".

### Negativas

- Trabajo adicional para P3 (Sigma rules en 3 nuevas categorías), P4 (simuladores + pgAudit + hping3 + sqlmap setup), P2 (modelos ML especializados por dominio), P1 (wiring SOAR con nuevos UCs y MITRE IDs).
- Demo en vivo crece de ~13 min a ~17 min. Requiere ajuste de tiempos (UC-05 sigue en vivo per decisión del user, ningún UC se baja a video).
- Threat model debe expandirse con nuevas amenazas T-080+ relacionadas a los nuevos vectores.
- La capa 3 (canary) sigue siendo ransomware-only, lo cual hay que documentar honestamente (no es defecto, es especialización deliberada).

## Plan de implementación

| Fase | Trabajo | Owner | Esfuerzo |
|------|---------|-------|---------|
| 1 | Update MITRE_WHITELIST + rebrand acrónimo en docs | P1 | 0.5 día |
| 2 | Sigma rules para DDoS rate-based + query patterns + SQLi signatures | P3 | 2.5 días |
| 3 | pgAudit setup + simuladores hping3/sqlmap wrappers + SELECT masivo simulator | P4 | 2 días |
| 4 | Modelos ML especializados (query_pattern + network_traffic) | P2 | 2 días |
| 5 | Wiring SOAR con nuevos UCs + categoría-aware tier classifier | P1 | 1.5 días |
| 6 | Rehearsals con los 8 UCs corriendo | Todos | 1 día |
| **Total** | | | **~9.5 días-persona** |

Esfuerzo distribuido entre las 3 semanas restantes hasta el 13 de junio. El sprint inicial de 7 días sigue válido como buffer para que P1 detecte temprano si los otros integrantes están atrasados.

## Revisión

A re-evaluar en el primer ensayo completo de los 8 UCs (probablemente Semana 8 calendario, Día 7 del sprint o Día 14 del proyecto). Si el demo excede 18 minutos en vivo, se decide qué UC bajar a "ejecutar pero no narrar" para mantener la ventana ~15 min de exposición.

## Notas para el informe técnico

Esta decisión es un buen ejemplo de **iteración arquitectónica honesta**. El kickoff identificó ransomware como el problema #1 de empresas LATAM y diseñó la arquitectura para ese caso. La revisión del profesor en Semana 7 expuso que el alcance acotado no encajaba con la narrativa de "réplica XDR profesional". En lugar de mantener el alcance original por tozudez o pivotar completamente por reactividad, el equipo eligió la expansión mínima representativa que mantiene la coherencia del diseño y agrega cobertura defendible. Documentar este camino de decisión (kickoff → revisión → expansión controlada) es más valioso que pretender que el alcance multi-vector estuvo desde el principio.

## Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 | 2026-05-24 | Initial — expansión de scope ransomware-only a multi-vector con énfasis primario en ransomware. Rebrand "Ransomware Guard" → "Response Guard". 3 nuevos UCs (DDoS, SELECT masivo FP, SQL injection). MITRE coverage expandida. Política Claude Code para integrantes reinterpretada. | P1 |
