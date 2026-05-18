# ADR-0001: LLM vendor-agnostic via LLMClient interface

**Estado:** Aceptado
**Fecha:** Semana 1
**Autores:** P1 (Enzo)
**Revisores:** Equipo completo

---

## Contexto

La Capa 4 del sistema requiere un Large Language Model para enriquecer alertas con análisis estructurado (técnica MITRE, severidad, runbook, acción recomendada). Las opciones consideradas:

1. **Claude API (Anthropic)** — alta calidad, pero costo elevado para volumen del proyecto.
2. **GPT-4 / GPT-4o (OpenAI)** — calidad alta, costo medio-alto.
3. **DeepSeek-V3** — calidad comparable a GPT-4o en razonamiento estructurado, ~1/30 del costo.
4. **Qwen2.5-72B-Instruct (Alibaba)** — comparable a DeepSeek en costo, mayor context window.
5. **Llama 3.1 8B / Mistral 7B local (vía Ollama)** — gratuito pero requiere hardware (32GB RAM + GPU recomendado), calidad menor.

## Decisión

**Implementar una interfaz abstracta `LLMClient` con dos backends activos:**

- **Primary:** DeepSeek-V3 vía API OpenAI-compatible.
- **Fallback:** Qwen2.5-72B vía DashScope API.

**El swap entre backends se controla por variable de entorno** `LLM_BACKEND={deepseek|qwen}`, sin cambios de código en el resto del sistema.

## Alternativas consideradas

### Claude API

- ❌ **Costo:** órdenes de magnitud mayor para nuestro volumen (~10-50K alertas en evaluación).
- ✅ **Calidad:** la mejor para razonamiento.
- **Veredicto:** descartado. Si en evaluación encontramos que DeepSeek/Qwen no son suficientes, swap es trivial (una variable).

### Llama local

- ❌ **Hardware:** ningún integrante del equipo tiene 32GB+ RAM + GPU para inferencia fluida.
- ❌ **Calidad:** menor que cualquier API actual.
- ✅ **Costo cero, soberanía total.**
- **Veredicto:** descartado para v1, queda como opción futura si se quiere mostrar "deployment 100% offline".

### Solo DeepSeek (sin fallback)

- ❌ **Single point of failure:** si DeepSeek tiene downtime durante el demo, el sistema cae.
- ❌ **Vendor lock-in implícito.**
- **Veredicto:** descartado.

## Consecuencias

### Positivas

- **Vendor portability:** swap a Claude API o GPT-4 es cambio de 1 línea + nueva clase. Demuestra arquitectura profesional en defensa.
- **Costo-beneficio:** DeepSeek-V3 a ~$0.14/$0.28 per 1M tokens cubre todo el proyecto por <$10 USD totales estimados.
- **Resiliencia:** fallback automático ante downtime del primario.
- **Argumento académico defensible:** "evaluamos costo-beneficio, sistema es vendor-agnostic, swappeable a cualquier OpenAI-compatible API".

### Negativas

- **Mayor complejidad inicial:** abstracción + 2 implementaciones vs 1.
- **Mantenimiento:** tests deben correr contra ambos backends.
- **Posible inconsistencia:** prompts pueden necesitar tuning ligero por backend (mitigable con templates).

### Riesgo: percepción de DeepSeek

DeepSeek es empresa china. Posible objeción del jurado: "¿por qué proveedor chino?". **Respuesta preparada:** evaluación costo-beneficio puramente técnica; sistema es vendor-agnostic; mismo razonamiento estructurado a fracción del costo; alternativas occidentales (Claude, GPT) requieren cambio de 1 línea.

## Plan de implementación

```python
# llm_triage/llm_client/base.py
from abc import ABC, abstractmethod
from pydantic import BaseModel

class TriageResponse(BaseModel):
    tecnica_mitre: str
    confianza: float
    severidad: str
    runbook_aplicable: str
    accion_recomendada: str  # DESCRIPTIVE TEXT ONLY — never parsed by SOAR. Shown to analyst as-is.
    indicadores_correlacionar: list[str]

class LLMClient(ABC):
    @abstractmethod
    async def analyze(self, alert_context: dict) -> TriageResponse:
        pass

# llm_triage/llm_client/deepseek.py
class DeepSeekClient(LLMClient):
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        ...

# llm_triage/llm_client/qwen.py
class QwenClient(LLMClient):
    def __init__(self, api_key: str, model: str = "qwen2.5-72b-instruct"):
        ...

# llm_triage/llm_client/factory.py
def get_llm_client() -> LLMClient:
    backend = os.getenv("LLM_BACKEND", "deepseek")
    if backend == "deepseek":
        return DeepSeekClient(api_key=os.getenv("DEEPSEEK_API_KEY"))
    elif backend == "qwen":
        return QwenClient(api_key=os.getenv("QWEN_API_KEY"))
    raise ValueError(f"Unknown LLM_BACKEND: {backend}")
```

## Invariante R-2: el LLM nunca acciona

El campo `accion_recomendada` del `TriageResponse` es **texto descriptivo en lenguaje natural** dirigido al analista humano. Ejemplos válidos: *"Isolate host, capture memory, preserve disk snapshot before remediation"*, *"Monitor process tree for 30 min before triaging"*, *"Escalate to L2 — pattern matches APT29 dwell-time signature"*.

El SOAR Decision Engine **nunca** parsea este campo para disparar acciones. La acción que el sistema ejecuta se decide enteramente desde las Capas 1-3 + el tier classifier, conforme a R-2 (`THREAT_MODEL.md` §6). El LLM puede recomendar *"isolate immediately"* en `accion_recomendada` pero esa recomendación solo viaja al analista (vía email post-facto, Telegram, Slack o UI). Si el analista decide actuar sobre la recomendación, lo hace **manualmente** vía el botón de aprobación correspondiente.

Esto preserva el invariante de seguridad: una alucinación del LLM (técnica MITRE inventada, severidad inflada, runbook inaplicable) **no puede** disparar una contención. Solo puede degradar la calidad del análisis que ve el humano.

## Métricas de éxito

- Ambos backends pasan el mismo test suite de structured output validation.
- Switch entre backends en demo en vivo funciona sin reinicio del servicio.
- Costo total del proyecto en LLM API: <$20 USD.

## Revisión

A re-evaluar en Gate 2 (semana 7). Si calidad de output no es aceptable con ambos, considerar swap a Claude API solo para evaluación final (costo controlado).
