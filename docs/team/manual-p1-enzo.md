# Manual P1 — Enzo Ordoñez Flores · Líder técnico

| Campo | Valor |
|-------|-------|
| Rol | Líder técnico e integrador cross-layer |
| Owns | SOAR Decision Engine (`soar/`) · HITL workflow · Notification Service · Approval API · `argos_contracts` |
| No owns | Layers 1/3 (P3) · Layer 2 ML + Layer 4 LLM (P2) · Lab + UI + DB (P4) |
| Outputs blocking | `Incident` model en Redis → P4 lee la UI · Tier router + Approver workflow → demo UC-04 |
| Entrega final | **13 de junio de 2026 (sábado)** |
| Cómo leer | Linealmente. Cada Fase asume la anterior cerrada. Cada sub-sección termina con un bloque de **Verificación**; no avances si falla algo. |

---

## 0. Tu charter en una frase

> Tú haces que las 4 capas hablen entre ellas, que un humano pueda aprobar/rechazar acciones críticas, y que las notificaciones lleguen a 4 canales sin caerse. Si tu pieza falla, el demo falla.

### 0.1 Tu camino crítico

```text
Fase 1            Fase 2                 Fase 3              Fase 4
(cimientos)       (skeletons)            (integración)       (polish)

prereqs ────┐                                                 
cuentas ────┼──→ tier router ──→ consume eventos ──→ rehearsal UC-01
repo ───────┘    notif telegram     reales del lab        rehearsal UC-04
                 notif discord      audit en PG           edge cases
                 notif twilio       LLM hook              contingencia
                 approval API       UC end-to-end
                 two-person rule
                 consolidation 60s
```

Las Fases son **orden de implementación**, no calendario. Avanzas cuando la anterior pasa su checklist.

### 0.2 Cómo leer cada sub-sección

Cada componente sigue la misma plantilla:

1. **Contexto** — para qué sirve, por qué importa.
2. **Pasos manuales** — si hay instalación o configuración que NO es un comando (clicks en una web, registros en un servicio externo).
3. **Comandos** — bloque copiable.
4. **Salida esperada** — qué debe imprimir el comando si todo está bien.
5. **Verificación** — comando(s) específicos para confirmar que el componente quedó funcional antes de seguir.
6. **Si algo falla** — síntoma observable → causa → fix.

---

# Fase 1 — Cimientos

## 1.1 Prerequisites del sistema

### Contexto

Confirmas que tu laptop tiene las versiones exactas de Python, git, Docker y herramientas CLI antes de tocar el código. El 80 % de los errores raros viene de versiones desalineadas entre integrantes.

### Comandos

```bash
python3 --version
pip --version
git --version
docker --version && docker compose version
redis-cli --version
curl --version | head -1
jq --version
```

### Salida esperada

```text
Python 3.11.7
pip 23.x.x from /usr/lib/python3/dist-packages/pip (python 3.11)
git version 2.34.1
Docker version 24.x.x, build xxxxx
Docker Compose version v2.x.x
redis-cli 7.0.x
curl 7.81.0 (x86_64-pc-linux-gnu) ...
jq-1.6
```

### Verificación

```verify
python3 -c "import sys; assert sys.version_info[:2] == (3, 11), sys.version" && echo "Python OK"
docker ps >/dev/null && echo "Docker OK"
redis-cli --version >/dev/null && echo "redis-cli OK"
```

Esperado:

```text
Python OK
Docker OK
redis-cli OK
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `python3 --version` no es 3.11 | Versión equivocada del sistema | Ubuntu: `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.11 python3.11-venv python3.11-dev` · macOS: `brew install python@3.11` |
| `docker ps` da `Cannot connect to the Docker daemon` | Daemon parado o usuario sin grupo `docker` | `sudo systemctl start docker` + `sudo usermod -aG docker $USER && newgrp docker` |
| `redis-cli` not found | Paquete no instalado | `sudo apt install redis-tools` |

---

## 1.2 Crear cuentas externas

### Contexto

ARGOS depende de cuatro servicios externos para LLM y notificaciones. Las cuatro tienen tier gratuito suficiente para el demo. Las credenciales se guardan en `.env` (que NUNCA se commitea).

### 1.2.1 Bot de Telegram (canal primario de notificaciones)

#### Pasos manuales

1. Abre **Telegram** (móvil o desktop).
2. Busca el usuario `@BotFather` y abre su chat.
3. Envía el mensaje `/newbot`.
4. Cuando pida nombre, responde `ARGOS Alerts Bot`.
5. Cuando pida username, responde `argos_alerts_<tu_inicial>_bot` (debe terminar en `_bot`).
6. BotFather responde con un token con formato `7123456789:AAFxxxxxxxx...`. **Cópialo** — es tu `TELEGRAM_BOT_TOKEN`.
7. Para obtener tu `TELEGRAM_CHAT_ID`:
   1. Envía cualquier mensaje al bot recién creado (por ejemplo, `hola`).
   2. Abre en navegador `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`.
   3. En la respuesta JSON busca `"chat":{"id": 123456789, ...}`. Ese número es tu `TELEGRAM_CHAT_ID`.

#### Verificación

```verify
export TELEGRAM_BOT_TOKEN="7123456789:AAFxxxx..."   # ← reemplaza
export TELEGRAM_CHAT_ID="123456789"                 # ← reemplaza
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" \
  -d "text=ARGOS test desde $(hostname)" | jq .ok
```

Esperado:

```text
true
```

Y en tu Telegram aparece el mensaje `ARGOS test desde <hostname>`.

#### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `"chat not found"` | Nunca enviaste mensaje al bot desde tu cuenta | Abre `t.me/<usuario_bot>`, envía `/start`, vuelve a consultar `getUpdates` |
| `"Unauthorized"` | Token mal copiado | Re-pide el token con `/mybots` → tu bot → `API Token` |
| `false` sin error visible | `chat_id` equivocado | Revisa el JSON de `getUpdates`; el campo correcto es `message.chat.id`, no `from.id` |

### 1.2.2 Webhook de Discord (canal secundario)

#### Pasos manuales

1. Crea un servidor Discord nuevo y nómbralo `ARGOS Demo`.
2. Crea un canal de texto llamado `#argos-alerts`.
3. Pasa el cursor sobre el canal y click en el engranaje (Editar canal).
4. **Integrations → Webhooks → New Webhook**.
5. Nombre: `ARGOS Notifier`. Avatar opcional.
6. Click **Copy Webhook URL**. Formato: `https://discord.com/api/webhooks/<id>/<token>`. Esa URL es tu `DISCORD_WEBHOOK_URL`.

#### Verificación

```verify
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/.../..."
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$DISCORD_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content": "ARGOS webhook test"}'
```

Esperado:

```text
HTTP 204
```

(204 = No Content, éxito). El mensaje aparece en `#argos-alerts`.

#### Si algo falla

| HTTP | Causa | Fix |
|------|-------|-----|
| 401 | Token mal copiado o webhook revocado | Recrea el webhook |
| 404 | Webhook eliminado o canal borrado | Recrea el webhook en otro canal |

### 1.2.3 Twilio (escalación T2 por voz DTMF)

#### Pasos manuales

1. Crea cuenta en `https://www.twilio.com/try-twilio` (trial gratis, USD 15 de crédito).
2. Verifica tu celular como _verified caller_ (Twilio trial sólo llama a números verificados; OK para el demo).
3. **Console → Account → API keys & tokens**, copia:
   - **Account SID** → `TWILIO_ACCOUNT_SID`.
   - **Auth Token** → `TWILIO_AUTH_TOKEN`.
4. **Phone Numbers → Get a trial number** (USA, gratis). El número que te asignan es `TWILIO_FROM_NUMBER`, formato `+1XXXXXXXXXX`.

#### Verificación

```verify
export TWILIO_ACCOUNT_SID="ACxxxx"
export TWILIO_AUTH_TOKEN="xxxx"
curl -sX GET "https://api.twilio.com/2010-04-01/Accounts/${TWILIO_ACCOUNT_SID}.json" \
  -u "${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}" | jq .status
```

Esperado:

```text
"active"
```

#### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `"unauthorized"` | SID o token mal copiados | Revisa **API keys & tokens** y vuelve a copiar |
| El día del demo no entra la llamada al Perú | Restricción geográfica del trial | Plan B documentado en ADR-0007 v2: escalación T2 cae a Telegram + Discord con prefijo `[T2-ESCALATION]` |

### 1.2.4 OpenAI API key (LLM Triage Layer 4)

#### Pasos manuales

1. Entra a `https://platform.openai.com/api-keys`.
2. Click **Create new secret key**. Nombre: `ARGOS demo`.
3. Copia la key (empieza con `sk-proj-...`) → `OPENAI_API_KEY`.
4. Set un límite de billing de USD 5/mes en `https://platform.openai.com/account/billing/limits` para protegerte.

#### Verificación

```verify
export OPENAI_API_KEY="sk-proj-xxxx"
curl -s https://api.openai.com/v1/models \
  -H "Authorization: Bearer ${OPENAI_API_KEY}" | jq '.data[0].id'
```

Esperado:

```text
"gpt-4o-mini-2024-07-18"
```

(O cualquier ID de modelo; lo que **no** debe aparecer es `"invalid_api_key"` o `"insufficient_quota"`.)

---

## 1.3 Clonar el repo y preparar el entorno Python

### Contexto

Creas tu working tree, virtualenv aislado y dependencias. El virtualenv es **obligatorio**: instalar paquetes en el Python del sistema rompe otras cosas.

### Comandos

```bash
mkdir -p ~/code && cd ~/code
git clone git@github.com:EnzoOrdonez/argos.git
cd argos

git status

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -e ./argos_contracts
pip install -r soar/requirements.txt
```

### Salida esperada

```text
Cloning into 'argos'...
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
Successfully installed pip-24.x.x
Successfully installed argos_contracts-1.1.0 pydantic-2.x.x ...
Successfully installed fastapi-0.110.x uvicorn-0.27.x redis-5.0.x httpx-0.27.x ...
```

### Verificación

```verify
which python && python -c "import argos_contracts; print('argos_contracts', argos_contracts.__version__)"
pytest -q 2>&1 | tail -3
```

Esperado:

```text
/home/<usuario>/code/argos/.venv/bin/python
argos_contracts 1.1.0
69 passed, 1 warning in 0.27s
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: argos_contracts` después de `pip install -e` | Instalaste fuera del venv | `which python` debe terminar en `.venv/bin/python`. Si no, `source .venv/bin/activate` |
| `pytest: command not found` | Falta dep del SOAR | `pip install -r soar/requirements.txt` |
| `git clone` pide password HTTPS | No tienes SSH key configurada | `gh auth login` o `git clone https://github.com/EnzoOrdonez/argos.git` |

---

## 1.4 Crear tu `.env`

### Contexto

`.env` vive en la raíz del repo y se carga con `python-dotenv` o `export $(grep -v '^#' .env | xargs)`. Está en `.gitignore`, así que tus credenciales no se filtran.

### Pasos manuales

1. Copia los valores que recolectaste en 1.2 (4 servicios).
2. Genera el archivo con el comando de abajo.
3. **No commitees `.env`**. Verifica con `git status` que no aparezca.

### Comandos

```bash
cat > .env << 'EOF'
# === Telegram ===
TELEGRAM_BOT_TOKEN=7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789

# === Discord ===
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/.../...

# === Twilio ===
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_FROM_NUMBER=+1XXXXXXXXXX
TWILIO_TO_NUMBER=+51XXXXXXXXX

# === OpenAI ===
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_BACKEND=openai_gpt4o_mini

# === Redis (lab Vagrant local) ===
REDIS_URL=redis://localhost:6379/0

# === PostgreSQL (audit log) ===
ARGOS_PG_URL=postgresql://argos:argos@localhost:5432/argos_audit
EOF
chmod 600 .env
```

(Reemplaza los placeholders con tus valores reales.)

### Verificación

```verify
ls -la .env
git check-ignore .env
test -s .env && echo "env NO vacío"
```

Esperado:

```text
-rw------- 1 usuario usuario 614 may 24 18:00 .env
.env
env NO vacío
```

(`git check-ignore .env` imprime el nombre si el archivo está en `.gitignore`; si no imprime nada → falta entrada en `.gitignore`).

---

## ✅ Checklist Fase 1

| # | Check | OK |
|---|-------|----|
| 1 | Python 3.11.x, Docker, redis-cli, jq presentes | ☐ |
| 2 | Bot Telegram envía mensaje real | ☐ |
| 3 | Webhook Discord devuelve HTTP 204 | ☐ |
| 4 | Twilio cuenta `"status": "active"` | ☐ |
| 5 | OpenAI key responde a `/v1/models` | ☐ |
| 6 | `pytest -q` → `69 passed` | ☐ |
| 7 | `.env` creado y `git check-ignore` lo detecta | ☐ |

**No avances a Fase 2 si algún check está rojo.**

---

# Fase 2 — Skeletons funcionales

> Goal: cada componente individual corre y pasa sus tests unitarios, **aún con stubs** en lugar de servicios reales. La conexión al lab real viene en Fase 3.

## 2.1 SOAR Decision Engine — Tier Router

### Contexto

El Tier Router es la pieza más crítica de todo ARGOS: recibe un evento normalizado de cualquier capa y decide qué Tier asignar (T0/T1/T2/T3). De ese tier salen las acciones automáticas y/o la solicitud de aprobación humana.

### Estructura

```text
soar/
├── requirements.txt
├── decision_engine/
│   ├── __init__.py
│   ├── tier_router.py     ← tú escribes
│   ├── policies.py        ← tú escribes (matrices de tier)
│   └── tests/
│       ├── test_tier_router.py
│       └── test_policies.py
```

### `policies.py`

```python
"""Matrices y constantes de política para el Tier Router.

Cualquier cambio aquí cambia el comportamiento del demo. Una sola fuente de verdad
evita branchear lógica en múltiples archivos.
"""

from argos_contracts.enums import Severity, Tier

# Técnicas que disparan T0 automático.
AUTO_T0_TECHNIQUES: frozenset[str] = frozenset({
    "T1486",  # Data Encrypted for Impact
    "T1490",  # Inhibit System Recovery
    "T1485",  # Data Destruction
    "T1561",  # Disk Wipe
})

# A partir de cuántas capas coincidentes consideramos "consenso" → boost a T0.
MIN_LAYERS_FOR_AUTO: int = 3

# Mapeo base severity → Tier antes de aplicar boosts.
SEVERITY_TO_BASE_TIER: dict[Severity, Tier] = {
    Severity.CRITICAL: Tier.T0,
    Severity.HIGH:     Tier.T1,
    Severity.MEDIUM:   Tier.T2,
    Severity.LOW:      Tier.T3,
}
```

### `tier_router.py`

```python
"""Tier Router — asigna T0/T1/T2/T3 a un evento normalizado."""

from __future__ import annotations
from typing import Literal

from argos_contracts.enums import Tier
from argos_contracts.incident import NormalizedEvent
from soar.decision_engine.policies import (
    AUTO_T0_TECHNIQUES, MIN_LAYERS_FOR_AUTO, SEVERITY_TO_BASE_TIER,
)

ConfidenceBand = Literal["high", "medium", "low"]


def confidence_band(score: float) -> ConfidenceBand:
    if score >= 0.85: return "high"
    if score >= 0.55: return "medium"
    return "low"


def route(event: NormalizedEvent) -> Tier:
    """Devuelve el Tier asignado a un evento. Pura: no I/O."""
    # 1. Auto-T0 por técnica MITRE crítica
    if event.mitre_technique in AUTO_T0_TECHNIQUES:
        return Tier.T0

    # 2. Tier base por severity
    base = SEVERITY_TO_BASE_TIER[event.severity]

    # 3. Boost por número de capas
    if event.num_layers_fired >= MIN_LAYERS_FOR_AUTO:
        if base in (Tier.T1, Tier.T2):
            return Tier.T0

    # 4. Down-tier si confianza baja (single layer + low confidence)
    band = confidence_band(event.confidence_score)
    if event.num_layers_fired == 1 and band == "low":
        return Tier.T3

    return base
```

### Tests

```python
# soar/decision_engine/tests/test_tier_router.py
import pytest

from argos_contracts.enums import Severity, Tier
from argos_contracts.incident import NormalizedEvent
from soar.decision_engine.tier_router import route, confidence_band


def make_event(**overrides) -> NormalizedEvent:
    base = dict(
        event_id="evt-test-001", severity=Severity.MEDIUM,
        mitre_technique="T1083", num_layers_fired=1,
        confidence_score=0.7, host="WIN-VICTIM-01", layer_origin="sigma",
    )
    base.update(overrides)
    return NormalizedEvent(**base)


@pytest.mark.parametrize("score, expected", [
    (0.95, "high"), (0.85, "high"),
    (0.84, "medium"), (0.55, "medium"),
    (0.54, "low"), (0.10, "low"),
])
def test_confidence_band(score, expected):
    assert confidence_band(score) == expected


def test_auto_t0_for_ransomware_technique():
    assert route(make_event(mitre_technique="T1486", severity=Severity.LOW)) == Tier.T0


def test_critical_maps_to_t0():
    assert route(make_event(severity=Severity.CRITICAL)) == Tier.T0


def test_three_layers_boost_t2_to_t0():
    assert route(make_event(num_layers_fired=3)) == Tier.T0


def test_single_layer_low_confidence_drops_to_t3():
    assert route(make_event(confidence_score=0.3)) == Tier.T3


def test_medium_two_layers_stays_t2():
    assert route(make_event(num_layers_fired=2, confidence_score=0.7)) == Tier.T2
```

### Comandos

```bash
pytest soar/decision_engine/tests/test_tier_router.py -v
```

### Salida esperada

```text
soar/decision_engine/tests/test_tier_router.py::test_confidence_band[0.95-high] PASSED
soar/decision_engine/tests/test_tier_router.py::test_confidence_band[0.85-high] PASSED
soar/decision_engine/tests/test_tier_router.py::test_confidence_band[0.84-medium] PASSED
soar/decision_engine/tests/test_tier_router.py::test_confidence_band[0.55-medium] PASSED
soar/decision_engine/tests/test_tier_router.py::test_confidence_band[0.54-low] PASSED
soar/decision_engine/tests/test_tier_router.py::test_confidence_band[0.1-low] PASSED
soar/decision_engine/tests/test_tier_router.py::test_auto_t0_for_ransomware_technique PASSED
soar/decision_engine/tests/test_tier_router.py::test_critical_maps_to_t0 PASSED
soar/decision_engine/tests/test_tier_router.py::test_three_layers_boost_t2_to_t0 PASSED
soar/decision_engine/tests/test_tier_router.py::test_single_layer_low_confidence_drops_to_t3 PASSED
soar/decision_engine/tests/test_tier_router.py::test_medium_two_layers_stays_t2 PASSED
======================= 11 passed in 0.08s =======================
```

### Verificación

```verify
python -c "from soar.decision_engine.tier_router import route; print('import OK')"
pytest --cov=soar.decision_engine.tier_router soar/decision_engine/tests/ 2>&1 | grep "tier_router.py"
```

Esperado:

```text
import OK
soar/decision_engine/tier_router.py     16      0   100%
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `ImportError: cannot import name 'Tier'` | `argos_contracts` desactualizado | `pip install -e ./argos_contracts --force-reinstall` |
| Tests `test_three_layers_boost_t2_to_t0` falla | Lógica de boost mal aplicada | Verifica que el `if base in (Tier.T1, Tier.T2)` use `in`, no `==` |
| Coverage < 100 % | Falta caso edge | Agrega test para `severity=HIGH + num_layers=1 + confidence=0.4` (espera T1, no T3) |

---

## 2.2 Notification Service — Estructura base

### Contexto

Adapter pattern: una interfaz `NotificationChannel` con N implementaciones (Telegram, Discord, Twilio, Email). El `NotificationService` recibe un `Incident` y despacha a los canales correspondientes según política. Cada canal nunca tira excepción hacia afuera; devuelve un `DispatchResult` que el servicio puede degradar.

### `base.py`

```python
"""Interfaz común a todos los canales de notificación."""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from argos_contracts.enums import NotificationChannelType
from argos_contracts.incident import Incident


@dataclass(frozen=True)
class DispatchResult:
    channel: NotificationChannelType
    success: bool
    latency_ms: int
    error: Optional[str] = None


class NotificationChannel(ABC):
    channel_type: NotificationChannelType   # subclase setea como class var

    @abstractmethod
    def dispatch(self, incident: Incident) -> DispatchResult:
        """Envía notificación. Nunca tira excepción al caller."""
        ...
```

### `service.py`

```python
"""Orquesta despacho a múltiples canales según el Tier del incidente."""

from __future__ import annotations
import logging, time
from typing import Iterable

from argos_contracts.enums import Tier, NotificationChannelType
from argos_contracts.incident import Incident
from soar.notifications.base import NotificationChannel, DispatchResult

logger = logging.getLogger(__name__)


TIER_CHANNELS: dict[Tier, list[NotificationChannelType]] = {
    Tier.T0: [NotificationChannelType.TELEGRAM, NotificationChannelType.DISCORD],
    Tier.T1: [NotificationChannelType.TELEGRAM, NotificationChannelType.DISCORD],
    Tier.T2: [NotificationChannelType.TELEGRAM, NotificationChannelType.DISCORD],
    Tier.T3: [],
}


class NotificationService:
    def __init__(self, channels: Iterable[NotificationChannel]):
        self._channels = {c.channel_type: c for c in channels}

    def dispatch_for_tier(self, incident: Incident) -> list[DispatchResult]:
        wanted = TIER_CHANNELS.get(incident.tier, [])
        results: list[DispatchResult] = []
        for channel_type in wanted:
            channel = self._channels.get(channel_type)
            if channel is None:
                results.append(DispatchResult(
                    channel=channel_type, success=False,
                    latency_ms=0, error="channel not configured",
                ))
                continue
            t0 = time.monotonic()
            try:
                results.append(channel.dispatch(incident))
            except Exception as exc:  # noqa: BLE001
                logger.exception("channel %s raised", channel_type)
                results.append(DispatchResult(
                    channel=channel_type, success=False,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    error=f"unexpected: {type(exc).__name__}: {exc}",
                ))
        return results

    def escalate_to_voice(self, incident: Incident) -> DispatchResult:
        voice = self._channels.get(NotificationChannelType.TWILIO_VOICE)
        if voice is None:
            return DispatchResult(
                channel=NotificationChannelType.TWILIO_VOICE,
                success=False, latency_ms=0, error="twilio not configured",
            )
        return voice.dispatch(incident)
```

### Verificación

```verify
python -c "from soar.notifications.service import NotificationService; print('service import OK')"
pytest soar/notifications/tests/test_service.py -q
```

Esperado:

```text
service import OK
5 passed in 0.04s
```

---

## 2.3 Notification Channel — Telegram

### Contexto

Mensajes con formato MarkdownV2 (Telegram-flavored). Botones inline `[Approve][Reject]` cuando `incident.requires_approval == True`.

### `channels/telegram.py`

```python
"""Telegram bot — canal primario para todos los tiers != T3."""

from __future__ import annotations
import logging, os, time
from typing import Optional
import httpx

from argos_contracts.enums import NotificationChannelType, Tier
from argos_contracts.incident import Incident
from soar.notifications.base import DispatchResult, NotificationChannel

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"


def _escape_md(text: str) -> str:
    for ch in r"_*[]()~`>#+-=|{}.!\\":
        text = text.replace(ch, f"\\{ch}")
    return text


def _format(incident: Incident) -> str:
    tier_emoji = {Tier.T0: "🔴", Tier.T1: "🟠", Tier.T2: "🟡", Tier.T3: "🔵"}
    return (
        f"{tier_emoji[incident.tier]} *ARGOS {incident.tier.value}* — "
        f"`{_escape_md(incident.host.hostname)}`\n"
        f"*Técnica:* `{_escape_md(incident.mitre_technique)}`\n"
        f"*Capas firing:* `{incident.num_layers_fired}`\n"
        f"*Confianza:* `{incident.confidence_score:.2f}`\n"
        f"*ID:* `{_escape_md(incident.incident_id)}`"
    )


def _inline_keyboard(incident_id: str) -> dict:
    return {"inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"approve:{incident_id}"},
        {"text": "❌ Reject",  "callback_data": f"reject:{incident_id}"},
    ]]}


class TelegramChannel(NotificationChannel):
    channel_type = NotificationChannelType.TELEGRAM

    def __init__(self, bot_token: Optional[str] = None,
                 chat_id: Optional[str] = None,
                 client: Optional[httpx.Client] = None,
                 timeout: float = 5.0):
        self._token   = bot_token or os.environ["TELEGRAM_BOT_TOKEN"]
        self._chat_id = chat_id   or os.environ["TELEGRAM_CHAT_ID"]
        self._client  = client or httpx.Client(timeout=timeout)

    def dispatch(self, incident: Incident) -> DispatchResult:
        t0 = time.monotonic()
        body = {
            "chat_id": self._chat_id,
            "text": _format(incident),
            "parse_mode": "MarkdownV2",
        }
        if incident.requires_approval:
            body["reply_markup"] = _inline_keyboard(incident.incident_id)
        try:
            r = self._client.post(_API.format(token=self._token), json=body)
            r.raise_for_status()
            payload = r.json()
            if not payload.get("ok"):
                return DispatchResult(
                    channel=self.channel_type, success=False,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    error=str(payload.get("description")),
                )
            return DispatchResult(
                channel=self.channel_type, success=True,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
        except httpx.HTTPError as exc:
            return DispatchResult(
                channel=self.channel_type, success=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=f"http: {exc}",
            )
```

### Smoke test manual

```bash
export $(grep -v '^#' .env | xargs)

python - << 'PY'
from datetime import datetime, timezone
from argos_contracts.incident import Incident, HostInfo
from argos_contracts.enums import Tier, Severity, IncidentState
from soar.notifications.channels.telegram import TelegramChannel

incident = Incident(
    incident_id="inc-smoke-001", tier=Tier.T0, state=IncidentState.NEW,
    severity=Severity.CRITICAL,
    host=HostInfo(hostname="WIN-VICTIM-01", ip="192.168.56.20", os="Windows 10"),
    mitre_technique="T1486", num_layers_fired=3, confidence_score=0.94,
    created_at=datetime.now(timezone.utc), requires_approval=False,
    approvers=[], final_decision=None, consolidation_window=None,
)
print(TelegramChannel().dispatch(incident))
PY
```

### Salida esperada

```text
DispatchResult(channel=<NotificationChannelType.TELEGRAM: 'telegram'>, success=True, latency_ms=287, error=None)
```

Y en Telegram aparece:

```text
🔴 ARGOS T0 — WIN-VICTIM-01
Técnica: T1486
Capas firing: 3
Confianza: 0.94
ID: inc-smoke-001
```

### Verificación

```verify
python -c "from soar.notifications.channels.telegram import TelegramChannel; print('telegram OK')"
```

Esperado:

```text
telegram OK
```

---

## 2.4 Notification Channel — Discord

### Contexto

Webhook simple. Mensaje con embed coloreado por tier (T0 rojo, T1 naranja, T2 amarillo, T3 azul). No requiere bot ni token de usuario.

### `channels/discord.py`

```python
"""Discord webhook channel."""

from __future__ import annotations
import logging, os, time
from typing import Optional
import httpx

from argos_contracts.enums import NotificationChannelType, Tier
from argos_contracts.incident import Incident
from soar.notifications.base import DispatchResult, NotificationChannel

logger = logging.getLogger(__name__)

_COLOR = {Tier.T0: 0xE53935, Tier.T1: 0xFB8C00, Tier.T2: 0xFDD835, Tier.T3: 0x1E88E5}


def _embed(incident: Incident) -> dict:
    return {
        "title": f"ARGOS {incident.tier.value} — {incident.host.hostname}",
        "color": _COLOR[incident.tier],
        "fields": [
            {"name": "Técnica MITRE", "value": incident.mitre_technique, "inline": True},
            {"name": "Capas firing",  "value": str(incident.num_layers_fired), "inline": True},
            {"name": "Confianza",     "value": f"{incident.confidence_score:.2f}", "inline": True},
            {"name": "Incident ID",   "value": f"`{incident.incident_id}`"},
        ],
        "footer": {"text": "ARGOS · respond on Telegram for approval"},
    }


class DiscordChannel(NotificationChannel):
    channel_type = NotificationChannelType.DISCORD

    def __init__(self, webhook_url: Optional[str] = None,
                 client: Optional[httpx.Client] = None,
                 timeout: float = 5.0):
        self._url    = webhook_url or os.environ["DISCORD_WEBHOOK_URL"]
        self._client = client or httpx.Client(timeout=timeout)

    def dispatch(self, incident: Incident) -> DispatchResult:
        t0 = time.monotonic()
        body = {"embeds": [_embed(incident)]}
        try:
            r = self._client.post(self._url, json=body)
            if r.status_code in (200, 204):
                return DispatchResult(
                    channel=self.channel_type, success=True,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                )
            return DispatchResult(
                channel=self.channel_type, success=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=f"http {r.status_code}: {r.text[:200]}",
            )
        except httpx.HTTPError as exc:
            return DispatchResult(
                channel=self.channel_type, success=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=f"http: {exc}",
            )
```

### Verificación

```verify
python - << 'PY'
import os
from datetime import datetime, timezone
from argos_contracts.incident import Incident, HostInfo
from argos_contracts.enums import Tier, Severity, IncidentState
from soar.notifications.channels.discord import DiscordChannel

i = Incident(
    incident_id="inc-smoke-002", tier=Tier.T2, state=IncidentState.NEW,
    severity=Severity.MEDIUM,
    host=HostInfo(hostname="LIN-VICTIM-01", ip="192.168.56.21", os="Ubuntu 22.04"),
    mitre_technique="T1083", num_layers_fired=2, confidence_score=0.71,
    created_at=datetime.now(timezone.utc), requires_approval=True,
    approvers=[], final_decision=None, consolidation_window=None,
)
r = DiscordChannel().dispatch(i)
print(r.success, r.latency_ms, "ms")
PY
```

Esperado:

```text
True 312 ms
```

Y un embed amarillo en `#argos-alerts`.

---

## 2.5 Notification Channel — Twilio Voice (escalación T2)

### Contexto

Sólo se dispara para T2 a los 60 segundos sin respuesta. La llamada lee TwiML que enuncia el incidente y captura DTMF (`1=approve`, `2=reject`). Es el último recurso antes de que el _conservative-wins policy_ decida solo.

### `channels/twilio_voice.py`

```python
"""Twilio voice — escalación DTMF."""

from __future__ import annotations
import logging, os, time
from typing import Optional
from urllib.parse import urlencode
import httpx

from argos_contracts.enums import NotificationChannelType
from argos_contracts.incident import Incident
from soar.notifications.base import DispatchResult, NotificationChannel

logger = logging.getLogger(__name__)


def _twiml_url(incident_id: str, base: str) -> str:
    return f"{base}/voice/twiml?{urlencode({'incident': incident_id})}"


class TwilioVoiceChannel(NotificationChannel):
    channel_type = NotificationChannelType.TWILIO_VOICE

    def __init__(self,
                 account_sid: Optional[str] = None,
                 auth_token: Optional[str] = None,
                 from_number: Optional[str] = None,
                 to_number: Optional[str] = None,
                 public_base_url: Optional[str] = None,
                 client: Optional[httpx.Client] = None,
                 timeout: float = 8.0):
        self._sid  = account_sid or os.environ["TWILIO_ACCOUNT_SID"]
        self._tok  = auth_token  or os.environ["TWILIO_AUTH_TOKEN"]
        self._from = from_number or os.environ["TWILIO_FROM_NUMBER"]
        self._to   = to_number   or os.environ["TWILIO_TO_NUMBER"]
        self._base = public_base_url or os.environ.get("ARGOS_PUBLIC_URL", "")
        self._client = client or httpx.Client(timeout=timeout, auth=(self._sid, self._tok))

    def dispatch(self, incident: Incident) -> DispatchResult:
        t0 = time.monotonic()
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._sid}/Calls.json"
        try:
            r = self._client.post(url, data={
                "From": self._from, "To": self._to,
                "Url": _twiml_url(incident.incident_id, self._base),
                "Method": "POST", "Timeout": "20",
            })
            if r.status_code in (200, 201):
                return DispatchResult(
                    channel=self.channel_type, success=True,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                )
            return DispatchResult(
                channel=self.channel_type, success=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=f"http {r.status_code}: {r.text[:300]}",
            )
        except httpx.HTTPError as exc:
            return DispatchResult(
                channel=self.channel_type, success=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=f"http: {exc}",
            )
```

### Pasos manuales para que Twilio pueda alcanzar tu Approval API local

Twilio necesita una URL pública para hacer callback al TwiML. Usa `ngrok`:

1. Instala ngrok: `https://ngrok.com/download`.
2. Regístrate gratis en ngrok.com y copia tu authtoken.
3. Configura: `ngrok config add-authtoken <tu_token>`.
4. En una terminal, mantén corriendo: `ngrok http 8001` (el puerto donde corre tu Approval API).
5. ngrok te muestra una URL como `https://abcd-1234.ngrok-free.app`. Exporta:

```bash
export ARGOS_PUBLIC_URL=https://abcd-1234.ngrok-free.app
```

### Verificación (gasta ~USD 0.013 de tu trial credit)

```verify
export ARGOS_PUBLIC_URL=https://abcd-1234.ngrok-free.app

python - << 'PY'
from datetime import datetime, timezone
from argos_contracts.incident import Incident, HostInfo
from argos_contracts.enums import Tier, Severity, IncidentState
from soar.notifications.channels.twilio_voice import TwilioVoiceChannel

i = Incident(
    incident_id="inc-smoke-003", tier=Tier.T2, state=IncidentState.NEW,
    severity=Severity.MEDIUM,
    host=HostInfo(hostname="WIN-VICTIM-01", ip="192.168.56.20", os="Windows 10"),
    mitre_technique="T1083", num_layers_fired=2, confidence_score=0.72,
    created_at=datetime.now(timezone.utc), requires_approval=True,
    approvers=[], final_decision=None, consolidation_window=None,
)
r = TwilioVoiceChannel().dispatch(i)
print(r.success, r.error or "no error")
PY
```

Esperado:

```text
True no error
```

Y tu celular suena con una llamada de tu número Twilio.

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| Error `21219` | Número `TWILIO_TO_NUMBER` no verificado | Verifícalo en `https://console.twilio.com/us1/develop/phone-numbers/manage/verified` |
| Error `21401` | Número `TO` mal formateado | Debe empezar con `+` y código país: `+51XXXXXXXXX` |
| Llamada cae al instante | TwiML URL inalcanzable (ngrok caído) | Vuelve a levantar `ngrok http 8001` y actualiza `ARGOS_PUBLIC_URL` |

---

## 2.6 Approval API — endpoints FastAPI

### Contexto

Mini API HTTP que recibe respuestas de aprobación de tres orígenes: callback de botón Telegram, reacción Discord (opcional), y DTMF Twilio. Cada respuesta muta el `Incident` en Redis y dispara la evaluación de la regla _two-person_.

### `main.py`

```python
"""Approval API — recibe respuestas y muta Incident en Redis."""

from __future__ import annotations
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as redis
from fastapi import FastAPI, Form, HTTPException, Response

from soar.approval_api.handlers import (
    record_approval_response, build_final_decision_if_ready,
)
from soar.approval_api.twiml import build_voice_gather_xml, dtmf_to_response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.redis = redis.from_url(
        os.environ["REDIS_URL"], decode_responses=True
    )
    try:
        yield
    finally:
        await app.state.redis.close()


app = FastAPI(title="ARGOS Approval API", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    pong = await app.state.redis.ping()
    return {"ok": True, "redis": pong}


@app.post("/telegram/callback")
async def telegram_callback(update: dict) -> dict:
    cq = update.get("callback_query")
    if cq is None:
        raise HTTPException(400, "missing callback_query")
    action, _, incident_id = (cq.get("data") or "").partition(":")
    if action not in ("approve", "reject") or not incident_id:
        raise HTTPException(400, "bad callback_data")
    user = cq.get("from", {})
    approver_id = f"telegram:{user.get('id')}"
    await record_approval_response(
        redis_client=app.state.redis,
        incident_id=incident_id, approver_id=approver_id,
        decision=action, channel="telegram",
    )
    await build_final_decision_if_ready(app.state.redis, incident_id)
    return {"ok": True}


@app.post("/voice/twiml", response_class=Response)
async def voice_twiml(incident: str) -> Response:
    return Response(content=build_voice_gather_xml(incident_id=incident),
                    media_type="application/xml")


@app.post("/voice/dtmf", response_class=Response)
async def voice_dtmf(Digits: str = Form(...), incident: str = Form(...)) -> Response:
    decision = dtmf_to_response(Digits)
    if decision is None:
        return Response(
            content="<Response><Say>Invalid input. Bye.</Say><Hangup/></Response>",
            media_type="application/xml",
        )
    await record_approval_response(
        redis_client=app.state.redis,
        incident_id=incident, approver_id=f"twilio:{incident}",
        decision=decision, channel="twilio_voice",
    )
    await build_final_decision_if_ready(app.state.redis, incident)
    return Response(
        content=f"<Response><Say>{decision} recorded. Goodbye.</Say><Hangup/></Response>",
        media_type="application/xml",
    )
```

### `twiml.py`

```python
"""Helpers para generar TwiML y traducir DTMF."""

from typing import Optional, Literal

Decision = Literal["approve", "reject"]


def build_voice_gather_xml(incident_id: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather numDigits="1" action="/voice/dtmf" method="POST" timeout="20">
    <Say voice="alice">
      ARGOS critical incident. Incident {incident_id}.
      Press one to approve, two to reject.
    </Say>
    <Pause length="2"/>
  </Gather>
  <Say>No input received. Goodbye.</Say>
  <Hangup/>
</Response>"""


_DTMF: dict[str, Decision] = {"1": "approve", "2": "reject"}


def dtmf_to_response(digits: str) -> Optional[Decision]:
    return _DTMF.get(digits.strip()) if digits else None
```

### Comandos

```bash
uvicorn soar.approval_api.main:app --host 0.0.0.0 --port 8001 --reload
```

### Salida esperada (terminal con uvicorn)

```text
INFO:     Will watch for changes in these directories: ['/home/usuario/code/argos']
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using StatReload
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### Verificación

```verify
curl -s http://localhost:8001/healthz | jq
```

Esperado:

```text
{
  "ok": true,
  "redis": true
}
```

Y para el endpoint TwiML:

```verify
curl -s -X POST 'http://localhost:8001/voice/twiml?incident=inc-test' | head -3
```

Esperado:

```text
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather numDigits="1" action="/voice/dtmf" method="POST" timeout="20">
```

---

## 2.7 Two-person rule + conservative-wins policy

### Contexto

Núcleo del HITL. Cuando un T2 dispara, se notifican N aprobadores (≥ 2). El sistema espera hasta 2 respuestas concordantes o cierra la ventana en 60 s. La política `conservative-wins` dice: ante conflicto, **prevalece reject**.

### `handlers.py` (lógica completa)

```python
"""Lógica HITL: registrar respuestas, evaluar quorum, resolver conflictos."""

from __future__ import annotations
import logging, time
from typing import Literal

import redis.asyncio as redis

from argos_contracts.enums import ApproverStatus, IncidentState
from argos_contracts.incident import ApproverState, FinalDecision, Incident

logger = logging.getLogger(__name__)

QUORUM_NEEDED = 2
DEFAULT_WINDOW_SECONDS = 60


async def _load_incident(r: redis.Redis, incident_id: str) -> Incident:
    raw = await r.get(f"incident:{incident_id}")
    if raw is None:
        raise KeyError(f"incident {incident_id} not in Redis")
    return Incident.model_validate_json(raw)


async def _save_incident(r: redis.Redis, incident: Incident) -> None:
    await r.set(f"incident:{incident.incident_id}", incident.model_dump_json())


async def record_approval_response(
    *, redis_client: redis.Redis,
    incident_id: str, approver_id: str,
    decision: Literal["approve", "reject"], channel: str,
) -> None:
    incident = await _load_incident(redis_client, incident_id)
    if incident.final_decision is not None:
        logger.info("incident %s already decided; ignoring late %s from %s",
                    incident_id, decision, approver_id)
        return

    status = (ApproverStatus.APPROVED if decision == "approve"
              else ApproverStatus.REJECTED)
    now = time.time()

    for ap in incident.approvers:
        if ap.approver_id == approver_id:
            ap.status = status
            ap.responded_at = now
            ap.channel = channel
            break
    else:
        incident.approvers.append(ApproverState(
            approver_id=approver_id, status=status, channel=channel,
            notified_at=now, responded_at=now,
        ))
    await _save_incident(redis_client, incident)


def _evaluate(incident: Incident) -> FinalDecision | None:
    """Pure: dada la lista de approvers, ¿hay decisión?"""
    approved = sum(a.status == ApproverStatus.APPROVED for a in incident.approvers)
    rejected = sum(a.status == ApproverStatus.REJECTED for a in incident.approvers)
    timeout  = sum(a.status == ApproverStatus.TIMEOUT  for a in incident.approvers)

    if approved >= QUORUM_NEEDED and rejected == 0:
        return FinalDecision(
            outcome="execute", policy_applied="two_person_approve",
            execution_status="pending",
            approved_count=approved, rejected_count=rejected, timeout_count=timeout,
        )
    if rejected >= QUORUM_NEEDED:
        return FinalDecision(
            outcome="block", policy_applied="two_person_reject",
            execution_status="not_required",
            approved_count=approved, rejected_count=rejected, timeout_count=timeout,
        )
    if approved >= 1 and rejected >= 1:
        return FinalDecision(
            outcome="block", policy_applied="conservative_wins",
            execution_status="not_required",
            approved_count=approved, rejected_count=rejected, timeout_count=timeout,
        )
    return None


async def build_final_decision_if_ready(
    r: redis.Redis, incident_id: str
) -> Incident:
    incident = await _load_incident(r, incident_id)
    if incident.final_decision is not None:
        return incident
    decision = _evaluate(incident)
    if decision is None:
        return incident
    incident.final_decision = decision
    incident.state = (
        IncidentState.RESOLVED if decision.outcome == "block"
        else IncidentState.PENDING_EXECUTION
    )
    await _save_incident(r, incident)
    return incident
```

### Verificación

```verify
pytest soar/approval_api/tests/test_handlers.py -v
```

Esperado:

```text
test_handlers.py::test_evaluate_decision_matrix[inputs0-execute-two_person_approve] PASSED
test_handlers.py::test_evaluate_decision_matrix[inputs1-block-two_person_reject]    PASSED
test_handlers.py::test_evaluate_decision_matrix[inputs2-block-conservative_wins]    PASSED
test_handlers.py::test_evaluate_decision_matrix[inputs3-block-conservative_wins]    PASSED
test_handlers.py::test_single_response_no_decision                                  PASSED
======================= 5 passed in 0.04s =======================
```

---

## 2.8 Consolidation window de 60 segundos

### Contexto

Background task que dado un `incident_id`, espera 60 s. Si no hay quorum, marca pendientes como TIMEOUT y evalúa una vez más. Si tampoco hay decisión (nadie respondió), crea `block / no_quorum_timeout`.

### `consolidation.py`

```python
"""Ventana de consolidación T2 — 60 segundos."""

from __future__ import annotations
import asyncio, logging, time
import redis.asyncio as redis

from argos_contracts.enums import ApproverStatus, IncidentState
from argos_contracts.incident import FinalDecision
from soar.approval_api.handlers import _evaluate, _load_incident, _save_incident

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60


async def consolidation_task(r: redis.Redis, incident_id: str) -> None:
    await asyncio.sleep(WINDOW_SECONDS)
    incident = await _load_incident(r, incident_id)
    if incident.final_decision is not None:
        return

    for ap in incident.approvers:
        if ap.status == ApproverStatus.PENDING:
            ap.status = ApproverStatus.TIMEOUT
            ap.responded_at = time.time()

    decision = _evaluate(incident)
    if decision is None:
        decision = FinalDecision(
            outcome="block", policy_applied="no_quorum_timeout",
            execution_status="not_required",
            approved_count=0, rejected_count=0,
            timeout_count=sum(1 for a in incident.approvers
                              if a.status == ApproverStatus.TIMEOUT),
        )
    incident.final_decision = decision
    incident.state = IncidentState.RESOLVED
    await _save_incident(r, incident)
```

### Verificación

```verify
pytest soar/approval_api/tests/test_consolidation.py -v
```

Esperado:

```text
test_consolidation.py::test_consolidation_no_response_blocks PASSED
test_consolidation.py::test_consolidation_partial_quorum_blocks PASSED
======================= 2 passed in 0.06s =======================
```

---

## ✅ Checklist Fase 2

| # | Check | OK |
|---|-------|----|
| 1 | `pytest soar/ -q` → ≥ 30 passed | ☐ |
| 2 | `uvicorn ... port 8001` arranca sin errores | ☐ |
| 3 | `/healthz` devuelve `{"ok": true, "redis": true}` | ☐ |
| 4 | Telegram, Discord smoke tests devuelven `success=True` | ☐ |
| 5 | Twilio dispara llamada real | ☐ |
| 6 | Tier router asigna T0 para `T1486` + `severity=LOW` | ☐ |
| 7 | Two-person resuelve conflict → `block / conservative_wins` | ☐ |
| 8 | Consolidation 60s cierra a `no_quorum_timeout` cuando nadie responde | ☐ |

---

# Fase 3 — Integración real

## 3.1 Consumer del stream `events:normalized`

### Contexto

Hasta ahora procesabas `NormalizedEvent` fabricados a mano en tests. Ahora vas a leerlos de un Redis Stream alimentado por las 4 capas (P3 inyecta Sigma/Canary, P2 inyecta ML/LLM). El contrato está en `docs/contracts/CONTRACTS_SPECIFICATION.md`.

### `consumer.py`

```python
"""Consumer del stream events:normalized → emite Incident a Redis."""

from __future__ import annotations
import asyncio, logging, os, uuid
from datetime import datetime, timezone

import redis.asyncio as redis

from argos_contracts.enums import IncidentState, Tier
from argos_contracts.incident import HostInfo, Incident, NormalizedEvent
from soar.decision_engine.tier_router import route
from soar.notifications.service import NotificationService

logger = logging.getLogger(__name__)

STREAM   = "events:normalized"
GROUP    = "soar-router"
CONSUMER = os.environ.get("SOAR_CONSUMER_NAME", "soar-1")
INCIDENT_TTL_SECONDS = 6 * 3600


async def ensure_group(r: redis.Redis) -> None:
    try:
        await r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


async def _process_event(r: redis.Redis, notif: NotificationService, raw: dict) -> None:
    event = NormalizedEvent.model_validate_json(raw["data"])
    tier = route(event)
    incident = Incident(
        incident_id=f"inc-{uuid.uuid4().hex[:12]}",
        tier=tier, state=IncidentState.NEW,
        severity=event.severity,
        host=HostInfo(hostname=event.host, ip="", os=""),
        mitre_technique=event.mitre_technique,
        num_layers_fired=event.num_layers_fired,
        confidence_score=event.confidence_score,
        created_at=datetime.now(timezone.utc),
        requires_approval=(tier == Tier.T2),
        approvers=[], final_decision=None, consolidation_window=None,
    )
    await r.setex(
        f"incident:{incident.incident_id}",
        INCIDENT_TTL_SECONDS, incident.model_dump_json(),
    )
    results = notif.dispatch_for_tier(incident)
    logger.info("incident %s → tier=%s notif=%s",
                incident.incident_id, tier.value,
                [(r.channel.value, r.success) for r in results])


async def run_consumer(notif: NotificationService) -> None:
    r = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await ensure_group(r)
    logger.info("consumer %s reading group %s on stream %s",
                CONSUMER, GROUP, STREAM)
    while True:
        resp = await r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=10, block=5000)
        for _stream, entries in resp or []:
            for entry_id, fields in entries:
                try:
                    await _process_event(r, notif, fields)
                    await r.xack(STREAM, GROUP, entry_id)
                except Exception:  # noqa: BLE001
                    logger.exception("failed to process %s; entry retained", entry_id)
```

### Comandos (arrancar consumer)

```bash
python -m soar.decision_engine.consumer
```

### Salida esperada

```text
INFO:soar.decision_engine.consumer:consumer soar-1 reading group soar-router on stream events:normalized
```

### Comandos (inyectar evento de prueba en otra terminal)

```bash
redis-cli XADD events:normalized '*' data \
  '{"event_id":"evt-001","severity":"CRITICAL","mitre_technique":"T1486","num_layers_fired":3,"confidence_score":0.94,"host":"WIN-VICTIM-01","layer_origin":"sigma"}'
```

### Salida esperada (terminal del consumer)

```text
INFO:soar.decision_engine.consumer:incident inc-abc123def456 → tier=T0 notif=[('telegram', True), ('discord', True)]
```

### Verificación

```verify
redis-cli KEYS 'incident:*'
redis-cli GET $(redis-cli KEYS 'incident:*' | tail -1) | jq '.tier, .host.hostname, .mitre_technique'
```

Esperado:

```text
"incident:inc-abc123def456"
"T0"
"WIN-VICTIM-01"
"T1486"
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `BUSYGROUP Consumer Group name already exists` en logs | El grupo ya existía. No es error real. | `redis-cli XGROUP DESTROY events:normalized soar-router && redis-cli XGROUP CREATE events:normalized soar-router 0 MKSTREAM` |
| `Connection refused 6379` | Redis no corre | `docker run -d -p 6379:6379 --name argos-redis redis:7` |
| Evento no genera incident | El consumer no consume del grupo | Verifica `redis-cli XINFO GROUPS events:normalized` |

---

## 3.2 Audit log en PostgreSQL

### Contexto

Cada `Incident` y cada respuesta de aprobador se persiste en PostgreSQL (P4 levantó la DB con `pgaudit` activo). Razón: trazabilidad forense post-mortem.

### Schema (acordado con P4, ya en `lab/postgres/init.sql`)

```sql
CREATE TABLE IF NOT EXISTS audit_incidents (
    incident_id   text PRIMARY KEY,
    tier          text NOT NULL,
    severity      text NOT NULL,
    host          text NOT NULL,
    technique     text NOT NULL,
    created_at    timestamptz NOT NULL,
    final_outcome text,
    final_policy  text,
    final_at      timestamptz,
    payload       jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_responses (
    id            bigserial PRIMARY KEY,
    incident_id   text REFERENCES audit_incidents(incident_id),
    approver_id   text NOT NULL,
    channel       text NOT NULL,
    decision      text NOT NULL,
    received_at   timestamptz NOT NULL
);
```

### Verificación (después de correr un UC end-to-end)

```verify
psql postgresql://argos:argos@localhost:5432/argos_audit -c \
  "SELECT incident_id, tier, technique, final_outcome FROM audit_incidents ORDER BY created_at DESC LIMIT 3;"
```

Esperado:

```text
   incident_id    | tier | technique | final_outcome
------------------+------+-----------+---------------
 inc-abc123def456 | T0   | T1486     | execute
 inc-987654321cba | T2   | T1083     | block
(2 rows)
```

---

## 3.3 Hook al LLM Triage (Layer 4 de P2)

### Contexto

Cuando el `tier_router` asigna T2, invocas el LLM Triage de P2 que devuelve `LLMVerdict` con label/confidence/reasoning. Enriquece el `Incident` antes de notificar.

### Patrón de integración

```python
# soar/decision_engine/consumer.py (modificación dentro de _process_event)

if tier == Tier.T2:
    from ml.llm_triage import classify as llm_classify
    try:
        verdict = await llm_classify(event)
        incident.llm_verdict = verdict
    except Exception:  # noqa: BLE001
        logger.exception("llm classify failed; continuing without enrichment")
        incident.llm_verdict = None
```

> **Importante**: si el LLM falla (rate-limit, timeout, OpenAI caído), el incidente sigue su curso sin enriquecimiento. **Nunca bloquees** el flujo HITL por el LLM.

### Verificación

```verify
redis-cli GET $(redis-cli KEYS 'incident:*' | tail -1) | jq '.llm_verdict'
```

Esperado (cuando el evento fue T2):

```text
{
  "label": "malicious",
  "confidence": 0.93,
  "reasoning": "...",
  "backend": "openai_gpt4o_mini",
  "latency_ms": 687
}
```

O `null` si el LLM falló (acceptable).

---

## 3.4 End-to-end UC-01 (ransomware T0)

### Contexto

Validación viva del flujo completo: ataque → Sigma + ML + Canary disparan → SOAR asigna T0 → notificaciones → Wazuh active-response aísla el host. Todo en menos de 15 s.

### Pasos manuales

Necesitas 3 terminales abiertas (idealmente con tmux/screen).

1. **Terminal 1** — consumer SOAR.
2. **Terminal 2** — Approval API (no se usa para T0 pero la dejas corriendo).
3. **Terminal 3** — vagrant ssh a la víctima donde corre el script de ataque.

### Comandos

```bash
# Terminal 1
python -m soar.decision_engine.consumer

# Terminal 2
uvicorn soar.approval_api.main:app --port 8001

# Terminal 3
vagrant ssh linux-victim
python /vagrant/attack-simulation/ransomware_simulator/lockbit_like.py \
       --variant uc01 --target linux-victim
```

### Salida esperada

En Terminal 3:

```text
[uc01] generated key: gAAAAAB...
[uc01] encrypted 200 files
[uc01] (simulated) vssadmin delete shadows /all /quiet
```

En Terminal 1:

```text
INFO:soar.decision_engine.consumer:incident inc-XYZ789ABC123 → tier=T0 notif=[('telegram', True), ('discord', True)]
```

En tu Telegram, dentro de 10 s:

```text
🔴 ARGOS T0 — linux-victim
Técnica: T1486
Capas firing: 3
Confianza: 0.94
ID: inc-XYZ789ABC123
```

### Verificación

```verify
# Latencia
psql postgresql://argos:argos@localhost:5432/argos_audit -c \
  "SELECT incident_id, EXTRACT(EPOCH FROM (final_at - created_at)) AS seconds_to_resolve \
   FROM audit_incidents WHERE technique='T1486' ORDER BY created_at DESC LIMIT 1;"
```

Esperado:

```text
   incident_id    | seconds_to_resolve
------------------+-------------------
 inc-XYZ789ABC123 |             8.42
```

Tiempo < 15 s = ✅.

---

## 3.5 End-to-end UC-04 (two-person rule)

### Contexto

UC-04 es el centerpiece del demo. Un T2 dispara, los 4 integrantes reciben Telegram con botones, se espera quorum de 2 approves o conflict.

### Comando (en Terminal 3, vagrant ssh)

```bash
python /vagrant/attack-simulation/ransomware_simulator/postgres_attack.py \
       --target linux-victim
```

### Timeline esperado

```text
t=0s    Ataque lanzado. Sigma + ML disparan.
t=2s    SOAR crea Incident T2 → notifica 4 integrantes.
t=10s   P1 toca [Approve].
t=18s   P2 toca [Approve] → quorum 2 → final_decision=execute → Wazuh aísla.
        Streamlit muestra banner verde: "2 approve · 0 reject · execute".
```

### Variante conflict

```text
t=10s   P1 toca [Approve]
t=18s   P2 toca [Reject]
        → conservative-wins → block / conservative_wins
        → Streamlit banner gris: "1 approve · 1 reject · block".
```

### Variante timeout

```text
t=10s   P1 toca [Approve]
t=55s   Twilio llama a P3 y P4.
t=60s   Window cierra → no quorum → block / no_quorum_timeout.
```

### Verificación

```verify
redis-cli GET $(redis-cli KEYS 'incident:*' | tail -1) | jq '.final_decision'
```

Esperado (caso aprobado):

```text
{
  "outcome": "execute",
  "policy_applied": "two_person_approve",
  "execution_status": "success",
  "approved_count": 2,
  "rejected_count": 0,
  "timeout_count": 2
}
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| Botones no aparecen en Telegram | `requires_approval=False` | Verifica que el incident T2 tiene `requires_approval=True` (Tier.T2 lo setea en el consumer) |
| Aprobar no actualiza Redis | Telegram callback no llega | El webhook de Telegram apunta a tu Approval API; usa `ngrok` y registra: `curl https://api.telegram.org/bot$TOKEN/setWebhook?url=https://abcd.ngrok.io/telegram/callback` |
| Streamlit no refresca | `streamlit-autorefresh` desactivado | F5 manual; los datos están en Redis |

---

## ✅ Checklist Fase 3

| # | Check | OK |
|---|-------|----|
| 1 | Consumer SOAR consume del stream real | ☐ |
| 2 | UC-01 corre end-to-end en < 15 s | ☐ |
| 3 | UC-04 con 2 approves → execute | ☐ |
| 4 | UC-04 conflict → block / conservative_wins | ☐ |
| 5 | UC-04 timeout → block / no_quorum_timeout | ☐ |
| 6 | `audit_incidents` se llena con cada UC | ☐ |
| 7 | LLM hook degrada graciosamente si OpenAI cae | ☐ |
| 8 | `pytest -q` global ≥ 80 passed | ☐ |

---

# Fase 4 — Rehearsal y polish

## 4.1 Rehearsal individual (silencioso)

### Contexto

Antes de invitar al equipo, tú haces el corrido completo solo. Mides latencias y registras fallos.

### Comandos (con cronómetro)

```bash
make demo-up

time {
  python attack-simulation/ransomware_simulator/lockbit_like.py --variant uc01 --target windows-victim
  sleep 20
  python attack-simulation/ransomware_simulator/canary_path.py --target linux-victim
  sleep 15
  python attack-simulation/ransomware_simulator/postgres_attack.py --target linux-victim
}
```

### Verificación — registrar métricas

```verify
psql postgresql://argos:argos@localhost:5432/argos_audit -c \
  "SELECT technique, tier, \
          EXTRACT(EPOCH FROM (final_at - created_at)) AS sec_to_resolve, \
          final_outcome, final_policy \
   FROM audit_incidents ORDER BY created_at DESC LIMIT 5;"
```

Esperado:

```text
 technique | tier | sec_to_resolve | final_outcome |     final_policy
-----------+------+----------------+---------------+----------------------
 T1486     | T0   |           7.12 | execute       | auto_t0
 T1083     | T0   |           5.84 | execute       | auto_t0
 T1190     | T2   |          22.45 | execute       | two_person_approve
(3 rows)
```

---

## 4.2 Rehearsal en grupo

### Pasos manuales

1. Crear evento Discord call: `"ARGOS Rehearsal Final"` para una hora acordada.
2. Cada integrante con su celular cargado, Telegram + Discord abiertos.
3. P4 confirma que su lab está arriba; tú confirmas lab espejo arriba.
4. Compartes pantalla con Streamlit Console (tab 2 Approval Console).
5. Sigues el script de 12-13 minutos del Manual de Equipo §2.2.

### Verificación

| Check | Esperado |
|-------|----------|
| Ningún integrante reporta no haber recibido Telegram | ✓ |
| Streamlit refresca ≤ 2 s tras cada acción | ✓ |
| Twilio entra a celular acordado | ✓ |
| Audit log final tiene los 3 escenarios UC-04 distinguibles | ✓ |
| Duración total ≤ 13 min | ✓ |

---

## 4.3 Edge cases y contingencias

### Tabla de fallos previstos

| Fallo | Probabilidad | Respuesta inmediata |
|-------|:------------:|---------------------|
| WiFi del salón bloquea `api.openai.com` | Alta | `export LLM_BACKEND=llama_local && make llm-restart` |
| Twilio trial sin saldo | Media | Verificar saldo T-24 h. Si < USD 3, top-up con USD 5 |
| Wazuh manager no arranca | Media | Switch a lab espejo: `export WAZUH_HOST=p1-espejo.local && make soar-restart` |
| Postgres lleno > 90 % | Baja | `make audit-vacuum` |
| Crash del consumer SOAR mid-demo | Media | `make soar-restart` (reinicia en < 5 s) |
| Streamlit no actualiza | Media | F5 manual |
| Llamada Twilio se va a buzón | Alta | Por diseño: `no_quorum_timeout` aplica |

### Plan de fallback nuclear

Si tres fallos consecutivos durante la primera parte del demo:

1. Detener intentos en vivo.
2. Mostrar video pre-grabado (P4 lo grabó en rehearsal).
3. P1 narra sobre el video.

**Tener el video listo es no-negociable.**

---

## 4.4 Checklist pre-demo (T-2 h)

| # | Check | OK |
|---|-------|----|
| 1 | Lab primario (P4) — `vagrant status` todos UP | ☐ |
| 2 | Lab espejo (P1) — `vagrant status` todos UP | ☐ |
| 3 | Telegram bot envía mensaje de prueba a los 4 celulares | ☐ |
| 4 | Discord webhook envía mensaje al canal | ☐ |
| 5 | Twilio: credit > USD 3 | ☐ |
| 6 | OpenAI: usage budget no excedido | ☐ |
| 7 | Postgres responde a `psql -c "\dt"` | ☐ |
| 8 | OpenSearch dashboard carga en `http://localhost:5601` | ☐ |
| 9 | Streamlit Console abre en `http://localhost:8501` | ☐ |
| 10 | Video respaldo grabado y accesible offline | ☐ |
| 11 | Pendrive USB con repo clonado | ☐ |
| 12 | Cargadores de las 2 laptops + cable al proyector | ☐ |

---

## ✅ Checklist Fase 4

| # | Check | OK |
|---|-------|----|
| 1 | Rehearsal individual cerrado sin issues abiertos | ☐ |
| 2 | Rehearsal en grupo cerrado con los 4 integrantes | ☐ |
| 3 | Video respaldo grabado | ☐ |
| 4 | Checklist pre-demo corrido T-2 h | ☐ |
| 5 | `docs/LESSONS_LEARNED.md` actualizado | ☐ |

---

# Apéndice A — Troubleshooting consolidado

| # | Síntoma | Diagnóstico rápido | Fix |
|---|---------|--------------------|-----|
| A.1 | `ModuleNotFoundError: argos_contracts` | `which python` no es venv | `source .venv/bin/activate && pip install -e ./argos_contracts` |
| A.2 | Telegram `"chat not found"` | Nunca enviaste mensaje al bot | `t.me/<usuario_bot>` → `/start` |
| A.3 | Discord webhook 401 | URL mal copiada | Recrea el webhook en el canal |
| A.4 | Twilio error 21219 | `TO_NUMBER` no verificado | Verifícalo en console.twilio.com |
| A.5 | Redis `CONNECTION REFUSED` | Daemon parado | `docker run -d -p 6379:6379 redis:7` |
| A.6 | `BUSYGROUP` en logs | Grupo ya existe | Ignorar — no es error |
| A.7 | Approval API `Event loop is closed` | Mal asyncio fixture | `pip install pytest-asyncio==0.23.x` y `asyncio_mode = "auto"` en `pyproject.toml` |
| A.8 | Tests `xfail` que pasan (`XPASSED`) | Bug resuelto | Borrar el mark `@pytest.mark.xfail` |
| A.9 | Latencias notif > 2 s | DNS o red lenta | `time curl https://api.telegram.org/bot$TOKEN/getMe` — si > 800 ms, cambiar red |

---

# Apéndice B — Comandos de emergencia (durante el demo)

```bash
# Reiniciar todo el plano de control SOAR sin tocar el lab
make soar-restart

# Switch a Llama local si OpenAI cae
export LLM_BACKEND=llama_local && make llm-restart

# Switch al lab espejo
export WAZUH_HOST=p1-espejo.local && make soar-restart

# Limpiar incidents del demo previo
redis-cli --scan --pattern 'incident:*' | xargs -r redis-cli DEL

# Resetear consumer group (re-procesa últimos eventos)
redis-cli XGROUP SETID events:normalized soar-router 0

# Forzar block manual de un incident colgado
redis-cli SET 'incident:inc-XXX:override' 'force_block'
```

---

# Apéndice C — Referencias cruzadas

| Cuando estés en... | Lee |
|--------------------|-----|
| `tier_router.py` | SAD §6.2, ADR-0002 |
| `notifications/` | ADR-0007 v2, SAD §8.3 |
| `approval_api/` | ADR-0006, USE_CASES UC-04 |
| `consumer.py` | `docs/contracts/CONTRACTS_SPECIFICATION.md` §4 |
| `audit/` | THREAT_MODEL §5, SAD §11 |
| Contingencias del demo | `docs/team/manual-equipo.md` §1, THREAT_MODEL §7 |

---

## Change log

| Versión | Fecha | Cambio |
|---------|-------|--------|
| 3.0 | 2026-05-24 | Reestructurado a Contexto → Pasos manuales → Comandos → Salida esperada → Verificación → Si algo falla. Bloques de comandos preparados para HTML interactivo con copy buttons. Eliminadas referencias temporales (semanas/días/sprint). Renombrado de `sprint-week-1-p1-enzo.md` a `manual-p1-enzo.md`. |
