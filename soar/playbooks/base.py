"""Interfaz de ejecución de respuestas (ADR-0012 §2.1/§2.5).

El SOAR nunca actúa directo sobre una VM: construye una `ProposedAction`
(contrato v1.1.0) y se la entrega a un `ResponseExecutor`. Dos implementaciones:
`WazuhActiveResponseExecutor` (real, el agente ejecuta vía active-response) y
`SimulatedExecutor` (demo-safe, sin tocar VMs).

`ExecutionResult` es un dataclass local a `soar/`, NO contrato cross-team.
Su `status` usa los mismos valores que `ExecutionStatus` del contrato
(`success|failed|partial`) para que el orquestador lo copie directo a
`FinalDecision.execution_status` (ADR-0012 §7.1).

Invariantes que los executors deben cumplir (ADR-0012 §2.4 + §7):
- Idempotencia: re-ejecutar una acción ya aplicada es no-op success.
- Fail-soft: un fallo se reporta en el resultado, nunca como excepción
  que tumbe al orquestador.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from argos_contracts.incident import ProposedAction

ResultStatus = Literal["success", "failed", "partial"]


@dataclass(frozen=True)
class ExecutionResult:
    """Resultado de ejecutar (o revertir) una `ProposedAction`."""

    action_id: str
    status: ResultStatus
    detail: str = ""
    latency_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "success"


class ResponseExecutor(Protocol):
    """Quien materializa una `ProposedAction` sobre el entorno (ADR-0012 §2.5)."""

    def run(self, action: ProposedAction) -> ExecutionResult: ...

    def revert(self, action: ProposedAction) -> ExecutionResult: ...
