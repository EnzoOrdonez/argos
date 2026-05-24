# Manual P1 — Enzo Ordoñez Flores (Líder Técnico)

| Campo | Valor |
|-------|-------|
| Rol | Líder técnico + integrador cross-layer |
| Owns | SOAR Decision Engine (`soar/`) · HITL workflow · Notification Service · Approval API · `argos_contracts` |
| No owns | Layers 1/3 (P3) · Layer 2 ML / Layer 4 LLM (P2) · Lab + UI + DB (P4) |
| Outputs blocking otros | `Incident` model en Redis → P4 (UI lee) · Tier router + Approver workflow → demo UC-04 |
| Deadline | **2026-06-13 (sábado)** — demo en vivo + informe entregado |
| Cómo leer este manual | Linealmente. Cada fase asume la anterior cerrada. Cada sección termina con un checklist; no avances si algún check falla. |

---

## 0. Tu charter en una frase

> Tú haces que las 4 capas hablen entre ellas, que un humano pueda aprobar/rechazar acciones críticas, y que las notificaciones lleguen a 4 canales sin caerse. Si tu pieza falla, el demo falla. Si tu pieza funciona, el resto del equipo brilla.

### 0.1 Tu camino crítico (visual)

```
┌──────────────────────────────────────────────────────────────────────┐
│  FASE 1            FASE 2               FASE 3            FASE 4     │
│  (cimientos)       (skeletons)          (integración)     (polish)   │
│                                                                      │
│  prereqs ─┐                                                          │
│  cuentas ─┼──→ tier router ──→ consume eventos ──→ rehearsal UC-01  │
│  repo ───┘     notif telegram     reales del lab       rehearsal UC-04│
│                notif discord      audit en PG          edge cases    │
│                notif twilio       LLM hook             contingencia  │
│                approval API       UC end-to-end                      │
│                two-person rule                                       │
│                consolidation 60s                                     │
└──────────────────────────────────────────────────────────────────────┘
        Día 0-1            Día 1-3            Día 4-5         Día 6-7
```

> Las "fases" no son calendario rígido; son **orden de implementación**. Si terminas Fase 2 en día 2, salta a Fase 3. Si te trabas en Fase 2 hasta día 4, recortas Fase 4 y avisas en standup.

### 0.2 Cómo leer los outputs esperados

Cuando veas un bloque marcado `# OUTPUT ESPERADO:` debajo de un comando, ese es el output **literal** que debes ver, salvo timestamps y UUIDs. Si tu output difiere en estructura (no en valores numéricos), algo está mal. **No avances** hasta resolverlo: usa el Apéndice A (Troubleshooting) o pinguea en `#argos-help` antes de 30 minutos.

### 0.3 Convenciones de error handling

Cada sección tiene tres niveles de control:

1. **Output esperado inmediato** después de cada comando crítico.
2. **Checklist de verificación** al final de cada sección.
3. **Tabla de troubleshooting** en Apéndice A — entrada por síntoma observable.

Si los tres niveles te fallan, asume que es un bug del manual y abre issue (`bug: manual P1 sección X.Y`) en GitHub. **No pivotees el diseño sin aviso** — eso es lo que rompió a equipos de años anteriores.

---

# FASE 1 — Cimientos

> Goal: terminar Fase 1 en ≤ 8 horas de trabajo activo (típicamente día 0 noche + día 1 mañana). Si te lleva más, escala.

---

## 1.1 Verificar prerequisites del sistema

### Qué estás haciendo

Confirmando que tu laptop tiene las versiones correctas de Python, git, Docker, y herramientas CLI antes de tocar el código. **El 80% de los errores raros vienen de versiones desalineadas** entre integrantes.

### Comandos

```bash
# Versión de Python (requerimos 3.11.x exacto)
python3 --version
# OUTPUT ESPERADO:
# Python 3.11.7  (o cualquier 3.11.x; NO 3.10, NO 3.12)

# Versión de pip (>= 23.0)
pip --version
# OUTPUT ESPERADO:
# pip 23.x.x from /usr/lib/python3/dist-packages/pip (python 3.11)

# git instalado
git --version
# OUTPUT ESPERADO:
# git version 2.34.1  (cualquier >= 2.30)

# Docker (necesario para Wazuh local + OpenSearch + Redis)
docker --version && docker compose version
# OUTPUT ESPERADO:
# Docker version 24.x.x, build xxxxx
# Docker Compose version v2.x.x

# redis-cli (para inspeccionar incidents en Redis directo)
redis-cli --version
# OUTPUT ESPERADO:
# redis-cli 7.0.x  (instalable con: apt install redis-tools)

# curl y jq (para probar APIs HTTP)
curl --version | head -1
jq --version
# OUTPUT ESPERADO:
# curl 7.81.0 (x86_64-pc-linux-gnu) ...
# jq-1.6
```

### Comprobar que todo salió bien

| Check | Comando | Esperado |
|-------|---------|----------|
| Python 3.11.x | `python3 --version` | `3.11.x` |
| pip >= 23 | `pip --version` | `23.x` o mayor |
| git >= 2.30 | `git --version` | `>= 2.30` |
| Docker daemon corre | `docker ps` | tabla vacía sin error |
| redis-cli | `redis-cli --version` | `7.x` |

Si **cualquiera falla** → Apéndice A.1 (instalación de prerequisites por OS).

---

## 1.2 Crear cuentas externas

### Qué estás haciendo

ARGOS depende de 4 servicios externos. Crea cuentas ahora; pegarlas en `.env` después. Cada cuenta es **gratuita** en su plan de prueba.

### 1.2.1 Telegram bot (canal primario)

```bash
# Abre Telegram en tu celular o desktop
# Busca: @BotFather
# Envía: /newbot
# Nombre: ARGOS Alerts Bot
# Username: argos_alerts_<tu_inicial>_bot   (debe terminar en _bot)
# 
# BotFather responde con:
# Use this token to access the HTTP API:
# 7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
#
# COPIA ESE TOKEN — es tu TELEGRAM_BOT_TOKEN.

# Para obtener tu chat_id (donde llegarán las alertas):
# 1. Envía cualquier mensaje a tu bot (hola)
# 2. Abre en navegador:
#    https://api.telegram.org/bot<TU_TOKEN>/getUpdates
# 3. En la respuesta JSON, busca: "chat":{"id": 123456789, ...}
# Ese número es tu TELEGRAM_CHAT_ID.

# Verifica que funciona:
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" \
  -d "text=ARGOS test from $(hostname)" | jq .ok
# OUTPUT ESPERADO:
# true
```

### 1.2.2 Discord webhook (canal secundario)

```
1. Crea un servidor Discord nuevo: "ARGOS Demo"
2. Crea canal #argos-alerts
3. Settings (engranaje del canal) → Integrations → Webhooks → New Webhook
4. Nombre: ARGOS Notifier
5. Copy Webhook URL  → es tu DISCORD_WEBHOOK_URL
   Formato: https://discord.com/api/webhooks/<id>/<token>

Verificar:
curl -X POST "$DISCORD_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content": "ARGOS webhook test"}'

OUTPUT ESPERADO:
(sin output — código HTTP 204; el mensaje aparece en el canal Discord)
```

### 1.2.3 Twilio (escalación T2 por voz DTMF)

```
1. https://www.twilio.com/try-twilio  → cuenta trial (gratis, USD 15 credit)
2. Verificar tu celular como "verified caller" (Twilio trial restringe llamadas
   solo a números verificados — esto está OK para el demo).
3. Console → Account → API keys & tokens → copy:
   - Account SID  → TWILIO_ACCOUNT_SID
   - Auth Token   → TWILIO_AUTH_TOKEN
4. Get a Twilio phone number (trial te da uno gratis, USA)
   → TWILIO_FROM_NUMBER  (formato +1XXXXXXXXXX)
```

> **Limitación trial**: si los 4 integrantes están en Perú, Twilio puede no entregar llamadas internacionales en trial. **Plan B** ya documentado en ADR-0007 v2: Twilio se prueba en sandbox; si en el día del demo no funciona, escalación T2 cae automáticamente a Telegram + Discord con prefijo `[T2-ESCALATION]`.

### 1.2.4 OpenAI API key (LLM Triage, Layer 4)

```
1. https://platform.openai.com/api-keys
2. Create new secret key → nombre: "ARGOS demo"
3. Copy key (empieza con sk-proj-...)  → OPENAI_API_KEY
4. Set billing limit a USD 5/mes en https://platform.openai.com/account/billing/limits
   (gpt-4o-mini cuesta ~$0.15 input + $0.60 output por 1M tokens; budget
   sobrado para el demo + rehearsals.)
```

> **Fallback**: si OpenAI cae, P2 tiene `LLM_BACKEND=llama_local` apuntando a Ollama corriendo Llama 3.1 8B en localhost. Tu trabajo aquí es **solo** crear la cuenta y poner la key; el switch lo hace P2 desde su capa.

### Comprobar que todo salió bien

| Check | Comando / Acción | Esperado |
|-------|------------------|----------|
| Bot Telegram responde | curl sendMessage con token | `"ok": true` |
| Webhook Discord funciona | curl POST | mensaje aparece en canal |
| Twilio credenciales válidas | login en console.twilio.com | dashboard carga |
| OpenAI key válida | `curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"` | JSON con lista de modelos (no `"invalid_api_key"`) |

**Si alguna falla**: no pases a 1.3. Resolver antes — los 4 son críticos para el demo.

---

## 1.3 Clonar repo y preparar entorno Python

### Comandos

```bash
# Carpeta de trabajo
mkdir -p ~/code && cd ~/code

# Clone
git clone git@github.com:enzizoor/argos.git
cd argos

# Verificar branch y estado
git status
# OUTPUT ESPERADO:
# On branch main
# Your branch is up to date with 'origin/main'.
# nothing to commit, working tree clean

# Crear virtualenv
python3 -m venv .venv
source .venv/bin/activate
# El prompt debe cambiar a:
# (.venv) usuario@host:~/code/argos$

# Actualizar pip dentro del venv
pip install --upgrade pip
# OUTPUT ESPERADO (última línea):
# Successfully installed pip-24.x.x

# Instalar argos_contracts en modo editable
pip install -e ./argos_contracts
# OUTPUT ESPERADO (últimas líneas):
# Successfully built argos_contracts
# Successfully installed argos_contracts-1.1.0 pydantic-2.x.x ...

# Verificar que el paquete importa
python -c "import argos_contracts; print(argos_contracts.__version__)"
# OUTPUT ESPERADO:
# 1.1.0

# Instalar dependencias del SOAR
pip install -r soar/requirements.txt
# OUTPUT ESPERADO (última línea):
# Successfully installed fastapi-0.110.x uvicorn-0.27.x redis-5.0.x httpx-0.27.x ...
```

### Crear `.env` con tus credenciales

```bash
# El archivo .env NUNCA se commitea (está en .gitignore).
# Plantilla:
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
TWILIO_TO_NUMBER=+51XXXXXXXXX   # tu número verificado

# === OpenAI ===
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_BACKEND=openai_gpt4o_mini   # alternativa: llama_local

# === Redis (lab Vagrant local) ===
REDIS_URL=redis://localhost:6379/0

# === PostgreSQL (audit log) ===
ARGOS_PG_URL=postgresql://argos:argos@localhost:5432/argos_audit
EOF

# Reemplaza los placeholders con tus valores reales.
chmod 600 .env
```

### Comprobar que todo salió bien

```bash
# Test smoke
pytest -q
# OUTPUT ESPERADO:
# .........................................................        [100%]
# 69 passed, 1 warning in 0.27s

# Confirmar venv activo y deps instaladas
which python
# OUTPUT ESPERADO:
# /home/<usuario>/code/argos/.venv/bin/python

pip list | grep -E "(argos|fastapi|redis|pydantic)"
# OUTPUT ESPERADO (4 líneas, versiones aproximadas):
# argos-contracts        1.1.0
# fastapi                0.110.x
# pydantic               2.x.x
# redis                  5.0.x
```

| Check Fase 1 | Estado esperado |
|-------------|-----------------|
| `python3 --version` | 3.11.x |
| Tests existentes pasan | 69 passed |
| `.env` existe con 4 credenciales reales | sí |
| Telegram, Discord, OpenAI keys funcionan | sí (verificado en 1.2) |
| `git status` | working tree clean |

**No avances a Fase 2 si cualquier check de 1.3 está rojo.**

---

# FASE 2 — Skeletons funcionales

> Goal: cada componente individual corre y pasa sus tests unitarios, **aún con stubs** en lugar de servicios reales. Conexión al lab real viene en Fase 3.

---

## 2.1 SOAR Decision Engine — Tier Router

### Qué estás haciendo

El Tier Router es **la pieza más crítica de todo ARGOS**: recibe un evento normalizado de cualquier capa y decide qué Tier asignar (T0 / T1 / T2 / T3). De ese tier salen las acciones automáticas y/o la solicitud de aprobación humana.

### Estructura de archivos

```
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

### Crear `tier_router.py` (código central completo)

```python
# soar/decision_engine/tier_router.py
"""
Tier Router — asigna T0/T1/T2/T3 a un evento normalizado.

Regla:
  - T0: alta confianza, acción inmediata automática (aislar host).
  - T1: alta confianza, acción automática reversible (quarantine).
  - T2: confianza media, requiere aprobación humana (HITL).
  - T3: baja confianza, sólo log + dashboard.

El tier sale de combinar:
  - severity (de la regla disparada)
  - num_layers_fired (1 capa = más débil; 3+ = más fuerte)
  - confidence_score (ML / LLM)
  - mitre_technique (algunos son auto-T0 por política)
"""

from __future__ import annotations

from typing import Literal

from argos_contracts.enums import Tier
from argos_contracts.incident import NormalizedEvent
from soar.decision_engine.policies import (
    AUTO_T0_TECHNIQUES,
    MIN_LAYERS_FOR_AUTO,
    SEVERITY_TO_BASE_Tier,
)

ConfidenceBand = Literal["high", "medium", "low"]


def confidence_band(score: float) -> ConfidenceBand:
    """Map [0.0, 1.0] → high/medium/low."""
    if score >= 0.85:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def route(event: NormalizedEvent) -> Tier:
    """
    Devuelve el Tier asignado a un evento. Pura: no I/O, no mutación.

    Args:
        event: evento normalizado proveniente de cualquier capa.

    Returns:
        Tier (T0, T1, T2, o T3).
    """
    # 1. Auto-T0 por técnica MITRE crítica (ransomware encryption, mass delete)
    if event.mitre_technique in AUTO_T0_TECHNIQUES:
        return Tier.T0

    # 2. Tier base por severity
    base = SEVERITY_TO_BASE_TIER[event.severity]

    # 3. Boost por número de capas que coincidieron
    if event.num_layers_fired >= MIN_LAYERS_FOR_AUTO:
        # 3+ capas → forzar a T0 si base ≤ T1
        if base in (Tier.T1, Tier.T2):
            return Tier.T0

    # 4. Down-tier si confianza baja (single layer + low confidence)
    band = confidence_band(event.confidence_score)
    if event.num_layers_fired == 1 and band == "low":
        return Tier.T3

    return base
```

### Crear `policies.py` (matrices completas)

```python
# soar/decision_engine/policies.py
"""
Matrices y constantes de política para el Tier Router.

Cualquier cambio aquí cambia el comportamiento del demo. Mantener una sola fuente
de verdad evita branchear lógica en múltiples archivos.
"""

from argos_contracts.enums import Severity, Tier

# Cualquier técnica en esta lista dispara T0 automático (acción inmediata).
# Justificación: el costo de un FP es bajo (aislar un host), el costo de un FN
# es altísimo (ransomware completo).
AUTO_T0_TECHNIQUES: frozenset[str] = frozenset({
    "T1486",  # Data Encrypted for Impact (ransomware)
    "T1490",  # Inhibit System Recovery (delete shadow copies)
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

### Tests unitarios completos

```python
# soar/decision_engine/tests/test_tier_router.py
import pytest

from argos_contracts.enums import Severity, Tier
from argos_contracts.incident import NormalizedEvent
from soar.decision_engine.tier_router import route, confidence_band


def make_event(**overrides) -> NormalizedEvent:
    """Factory con defaults sensatos para tests."""
    base = dict(
        event_id="evt-test-001",
        severity=Severity.MEDIUM,
        mitre_technique="T1083",   # File and Directory Discovery
        num_layers_fired=1,
        confidence_score=0.7,
        host="WIN-VICTIM-01",
        layer_origin="sigma",
    )
    base.update(overrides)
    return NormalizedEvent(**base)


# --- confidence_band -----------------------------------------------------
@pytest.mark.parametrize("score, expected", [
    (0.95, "high"), (0.85, "high"),
    (0.84, "medium"), (0.60, "medium"), (0.55, "medium"),
    (0.54, "low"), (0.10, "low"),
])
def test_confidence_band(score, expected):
    assert confidence_band(score) == expected


# --- route ---------------------------------------------------------------
def test_auto_t0_for_ransomware_technique():
    e = make_event(mitre_technique="T1486", severity=Severity.LOW)
    assert route(e) == Tier.T0   # técnica crítica fuerza T0 aún con severity LOW


def test_critical_severity_maps_to_t0():
    e = make_event(severity=Severity.CRITICAL, mitre_technique="T1083")
    assert route(e) == Tier.T0


def test_three_layers_boost_t2_to_t0():
    e = make_event(severity=Severity.MEDIUM, num_layers_fired=3)
    assert route(e) == Tier.T0


def test_single_layer_low_confidence_drops_to_t3():
    e = make_event(severity=Severity.MEDIUM, num_layers_fired=1, confidence_score=0.3)
    assert route(e) == Tier.T3


def test_medium_severity_two_layers_stays_t2():
    e = make_event(severity=Severity.MEDIUM, num_layers_fired=2, confidence_score=0.7)
    assert route(e) == Tier.T2
```

### Correr y verificar

```bash
# Desde la raíz del repo, con venv activo:
pytest soar/decision_engine/tests/ -v
# OUTPUT ESPERADO:
# soar/decision_engine/tests/test_tier_router.py::test_confidence_band[0.95-high]   PASSED
# soar/decision_engine/tests/test_tier_router.py::test_confidence_band[0.85-high]   PASSED
# ... (7 parametrize + 5 tests = 12 PASSED)
# ============================== 12 passed in 0.08s ==============================
```

### Comprobar que todo salió bien (sección 2.1)

| Check | Comando | Esperado |
|-------|---------|----------|
| Tests router | `pytest soar/decision_engine/tests/test_tier_router.py -v` | 12 passed |
| Sin imports rotos | `python -c "from soar.decision_engine.tier_router import route; print('ok')"` | `ok` |
| Coverage del router ≥ 90% | `pytest --cov=soar.decision_engine.tier_router soar/` | `>=90%` |

---

## 2.2 Notification Service — Estructura base

### Qué estás haciendo

Adapter pattern: una interfaz `NotificationChannel` con N implementaciones (Telegram, Discord, Twilio, Email). El `NotificationService` recibe un `Incident` y despacha a los canales correspondientes según política.

### Estructura

```
soar/
├── notifications/
│   ├── __init__.py
│   ├── base.py            ← interfaz + clase base (full)
│   ├── service.py         ← orquestador (full)
│   ├── channels/
│   │   ├── __init__.py
│   │   ├── telegram.py    ← 2.3 (full)
│   │   ├── discord.py     ← 2.4 (full)
│   │   ├── twilio_voice.py ← 2.5 (full)
│   │   └── email_postfact.py ← skeleton + reference
│   └── tests/
│       ├── test_service.py
│       └── channels/
```

### Crear `base.py` (interfaz central)

```python
# soar/notifications/base.py
"""
Interfaz común a todos los canales de notificación.

Convención: un canal SIEMPRE devuelve DispatchResult, nunca tira excepción
hacia afuera. Eso permite al Service degradar (intentar canal B si canal A
falla) sin try/except esparcido.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from argos_contracts.incident import Incident
from argos_contracts.enums import NotificationChannelType


@dataclass(frozen=True)
class DispatchResult:
    channel: NotificationChannelType
    success: bool
    latency_ms: int
    error: Optional[str] = None


class NotificationChannel(ABC):
    """Cada canal implementa esto. Sin estado mutable salvo `self.config`."""

    channel_type: NotificationChannelType   # subclase setea como class var

    @abstractmethod
    def dispatch(self, incident: Incident) -> DispatchResult:
        """Envía notificación. Nunca tira excepción al caller."""
        ...
```

### Crear `service.py` (orquestador central)

```python
# soar/notifications/service.py
"""
Orquesta despacho a múltiples canales según el Tier del incidente.

Política de despacho (de ADR-0007 v2):
    T0 → Telegram + Discord (informativo, sin pedir aprobación)
    T1 → Telegram + Discord (informativo)
    T2 → Telegram + Discord (con botones de aprobación)
         + Twilio Voice si nadie respondió en 60s
    T3 → solo log (no notificación)
"""

from __future__ import annotations

import logging
import time
from typing import Iterable

from argos_contracts.enums import Tier, NotificationChannelType
from argos_contracts.incident import Incident

from soar.notifications.base import NotificationChannel, DispatchResult

logger = logging.getLogger(__name__)


# Política: qué canales para qué tier en el primer disparo.
TIER_CHANNELS: dict[Tier, list[NotificationChannelType]] = {
    Tier.T0: [NotificationChannelType.TELEGRAM, NotificationChannelType.DISCORD],
    Tier.T1: [NotificationChannelType.TELEGRAM, NotificationChannelType.DISCORD],
    Tier.T2: [NotificationChannelType.TELEGRAM, NotificationChannelType.DISCORD],
    Tier.T3: [],
}


class NotificationService:
    """
    Inyecta canales en el constructor → testeable con fakes.
    Las llamadas dispatch() son síncronas: para HITL no necesitamos throughput,
    necesitamos predictibilidad.
    """

    def __init__(self, channels: Iterable[NotificationChannel]):
        self._channels: dict[NotificationChannelType, NotificationChannel] = {
            c.channel_type: c for c in channels
        }

    def dispatch_for_tier(self, incident: Incident) -> list[DispatchResult]:
        wanted = TIER_CHANNELS.get(incident.tier, [])
        results: list[DispatchResult] = []
        for channel_type in wanted:
            channel = self._channels.get(channel_type)
            if channel is None:
                results.append(DispatchResult(
                    channel=channel_type,
                    success=False,
                    latency_ms=0,
                    error="channel not configured",
                ))
                continue
            t0 = time.monotonic()
            try:
                results.append(channel.dispatch(incident))
            except Exception as exc:   # noqa: BLE001 — defensive último resorte
                logger.exception("channel %s raised unexpected exception", channel_type)
                results.append(DispatchResult(
                    channel=channel_type,
                    success=False,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    error=f"unexpected: {type(exc).__name__}: {exc}",
                ))
        return results

    def escalate_to_voice(self, incident: Incident) -> DispatchResult:
        """T2 a t=60s sin respuesta → llamada Twilio (DTMF)."""
        voice = self._channels.get(NotificationChannelType.TWILIO_VOICE)
        if voice is None:
            return DispatchResult(
                channel=NotificationChannelType.TWILIO_VOICE,
                success=False, latency_ms=0,
                error="twilio not configured",
            )
        return voice.dispatch(incident)
```

### Tests del orquestador (parte boilerplate, skeleton + referencia)

```python
# soar/notifications/tests/test_service.py
"""
Verifica:
  - dispatch_for_tier respeta TIER_CHANNELS
  - Si un canal lanza excepción, se captura → success=False (no propaga)
  - T3 no despacha nada

Patrón: FakeChannel implementa NotificationChannel devolviendo lo que le digamos.
Ver `tests/conftest.py` para fixture `fake_channel_factory`.
"""

# ... (tests parametrizados — patrón estándar pytest; ver
#      docs/contracts/CONTRACTS_SPECIFICATION.md §3 para ejemplos similares)
```

### Comprobar que todo salió bien (sección 2.2)

| Check | Comando | Esperado |
|-------|---------|----------|
| `base.py` y `service.py` importan | `python -c "from soar.notifications.service import NotificationService; print('ok')"` | `ok` |
| Tests del service pasan | `pytest soar/notifications/tests/test_service.py -v` | `>= 5 passed` |
| Cobertura del service ≥ 80% | `pytest --cov=soar.notifications.service` | `>=80%` |

---

## 2.3 Notification Channel — Telegram

### Código completo

```python
# soar/notifications/channels/telegram.py
"""
Telegram bot — canal primario para todos los tiers != T3.

Mensajes formateados con MarkdownV2 (Telegram-flavored). Botones inline para T2
(Approve / Reject) cuando incident.requires_approval == True.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

from argos_contracts.enums import NotificationChannelType, Tier
from argos_contracts.incident import Incident

from soar.notifications.base import DispatchResult, NotificationChannel

logger = logging.getLogger(__name__)


_API = "https://api.telegram.org/bot{token}/sendMessage"


def _escape_md(text: str) -> str:
    """MarkdownV2 reserved: _*[]()~`>#+-=|{}.!"""
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


def _inline_keyboard_for_approval(incident_id: str) -> dict:
    return {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"approve:{incident_id}"},
            {"text": "❌ Reject",  "callback_data": f"reject:{incident_id}"},
        ]]
    }


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
            body["reply_markup"] = _inline_keyboard_for_approval(incident.incident_id)
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

### Prueba manual (smoke test)

```bash
# Exportar credenciales y simular un incidente T0
export $(grep -v '^#' .env | xargs)

python - << 'PY'
from argos_contracts.incident import Incident, HostInfo
from argos_contracts.enums import Tier, Severity, IncidentState
from soar.notifications.channels.telegram import TelegramChannel
from datetime import datetime, timezone

incident = Incident(
    incident_id="inc-smoke-001",
    tier=Tier.T0,
    state=IncidentState.NEW,
    severity=Severity.CRITICAL,
    host=HostInfo(hostname="WIN-VICTIM-01", ip="192.168.56.20", os="Windows 10"),
    mitre_technique="T1486",
    num_layers_fired=3,
    confidence_score=0.94,
    created_at=datetime.now(timezone.utc),
    requires_approval=False,
    approvers=[], final_decision=None, consolidation_window=None,
)
result = TelegramChannel().dispatch(incident)
print(result)
PY
# OUTPUT ESPERADO:
# DispatchResult(channel=<NotificationChannelType.TELEGRAM: 'telegram'>, success=True, latency_ms=287, error=None)
#
# Y en tu Telegram:
# 🔴 ARGOS T0 — WIN-VICTIM-01
# Técnica: T1486
# Capas firing: 3
# Confianza: 0.94
# ID: inc-smoke-001
```

### Comprobar que todo salió bien (sección 2.3)

| Check | Esperado |
|-------|----------|
| Smoke test arriba devuelve `success=True` | sí |
| Mensaje llega a Telegram en < 1s | sí |
| Si pones token inválido, devuelve `success=False` con error visible (no excepción) | sí |

---

## 2.4 Notification Channel — Discord

### Código completo

```python
# soar/notifications/channels/discord.py
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
            # Discord webhook devuelve 204 No Content en éxito.
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

### Smoke test

```bash
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
print(DiscordChannel().dispatch(i))
PY
# OUTPUT ESPERADO:
# DispatchResult(channel=<NotificationChannelType.DISCORD: 'discord'>, success=True, latency_ms=312, error=None)
#
# En Discord aparece un embed amarillo con los 4 fields.
```

### Comprobar (sección 2.4)

| Check | Esperado |
|-------|----------|
| Smoke test devuelve `success=True` | sí |
| Embed visible en canal #argos-alerts con color correcto por tier | sí |
| URL mal escrita → `success=False` con error 401/404, no excepción | sí |

---

## 2.5 Notification Channel — Twilio Voice (escalación T2)

### Por qué importa

Sólo se dispara para T2 a t=60s sin respuesta. La llamada lee TwiML que enuncia el incidente y captura DTMF (`1=approve`, `2=reject`). Se llama **una vez por aprobador** que no haya respondido. Es el último recurso antes de que el conservative-wins policy decida solo.

### Código completo

```python
# soar/notifications/channels/twilio_voice.py
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
    """URL pública que sirve el TwiML.

    Para el lab usamos `ngrok` apuntando al Approval API local.
    El TwiML responde:
      <Response>
        <Gather numDigits="1" action="/voice/dtmf?incident=...">
          <Say voice="alice">ARGOS critical incident on host X.
                             Press 1 to approve, 2 to reject.</Say>
        </Gather>
      </Response>
    """
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
        self._sid   = account_sid or os.environ["TWILIO_ACCOUNT_SID"]
        self._tok   = auth_token  or os.environ["TWILIO_AUTH_TOKEN"]
        self._from  = from_number or os.environ["TWILIO_FROM_NUMBER"]
        self._to    = to_number   or os.environ["TWILIO_TO_NUMBER"]
        self._base  = public_base_url or os.environ.get("ARGOS_PUBLIC_URL", "")
        self._client = client or httpx.Client(timeout=timeout,
                                              auth=(self._sid, self._tok))

    def dispatch(self, incident: Incident) -> DispatchResult:
        t0 = time.monotonic()
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._sid}/Calls.json"
        try:
            r = self._client.post(url, data={
                "From": self._from,
                "To":   self._to,
                "Url":  _twiml_url(incident.incident_id, self._base),
                "Method": "POST",
                "Timeout": "20",
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

### Smoke test (cuidado — gasta credit Twilio trial)

```bash
# Solo cuando estés listo para probar. Cada llamada consume ~$0.013 trial credit.
# El Approval API debe estar corriendo (sección 2.6) y ngrok debe estar levantado:
# ngrok http 8001

export ARGOS_PUBLIC_URL=https://abcd-1234.ngrok-free.app

python - << 'PY'
import os
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
print(TwilioVoiceChannel().dispatch(i))
PY
# OUTPUT ESPERADO:
# DispatchResult(channel=<NotificationChannelType.TWILIO_VOICE: 'twilio_voice'>, success=True, latency_ms=1432, error=None)
#
# Y en tu celular: una llamada de tu número Twilio. Si contestas, una voz
# dice "ARGOS critical incident...". Presionas 1 o 2.
```

### Comprobar (sección 2.5)

| Check | Esperado |
|-------|----------|
| Trial credit > $1 antes de pruebas | sí |
| `ngrok http 8001` corriendo (para el TwiML callback) | sí |
| `success=True` y la llamada entra al celular | sí |
| Si `TWILIO_TO_NUMBER` no está verificado → error 21219 visible en `result.error` | sí |

---

## 2.6 Approval API — FastAPI endpoints

### Qué estás haciendo

Una mini API HTTP que recibe respuestas de aprobación de **tres orígenes**:

- Telegram → callback de botón inline → webhook en `/telegram/callback`
- Discord → reacción/comando slash → webhook en `/discord/callback` *(opcional para v1)*
- Twilio → DTMF gather → POST a `/voice/dtmf`

Cualquier respuesta mutiá el `Incident` en Redis y dispara la evaluación de la regla two-person.

### Estructura

```
soar/approval_api/
├── __init__.py
├── main.py              ← FastAPI app + endpoints (full)
├── handlers.py          ← lógica HITL (two-person, consolidation) (full)
├── twiml.py             ← genera XML para Twilio (full)
└── tests/
    ├── test_main.py
    ├── test_handlers.py
    └── test_twiml.py
```

### `main.py` (entrypoint completo)

```python
# soar/approval_api/main.py
"""
Approval API — recibe respuestas de los aprobadores y muta el Incident en Redis.

NO escribe acciones (aislar host, kill proceso, etc.); eso lo hace el SOAR
Decision Engine al ver el final_decision en Redis. Esta API es solo el plano
de control HITL.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as redis
from fastapi import FastAPI, Form, HTTPException, Response

from soar.approval_api.handlers import (
    record_approval_response,
    build_final_decision_if_ready,
)
from soar.approval_api.twiml import build_voice_gather_xml, dtmf_to_response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Conexión Redis compartida en app.state."""
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


# ----- Telegram callback ------------------------------------------------
@app.post("/telegram/callback")
async def telegram_callback(update: dict) -> dict:
    """
    Telegram Bot API envía updates aquí cuando alguien toca un botón inline.
    Estructura esperada:
        update["callback_query"] = {
            "id": "...", "data": "approve:inc-001",
            "from": {"id": 12345, "first_name": "Enzo"},
        }
    """
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
        incident_id=incident_id,
        approver_id=approver_id,
        decision=action,
        channel="telegram",
    )
    await build_final_decision_if_ready(app.state.redis, incident_id)
    return {"ok": True}


# ----- Twilio voice -----------------------------------------------------
@app.post("/voice/twiml", response_class=Response)
async def voice_twiml(incident: str) -> Response:
    """Devuelve TwiML que Twilio reproduce; el Gather captura DTMF."""
    xml = build_voice_gather_xml(incident_id=incident)
    return Response(content=xml, media_type="application/xml")


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
        incident_id=incident,
        approver_id=f"twilio:{incident}",
        decision=decision,
        channel="twilio_voice",
    )
    await build_final_decision_if_ready(app.state.redis, incident)
    return Response(
        content=f"<Response><Say>{decision} recorded. Goodbye.</Say><Hangup/></Response>",
        media_type="application/xml",
    )
```

### `twiml.py` (helper completo, pequeño)

```python
# soar/approval_api/twiml.py
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


_DTMF_TO_DECISION: dict[str, Decision] = {"1": "approve", "2": "reject"}


def dtmf_to_response(digits: str) -> Optional[Decision]:
    return _DTMF_TO_DECISION.get(digits.strip()) if digits else None
```

### Correr y verificar

```bash
# Levantar la API en otra terminal:
uvicorn soar.approval_api.main:app --host 0.0.0.0 --port 8001 --reload
# OUTPUT ESPERADO:
# INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
# INFO:     Started reloader process [12345] using StatReload
# INFO:     Started server process [12346]
# INFO:     Waiting for application startup.
# INFO:     Application startup complete.

# Health check
curl -s http://localhost:8001/healthz | jq
# OUTPUT ESPERADO:
# {
#   "ok": true,
#   "redis": true
# }
```

### Comprobar (sección 2.6)

| Check | Comando | Esperado |
|-------|---------|----------|
| API corre | `curl http://localhost:8001/healthz` | `"ok": true, "redis": true` |
| Tests API | `pytest soar/approval_api/tests/ -v` | `>= 8 passed` |
| Endpoint Telegram acepta payload válido | POST con JSON simulado | `{"ok": true}` |
| Endpoint Twilio devuelve TwiML válido | `curl -X POST 'http://localhost:8001/voice/twiml?incident=test'` | XML con `<Gather>` |

---

## 2.7 Two-person rule + conservative-wins policy

### Qué estás haciendo

El núcleo del HITL. Cuando un T2 dispara, se notifican N aprobadores (≥ 2). El sistema espera **hasta 2 respuestas concordantes** o cierra la ventana en 60s. La política `conservative-wins` dice: ante conflicto, **prevalece reject**.

### Código central completo (`handlers.py`)

```python
# soar/approval_api/handlers.py
"""
Lógica HITL: registrar respuestas, evaluar two-person, resolver conflictos.

Estado vive en Redis bajo la clave `incident:{id}`. Cada respuesta se appendea
al array `approvers`. Una vez alcanzado el umbral (2 respuestas concordantes
o timeout), se escribe `final_decision`.

Política conservative-wins (ADR-0006):
  - Si ambos approve → execute.
  - Si ambos reject  → block.
  - Si discrepan     → block (conservative wins).
  - Si solo 1 responde y timeout → block (no quorum).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Literal

import redis.asyncio as redis

from argos_contracts.enums import ApproverStatus, IncidentState
from argos_contracts.incident import (
    ApproverState, FinalDecision, Incident,
)

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
    incident_id: str,
    approver_id: str,
    decision: Literal["approve", "reject"],
    channel: str,
) -> None:
    incident = await _load_incident(redis_client, incident_id)

    # No-op si ya hay final_decision (idempotencia ante reintentos de webhook)
    if incident.final_decision is not None:
        logger.info("incident %s already decided; ignoring late %s from %s",
                    incident_id, decision, approver_id)
        return

    status = (ApproverStatus.APPROVED if decision == "approve"
              else ApproverStatus.REJECTED)
    now = time.time()

    # Actualizar o agregar al array de aprobadores
    found = False
    for ap in incident.approvers:
        if ap.approver_id == approver_id:
            ap.status = status
            ap.responded_at = now
            ap.channel = channel
            found = True
            break
    if not found:
        incident.approvers.append(ApproverState(
            approver_id=approver_id,
            status=status,
            channel=channel,
            notified_at=now,
            responded_at=now,
        ))

    await _save_incident(redis_client, incident)


def _evaluate(incident: Incident) -> FinalDecision | None:
    """Pure: dada la lista de approvers actual, ¿hay decisión?"""
    approved = sum(a.status == ApproverStatus.APPROVED for a in incident.approvers)
    rejected = sum(a.status == ApproverStatus.REJECTED for a in incident.approvers)
    timeout  = sum(a.status == ApproverStatus.TIMEOUT  for a in incident.approvers)

    # Caso 1: quorum claro a favor de approve
    if approved >= QUORUM_NEEDED and rejected == 0:
        return FinalDecision(
            outcome="execute",
            policy_applied="two_person_approve",
            execution_status="pending",
            approved_count=approved, rejected_count=rejected, timeout_count=timeout,
        )

    # Caso 2: quorum claro de reject
    if rejected >= QUORUM_NEEDED:
        return FinalDecision(
            outcome="block",
            policy_applied="two_person_reject",
            execution_status="not_required",
            approved_count=approved, rejected_count=rejected, timeout_count=timeout,
        )

    # Caso 3: conflicto (al menos 1 approve y al menos 1 reject)
    if approved >= 1 and rejected >= 1:
        return FinalDecision(
            outcome="block",
            policy_applied="conservative_wins",
            execution_status="not_required",
            approved_count=approved, rejected_count=rejected, timeout_count=timeout,
        )

    # Caso 4: aún no hay quorum
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
    logger.info("incident %s decided: %s (policy=%s)",
                incident_id, decision.outcome, decision.policy_applied)
    return incident
```

### Tests parametrizados (los casos importantes — completos)

```python
# soar/approval_api/tests/test_handlers.py
import pytest
from argos_contracts.enums import ApproverStatus
from argos_contracts.incident import ApproverState
from soar.approval_api.handlers import _evaluate


def _ap(decision):
    status = {"approve": ApproverStatus.APPROVED,
              "reject":  ApproverStatus.REJECTED,
              "timeout": ApproverStatus.TIMEOUT}[decision]
    return ApproverState(approver_id=decision+"-x", status=status,
                         channel="telegram", notified_at=0, responded_at=0)


@pytest.mark.parametrize("inputs, outcome, policy", [
    # Two approves → execute
    (["approve", "approve"], "execute", "two_person_approve"),
    # Two rejects → block
    (["reject", "reject"], "block", "two_person_reject"),
    # Conflict → conservative-wins block
    (["approve", "reject"], "block", "conservative_wins"),
    (["approve", "reject", "approve"], "block", "conservative_wins"),
    # Only 1 response → no decision yet
    # (handled separately, _evaluate returns None)
])
def test_evaluate_decision_matrix(inputs, outcome, policy, fake_incident):
    inc = fake_incident
    inc.approvers = [_ap(x) for x in inputs]
    decision = _evaluate(inc)
    assert decision is not None
    assert decision.outcome == outcome
    assert decision.policy_applied == policy


def test_single_response_no_decision(fake_incident):
    inc = fake_incident
    inc.approvers = [_ap("approve")]
    assert _evaluate(inc) is None
```

### Correr

```bash
pytest soar/approval_api/tests/test_handlers.py -v
# OUTPUT ESPERADO:
# test_handlers.py::test_evaluate_decision_matrix[inputs0-execute-two_person_approve] PASSED
# test_handlers.py::test_evaluate_decision_matrix[inputs1-block-two_person_reject]    PASSED
# test_handlers.py::test_evaluate_decision_matrix[inputs2-block-conservative_wins]    PASSED
# test_handlers.py::test_evaluate_decision_matrix[inputs3-block-conservative_wins]    PASSED
# test_handlers.py::test_single_response_no_decision                                  PASSED
# ============================== 5 passed in 0.04s ==============================
```

### Comprobar (sección 2.7)

| Check | Esperado |
|-------|----------|
| 5 tests de la matriz pasan | sí |
| Decisión es idempotente (segundo `build_final_decision_if_ready` no muta nada) | sí |
| Si llega un response **después** de `final_decision`, se ignora con log | sí |

---

## 2.8 Consolidation window — 60 segundos

### Qué estás haciendo

Un job background (asyncio task) que dado un `incident_id` espera 60s y, si no hay quorum, marca a los pendientes como TIMEOUT y llama `build_final_decision_if_ready` una última vez.

### Código completo

```python
# soar/approval_api/consolidation.py
"""
Ventana de consolidación T2 — 60 segundos.

Se invoca en cuanto se crea un Incident T2. Si al cumplirse el tiempo no hay
final_decision, se marcan los pendientes como TIMEOUT y se evalúa la última
vez. Si la evaluación final no produce decisión (ej. nadie respondió), se
crea una decisión `block` con policy `no_quorum_timeout`.
"""

from __future__ import annotations

import asyncio
import logging
import time

import redis.asyncio as redis

from argos_contracts.enums import ApproverStatus, IncidentState
from argos_contracts.incident import FinalDecision
from soar.approval_api.handlers import (
    _evaluate, _load_incident, _save_incident,
)

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60


async def consolidation_task(r: redis.Redis, incident_id: str) -> None:
    """Background task. Spawn con `asyncio.create_task(...)`."""
    await asyncio.sleep(WINDOW_SECONDS)

    incident = await _load_incident(r, incident_id)
    if incident.final_decision is not None:
        return  # alguien ya cerró antes de los 60s

    # Marcar a los que no respondieron como TIMEOUT
    for ap in incident.approvers:
        if ap.status == ApproverStatus.PENDING:
            ap.status = ApproverStatus.TIMEOUT
            ap.responded_at = time.time()

    decision = _evaluate(incident)
    if decision is None:
        # Nadie respondió o solo timeouts → conservative block
        decision = FinalDecision(
            outcome="block",
            policy_applied="no_quorum_timeout",
            execution_status="not_required",
            approved_count=0, rejected_count=0,
            timeout_count=sum(1 for a in incident.approvers
                              if a.status == ApproverStatus.TIMEOUT),
        )

    incident.final_decision = decision
    incident.state = IncidentState.RESOLVED
    await _save_incident(r, incident)
    logger.info("incident %s: window closed (%s)",
                incident_id, decision.policy_applied)
```

### Test (acelerando la ventana con monkeypatch)

```python
# soar/approval_api/tests/test_consolidation.py
import asyncio
import pytest

import soar.approval_api.consolidation as consolidation_mod


@pytest.mark.asyncio
async def test_consolidation_no_response_blocks(monkeypatch, fake_redis, fake_incident_t2):
    # Acelerar la ventana de 60s → 0.01s para test
    monkeypatch.setattr(consolidation_mod, "WINDOW_SECONDS", 0.01)

    await fake_redis.set(
        f"incident:{fake_incident_t2.incident_id}",
        fake_incident_t2.model_dump_json(),
    )
    await consolidation_mod.consolidation_task(fake_redis, fake_incident_t2.incident_id)

    raw = await fake_redis.get(f"incident:{fake_incident_t2.incident_id}")
    from argos_contracts.incident import Incident
    final = Incident.model_validate_json(raw)
    assert final.final_decision.outcome == "block"
    assert final.final_decision.policy_applied == "no_quorum_timeout"
```

### Comprobar (sección 2.8)

| Check | Esperado |
|-------|----------|
| `pytest soar/approval_api/tests/test_consolidation.py` | passed |
| Si ya hay `final_decision` antes de 60s, el task no hace nada | sí |
| Si llegan 0 respuestas, decisión es `block / no_quorum_timeout` | sí |

---

## ✅ Checklist Fase 2 — antes de pasar a Fase 3

| # | Check | OK |
|---|-------|----|
| 1 | `pytest soar/` corre y pasa todo (esperado ≥ 30 passed) | ☐ |
| 2 | `uvicorn soar.approval_api.main:app --port 8001` levanta sin errores | ☐ |
| 3 | `/healthz` devuelve `{"ok": true, "redis": true}` con Redis local arriba | ☐ |
| 4 | Telegram smoke test envía mensaje real | ☐ |
| 5 | Discord smoke test envía embed real | ☐ |
| 6 | Twilio Voice smoke test produce llamada (al menos una vez) | ☐ |
| 7 | Tier router asigna T0 para técnica `T1486` y `severity=LOW` | ☐ |
| 8 | Two-person rule resuelve conflict → `block / conservative_wins` | ☐ |
| 9 | Consolidation window cierra a `no_quorum_timeout` cuando nadie responde | ☐ |
| 10 | `.env` cargado correctamente (sin hardcoded credentials en código) | ☐ |

**Si menos de 8/10 está OK, NO avances a Fase 3.** Dedica la mitad del día a cerrar lo restante; pinguea en `#argos-help` si te bloqueas.

---

# FASE 3 — Integración real

> Goal: tu código habla con el lab Vagrant de verdad (Wazuh manager + Redis + Postgres + las 4 capas). Aquí dejan de ser stubs.

---

## 3.1 Consumir eventos reales del lab

### Qué estás haciendo

Hasta ahora tu SOAR procesa `NormalizedEvent` fabricados a mano en tests. Ahora va a leerlos de un Redis stream alimentado por las 4 capas (P3 mete Sigma/Canary, P2 mete ML/LLM).

### Acuerdo de contrato con P2 y P3 (ya documentado en `docs/contracts/CONTRACTS_SPECIFICATION.md`)

```
Stream Redis:                events:normalized
Cada XADD:                   { "data": <NormalizedEvent JSON> }
Consumer group:              soar-router
Tu consumer name:            soar-1
```

### Código central (`soar/decision_engine/consumer.py`)

```python
# soar/decision_engine/consumer.py
"""Consumer del stream Redis events:normalized → emite Incident a Redis."""

from __future__ import annotations

import asyncio, json, logging, os, uuid
from datetime import datetime, timezone

import redis.asyncio as redis

from argos_contracts.enums import IncidentState
from argos_contracts.incident import HostInfo, Incident, NormalizedEvent
from soar.decision_engine.tier_router import route
from soar.notifications.service import NotificationService

logger = logging.getLogger(__name__)

STREAM      = "events:normalized"
GROUP       = "soar-router"
CONSUMER    = os.environ.get("SOAR_CONSUMER_NAME", "soar-1")
INCIDENT_TTL_SECONDS = 6 * 3600  # 6 horas


async def ensure_group(r: redis.Redis) -> None:
    try:
        await r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


async def _process_event(
    r: redis.Redis, notif: NotificationService, raw: dict
) -> None:
    event = NormalizedEvent.model_validate_json(raw["data"])
    tier = route(event)
    incident = Incident(
        incident_id=f"inc-{uuid.uuid4().hex[:12]}",
        tier=tier,
        state=IncidentState.NEW,
        severity=event.severity,
        host=HostInfo(hostname=event.host, ip="", os=""),
        mitre_technique=event.mitre_technique,
        num_layers_fired=event.num_layers_fired,
        confidence_score=event.confidence_score,
        created_at=datetime.now(timezone.utc),
        requires_approval=(tier == tier.T2),
        approvers=[], final_decision=None, consolidation_window=None,
    )
    await r.setex(
        f"incident:{incident.incident_id}",
        INCIDENT_TTL_SECONDS,
        incident.model_dump_json(),
    )
    results = notif.dispatch_for_tier(incident)
    logger.info("incident %s → tier=%s notif=%s",
                incident.incident_id, tier.value,
                [(r.channel.value, r.success) for r in results])


async def run_consumer(notif: NotificationService) -> None:
    r = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await ensure_group(r)
    logger.info("consumer %s reading group %s on stream %s", CONSUMER, GROUP, STREAM)
    while True:
        resp = await r.xreadgroup(
            GROUP, CONSUMER, {STREAM: ">"}, count=10, block=5000
        )
        for _stream, entries in resp or []:
            for entry_id, fields in entries:
                try:
                    await _process_event(r, notif, fields)
                    await r.xack(STREAM, GROUP, entry_id)
                except Exception:   # noqa: BLE001
                    logger.exception("failed to process %s; entry retained", entry_id)
                    # No-ack → reintento próximo xreadgroup tras min-idle.
```

### Probar end-to-end con un evento inyectado manualmente

```bash
# Terminal A: levanta el consumer
python -m soar.decision_engine.consumer
# OUTPUT ESPERADO:
# INFO:soar.decision_engine.consumer:consumer soar-1 reading group soar-router on stream events:normalized

# Terminal B: inyecta un evento simulado
redis-cli XADD events:normalized '*' data '{"event_id":"evt-001","severity":"CRITICAL","mitre_technique":"T1486","num_layers_fired":3,"confidence_score":0.94,"host":"WIN-VICTIM-01","layer_origin":"sigma"}'
# OUTPUT ESPERADO:
# "1716580800000-0"   (timestamp-secuencia)

# En terminal A debes ver:
# INFO:soar.decision_engine.consumer:incident inc-abc123def456 → tier=T0 notif=[('telegram', True), ('discord', True)]

# Verificar incident persistido en Redis
redis-cli KEYS 'incident:*'
# OUTPUT ESPERADO:
# 1) "incident:inc-abc123def456"

redis-cli GET incident:inc-abc123def456 | jq .tier,.host.hostname,.mitre_technique
# OUTPUT ESPERADO:
# "T0"
# "WIN-VICTIM-01"
# "T1486"
```

### Comprobar (sección 3.1)

| Check | Esperado |
|-------|----------|
| Consumer arranca sin errores | sí |
| Evento inyectado → genera `incident:*` en Redis | sí |
| Tier asignado coincide con la matriz de `tier_router` | sí |
| Notificaciones llegan a Telegram + Discord (canales aparecen `success=True`) | sí |

---

## 3.2 Audit log en PostgreSQL

### Qué estás haciendo

Cada `Incident` y cada respuesta de aprobador debe persistirse en PostgreSQL (P4 levantó la DB con `pgaudit` activo en su Fase 1). Razón: trazabilidad forense post-mortem.

### Schema (acordado con P4 — ya está en `lab/postgres/init.sql`)

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

### Persistencia (boilerplate, skeleton + referencia)

```python
# soar/audit/postgres_sink.py
"""
Sink de auditoría hacia PostgreSQL.

Se llama dos veces:
  - al crear el incidente (insert)
  - al cerrar la final_decision (update)
  - cada vez que llega una respuesta de aprobador (insert en audit_responses)

Usar asyncpg (async, pooled). El pool se crea en startup de la app.

Para detalles del esquema y migrations, ver `lab/postgres/init.sql` (owner: P4).
La función a llamar desde `consumer.py` es:

    await persist_new_incident(pool, incident)
    await persist_final_decision(pool, incident)
    await persist_response(pool, incident_id, approver_id, channel, decision, ts)

Patrón estándar: parametrized queries, JSONB para el payload completo,
upsert con ON CONFLICT en `incident_id`. Ver test_postgres_sink.py para fixtures.
"""

# (Skeleton — completa siguiendo el patrón conocido. ~80 LOC totales.)
```

### Comprobar (sección 3.2)

```bash
# Con el lab arriba (Vagrant levantado por P4):
psql postgresql://argos:argos@localhost:5432/argos_audit -c \
  "SELECT incident_id, tier, technique, final_outcome FROM audit_incidents ORDER BY created_at DESC LIMIT 5;"
# OUTPUT ESPERADO (después de correr una simulación):
#       incident_id      | tier | technique | final_outcome
# ---------------------+------+-----------+---------------
#  inc-abc123def456    | T0   | T1486     | execute
#  ...
```

| Check | Esperado |
|-------|----------|
| Tabla `audit_incidents` se llena tras un evento | sí |
| Tabla `audit_responses` se llena tras una aprobación | sí |
| `pgaudit` registra los INSERT (verificable con `SELECT * FROM pg_stat_activity`) | sí |

---

## 3.3 Hook a LLM Triage (Layer 4)

### Qué estás haciendo

Cuando el `tier_router` asigna T2 (no T0, no T3), invocas el LLM Triage que P2 expone como módulo `ml.llm_triage.classify(event)` y devuelve un campo extra `llm_verdict` que enriquece el `Incident`.

### Patrón de integración

```python
# soar/decision_engine/consumer.py — modificación en _process_event:

# ... después de calcular tier:
if tier == Tier.T2:
    from ml.llm_triage import classify as llm_classify
    try:
        verdict = await llm_classify(event)   # P2 expone esto
        # verdict = LLMVerdict(label=..., reasoning=..., confidence=...)
    except Exception:   # noqa: BLE001
        logger.exception("llm classify failed; continuing without enrichment")
        verdict = None
    incident.llm_verdict = verdict
```

> **Importante**: si el LLM falla (rate-limit, timeout, OpenAI down), el incidente sigue su curso sin enriquecimiento. **Nunca bloquees** el flujo HITL por el LLM.

### Comprobar (sección 3.3)

| Check | Esperado |
|-------|----------|
| Para evento T2, `incident.llm_verdict` está poblado en Redis | sí |
| Si `LLM_BACKEND=llama_local` y Ollama no corre, el flujo no se cae (verdict=None) | sí |

---

## 3.4 End-to-end UC-01 (ransomware T0)

### Comando del demo

```bash
# Terminal 1 — consumer
python -m soar.decision_engine.consumer

# Terminal 2 — approval API
uvicorn soar.approval_api.main:app --port 8001

# Terminal 3 — lanzar ataque
python attack-simulation/ransomware_simulator/lockbit_like.py \
       --variant uc01 --target windows-victim

# OUTPUT ESPERADO (en terminal 1):
# INFO:soar.decision_engine.consumer:incident inc-XXX → tier=T0 notif=[('telegram', True), ('discord', True)]
#
# OUTPUT ESPERADO (en Streamlit Console http://localhost:8501):
# Incident card con tier=T0, técnica=T1486, host=WIN-VICTIM-01,
# y al cabo de pocos segundos: state=PENDING_EXECUTION → execution_status=success
# (acción: aislar host vía Wazuh active response).
```

### Comprobar (sección 3.4)

| Check | Esperado |
|-------|----------|
| Tiempo desde lanzar ataque → notificación Telegram ≤ 8s | sí |
| Tiempo desde lanzar ataque → host aislado (red bloqueada) ≤ 15s | sí |
| `incident.final_decision.policy_applied == "auto_t0"` (sin pasar por HITL) | sí |
| Postgres tiene fila correspondiente en `audit_incidents` | sí |

---

## 3.5 End-to-end UC-04 (two-person rule)

### Comando

```bash
# Terminales 1 y 2 como arriba.
# Terminal 3:
python attack-simulation/ransomware_simulator/postgres_attack.py \
       --target linux-victim
```

### Lo que debería pasar (timeline)

```
t=0s    Ataque lanzado. Wazuh dispara regla Sigma → evento normalizado.
t=2s    SOAR consumer crea Incident T2 → notifica Telegram + Discord.
        Los 4 integrantes reciben mensaje con botones [Approve] [Reject].
t=10s   P1 toca [Approve] → Approval API registra → 1 approve.
t=18s   P2 toca [Approve] → 2 approves → final_decision=execute → acción ejecuta.
        Streamlit muestra banner verde: "2 approve · 0 reject · execute".
```

### Variante con conflict

```
t=10s   P1 toca [Approve]
t=18s   P2 toca [Reject]
        → conservative-wins → final_decision=block / policy=conservative_wins
        → Streamlit muestra banner gris: "1 approve · 1 reject · block".
```

### Variante con timeout

```
t=10s   P1 toca [Approve]
t=60s   ventana cierra → P2/P3/P4 marcados TIMEOUT
        → no quorum → final_decision=block / policy=no_quorum_timeout
        → en t=60s también dispara Twilio Voice a los que no respondieron
          (si la ventana es ≥ 60s, la llamada sale a t=55s).
```

### Comprobar (sección 3.5)

| Check | Esperado |
|-------|----------|
| Los 4 integrantes reciben Telegram | sí |
| Botones aparecen y son clickeables | sí |
| 2 approves → execute en ≤ 20s | sí |
| Conflict caso → block / conservative_wins | sí |
| Timeout caso → block / no_quorum_timeout | sí |
| Twilio dispara a t=55-60s para no-respondientes | sí |

---

## ✅ Checklist Fase 3 — antes de pasar a Fase 4

| # | Check | OK |
|---|-------|----|
| 1 | Consumer SOAR consume del stream real y emite incidents a Redis | ☐ |
| 2 | UC-01 corre end-to-end (T0 auto) en < 15s p95 | ☐ |
| 3 | UC-04 corre end-to-end con 2 approves → execute | ☐ |
| 4 | UC-04 conflict → block / conservative_wins | ☐ |
| 5 | UC-04 timeout → block / no_quorum_timeout | ☐ |
| 6 | Audit log en PostgreSQL refleja cada incident + cada response | ☐ |
| 7 | LLM hook degrada graciosamente si OpenAI cae | ☐ |
| 8 | `pytest -q` global pasa (esperado 80+ tests) | ☐ |

---

# FASE 4 — Rehearsal y polish

> Goal: simular el demo completo dos veces. La segunda vez con todos los integrantes presentes en llamada Discord. Documentar cada fallo y resolverlo antes del demo real.

---

## 4.1 Rehearsal #1 — solo P1 (silencioso)

### Procedimiento

```bash
# 1. Vagrant arriba, todos los servicios up
make demo-up

# 2. Cronómetro arriba (usa `time` en bash o un timer real)
time {
  python attack-simulation/ransomware_simulator/lockbit_like.py --variant uc01 --target windows-victim
  sleep 20  # esperar ejecución
  python attack-simulation/ransomware_simulator/canary_path.py --target linux-victim
  sleep 15
  python attack-simulation/ransomware_simulator/postgres_attack.py --target linux-victim
  # esperar two-person en otro terminal
}

# Métricas a registrar:
# - tiempo total desde primer comando hasta último incident.state=RESOLVED
# - número de notificaciones que fallaron (revisar logs del consumer)
# - cualquier excepción no manejada (grep ERROR en logs)
```

### Reportar resultado en standup

| UC | Tiempo p50 | Tiempo p95 | Fallos |
|----|------------|------------|--------|
| UC-01 | 7s | 12s | 0 |
| UC-02 | 5s | 8s | 0 |
| UC-04 (2-approve) | 22s | 35s | 0 |

Cualquier fallo → ticket → resolver antes de rehearsal #2.

---

## 4.2 Rehearsal #2 — con los 4 integrantes (call Discord)

### Preparación (T-30 min)

1. Crear evento Discord call: "ARGOS Rehearsal Final" a hora X.
2. Cada integrante con su celular cargado, Telegram + Discord abiertos.
3. P4 confirma que su lab está arriba y que tu lab espejo también.
4. Tú compartes pantalla con Streamlit Console.

### Script del ensayo (12-13 min)

| Tiempo | Acción | Quién |
|--------|--------|-------|
| 0:00 | "Comenzamos UC-01" | P1 (tú) narras |
| 0:05 | `python ...lockbit_like.py ...` | P4 ejecuta |
| 0:30 | Mostrar Streamlit con incident T0 | P1 explica capas firing |
| 2:00 | "UC-02 ahora" | P1 |
| 2:05 | `python ...canary_path.py ...` | P4 |
| 4:00 | "UC-04 — todos atentos al celular" | P1 |
| 4:05 | `python ...postgres_attack.py ...` | P4 |
| 4:10 | Telegram llega — P1 aprueba | P1 |
| 4:18 | P2 aprueba | P2 |
| 4:30 | Mostrar banner "execute" | P1 explica policy |
| 6:00 | Repetir UC-04 — esta vez P1 approve, P2 reject (conflict) | mismo guion |
| 8:00 | Repetir UC-04 — nadie responde (timeout + Twilio) | celular suena |
| 10:00 | Q&A simulado | todos |

### Comprobar (sección 4.2)

| Check | Esperado |
|-------|----------|
| Ningún integrante reporta no haber recibido Telegram | sí |
| Streamlit Console refresca en ≤ 2s tras cada acción | sí |
| Llamada Twilio entra a celular acordado | sí |
| Audit log final tiene los 3 escenarios UC-04 distinguibles | sí |
| Total ≤ 13 minutos | sí |

---

## 4.3 Edge cases y contingencias

### Tabla de fallos previstos y respuesta

| Fallo | Probabilidad | Respuesta inmediata |
|-------|:------------:|---------------------|
| WiFi del salón bloquea api.openai.com | Alta | Cambiar `LLM_BACKEND=llama_local` y reiniciar el LLM Triage (P2) |
| Telegram API rate limit (>30 msgs/s) | Baja | No es escenario probable — solo demos manuales. Si pasa, Discord aún funciona. |
| Twilio trial sin saldo | Media | Verificar saldo T-24h. Si <$3, top-up con $5 más. |
| Wazuh manager no arranca | Media | Tu lab espejo. Switch con `export WAZUH_HOST=p1-espejo.local` y reiniciar consumer. |
| Postgres lleno (>90%) | Baja | `make audit-vacuum` (script que limpia incidents > 24h en demo) |
| Crash del SOAR consumer mid-demo | Media | Script `make soar-restart` (systemd-like, reinicia en < 5s sin perder el offset del stream gracias al group) |
| Streamlit no actualiza | Media | Refresh manual F5 — los datos están en Redis, la UI sólo lee |
| Llamada Twilio se va a buzón de voz | Alta | Por diseño: si nadie levanta, decisión cae a `no_quorum_timeout` automáticamente |

### Plan de fallback nuclear

Si **3 fallos consecutivos** durante la primera parte del demo:

1. Detener intentos en vivo.
2. Mostrar video pre-grabado de rehearsal #2 (graba con OBS antes).
3. P1 narra sobre el video.
4. Q&A se hace al final con sistema arriba o no.

**Tener el video listo es no-negociable.** Grábalo en rehearsal #2 con OBS.

---

## 4.4 Checklist pre-demo (T-2 horas)

| # | Check | OK |
|---|-------|----|
| 1 | Lab primario (P4) — `vagrant status` todos UP | ☐ |
| 2 | Lab espejo (P1) — `vagrant status` todos UP | ☐ |
| 3 | Telegram bot envía mensaje de prueba a los 4 celulares | ☐ |
| 4 | Discord webhook envía mensaje al canal | ☐ |
| 5 | Twilio: credit > $3 USD | ☐ |
| 6 | OpenAI: usage budget no excedido | ☐ |
| 7 | Postgres responde a `psql -c "\dt"` | ☐ |
| 8 | OpenSearch dashboard carga en http://localhost:5601 | ☐ |
| 9 | Streamlit Console abre en http://localhost:8501 | ☐ |
| 10 | Video respaldo grabado y accesible offline | ☐ |
| 11 | Pendrive USB con repo clonado (para caso laptop totalmente muerta) | ☐ |
| 12 | Cargadores de las 2 laptops (P1 + P4) | ☐ |

---

## ✅ Checklist Fase 4 — listo para el demo

| # | Check | OK |
|---|-------|----|
| 1 | Rehearsal #1 cerrado sin issues abiertos | ☐ |
| 2 | Rehearsal #2 cerrado con los 4 integrantes presentes | ☐ |
| 3 | Video respaldo grabado | ☐ |
| 4 | Checklist 4.4 corrido T-2 horas | ☐ |
| 5 | Lessons learned actualizado en `docs/LESSONS_LEARNED.md` | ☐ |

---

# Apéndice A — Troubleshooting común

### A.1 Prereqs no instalados / versión equivocada

| OS | Comando |
|----|---------|
| Ubuntu/Debian | `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt update && sudo apt install python3.11 python3.11-venv python3.11-dev redis-tools jq` |
| macOS (brew) | `brew install python@3.11 redis jq` |
| Windows | Usa WSL2 Ubuntu — mismas instrucciones que Ubuntu |

### A.2 `argos_contracts` no importa después de `pip install -e`

Síntoma: `ModuleNotFoundError: No module named 'argos_contracts'`.
Causa común: instalaste sin venv activo o desde la carpeta equivocada.

```bash
which python    # debe terminar en .venv/bin/python
cd ~/code/argos
pip install -e ./argos_contracts --force-reinstall
python -c "import argos_contracts; print(argos_contracts.__file__)"
# Debe apuntar a tu repo, no a site-packages global.
```

### A.3 Telegram devuelve `"chat not found"`

Causa: nunca enviaste un mensaje al bot desde tu cuenta, entonces `getUpdates`
no devuelve tu chat_id real.

Fix: abre el bot en Telegram (link `t.me/<usuario_bot>`), envía `/start`,
luego reconsulta `getUpdates`.

### A.4 Discord webhook 401

Causa: webhook URL mal copiada (te falta el token al final) o el canal fue
eliminado.

Fix: recrear el webhook (Settings → Integrations → Webhooks → New).

### A.5 Twilio error 21219 — `Number not verified`

Causa: trial Twilio requiere que `TO` esté en la lista de "verified numbers".

Fix: https://console.twilio.com/us1/develop/phone-numbers/manage/verified

### A.6 Redis `CONNECTION REFUSED`

Causa: Redis no está corriendo en el host esperado.

```bash
# ¿corre algún Redis local?
ss -tlnp | grep 6379
# Si no aparece nada:
docker run -d -p 6379:6379 --name argos-redis redis:7
redis-cli ping
# OUTPUT ESPERADO: PONG
```

### A.7 `BUSYGROUP Consumer Group name already exists`

No es error real: significa que el grupo ya estaba creado de una corrida previa.
El código ignora este caso. Si sigue molestando:

```bash
redis-cli XGROUP DESTROY events:normalized soar-router
redis-cli XGROUP CREATE events:normalized soar-router 0 MKSTREAM
```

### A.8 Approval API `RuntimeError: Event loop is closed`

Causa: alguna fixture de test cerró el loop antes que el cliente Redis terminara.

Fix: en `conftest.py`, usa `asyncio_mode = "auto"` en `pyproject.toml`
y `pytest-asyncio==0.23.x`. Verificar `pip show pytest-asyncio`.

### A.9 Tests `xfail` que pasan

Si ves `XPASSED` en algún test marcado como `@pytest.mark.xfail`, **bórrale**
el mark. Significa que el bug fue resuelto y el test ya pasa.

### A.10 Latencias notif > 2s (lento sospechoso)

```bash
# Mide round-trip a la API externa:
time curl -s https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe > /dev/null
# Esperado < 800ms en una conexión decente.
# Si >2s: DNS lento, o tu hotspot de celular tiene mala latencia → cambiar red.
```

---

# Apéndice B — Comandos de emergencia (durante demo)

```bash
# Reiniciar todo el plano de control SOAR sin tocar el lab
make soar-restart
# (alias de: pkill -f 'uvicorn soar.approval_api' ; pkill -f 'soar.decision_engine.consumer' ;
#           sleep 1 ; nohup ... > logs/soar.log 2>&1 & )

# Switch a Llama local si OpenAI cae
export LLM_BACKEND=llama_local && make llm-restart

# Switch al lab espejo
export WAZUH_HOST=p1-espejo.local && make soar-restart

# Limpiar incidents del demo previo (para empezar limpio)
redis-cli --scan --pattern 'incident:*' | xargs -r redis-cli DEL

# Resetear consumer group offset (re-procesa últimos eventos)
redis-cli XGROUP SETID events:normalized soar-router 0

# Forzar block manual de un incident colgado
redis-cli SET 'incident:inc-XXX:override' 'force_block'
# (handler en `consumer.py` chequea este flag al cargar incident)
```

---

# Apéndice C — Referencias cruzadas

| Cuando estés en... | Lee |
|--------------------|-----|
| `tier_router.py` | SAD §6.2 (Decision Engine), ADR-0002 (tier matrix) |
| `notifications/` | ADR-0007 v2 (multi-channel + escalación), SAD §8.3 |
| `approval_api/` | ADR-0006 (split-brain + conservative-wins), USE_CASES UC-04 |
| `consumer.py` | `docs/contracts/CONTRACTS_SPECIFICATION.md` §4 (Redis streams) |
| `audit/` | THREAT_MODEL §5 (trazabilidad), SAD §11 (audit) |
| Contingencias del demo | `docs/team/sprint-week-1-overview.md` §1 + THREAT_MODEL §7 |

**Cuando edites un ADR o el SAD durante la semana**: NO. Esta semana está congelado (regla de oro #1 del overview). Cualquier cambio arquitectónico abre ADR nuevo después del demo.

---

## Change log de este manual

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 2.0 | 2026-05-24 | Reorganización completa: estructura day-by-day → estructura por feature (Fase 1-4). Agregados expected outputs literales después de cada comando, checklists al final de cada sección, troubleshooting con 10 entradas, comandos de emergencia para demo. | P1 |
