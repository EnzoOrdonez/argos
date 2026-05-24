# ADR-0001: LLM vendor-agnostic via LLMClient interface

**Estado:** Aceptado
**Versión:** 2.0 (proveedor primario reasignado por soberanía de datos)
**Fecha:** Semana 1 (v1) · 2026-05-23 (v2)
**Autores:** P1 (Enzo Ordoñez Flores)
**Revisores:** Equipo completo

---

## Contexto

La Capa 4 del sistema requiere un Large Language Model para enriquecer alertas con análisis estructurado (técnica MITRE, severidad, runbook, acción recomendada). Las opciones consideradas:

1. **Claude (Anthropic, USA)** — alta calidad para razonamiento estructurado y seguridad; pricing premium (Sonnet ~$3 / $15 per 1M; Haiku ~$0.80 / $4).
2. **GPT-4o / GPT-4o-mini (OpenAI, USA)** — calidad alta, GPT-4o-mini a ~$0.15 / $0.60 per 1M es comparable a DeepSeek en costo y supera a DeepSeek en rankings de razonamiento orientado a seguridad (HELM, LMSys arena).
3. **DeepSeek-V3 (Hangzhou, China)** — buen costo/rendimiento (~$0.14 / $0.28 per 1M) pero hosted bajo jurisdicción china.
4. **Qwen2.5-72B-Instruct (Alibaba, Hangzhou, China)** — comparable a DeepSeek en costo y jurisdicción.
5. **Llama 3.1 8B local (vía Ollama)** — gratuito, corre en hardware modesto (~8 GB RAM), zero-egress.
6. **Mistral Large 2 (Mistral, Francia/EU)** — calidad alta, pricing medio, jurisdicción EU.

## Decisión (v2)

**Implementar la interfaz abstracta `LLMClient` con dos backends activos:**

- **Primary:** **GPT-4o-mini** (OpenAI) vía API.
- **Fallback:** **Llama 3.1 8B local** vía Ollama, corriendo en la misma máquina que el SOAR.

**El swap entre backends se controla por variable de entorno** `LLM_BACKEND={openai|llama_local}`, sin cambios de código en el resto del sistema.

### Cambio v1 → v2

La v1 elegía DeepSeek-V3 (primario) + Qwen2.5-72B (fallback) basándose puramente en costo/beneficio. La v2 corrige esta decisión por dos razones técnicas defendibles:

**1. Soberanía de datos en un proyecto de ciberseguridad.** ARGOS envía a su LLM telemetría que contiene nombres de host internos, command lines, paths de filesystem, IPs internas, y patrones de actividad que pueden ser usados para perfilar la infraestructura defendida. DeepSeek y Qwen están hosted bajo PRC Data Security Law y la Cybersecurity Law china, que obligan a los proveedores a entregar datos a autoridades sin opción de notificar al usuario. Para un proyecto cuya tesis explícita es "defendemos un activo crítico" (PostgreSQL en producción), enviar esa telemetría a un proveedor sujeto a esa jurisdicción es una contradicción que un evaluador con experiencia en cumplimiento (NIST CSF, ISO 27001, SOC 2) detectaría. Los proveedores estadounidenses también están sujetos a requests gubernamentales (NSA, FBI), pero el marco legal es más transparente, hay órdenes judiciales públicas, y el sandbox de seguridad de datos es auditable.

**2. Calidad para razonamiento de ciberseguridad.** DeepSeek-V3 y Qwen son modelos generales optimizados a costo. Para razonamiento estructurado de seguridad específicamente (identificar técnicas MITRE, escribir runbooks NIST coherentes, validar IoCs), GPT-4o-mini y Claude Haiku consistentemente puntúan más alto en benchmarks públicos (SecEval, HELM cybersecurity subset). El costo por millón de tokens de GPT-4o-mini (~$0.15 input / $0.60 output) es prácticamente equivalente al de DeepSeek a este volumen.

**3. Fallback con propiedad demostrable.** Llama 3.1 8B local sustituye a Qwen como fallback porque ofrece algo que ningún API externo puede: **inferencia zero-egress**. Si el cliente exige air-gap, si el primario se cae, o si la conexión a internet del lab falla en demo, ARGOS sigue produciendo análisis LLM sin que un byte salga de la máquina. Eso es un argumento de defensa más fuerte que "tenemos dos APIs externas redundantes". Llama 3.1 8B corre en cualquier laptop moderno (8 GB RAM) y aunque su calidad es menor que GPT-4o-mini, es suficiente para producir un análisis estructurado válido en el formato Pydantic esperado.

## Alternativas consideradas

### Claude (Sonnet o Haiku)

- ✅ **Calidad:** la mejor para razonamiento estructurado de seguridad.
- ✅ **Anthropic safety posture:** alineada con el espíritu del proyecto.
- ⚠️ **Costo:** Sonnet es ~20× más caro que GPT-4o-mini; Haiku es ~5× más caro.
- ⚠️ **Disponibilidad:** API estable, sin objeciones operacionales.
- **Veredicto:** descartado como primario por costo. Queda como opción "upgrade trivial" si se quiere calidad máxima en evaluación final (cambio de 1 línea + nueva clase).

### DeepSeek-V3 / Qwen2.5-72B (selección v1)

- ❌ **Soberanía de datos:** PRC Data Security Law + Cybersecurity Law obligan a los proveedores a compartir datos con autoridades chinas sin notificación al usuario. Contradicción directa con el caso de uso de ARGOS.
- ❌ **Calidad relativa:** menor que GPT-4o-mini en benchmarks de razonamiento de seguridad.
- ✅ **Costo:** competitivo, pero ya no es ventaja decisiva vs GPT-4o-mini.
- **Veredicto:** descartados en v2.

### Mistral Large 2 (EU)

- ✅ **Jurisdicción EU:** GDPR-friendly, sin obligación de compartir con gobiernos no-UE.
- ⚠️ **Costo:** similar a GPT-4o, sin ventaja clara.
- ⚠️ **Disponibilidad:** API estable pero menos documentada.
- **Veredicto:** descartado por ser opción intermedia sin ventaja clara; GPT-4o-mini cubre el caso US-based con mejor pricing.

### Solo GPT-4o-mini (sin fallback)

- ❌ **Single point of failure:** si OpenAI tiene downtime durante el demo, el sistema cae.
- ❌ **Pierde propiedad de "air-gap demostrable"** que da Llama local.
- **Veredicto:** descartado.

### Llama 3.1 8B como primario único

- ✅ **Soberanía total:** cero datos salen del lab.
- ✅ **Costo cero marginal.**
- ⚠️ **Calidad menor que GPT-4o-mini** en razonamiento estructurado.
- ⚠️ **Requiere hardware mínimo** corriendo permanentemente.
- **Veredicto:** descartado como primario, mantenido como fallback porque su propiedad de zero-egress es valiosa.

## Consecuencias

### Positivas

- **Soberanía de datos defendible** ante evaluador con criterio de cumplimiento.
- **Demo más impactante:** "si el primario falla, el sistema sigue funcionando con inferencia local sin salir del lab" es un mensaje fuerte para una defensa de ciberseguridad.
- **Vendor portability:** swap a Claude API es cambio de 1 línea + nueva clase. Demuestra arquitectura profesional.
- **Costo controlado:** GPT-4o-mini a precio comparable a DeepSeek; Llama local sin costo marginal.
- **Resiliencia genuina:** dos backends sobre infraestructura completamente distinta (cloud US vs hardware local).

### Negativas

- **Mayor complejidad de setup del fallback:** Ollama + modelo descargado (~5 GB) en la máquina de demo.
- **Calidad del fallback menor:** si el primario falla, los análisis enriquecidos serán menos detallados.
- **Mantenimiento de prompts:** templates deben ser robustos a la diferencia de capacidad entre los dos backends.

## Plan de implementación

```python
# llm_triage/llm_client/base.py
from abc import ABC, abstractmethod
from argos_contracts.triage import TriageResponse

class LLMClient(ABC):
    @abstractmethod
    async def analyze(self, alert_context: dict) -> TriageResponse:
        pass

# llm_triage/llm_client/openai_client.py
class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        ...

# llm_triage/llm_client/llama_local.py
class LlamaLocalClient(LLMClient):
    """Inferencia local vía Ollama. Modelo descargado a ~/.ollama/models/.
    Cero egress de datos: la telemetría nunca sale de la máquina."""
    def __init__(self, model: str = "llama3.1:8b", base_url: str = "http://localhost:11434"):
        ...

# llm_triage/llm_client/factory.py
def get_llm_client() -> LLMClient:
    backend = os.getenv("LLM_BACKEND", "openai")
    if backend == "openai":
        return OpenAIClient(api_key=os.getenv("OPENAI_API_KEY"))
    elif backend == "llama_local":
        return LlamaLocalClient()
    raise ValueError(f"Unknown LLM_BACKEND: {backend}")
```

## Invariante R-2: el LLM nunca acciona

El campo `accion_recomendada` del `TriageResponse` es **texto descriptivo en lenguaje natural** dirigido al analista humano. Ejemplos válidos: *"Isolate host, capture memory, preserve disk snapshot before remediation"*, *"Monitor process tree for 30 min before triaging"*, *"Escalate to L2 — pattern matches APT29 dwell-time signature"*.

El SOAR Decision Engine **nunca** parsea este campo para disparar acciones. La acción que el sistema ejecuta se decide enteramente desde las Capas 1-3 + el tier classifier, conforme a R-2 (`THREAT_MODEL.md` §6). El LLM puede recomendar *"isolate immediately"* en `accion_recomendada` pero esa recomendación solo viaja al analista (vía Telegram, Discord o UI). Si el analista decide actuar sobre la recomendación, lo hace **manualmente** vía el botón de aprobación correspondiente.

Esto preserva el invariante de seguridad: una alucinación del LLM (técnica MITRE inventada, severidad inflada, runbook inaplicable) **no puede** disparar una contención. Solo puede degradar la calidad del análisis que ve el humano.

## Métricas de éxito

- Ambos backends pasan el mismo test suite de structured output validation.
- Switch entre backends en demo en vivo funciona sin reinicio del servicio.
- Failover de OpenAI → Llama local demostrable en menos de 30 segundos.
- Costo total del proyecto en API: <$20 USD (con GPT-4o-mini el budget es conservador).

## Política de manejo de datos sensibles

Cualquier payload que viaja al backend `openai` pasa por la capa de sanitización descrita en `docs/data-handling.md`: redacción de patrones de credenciales, normalización de IPs internas, eliminación de usernames identificables. Esta sanitización es **obligatoria** para el backend cloud y **opcional** para el backend local (Llama corriendo en el mismo lab; los datos nunca salen).

## Revisión

A re-evaluar en Gate 2. Si calidad de output de Llama local no es aceptable, considerar:

- Llama 3.1 70B local (requiere ~40 GB RAM, fuera de hardware típico del equipo).
- Mistral 7B local como segunda alternativa.
- Claude Haiku como upgrade del primario si presupuesto lo permite.

## Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 | Semana 1 | Decisión original: DeepSeek-V3 primario + Qwen2.5-72B fallback. Optimizado puramente a costo. | P1 |
| 2.0 | 2026-05-23 | Re-evaluación por soberanía de datos: en un proyecto de ciberseguridad enviar telemetría a proveedores chinos contradice el caso de uso. Primario reasignado a GPT-4o-mini (US-based, costo equivalente, mejor en benchmarks de seguridad). Fallback reasignado a Llama 3.1 8B local (zero-egress, propiedad demostrable de air-gap). | P1 |
