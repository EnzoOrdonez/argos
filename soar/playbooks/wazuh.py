"""WazuhActiveResponseExecutor: el manager ordena, el agente ejecuta (ADR-0012 §2.1.1).

Patrón XDR estándar: el SOAR llama al API del Wazuh manager
(PUT /active-response, documentación oficial de Wazuh, capítulo Active
Response) y el agente corre el comando en la VM víctima. El SOAR nunca
shell-ea directo a una víctima (alternativa SSH rechazada en ADR-0012 §5).

Los nombres de comando AR son dominio de P3 (ADR-0012 §3): acá viven como
defaults configurables. Sin el lab de P4, este executor se valida con respx;
la validación real queda para integración.

Fail-soft (ADR-0012 §2.4): cualquier error HTTP o de red se reporta como
`ExecutionResult(status="failed")`, nunca como excepción.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from argos_contracts.enums import ActionType
from argos_contracts.incident import ProposedAction
from soar.playbooks.base import ExecutionResult

logger = logging.getLogger(__name__)

# Comandos active-response por accion (defaults; P3 define los reales en Wazuh).
DEFAULT_RUN_COMMANDS: dict[ActionType, str] = {
    ActionType.PROCESS_THROTTLE: "argos-throttle",
    ActionType.DISK_SNAPSHOT: "argos-snapshot",
    ActionType.HOST_ISOLATION: "argos-isolate",
    ActionType.PROCESS_KILL: "argos-kill",
    ActionType.BLOCK_IP: "argos-block-ip",
}
# Reverts con comando AR propio. Snapshot y kill no tienen revert remoto:
# snapshot es no-op (§7.6) y un kill no se "des-mata".
DEFAULT_REVERT_COMMANDS: dict[ActionType, str] = {
    ActionType.PROCESS_THROTTLE: "argos-unthrottle",
    ActionType.HOST_ISOLATION: "argos-unisolate",
    ActionType.BLOCK_IP: "argos-unblock-ip",
}


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


class WazuhActiveResponseExecutor:
    """Ejecuta `ProposedAction` vía active-response del Wazuh manager.

    `action.target` se pasa como `agents_list`; el mapeo host_id -> agent_id
    es configuración del lab (P3/P4). Idempotencia por (type, target) en
    memoria: re-ejecutar no repite la llamada al API (ADR-0012 §7.4).
    """

    def __init__(
        self,
        api_url: str | None = None,
        user: str | None = None,
        password: str | None = None,
        *,
        client: httpx.Client | None = None,
        timeout: float = 5.0,
        run_commands: dict[ActionType, str] | None = None,
        revert_commands: dict[ActionType, str] | None = None,
    ) -> None:
        self._url = (api_url or os.environ["WAZUH_API_URL"]).rstrip("/")
        self._user = user or os.environ["WAZUH_API_USER"]
        self._password = password or os.environ["WAZUH_API_PASSWORD"]
        verify_ssl = os.environ.get("WAZUH_VERIFY_SSL", "false").lower() == "true"
        self._client = client or httpx.Client(timeout=timeout, verify=verify_ssl)
        self._run_commands = run_commands or DEFAULT_RUN_COMMANDS
        self._revert_commands = revert_commands or DEFAULT_REVERT_COMMANDS
        self._token: str | None = None
        self.applied: dict[tuple[ActionType, str], ProposedAction] = {}

    # -- API plumbing ------------------------------------------------------

    def _authenticate(self) -> str:
        response = self._client.post(
            f"{self._url}/security/user/authenticate",
            auth=(self._user, self._password),
        )
        response.raise_for_status()
        token = str(response.json()["data"]["token"])
        self._token = token
        return token

    def _put_active_response(
        self, agent: str, command: str, action: ProposedAction
    ) -> httpx.Response:
        token = self._token or self._authenticate()
        body: dict[str, Any] = {
            "command": command,
            "arguments": [action.id],
            "alert": {"data": {"argos": dict(action.parameters)}},
        }
        response = self._client.put(
            f"{self._url}/active-response",
            params={"agents_list": agent},
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 401:
            # Token vencido: re-autenticar una vez y reintentar.
            token = self._authenticate()
            response = self._client.put(
                f"{self._url}/active-response",
                params={"agents_list": agent},
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
        return response

    def _call(self, command: str, action: ProposedAction) -> ExecutionResult:
        started = time.monotonic()
        try:
            response = self._put_active_response(action.target, command, action)
            response.raise_for_status()
            payload = response.json()
            if payload.get("error", 0) != 0:
                return ExecutionResult(
                    action_id=action.id,
                    status="failed",
                    detail=f"wazuh error: {payload.get('message')}",
                    latency_ms=_elapsed_ms(started),
                )
            failed_items = payload.get("data", {}).get("total_failed_items", 0)
            status = "partial" if failed_items else "success"
            return ExecutionResult(
                action_id=action.id,
                status=status,
                detail=f"AR '{command}' -> agent {action.target}",
                latency_ms=_elapsed_ms(started),
            )
        except httpx.HTTPError as exc:
            logger.warning("wazuh AR %s fallo para %s: %s", command, action.id, exc)
            return ExecutionResult(
                action_id=action.id,
                status="failed",
                detail=f"http: {exc}",
                latency_ms=_elapsed_ms(started),
            )

    # -- ResponseExecutor --------------------------------------------------

    def run(self, action: ProposedAction) -> ExecutionResult:
        key = (action.type, action.target)
        if key in self.applied:
            return ExecutionResult(
                action_id=action.id,
                status="success",
                detail=f"no-op: {action.type.value} ya aplicada en {action.target}",
            )
        command = self._run_commands.get(action.type)
        if command is None:
            return ExecutionResult(
                action_id=action.id,
                status="failed",
                detail=f"sin comando AR para {action.type.value}",
            )
        result = self._call(command, action)
        if result.status in ("success", "partial"):
            self.applied[key] = action
        return result

    def revert(self, action: ProposedAction) -> ExecutionResult:
        key = (action.type, action.target)
        command = self._revert_commands.get(action.type)
        if command is None:
            # Snapshot/kill: revert local no-op (ADR-0012 §7.6).
            self.applied.pop(key, None)
            return ExecutionResult(
                action_id=action.id,
                status="success",
                detail=f"no-op: revert de {action.type.value} no aplica",
            )
        result = self._call(command, action)
        if result.status in ("success", "partial"):
            self.applied.pop(key, None)
        return result
