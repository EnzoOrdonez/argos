"""Fail-closed response-executor selection (ADR-0017).

The factory lives in ``soar`` so every operational entrypoint shares the same
environment policy. Explicit non-live demos may instantiate ``SimulatedExecutor``
directly without using this factory.
"""

from __future__ import annotations

import os

from soar.playbooks.base import ResponseExecutor

_ENVIRONMENTS = {"development", "test", "staging", "production"}
_EXECUTORS = {"simulated", "wazuh"}
_LIVE_ENVIRONMENTS = {"staging", "production"}
_WAZUH_REQUIRED = (
    "WAZUH_API_URL",
    "WAZUH_API_USER",
    "WAZUH_API_PASSWORD",
    "WAZUH_AGENT_MAP",
)


class ExecutorConfigurationError(RuntimeError):
    """The response executor cannot be selected safely from runtime configuration."""


def make_executor() -> ResponseExecutor:
    """Build the explicitly selected executor or reject unsafe configuration."""
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    if not environment:
        raise ExecutorConfigurationError("ENVIRONMENT must be configured explicitly")
    if environment not in _ENVIRONMENTS:
        raise ExecutorConfigurationError("unsupported ENVIRONMENT value")

    mode = os.environ.get("ARGOS_EXECUTOR", "").strip().lower()
    if not mode:
        raise ExecutorConfigurationError("ARGOS_EXECUTOR must be configured explicitly")
    if mode not in _EXECUTORS:
        raise ExecutorConfigurationError("unsupported ARGOS_EXECUTOR value")
    if mode == "simulated" and environment in _LIVE_ENVIRONMENTS:
        raise ExecutorConfigurationError(
            f"ARGOS_EXECUTOR=simulated is not allowed in ENVIRONMENT={environment}"
        )

    if mode == "simulated":
        from soar.playbooks.simulated import SimulatedExecutor

        return SimulatedExecutor()

    missing = [name for name in _WAZUH_REQUIRED if not os.environ.get(name, "").strip()]
    if missing:
        raise ExecutorConfigurationError(
            "missing required Wazuh configuration: " + ", ".join(missing)
        )
    try:
        from soar.playbooks.wazuh import WazuhActiveResponseExecutor

        return WazuhActiveResponseExecutor()
    except Exception:
        raise ExecutorConfigurationError("Wazuh executor initialization failed") from None
