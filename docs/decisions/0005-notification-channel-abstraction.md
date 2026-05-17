# ADR-0005: Notification channel abstraction

**Estado:** Aceptado · implementaciones concretas en ADR-0007
**Fecha:** Semana 1
**Autores:** P1 (Enzo)
**Revisores:** Equipo completo

---

## Contexto

> **Nota (Semana 9):** Este ADR define la **abstracción `NotificationChannel`** y sigue siendo la interfaz canónica. Las **implementaciones concretas** y la cadena de escalación temporal entre canales se definen en `ADR-0007` (Telegram + ntfy.sh + Slack + Twilio Voice). Email queda degradado al rol de notificación post-facto. Ver §"Actualizaciones posteriores" al pie.

ADR-0003 introduce email + botón de aprobación como canal de comunicación con el equipo de TI. En el futuro se quieren soportar canales adicionales: Slack, Microsoft Teams, Telegram, SMS, llamada vía PagerDuty.

Sin abstracción explícita, agregar cada nuevo canal requeriría modificar el Decision Engine y duplicar lógica de templating, JWT, y handling de respuestas.

## Decisión

**Implementar una interfaz abstracta `NotificationChannel` con método polimórfico `send(approval_request)` y `verify_response(token)`. v1 implementa solo `EmailChannel`. Channels futuros se agregan como nuevas implementaciones de la interfaz.**

## Diseño

### Interfaz base

```python
# notification/base.py
from abc import ABC, abstractmethod
from pydantic import BaseModel
from datetime import datetime

class ApprovalRequest(BaseModel):
    incident_id: str
    tier: str  # T0, T1, T2, T3
    alert_summary: str
    llm_analysis: dict
    proposed_actions: list[str]
    recipients: list[str]
    timeout_seconds: int
    created_at: datetime

class ApprovalResponse(BaseModel):
    incident_id: str
    responder: str
    decision: str  # "approve" | "reject" | "revert"
    timestamp: datetime
    channel: str  # "email", "slack", etc.

class NotificationChannel(ABC):
    @abstractmethod
    async def send(self, request: ApprovalRequest) -> bool:
        """Send approval request through this channel. Return True on success."""

    @abstractmethod
    async def verify_response(self, token: str) -> ApprovalResponse:
        """Validate incoming response token and return parsed response."""

    @abstractmethod
    def channel_name(self) -> str:
        """Return canonical name of channel for audit log."""
```

### Implementación v1: EmailChannel

```python
# notification/email_channel.py
class EmailChannel(NotificationChannel):
    def __init__(self, smtp_config, jwt_secret):
        self.smtp = smtp_config
        self.jwt = jwt_secret

    async def send(self, request: ApprovalRequest) -> bool:
        # Generate JWT token per recipient with 5-min expiration
        # Render Jinja2 template with action buttons (approve / reject)
        # Send via SMTP
        ...
```

### Configuración runtime

```bash
# .env
NOTIFICATION_CHANNELS=email
# Future: NOTIFICATION_CHANNELS=email,slack,telegram
```

Cada channel se inicializa al startup según la lista. El Decision Engine envía a todos los channels activos en paralelo.

### Channels futuros (no implementados en v1)

| Channel | Trigger | Tier típico | Esfuerzo estimado |
|---------|---------|-------------|-------------------|
| Slack | webhook + Bolt SDK | T1, T2 | 2-3 días |
| Microsoft Teams | webhook + Adaptive Cards | T1, T2 (enterprise) | 2-3 días |
| Telegram | bot API | T1, T2 (LATAM) | 1-2 días |
| SMS | Twilio | T0, T1 (urgent) | 1-2 días |
| PagerDuty | API + escalation policy | T0 (24/7 SOC) | 3-4 días |

## Configuración de destinatarios

Aunque v1 solo implementa email, el sistema debe soportar configuración runtime de destinatarios para que en el futuro un operador pueda decidir a qué cuentas se envían los emails de aprobación.

### Diseño

```yaml
# config/recipients.yaml
default_recipients:
  - email: it_lead@empresa.com
    role: it_lead
    priority: 1
  - email: soc_analyst@empresa.com
    role: analyst
    priority: 2

per_tier_overrides:
  T0:  # critical: notify everyone urgently
    additional_recipients:
      - email: ciso@empresa.com
        role: ciso
        priority: 0
  T3:  # informational: only analyst
    only_recipients:
      - email: soc_analyst@empresa.com
        role: analyst
        priority: 2
```

### UI futura para reconfiguración

Para v1: configuración por archivo YAML, edición manual.
Future: panel admin en Streamlit para que un operador modifique destinatarios sin tocar archivos.

## Alternativas consideradas

### Hardcodear email en Decision Engine

- ❌ Lock-in al canal.
- ❌ Cambio futuro requiere refactor profundo.
- **Veredicto:** rechazado.

### Adoptar librería existente (Apprise, dispatch)

- ✅ Soporta muchos canales out-of-the-box.
- ❌ Apprise no tiene concepto de "approval response with signed token" — diseñado para notificaciones one-way.
- ⚠️ Adaptable pero introduce dependencia pesada.
- **Veredicto:** considerado, descartado por mismatch con caso de uso bidireccional.

## Consecuencias

### Positivas

- Patrón industrial (Strategy pattern aplicado a notifications).
- Adding new channel = new file, no modifications elsewhere.
- Vendor portability como ya establecido en ADR-0001 para LLM.

### Negativas

- Pequeña overhead de abstracción para v1 que solo tiene un channel.
- Cambios futuros en la interfaz base obligan modificar todas las implementaciones.

## Revisión

A re-evaluar si en el desarrollo se descubre que la abstracción no calza para algún channel específico (por ejemplo, voz humana vía PagerDuty no encaja exactamente en send/verify_response sincrónico).

## Actualizaciones posteriores

- **Semana 9:** ADR-0007 cierra el capítulo de implementaciones concretas para v1: Telegram (primario) + ntfy.sh + Slack/Discord (paralelos en t=0) + Twilio Voice DTMF (escalación en t=60s). El comentario "voz humana vía PagerDuty no encaja exactamente" en la sección Revisión fue resuelto adaptando el patrón: el `TwilioVoiceChannel` usa correlation_id por llamada saliente para encajar en `send` + verificación asincrónica de respuestas DTMF. La interfaz definida en este ADR no requirió cambios. Email pasa a notificación post-facto (resumen tras la decisión final), preservando la implementación de `EmailChannel` pero reasignando su rol.
