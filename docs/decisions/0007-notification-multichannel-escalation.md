# ADR-0007: Cadena de notificación multi-canal con escalación temporal

**Estado:** Aceptado · arquitectura decidida · **implementación pendiente**
**Versión:** 2.0 (canales actualizados a contexto real del equipo)
**Fecha:** Semana 1-2 (v1) · 2026-05-23 (v2)
**Autores:** P1 (Enzo Ordoñez Flores)
**Revisores:** Equipo completo
**Relacionado con:** ADR-0003 (HITL SOAR), ADR-0005 (Notification channel abstraction), ADR-0006 (Split-brain)

---

## Contexto

ADR-0005 estableció la abstracción `NotificationChannel` y dejó deliberadamente abierta la cuestión de qué canales concretos implementar. La v1 quedó con un único canal (`EmailChannel`) por simplicidad de demo y por compatibilidad con el flujo JWT ya diseñado en ADR-0003.

Durante la revisión técnica con el asesor del curso emergió una crítica sólida al canal email para este caso de uso:

> *"Nadie revisa el correo todo el rato; para una ventana de aprobación de 3 minutos, el email es estructuralmente inadecuado."*

La crítica está respaldada por datos públicos: la mediana de tiempo de respuesta a email corporativo es de horas, no minutos. Las notificaciones push de email son fácilmente silenciables y la mayoría de usuarios las tienen agrupadas o deshabilitadas. Para un canal cuya consecuencia de no respuesta es `auto-isolate`, esto es la peor combinación posible.

La conclusión es que el problema no se resuelve eligiendo *un* canal mejor, sino aplicando el patrón industrial estándar de **multi-canal con escalación temporal**, que es lo que hacen PagerDuty, Opsgenie y Splunk On-Call.

## Decisión (v2)

**v1 implementará una cadena con tres canales activos en paralelo al inicio más un cuarto canal de escalación pagado disparado solo si los gratis fallan.** Los canales elegidos son los que el equipo realmente usa en su día a día — no canales teóricamente óptimos que nadie monitorea.

### Cambio v1 → v2

La v1 (semana 1) listaba Telegram + ntfy.sh + Slack + Twilio Voice. La v2 (semana 7 calendario) la actualiza a **Telegram + Discord + Twilio Voice + Email post-facto** por dos razones honestas:

- **ntfy.sh** se eliminó porque ningún integrante del equipo lo usa ni lo conoce. Un canal que nadie revisa es ruido configurado, no resiliencia.
- **Slack** se eliminó porque la organización del equipo no usa Slack. La hipótesis de "visibilidad en el canal del SOC" suponía un SOC formal que no existe en este contexto académico.
- **Discord** se añadió porque es el canal de chat que el equipo sí usa para coordinación cotidiana — un mensaje en el server del equipo tiene alta probabilidad de ser visto por al menos un compañero presente cuando dispara la alerta.
- **Twilio Voice DTMF** se mantiene porque es el canal con mayor probabilidad de "sacar a alguien de una reunión" y aporta impacto demostrable durante la exposición en vivo.

## Diseño

### Cadena de escalación temporal (T2 / production-critical)

| t (s) | Acción | Canal | Costo unitario | Justificación |
|---|---|---|---|---|
| **0** | Notificación primaria a todos los aprobadores | **Telegram Bot** con botones inline (`InlineKeyboardButton`) | $0 — API gratis e ilimitada | Push nativo agresivo, botones nativos, alta probabilidad de respuesta inmediata. Canal primario del equipo |
| **0** (paralelo) | Visibilidad pública en el server del equipo | **Discord webhook** con embed estructurado | $0 — webhooks son free | Permite que un compañero presente vea el incidente y alerte personalmente al aprobador. Discord ES donde el equipo coordina día a día |
| **60** si nadie respondió | Escalación a canal intrusivo | **Llamada Twilio con DTMF** (sin STT) | ~$0.02 USD por incidente | Última oportunidad humana; voz tiene la mayor probabilidad de despertar a alguien o sacarlo de una reunión. DTMF (`presione 1 / presione 2`) por confiabilidad |
| **180** | Auto-execute por timeout (per ADR-0003) | — | $0 | Bound the damage; throttle ya está activo desde t=0 |
| **post-decisión** | Resumen asíncrono | **Email** con análisis LLM + audit trail | $0 (SMTP) | Solo informativo; nunca en el path crítico |

### Diseño del IVR para la llamada de escalación

El script de la llamada sigue el patrón estándar **acción primero, detalle bajo demanda** — el aprobador puede decidir y colgar en menos de 20 s totales:

```
[TTS, voz neutra, español]
"Alerta crítica de ARGOS. Tier T2 en host VICTIM-01.
 Encriptación sospechosa. Throttle ya activo, daño contenido.
 Presione 1 para aprobar aislamiento.
 Presione 2 para rechazar.
 Presione 9 para repetir o escuchar análisis del LLM."
```

NO se usa speech-to-text por tres razones:

1. STT en condiciones reales tiene error de ~5% en single-word commands; en una decisión binaria de seguridad ese error es catastrófico.
2. DTMF es 100% determinístico y no requiere modelo de habla en el camino crítico.
3. El aprobador puede actuar sin necesidad de hablar (útil en reuniones, lugares públicos, transporte).

### Configuración

```yaml
# config/notification_channels.yaml
channels:
  telegram:
    enabled: true
    bot_token: ${TELEGRAM_BOT_TOKEN}
    chat_ids: [${APPROVER_1_CHAT_ID}, ${APPROVER_2_CHAT_ID}, ...]
    trigger_at_seconds: 0

  discord:
    enabled: true
    webhook_url: ${DISCORD_WEBHOOK_URL}
    mention_role_id: ${DISCORD_APPROVERS_ROLE_ID}   # @-mention para push agresivo
    trigger_at_seconds: 0

  twilio_voice:
    enabled: true
    account_sid: ${TWILIO_ACCOUNT_SID}
    auth_token: ${TWILIO_AUTH_TOKEN}
    from_number: ${TWILIO_FROM_NUMBER}
    to_numbers: [${APPROVER_1_PHONE}, ${APPROVER_2_PHONE}, ...]
    trigger_at_seconds: 60          # solo escala si nadie respondió a los 60s
    cost_cap_per_month_usd: 5       # hard cap, abre circuit breaker si se supera

  email:
    enabled: true
    smtp_host: ${SMTP_HOST}
    role: post_facto_summary        # nunca en path crítico
```

### El email se mantiene como notificación post-facto

`EmailChannel` permanece en el código pero se asigna al rol de **notificación informativa post-decisión**:

- *Tras* la ejecución (aprobada, rechazada, timeout) se envía un email resumen a todos los aprobadores con: decisión final, identidad de quien aprobó/rechazó, runbook del LLM, link al audit log.
- Este uso es asíncrono y no está en el path crítico, por lo que la latencia del email es irrelevante.

## Análisis de canales evaluados

### ✅ Telegram Bot — primario

- API genuinamente gratis e ilimitada.
- Soporta `InlineKeyboardButton` nativos (UX equivalente a un botón en email pero con push real).
- Librería `python-telegram-bot` madura, ~2 días de implementación.
- El bot puede editar el mensaje original al recibir el voto (`editMessageText`) → consolida visual de "este incidente ya tiene voto" en el chat.
- **Razón decisiva:** todo el equipo lo tiene instalado y notifica con push agresivo.

### ✅ Discord webhook — visibilidad pública

- Cero esfuerzo de implementación (~1 día).
- Convierte un evento privado (alerta a aprobador) en evento público en el server del equipo.
- Permite que un compañero del aprobador lo "empuje" personalmente si está distraído.
- Soporta `@mention` de role para push agresivo a todos los aprobadores simultáneamente.
- **Razón decisiva:** es donde el equipo coordina día a día — alta probabilidad de ser visto.

### ✅ Twilio Voice (DTMF) — escalación condicional

- Costo trivial al volumen del proyecto (~$2/mes peor caso).
- Trial gratis de Twilio cubre todo el ciclo del curso (~$15 USD).
- Solo se dispara cuando los canales free ya fallaron → costo correlacionado con valor.
- DTMF es 100% determinístico (no STT).
- **Razón decisiva (demo):** el contraste visual de "Telegram → Discord → suena el celular del aprobador en vivo" es de los momentos más impactantes que se pueden mostrar en exposición.

### ❌ ntfy.sh — rechazado en v2

Originalmente elegido como "redundancia gratis self-hosteable", pero nadie del equipo lo usa ni lo conoce. Un canal que nadie revisa es configuración muerta. La resiliencia que aportaba (independencia de proveedor) ya la cubre Discord — son dos servicios independientes (Telegram + Discord) sobre infraestructura distinta.

### ❌ Slack webhook — rechazado en v2

Originalmente justificado como "visibilidad en el canal del SOC". No hay SOC; este es un proyecto académico y el equipo no usa Slack. Discord cumple el mismo rol con higiene mejor (es donde ya están).

### ❌ WhatsApp Business API — rechazado

- **Costo no trivial:** ~$0.005–$0.08 USD por mensaje según región; la afirmación común de que "WhatsApp es gratis" se refiere a la app de consumidor, no a la API.
- **Templates pre-aprobados:** botones interactivos exigen plantillas con moderación de Meta (días/semanas para aprobar cambios).
- **Ventana de 24h:** mensajes fuera de la ventana de servicio cuestan más.
- **Vendor lock-in fuerte:** Meta puede vetar cuentas, cambiar políticas o subir precios sin recurso.
- Veredicto: **incompatible con un sistema de seguridad que evoluciona rápido.**

### ❌ WhatsApp consumidor con librerías no oficiales (Baileys, whatsapp-web.js) — rechazado

- Sin API oficial; las librerías hacen scraping del WhatsApp Web.
- Meta banea números detectados como bots regularmente.
- Inaceptable usar canal con probabilidad alta de ban silencioso para un sistema de seguridad.

### ❌ SMS como canal primario — rechazado

- ~$0.01/msg por Twilio (similar a voz por costo).
- No tiene botones; respuesta requiere SMS de vuelta o link a URL externa.
- Sin push agresivo (depende del cliente SMS del usuario).
- **Veredicto:** sin ventajas frente a Telegram, y peor latencia de respuesta.

### ❌ Voz como canal primario — rechazado

- Latencia de canal: 45–95 s sólo en el discado, TTS, y entrada DTMF — esto consume hasta el **50% del countdown de 3 min** en el peor caso.
- Voicemail intercepción: si el aprobador no contesta, la llamada va a buzón y el IVR le canta el mensaje a la grabadora; el sistema registra "llamada efectuada" pero no puede distinguir éxito de fracaso de manera fiable (Twilio AMD ~85% accuracy).
- **Veredicto:** voz solo tiene sentido como **escalación**, no como primario.

### ❌ Un solo canal (cualquiera) — rechazado

- Si Telegram cae globalmente, el SOC se queda ciego.
- Multi-canal es defense-in-depth, mismo principio que ya aplicamos en las capas de detección 1, 2 y 3.

## Consecuencias

### Positivas

- Tiempo de respuesta humano realista (mediana esperada < 30 s vs. horas con email).
- Costo operativo cercano a cero en operación normal; voz solo cuesta cuando ya falló todo lo gratis.
- Resiliencia frente a outage de un proveedor (2 canales independientes en paralelo en t=0 + 1 de escalación).
- Visibilidad pública en Discord crea presión social y trazabilidad conversacional.
- Reusa la abstracción `NotificationChannel` ya definida en ADR-0005 → cada canal es una nueva implementación de la interfaz.
- Canales elegidos sobre la base de **uso real del equipo**, no sobre justificación teórica.

### Negativas

- Aumenta la superficie de configuración (3 canales activos + 1 post-facto en lugar de 1).
- Cada canal nuevo introduce sus propias amenazas (ver §Threats abajo y referencias en `THREAT_MODEL.md`).
- Implementación es mayor: ~7 días vs. los ~2 que tomó email.
- Dependencias de terceros (Telegram, Discord, Twilio) — sin canal self-hosteable en esta v2.

## Nuevas amenazas introducidas

Esta decisión añade nuevos vectores que se documentan en `THREAT_MODEL.md` §3.7 como T-067, T-068, T-069 (ver detalles en ese documento). Resumen:

- **T-067 — SIM-swap del teléfono del aprobador:** atacante toma control del número y aprueba/rechaza vía Telegram (vía SMS confirmation hijack al re-loguear) o vía Twilio voice. Mitigación: `conservative-wins` (ADR-0006) protege contra rechazos malintencionados; alertar al aprobador por canal alternativo cuando se detecta nueva sesión Telegram.
- **T-068 — Caller-ID spoofing al endpoint Twilio:** atacante llama al webhook simulando ser el aprobador. Mitigación: aceptar callbacks solo correlacionados con una llamada *saliente activa*; nunca aceptar inbound calls como votos.
- **T-069 — Compromise del bot Telegram (token leakage):** atacante con el bot token puede leer mensajes y aprobar en nombre del bot. Mitigación: bot token en secreto rotable (Vault en producción, `.env` con permisos 0600 en v1); bot solo puede *enviar* mensajes, las respuestas se validan contra el chat_id del aprobador esperado.
- **T-070 (v2) — Discord webhook leak:** si el webhook URL se filtra, atacante puede publicar mensajes falsos en el server del equipo causando confusión. Mitigación: webhook URL en `.env` con permisos 0600; el sistema NO acepta votos vía Discord, solo notifica.

## Plan de implementación

| Fase | Trabajo | Owner | Estimación |
|---|---|---|---|
| 1 | Refactor de `EmailChannel` para que pueda ser solo post-facto | P1 | 0.5 día |
| 2 | `TelegramChannel` con `InlineKeyboardButton` y edición del mensaje al votar | P1 | 2 días |
| 3 | `DiscordChannel` (webhook + embed + role mention) | P1 | 1 día |
| 4 | `TwilioVoiceChannel` con TwiML para IVR DTMF | P1 | 2 días |
| 5 | `EscalationOrchestrator` (decide qué canales disparar y cuándo) | P1 | 1 día |
| 6 | Tests unitarios + integración con stub de aprobador | P1 | 1.5 días |
| **Total** | | | **~8 días** |

Si la presión de calendario obliga a recortar, el orden de sacrificio es: **Twilio Voice → Discord → Telegram** (Telegram es el último porque es el canal primario crítico). El `EmailChannel` post-facto queda garantizado como fallback en todos los casos.

## Revisión

A re-evaluar tras la primera demo en vivo. Si Telegram + Discord genera tasa de respuesta humana > 90% en los primeros 30s, considerar relegar la llamada Twilio a opcional / tier de pago. Si la tasa es < 70%, considerar invertir el orden y poner la llamada como concurrente al t=0.

## Notas para el informe técnico

Esta decisión es un buen ejemplo de **patrón industrial vs. solución intuitiva** y también de **canal teóricamente óptimo vs. canal que el equipo realmente usa**. La intuición inicial (email) era aparentemente razonable pero estructuralmente incompatible con la ventana de tiempo del problema. La v1 corrigió con multi-canal genérico (Telegram + ntfy + Slack + Twilio). La v2 corrige nuevamente con un principio operacional: un canal que nadie revisa es ruido configurado. La selección final (Telegram + Discord + Twilio + Email post-facto) es la que tiene mayor probabilidad de respuesta real, no la que se ve mejor en un slide. Documentar el camino completo es más valioso para el lector que solo presentar la conclusión.

## Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 | Semana 1-2 | Decisión original: Telegram + ntfy.sh + Slack + Twilio Voice. | P1 |
| 2.0 | 2026-05-23 | Canales actualizados al contexto real del equipo: Telegram (primario) + Discord (visibilidad, reemplaza Slack) + Twilio Voice (escalación) + Email (post-facto). Eliminados ntfy.sh y Slack porque ningún integrante los usa. T-070 añadido al threat model. | P1 |
