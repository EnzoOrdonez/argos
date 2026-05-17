# ADR-0007: Cadena de notificación multi-canal con escalación temporal

**Estado:** Aceptado
**Fecha:** Semana 9 (post Gate 2, feedback de profesor + revisión crítica)
**Autores:** P1 (Enzo)
**Revisores:** Equipo completo
**Relacionado con:** ADR-0003 (HITL SOAR), ADR-0005 (Notification channel abstraction), ADR-0006 (Split-brain)

---

## Contexto

ADR-0005 estableció la abstracción `NotificationChannel` y dejó deliberadamente abierta la cuestión de qué canales concretos implementar. La v1 quedó con un único canal (`EmailChannel`) por simplicidad de demo y por compatibilidad con el flujo JWT ya diseñado en ADR-0003.

Durante la revisión técnica con el asesor del curso emergió una crítica sólida al canal email para este caso de uso:

> *"Nadie revisa el correo todo el rato; para una ventana de aprobación de 3 minutos, el email es estructuralmente inadecuado."*

La crítica está respaldada por datos públicos: la mediana de tiempo de respuesta a email corporativo es de horas, no minutos. Las notificaciones push de email son fácilmente silenciables y la mayoría de usuarios las tienen agrupadas o deshabilitadas. Para un canal cuya consecuencia de no respuesta es `auto-isolate`, esto es la peor combinación posible.

Se evaluaron canales alternativos (WhatsApp, Telegram, voz, SMS) y un análisis honesto reveló dos errores conceptuales adicionales:

1. La afirmación de que *"WhatsApp es gratis"* es falsa para uso programático: WhatsApp Business API cobra por conversación (~$0.005–$0.08 por mensaje según región) y requiere templates pre-aprobados por Meta para botones interactivos.
2. La afirmación de que *"la voz es prohibitivamente cara"* es desproporcionada: Twilio Voice cuesta ~$0.013/min, lo que para el volumen previsto de ARGOS son fracciones de dólar al mes. El problema real con voz no es el costo sino la **latencia de canal** (45–95 s consume hasta el 50% del countdown de 3 min).

La conclusión es que el problema no se resuelve eligiendo *un* canal mejor, sino aplicando el patrón industrial estándar de **multi-canal con escalación temporal**, que es lo que hacen PagerDuty, Opsgenie y Splunk On-Call.

## Decisión

**v1 implementará una cadena de notificación con tres canales paralelos al inicio (todos gratis) más un cuarto canal de escalación pagado disparado solo si los gratis fallan. La voz no se usa como primario; es el último recurso antes del timeout automático.**

## Diseño

### Cadena de escalación temporal (T2/T3 únicamente)

| t (s) | Acción | Canal | Costo unitario | Justificación |
|---|---|---|---|---|
| **0** | Notificación primaria a todos los aprobadores | **Telegram Bot** con botones inline (`InlineKeyboardButton`) | $0 — API gratis e ilimitada | Push nativo agresivo, botones nativos, alta probabilidad de respuesta inmediata |
| **0** (paralelo) | Push de respaldo independiente del proveedor | **ntfy.sh** con prioridad `urgent` | $0 — self-hosteable | Resiliencia: si Telegram cae globalmente (precedente: 2018, 2022, 2023), este canal sigue activo. Suena con prioridad alta y rompe el modo No Molestar |
| **0** (paralelo) | Visibilidad pública en el canal del SOC | **Slack o Discord webhook** | $0 — webhooks son free | Permite que un humano *no* aprobador pero *presente* vea el incidente y alerte personalmente al aprobador. Genera log conversacional auditable |
| **60** si nadie respondió | Escalación a canal intrusivo | **Llamada Twilio con DTMF** (sin STT) | ~$0.02 USD por incidente | Última oportunidad humana; voz tiene la mayor probabilidad de despertar a alguien o sacarlo de una reunión. DTMF (`presione 1 / presione 2`) en vez de speech-to-text por confiabilidad |
| **180** | Auto-execute por timeout (per ADR-0003) | — | $0 | Bound the damage; throttle ya está activo desde t=0 |

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

NO se usa speech-to-text (`"diga ACEPTO o DENEGAR"`) por tres razones:

1. STT en condiciones reales (ruido, acento, voz somnolienta, "sí, acepto" vs "acepto") tiene error de ~5% en single-word commands; en una decisión binaria de seguridad ese error es catastrófico.
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

  ntfy:
    enabled: true
    server: https://ntfy.sh         # o self-hosted
    topic: argos-approvals-${ENV}
    priority: urgent
    trigger_at_seconds: 0

  slack:
    enabled: true
    webhook_url: ${SLACK_WEBHOOK_URL}
    channel: "#argos-soc"
    trigger_at_seconds: 0

  twilio_voice:
    enabled: true
    account_sid: ${TWILIO_ACCOUNT_SID}
    auth_token: ${TWILIO_AUTH_TOKEN}
    from_number: "+15551234567"
    to_numbers: [${APPROVER_1_PHONE}, ${APPROVER_2_PHONE}, ...]
    trigger_at_seconds: 60          # solo escala si nadie respondió a los 60s
    cost_cap_per_month_usd: 5       # hard cap, abre circuit breaker si se supera
```

### El email NO se elimina, se degrada a canal de notificación post-facto

`EmailChannel` permanece en el código pero se reasigna al rol de **notificación informativa post-decisión**:

- *Tras* la ejecución (aprobada, rechazada, timeout) se envía un email resumen a todos los aprobadores con: decisión final, identidad de quien aprobó/rechazó, runbook del LLM, link al audit log.
- Este uso es asíncrono y no está en el path crítico, por lo que la latencia del email es irrelevante.

## Análisis de canales evaluados

### ✅ Telegram Bot — escogido como primario

- API genuinamente gratis e ilimitada.
- Soporta `InlineKeyboardButton` nativos (UX equivalente a un botón en email pero con push real).
- Librería `python-telegram-bot` madura, ~5 días de implementación.
- El bot puede editar el mensaje original al recibir el voto (`editMessageText`) → consolida visual de "este incidente ya tiene voto" en el chat.

### ✅ ntfy.sh — escogido como redundancia gratis

- Self-hosteable (no dependencia de tercero si se quiere).
- Prioridad `urgent` rompe el modo No Molestar de Android e iOS.
- Cliente nativo para Android e iOS, también web push.
- 10 líneas de código (es solo un POST HTTP).

### ✅ Slack/Discord webhook — escogido como visibilidad pública

- Cero esfuerzo de implementación.
- Convierte un evento privado (alerta a aprobador) en evento público (canal del SOC).
- Permite que un compañero del aprobador lo "empuje" personalmente si está distraído.

### ✅ Twilio Voice (DTMF) — escogido como escalación condicional

- Costo trivial al volumen del proyecto (~$2/mes peor caso).
- Trial gratis de Twilio cubre todo el ciclo del curso (~$15 USD).
- Solo se dispara cuando los canales gratis ya fallaron → costo correlacionado con valor.
- DTMF es 100% determinístico (no STT).

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
- Resiliencia frente a outage de un proveedor (3 canales independientes en paralelo en t=0).
- Visibilidad pública en Slack/Discord crea presión social y trazabilidad conversacional.
- Reusa la abstracción `NotificationChannel` ya definida en ADR-0005 → cada canal es una nueva implementación de la interfaz.

### Negativas

- Aumenta la superficie de configuración (4 canales activos en lugar de 1).
- Cada canal nuevo introduce sus propias amenazas (ver §Threats abajo y referencias en `THREAT_MODEL.md`).
- Implementación es mayor: ~10 días vs. los ~2 que tomó email.
- Dependencias de terceros (Telegram, Slack, Twilio) — mitigado parcialmente con ntfy self-hosteable.

## Nuevas amenazas introducidas

Esta decisión añade nuevos vectores que se documentan en `THREAT_MODEL.md` §3.7 como T-067, T-068, T-069 (ver detalles en ese documento). Resumen:

- **T-067 — SIM-swap del teléfono del aprobador:** atacante toma control del número y aprueba/rechaza vía Telegram (vía SMS confirmation hijack al re-loguear) o vía Twilio voice. Mitigación: `conservative-wins` (ADR-0006) protege contra rechazos malintencionados; alertar al aprobador por canal alternativo cuando se detecta nueva sesión Telegram.
- **T-068 — Caller-ID spoofing al endpoint Twilio:** atacante llama al webhook simulando ser el aprobador. Mitigación: aceptar callbacks solo correlacionados con una llamada *saliente activa*; nunca aceptar inbound calls como votos.
- **T-069 — Compromise del bot Telegram (token leakage):** atacante con el bot token puede leer mensajes y aprobar en nombre del bot. Mitigación: bot token en secreto rotable (Vault en producción, `.env` con permisos 0600 en v1); bot solo puede *enviar* mensajes, las respuestas se validan contra el chat_id del aprobador esperado.

## Plan de implementación

| Fase | Trabajo | Owner | Estimación |
|---|---|---|---|
| 1 | Refactor de `EmailChannel` para que pueda ser solo post-facto | P1 | 0.5 día |
| 2 | `TelegramChannel` con `InlineKeyboardButton` y edición del mensaje al votar | P1 | 2 días |
| 3 | `NtfyChannel` con prioridad urgent y action buttons | P1 | 0.5 día |
| 4 | `SlackChannel` (webhook + BlockKit) | P1 | 1 día |
| 5 | `TwilioVoiceChannel` con TwiML para IVR DTMF | P1 | 2 días |
| 6 | `EscalationOrchestrator` (decide qué canales disparar y cuándo) | P1 | 1 día |
| 7 | Tests unitarios + integración con stub de aprobador | P1 | 2 días |
| **Total** | | | **~9 días** |

Reemplaza el target original de Gate 3 que asumía solo email (~3 días). El delta de 6 días se absorbe del buffer de Gate 3 → 4 (PRs Sigma upstream).

## Revisión

A re-evaluar tras la primera demo en vivo (Semana 13). Si Telegram + ntfy + Slack genera tasa de respuesta humana > 90% en los primeros 30s, considerar relegar la llamada Twilio a opcional / tier de pago. Si la tasa es < 70%, considerar invertir el orden y poner la llamada como concurrente al t=0.

## Notas para el informe técnico

Esta decisión es un buen ejemplo de **patrón industrial vs. solución intuitiva**. La intuición inicial (email) era *aparentemente razonable* pero estructuralmente incompatible con la ventana de tiempo del problema. La solución correcta no es elegir un canal mejor sino aplicar el patrón de escalación multi-canal que la industria de incident response ya converge — exactamente lo que hacen PagerDuty, Opsgenie y Splunk On-Call. Documentar el camino completo (por qué email falla, por qué WhatsApp Business no es gratis, por qué voz no es primario) es más valioso para el lector que solo presentar la conclusión.
