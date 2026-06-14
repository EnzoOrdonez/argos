"""SimulatedExecutor: ejecuta acciones sin tocar VMs (ADR-0012 §2.1.2).

Usos: tests sin lab, ensayos del demo y fallback del video-backup. Mantiene la
paridad con el executor real (ADR-0012 §7.5): mismo shape de resultado, misma
idempotencia por (type, target), y fallos inyectables para ensayar los caminos
`failed`/`partial` que en el mundo real produce el API de Wazuh.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Collection

from argos_contracts.enums import ActionType
from argos_contracts.incident import ProposedAction

from soar.playbooks.base import ExecutionResult

logger = logging.getLogger(__name__)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


class SimulatedExecutor:
    """Loguea lo que ejecutaría y registra el estado en memoria.

    `fail_on` / `partial_on` / `fail_revert_on`: tipos de acción cuyos run/revert
    devuelven `failed`/`partial`, para tests de fail-soft. Nunca lanza.
    """

    def __init__(
        self,
        *,
        fail_on: Collection[ActionType] = (),
        partial_on: Collection[ActionType] = (),
        fail_revert_on: Collection[ActionType] = (),
    ) -> None:
        self._fail_on = frozenset(fail_on)
        self._partial_on = frozenset(partial_on)
        self._fail_revert_on = frozenset(fail_revert_on)
        # Registro de acciones aplicadas, por (type, target) (ADR-0012 §7.4).
        self.applied: dict[tuple[ActionType, str], ProposedAction] = {}
        # Historial (op, action_id, status) para asserts y para el audit del demo.
        self.history: list[tuple[str, str, str]] = []

    def _record(self, op: str, result: ExecutionResult) -> ExecutionResult:
        self.history.append((op, result.action_id, result.status))
        logger.info("[simulated] %s %s -> %s", op, result.action_id, result.status)
        return result

    def run(self, action: ProposedAction) -> ExecutionResult:
        started = time.monotonic()
        if action.type in self._fail_on:
            return self._record(
                "run",
                ExecutionResult(
                    action_id=action.id,
                    status="failed",
                    detail=f"simulated failure for {action.type.value}",
                    latency_ms=_elapsed_ms(started),
                ),
            )
        if action.type in self._partial_on:
            return self._record(
                "run",
                ExecutionResult(
                    action_id=action.id,
                    status="partial",
                    detail=f"simulated partial result for {action.type.value}",
                    latency_ms=_elapsed_ms(started),
                ),
            )
        key = (action.type, action.target)
        if key in self.applied:
            return self._record(
                "run",
                ExecutionResult(
                    action_id=action.id,
                    status="success",
                    detail=f"no-op: {action.type.value} ya aplicada en {action.target}",
                    latency_ms=_elapsed_ms(started),
                ),
            )
        self.applied[key] = action
        return self._record(
            "run",
            ExecutionResult(
                action_id=action.id,
                status="success",
                detail=f"simulated {action.type.value} on {action.target}",
                latency_ms=_elapsed_ms(started),
            ),
        )

    def revert(self, action: ProposedAction) -> ExecutionResult:
        started = time.monotonic()
        if action.type in self._fail_revert_on:
            return self._record(
                "revert",
                ExecutionResult(
                    action_id=action.id,
                    status="failed",
                    detail=f"simulated revert failure for {action.type.value}",
                    latency_ms=_elapsed_ms(started),
                ),
            )
        if action.type == ActionType.DISK_SNAPSHOT:
            # El snapshot no se "des-toma": revert documentado como no-op (§7.6).
            return self._record(
                "revert",
                ExecutionResult(
                    action_id=action.id,
                    status="success",
                    detail="no-op: snapshot revert no aplica",
                    latency_ms=_elapsed_ms(started),
                ),
            )
        removed = self.applied.pop((action.type, action.target), None)
        detail = (
            f"simulated revert of {action.type.value} on {action.target}"
            if removed is not None
            else f"no-op: {action.type.value} no estaba aplicada en {action.target}"
        )
        return self._record(
            "revert",
            ExecutionResult(
                action_id=action.id,
                status="success",
                detail=detail,
                latency_ms=_elapsed_ms(started),
            ),
        )
