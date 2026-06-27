"""Interfaz vendor-agnóstica del cliente LLM (ADR-0001 §interfaz).

Cada backend (OpenAI-compatible / Ollama) implementa `analyze`: recibe un
`AlertContext` y devuelve un `TriageResponse` validado contra el contrato. El
backend NUNCA está en la ruta de contención (invariante R-2): el SOAR trata su
salida como texto para el analista humano y degrada a None ante cualquier fallo
(lo absorbe `soar/decision_engine/triage_hook.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from argos_contracts.triage import AlertContext, TriageResponse


class LLMClient(ABC):
    """Backend de triage. `backend_id` identifica el modelo/proveedor para el audit."""

    backend_id: str = "abstract"

    @abstractmethod
    async def analyze(self, context: AlertContext) -> TriageResponse:
        """Analiza el contexto y devuelve un `TriageResponse` válido.

        Lanza si no puede producir uno válido (el servicio `/triage` lo traduce a
        502 y el hook del SOAR a None). NUNCA debe colgar la contención.
        """
        raise NotImplementedError
