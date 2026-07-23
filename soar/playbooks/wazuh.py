"""WazuhActiveResponseExecutor: el manager ordena, el agente ejecuta (ADR-0012 §2.1.1).

Patrón XDR estándar: el SOAR llama al API del Wazuh manager
(PUT /active-response, documentación oficial de Wazuh, capítulo Active
Response) y el agente corre el comando en la VM víctima. El SOAR nunca
shell-ea directo a una víctima (alternativa SSH rechazada en ADR-0012 §5).

Los nombres de comando AR son dominio de P3 (ADR-0012 §3): acá viven como
defaults configurables. Sin el lab de P4, este executor se valida con respx;
la validación real queda para integración.

Los rechazos comprobables son `failed`. Una aceptación del manager, timeout,
5xx o pérdida de respuesta tras iniciar el despacho es `partial`: sin recibo
del endpoint el journal durable debe conservar el estado `ambiguous`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import httpx

from argos_contracts.enums import ActionType
from argos_contracts.incident import ProposedAction
from soar.execution.identity import ExecutionIdentity
from soar.playbooks.base import ExecutionResult

logger = logging.getLogger(__name__)


class WazuhExecutionContractError(RuntimeError):
    """The requested effect cannot be bound to a complete execution identity."""


class _AgentPreflightError(RuntimeError):
    """Agent cannot safely receive an action; message contains no secrets."""


_AGENT_ID = re.compile(r"^[0-9]{3,}$")


def _required_setting(explicit: str | None, environment_name: str) -> str:
    value = explicit if explicit is not None else os.environ.get(environment_name, "")
    if not value.strip():
        raise WazuhExecutionContractError("incomplete Wazuh configuration")
    return value


def _load_agent_mapping(raw: str) -> dict[str, str]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise WazuhExecutionContractError("invalid Wazuh agent mapping") from None
    if not isinstance(value, dict) or not value:
        raise WazuhExecutionContractError("invalid Wazuh agent mapping")
    mapping = {str(asset): str(agent) for asset, agent in value.items()}
    if any(not asset.strip() or not _AGENT_ID.fullmatch(agent) for asset, agent in mapping.items()):
        raise WazuhExecutionContractError("invalid Wazuh agent mapping")
    if len(set(mapping.values())) != len(mapping):
        raise WazuhExecutionContractError("Wazuh agent mapping must be one-to-one")
    return mapping


def _require_execution(
    action: ProposedAction,
    execution: ExecutionIdentity | None,
    operation: str,
) -> ExecutionIdentity:
    if execution is None:
        raise WazuhExecutionContractError("execution identity is required")
    if execution.action_id != action.id or execution.operation != operation:
        raise WazuhExecutionContractError("execution identity does not match action")
    return execution

# Comandos active-response por accion (defaults; P3 define los reales en Wazuh).
DEFAULT_RUN_COMMANDS: dict[ActionType, str] = {
    ActionType.PROCESS_THROTTLE: "argos-throttle",
    ActionType.DISK_SNAPSHOT: "argos-snapshot",
    ActionType.HOST_ISOLATION: "argos-isolate",
    ActionType.PROCESS_KILL: "argos-kill",
    ActionType.BLOCK_IP: "argos-block-ip",
}
# Scripts de revert disponibles en el paquete. PR-01B3a no los despacha:
# falta capturar y verificar estado previo del endpoint (gate PR-01B3b).
DEFAULT_REVERT_COMMANDS: dict[ActionType, str] = {
    ActionType.PROCESS_THROTTLE: "argos-unthrottle",
    ActionType.HOST_ISOLATION: "argos-unisolate",
    ActionType.BLOCK_IP: "argos-unblock-ip",
}
_IRREVERSIBLE_ACTIONS = {ActionType.PROCESS_KILL, ActionType.DISK_SNAPSHOT}


def _validate_reversibility(action: ProposedAction) -> None:
    if action.type in _IRREVERSIBLE_ACTIONS and action.reversible:
        raise WazuhExecutionContractError(
            "irreversible action cannot be declared reversible"
        )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


class WazuhActiveResponseExecutor:
    """Ejecuta `ProposedAction` vía active-response del Wazuh manager.

    `action.target` se resuelve mediante un mapping uno-a-uno fail-closed. La
    identidad estable proviene del journal durable; este adapter no afirma ni
    implementa exactly-once para efectos externos.
    """

    def __init__(
        self,
        api_url: str | None = None,
        user: str | None = None,
        password: str | None = None,
        *,
        client: httpx.Client | None = None,
        timeout: float | None = None,
        agent_mapping: dict[str, str] | None = None,
        run_commands: dict[ActionType, str] | None = None,
    ) -> None:
        self._url = _required_setting(api_url, "WAZUH_API_URL").rstrip("/")
        self._user = _required_setting(user, "WAZUH_API_USER")
        self._password = _required_setting(password, "WAZUH_API_PASSWORD")
        verify_ssl = os.environ.get("WAZUH_VERIFY_SSL", "false").lower() == "true"
        try:
            self._timeout = float(
                timeout
                if timeout is not None
                else os.environ.get("WAZUH_API_TIMEOUT_SECONDS", "5")
            )
        except (TypeError, ValueError):
            raise WazuhExecutionContractError("invalid Wazuh API timeout") from None
        if not 0 < self._timeout <= 30:
            raise WazuhExecutionContractError("Wazuh API timeout must be within 30 seconds")
        self._client = client or httpx.Client(verify=verify_ssl)
        raw_mapping = os.environ.get("WAZUH_AGENT_MAP", "")
        self._agent_mapping = _load_agent_mapping(
            json.dumps(agent_mapping) if agent_mapping is not None else raw_mapping
        )
        self._run_commands = run_commands or DEFAULT_RUN_COMMANDS
        self._token: str | None = None

    def _agent_id(self, asset_id: str) -> str:
        try:
            return self._agent_mapping[asset_id]
        except KeyError:
            raise WazuhExecutionContractError(
                "asset has no unique Wazuh agent mapping"
            ) from None

    # -- API plumbing ------------------------------------------------------

    def _authenticate(self) -> str:
        response = self._client.post(
            f"{self._url}/security/user/authenticate",
            auth=(self._user, self._password),
            timeout=self._timeout,
        )
        response.raise_for_status()
        try:
            token = str(response.json()["data"]["token"])
        except (ValueError, KeyError, TypeError):
            raise _AgentPreflightError(
                "Wazuh authentication response is invalid"
            ) from None
        if not token.strip():
            raise _AgentPreflightError("Wazuh authentication response is invalid")
        self._token = token
        return token

    def _put_active_response(
        self,
        agent: str,
        command: str,
        action: ProposedAction,
        execution: ExecutionIdentity | None,
    ) -> httpx.Response:
        token = self._token or self._authenticate()
        argos = dict(action.parameters)
        if execution is not None:
            argos["execution"] = execution.as_payload()
        body: dict[str, Any] = {
            "command": command,
            "arguments": [execution.execution_id if execution else action.id],
            "alert": {"data": {"argos": argos}},
        }
        response = self._client.put(
            f"{self._url}/active-response",
            params={"agents_list": agent},
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self._timeout,
        )
        if response.status_code == 401:
            # Token vencido: re-autenticar una vez y reintentar.
            token = self._authenticate()
            response = self._client.put(
                f"{self._url}/active-response",
                params={"agents_list": agent},
                json=body,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self._timeout,
            )
        return response

    def _preflight_agent(self, agent_id: str) -> None:
        token = self._token or self._authenticate()
        response = self._client.get(
            f"{self._url}/agents",
            params={"agents_list": agent_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self._timeout,
        )
        if response.status_code == 401:
            token = self._authenticate()
            response = self._client.get(
                f"{self._url}/agents",
                params={"agents_list": agent_id},
                headers={"Authorization": f"Bearer {token}"},
                timeout=self._timeout,
            )
        response.raise_for_status()
        try:
            payload = response.json()
            items = payload["data"]["affected_items"]
        except (ValueError, KeyError, TypeError):
            raise _AgentPreflightError("Wazuh agent preflight response is invalid") from None
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise _AgentPreflightError("Wazuh agent preflight response is invalid")
        if len(items) != 1 or str(items[0].get("id")) != agent_id:
            raise _AgentPreflightError("mapped Wazuh agent was not found")
        if str(items[0].get("status", "")).lower() != "active":
            raise _AgentPreflightError("mapped Wazuh agent is not active")

    def _call(
        self,
        agent_id: str,
        command: str,
        action: ProposedAction,
        execution: ExecutionIdentity | None,
    ) -> ExecutionResult:
        started = time.monotonic()
        try:
            self._preflight_agent(agent_id)
        except (_AgentPreflightError, httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "Wazuh agent preflight rejected for action %s (%s)",
                action.id,
                type(exc).__name__,
            )
            detail = (
                str(exc)
                if isinstance(exc, _AgentPreflightError)
                else "Wazuh agent preflight unavailable"
            )
            return ExecutionResult(
                action_id=action.id,
                status="failed",
                detail=detail,
                latency_ms=_elapsed_ms(started),
            )

        try:
            response = self._put_active_response(
                agent_id, command, action, execution
            )
            if 400 <= response.status_code < 500:
                return ExecutionResult(
                    action_id=action.id,
                    status="failed",
                    detail="Wazuh dispatch rejected",
                    latency_ms=_elapsed_ms(started),
                )
            if response.status_code >= 500:
                return ExecutionResult(
                    action_id=action.id,
                    status="partial",
                    detail="Wazuh dispatch outcome is uncertain",
                    latency_ms=_elapsed_ms(started),
                )
            payload = response.json()
            if payload.get("error", 0) != 0:
                return ExecutionResult(
                    action_id=action.id,
                    status="failed",
                    detail="Wazuh manager rejected active response",
                    latency_ms=_elapsed_ms(started),
                )
            return ExecutionResult(
                action_id=action.id,
                status="partial",
                detail="Wazuh manager accepted dispatch without endpoint receipt",
                latency_ms=_elapsed_ms(started),
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "Wazuh dispatch uncertain for action %s (%s)",
                action.id,
                type(exc).__name__,
            )
            return ExecutionResult(
                action_id=action.id,
                status="partial",
                detail="Wazuh dispatch outcome is uncertain",
                latency_ms=_elapsed_ms(started),
            )

    # -- ResponseExecutor --------------------------------------------------

    def run(
        self,
        action: ProposedAction,
        *,
        execution: ExecutionIdentity | None = None,
    ) -> ExecutionResult:
        execution = _require_execution(action, execution, "run")
        _validate_reversibility(action)
        agent_id = self._agent_id(action.target)
        command = self._run_commands.get(action.type)
        if command is None:
            return ExecutionResult(
                action_id=action.id,
                status="failed",
                detail=f"sin comando AR para {action.type.value}",
            )
        return self._call(agent_id, command, action, execution)

    def revert(
        self,
        action: ProposedAction,
        *,
        execution: ExecutionIdentity | None = None,
    ) -> ExecutionResult:
        execution = _require_execution(action, execution, "revert")
        _validate_reversibility(action)
        return ExecutionResult(
            action_id=action.id,
            status="failed",
            detail="rollback requires verified prior state",
        )
