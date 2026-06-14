"""Playbooks de respuesta del SOAR (ADR-0012)."""

from soar.playbooks.base import ExecutionResult, ResponseExecutor
from soar.playbooks.builders import (
    build_isolation,
    build_kill,
    build_snapshot,
    build_throttle,
)
from soar.playbooks.simulated import SimulatedExecutor
from soar.playbooks.wazuh import WazuhActiveResponseExecutor

__all__ = [
    "ExecutionResult",
    "ResponseExecutor",
    "SimulatedExecutor",
    "WazuhActiveResponseExecutor",
    "build_isolation",
    "build_kill",
    "build_snapshot",
    "build_throttle",
]
