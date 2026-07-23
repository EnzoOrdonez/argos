"""WazuhActiveResponseExecutor contra un API mockeado con respx (sin lab)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from argos_contracts.enums import ActionType
from soar.decision_engine.containment import _execute_effect
from soar.execution.identity import ExecutionIdentity
from soar.execution.journal import (
    AmbiguousExecutionError,
    MemoryExecutionStore,
    ResponseExecutionJournal,
)
from soar.playbooks.builders import (
    build_block_ip,
    build_isolation,
    build_kill,
    build_snapshot,
    build_throttle,
)
from soar.playbooks.wazuh import WazuhActiveResponseExecutor, WazuhExecutionContractError

BASE = "https://wazuh.test:55000"


def _executor() -> WazuhActiveResponseExecutor:
    return WazuhActiveResponseExecutor(
        api_url=BASE,
        user="api-user",
        password="api-pass",
        client=httpx.Client(),
        agent_mapping={"asset-001": "001", "web-prod-01": "002"},
    )


def _mock_auth(router: respx.Router) -> respx.Route:
    return router.post(f"{BASE}/security/user/authenticate").respond(
        200, json={"data": {"token": "tok-123"}}
    )


def _ar_payload(failed: int = 0) -> dict[str, object]:
    return {
        "error": 0,
        "data": {"total_affected_items": 1, "total_failed_items": failed},
    }


def _execution(action, operation: str = "run") -> ExecutionIdentity:
    return ExecutionIdentity("INC-2026-07-23-001", action.id, operation)


def _mock_active_agent(router: respx.Router, agent_id: str = "001") -> respx.Route:
    return router.get(f"{BASE}/agents").respond(
        200,
        json={
            "error": 0,
            "data": {
                "affected_items": [{"id": agent_id, "status": "active"}],
                "total_affected_items": 1,
            },
        },
    )


@respx.mock
def test_run_propagates_complete_execution_identity(respx_mock: respx.Router) -> None:
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    ar = respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload())
    action = build_isolation("asset-001", action_id="act-001")
    execution = ExecutionIdentity("INC-2026-07-23-001", action.id, "run")

    _executor().run(action, execution=execution)

    body = __import__("json").loads(ar.calls.last.request.content)
    assert body["arguments"] == [execution.execution_id]
    assert body["alert"]["data"]["argos"]["execution"] == execution.as_payload()


def test_run_rejects_missing_execution_identity() -> None:
    with pytest.raises(WazuhExecutionContractError, match="identity is required"):
        _executor().run(build_isolation("001", action_id="act-001"))


def test_run_rejects_asset_without_agent_mapping() -> None:
    action = build_isolation("unknown-asset", action_id="act-001")

    with pytest.raises(WazuhExecutionContractError, match="agent mapping"):
        _executor().run(action, execution=_execution(action))


def test_constructor_rejects_ambiguous_agent_mapping() -> None:
    with pytest.raises(WazuhExecutionContractError, match="one-to-one"):
        WazuhActiveResponseExecutor(
            api_url=BASE,
            user="api-user",
            password="api-pass",
            client=httpx.Client(),
            agent_mapping={"asset-a": "001", "asset-b": "001"},
        )


@pytest.mark.parametrize("field", ["api_url", "user", "password"])
def test_constructor_rejects_incomplete_direct_configuration(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    for name in ("WAZUH_API_URL", "WAZUH_API_USER", "WAZUH_API_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    values = {"api_url": BASE, "user": "api-user", "password": "api-pass"}
    values[field] = ""

    with pytest.raises(WazuhExecutionContractError, match="incomplete"):
        WazuhActiveResponseExecutor(
            **values,
            client=httpx.Client(),
            agent_mapping={"asset-001": "001"},
        )


@pytest.mark.parametrize("builder", [build_kill, build_snapshot])
def test_executor_rejects_irreversible_action_declared_reversible(builder) -> None:
    action = builder("asset-001", action_id="act-001").model_copy(
        update={"reversible": True}
    )

    with pytest.raises(WazuhExecutionContractError, match="irreversible"):
        _executor().run(action, execution=_execution(action))


def test_revert_is_blocked_without_verified_prior_state() -> None:
    action = build_isolation("asset-001", action_id="act-001")

    result = _executor().revert(action, execution=_execution(action, "revert"))

    assert result.status == "failed"
    assert result.detail == "rollback requires verified prior state"


@respx.mock
def test_preflight_rejects_missing_agent_before_dispatch(
    respx_mock: respx.Router,
) -> None:
    _mock_auth(respx_mock)
    respx_mock.get(f"{BASE}/agents").respond(
        200, json={"error": 0, "data": {"affected_items": []}}
    )
    dispatch = respx_mock.put(f"{BASE}/active-response").respond(
        200, json=_ar_payload()
    )
    action = build_isolation("asset-001", action_id="act-001")

    result = _executor().run(action, execution=_execution(action))

    assert result.status == "failed"
    assert dispatch.call_count == 0


@respx.mock
def test_preflight_rejects_inactive_agent_before_dispatch(
    respx_mock: respx.Router,
) -> None:
    _mock_auth(respx_mock)
    respx_mock.get(f"{BASE}/agents").respond(
        200,
        json={
            "error": 0,
            "data": {"affected_items": [{"id": "001", "status": "disconnected"}]},
        },
    )
    dispatch = respx_mock.put(f"{BASE}/active-response").respond(
        200, json=_ar_payload()
    )
    action = build_isolation("asset-001", action_id="act-001")

    result = _executor().run(action, execution=_execution(action))

    assert result.status == "failed"
    assert dispatch.call_count == 0


@respx.mock
def test_malformed_auth_response_fails_before_dispatch_without_leaking(
    respx_mock: respx.Router, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "malformed-sensitive-auth-body"
    respx_mock.post(f"{BASE}/security/user/authenticate").respond(
        200, json={"unexpected": secret}
    )
    dispatch = respx_mock.put(f"{BASE}/active-response").respond(
        200, json=_ar_payload()
    )
    action = build_isolation("asset-001", action_id="act-001")

    result = _executor().run(action, execution=_execution(action))

    assert result.status == "failed"
    assert dispatch.call_count == 0
    assert secret not in result.detail
    assert secret not in caplog.text


@respx.mock
def test_malformed_agent_list_fails_before_dispatch(
    respx_mock: respx.Router,
) -> None:
    _mock_auth(respx_mock)
    respx_mock.get(f"{BASE}/agents").respond(
        200, json={"data": {"affected_items": "x"}}
    )
    dispatch = respx_mock.put(f"{BASE}/active-response").respond(
        200, json=_ar_payload()
    )
    action = build_isolation("asset-001", action_id="act-001")

    result = _executor().run(action, execution=_execution(action))

    assert result.status == "failed"
    assert dispatch.call_count == 0


@respx.mock
def test_run_exitoso_llama_active_response_con_bearer(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    ar = respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload())
    action = build_isolation("asset-001", action_id="act-001")

    result = _executor().run(action, execution=_execution(action))

    assert result.status == "partial"
    assert ar.call_count == 1
    request = ar.calls.last.request
    assert request.headers["Authorization"] == "Bearer tok-123"
    assert request.url.params["agents_list"] == "001"


@respx.mock
def test_adapter_does_not_claim_local_exactly_once(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    ar = respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload())
    executor = _executor()
    isolation = build_isolation("asset-001", action_id="act-001")

    executor.run(isolation, execution=_execution(isolation))
    second = executor.run(isolation, execution=_execution(isolation))

    assert second.status == "partial"
    assert ar.call_count == 2


@respx.mock
def test_api_500_is_ambiguous_without_endpoint_receipt(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    respx_mock.put(f"{BASE}/active-response").respond(500)
    action = build_isolation("asset-001", action_id="act-001")

    result = _executor().run(action, execution=_execution(action))

    assert result.status == "partial"


@respx.mock
def test_error_de_red_devuelve_failed(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    respx_mock.put(f"{BASE}/active-response").mock(
        side_effect=httpx.ConnectError("boom")
    )

    action = build_throttle("asset-001", action_id="act-001")
    result = _executor().run(action, execution=_execution(action))

    assert result.status == "partial"
    assert result.detail == "Wazuh dispatch outcome is uncertain"


@respx.mock
def test_dispatch_timeout_is_ambiguous(respx_mock: respx.Router) -> None:
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    respx_mock.put(f"{BASE}/active-response").mock(
        side_effect=httpx.ReadTimeout("sensitive transport detail")
    )
    action = build_isolation("asset-001", action_id="act-001")

    result = _executor().run(action, execution=_execution(action))

    assert result.status == "partial"
    assert result.detail == "Wazuh dispatch outcome is uncertain"


@respx.mock
def test_dispatch_uses_executor_timeout_with_injected_client(
    respx_mock: respx.Router,
) -> None:
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    dispatch = respx_mock.put(f"{BASE}/active-response").respond(
        200, json=_ar_payload()
    )
    executor = WazuhActiveResponseExecutor(
        api_url=BASE,
        user="api-user",
        password="api-pass",
        client=httpx.Client(timeout=99),
        timeout=1.25,
        agent_mapping={"asset-001": "001"},
    )
    action = build_isolation("asset-001", action_id="act-001")

    executor.run(action, execution=_execution(action))

    assert dispatch.calls.last.request.extensions["timeout"]["read"] == 1.25


@pytest.mark.parametrize("timeout", [0, -1, 31])
def test_constructor_rejects_unsafe_timeout(timeout: float) -> None:
    with pytest.raises(WazuhExecutionContractError, match="timeout"):
        WazuhActiveResponseExecutor(
            api_url=BASE,
            user="api-user",
            password="api-pass",
            client=httpx.Client(),
            timeout=timeout,
            agent_mapping={"asset-001": "001"},
        )


@respx.mock
def test_http_200_without_endpoint_receipt_is_ambiguous(
    respx_mock: respx.Router,
) -> None:
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload())
    action = build_isolation("asset-001", action_id="act-001")

    result = _executor().run(action, execution=_execution(action))

    assert result.status == "partial"
    assert "receipt" in result.detail


@respx.mock
async def test_durable_journal_prevents_automatic_repeat_of_ambiguous_dispatch(
    respx_mock: respx.Router,
) -> None:
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    dispatch = respx_mock.put(f"{BASE}/active-response").respond(
        200, json=_ar_payload()
    )
    action = build_isolation("asset-001", action_id="act-001")
    journal = ResponseExecutionJournal(MemoryExecutionStore(), owner="worker-a")

    with pytest.raises(AmbiguousExecutionError):
        await _execute_effect(
            journal, _executor(), "INC-2026-07-23-001", action, "run"
        )
    with pytest.raises(AmbiguousExecutionError):
        await _execute_effect(
            journal, _executor(), "INC-2026-07-23-001", action, "run"
        )

    assert dispatch.call_count == 1
    record = journal.get("INC-2026-07-23-001", action.id, "run")
    assert record is not None
    assert record.state == "ambiguous"


@respx.mock
def test_transport_errors_do_not_expose_secrets(
    respx_mock: respx.Router, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "do-not-leak-this-password"
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    respx_mock.put(f"{BASE}/active-response").mock(
        side_effect=httpx.ConnectError(secret)
    )
    action = build_isolation("asset-001", action_id="act-001")

    result = _executor().run(action, execution=_execution(action))

    assert secret not in result.detail
    assert secret not in caplog.text


@respx.mock
def test_failed_items_produce_partial(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload(failed=1))
    action = build_isolation("asset-001", action_id="act-001")

    result = _executor().run(action, execution=_execution(action))

    assert result.status == "partial"


@respx.mock
def test_revert_de_isolation_is_blocked_without_prior_state(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    ar = respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload())
    executor = _executor()
    isolation = build_isolation("asset-001", action_id="act-001")
    executor.run(isolation, execution=_execution(isolation))

    result = executor.revert(isolation, execution=_execution(isolation, "revert"))

    assert result.status == "failed"
    commands = [json.loads(call.request.content)["command"] for call in ar.calls]
    assert commands == ["argos-isolate"]


@respx.mock
def test_block_ip_manda_srcip_y_comando_correcto(respx_mock: respx.Router):
    """block-ip: el PUT usa el comando argos-block-ip y lleva la IP atacante en
    alert.data.argos.src_ip (el script AR la lee de ahí para el iptables DROP)."""
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock, "002")
    ar = respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload())
    import json

    action = build_block_ip("web-prod-01", action_id="act-001", src_ip="203.0.113.7")
    result = _executor().run(action, execution=_execution(action))

    assert result.status == "partial"
    body = json.loads(ar.calls.last.request.content)
    assert body["command"] == "argos-block-ip"
    assert body["alert"]["data"]["argos"]["src_ip"] == "203.0.113.7"
    assert ar.calls.last.request.url.params["agents_list"] == "002"


@respx.mock
def test_revert_de_block_ip_is_blocked_without_prior_state(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    _mock_active_agent(respx_mock, "002")
    ar = respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload())
    executor = _executor()
    block = build_block_ip("web-prod-01", action_id="act-001", src_ip="203.0.113.7")
    executor.run(block, execution=_execution(block))

    result = executor.revert(block, execution=_execution(block, "revert"))

    assert result.status == "failed"
    commands = [json.loads(call.request.content)["command"] for call in ar.calls]
    assert commands == ["argos-block-ip"]


@respx.mock
def test_401_reautentica_y_reintenta_una_vez(respx_mock: respx.Router):
    auth = _mock_auth(respx_mock)
    _mock_active_agent(respx_mock)
    ar = respx_mock.put(f"{BASE}/active-response")
    ar.side_effect = [
        httpx.Response(401),
        httpx.Response(200, json=_ar_payload()),
    ]

    action = build_isolation("asset-001", action_id="act-001")
    result = _executor().run(action, execution=_execution(action))

    assert result.status == "partial"
    assert auth.call_count == 2
    assert ar.call_count == 2


@respx.mock
def test_accion_sin_comando_configurado_falla_fail_soft(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    executor = WazuhActiveResponseExecutor(
        api_url=BASE,
        user="u",
        password="p",
        client=httpx.Client(),
        agent_mapping={"asset-001": "001"},
        run_commands={ActionType.HOST_ISOLATION: "argos-isolate"},
    )
    action = build_throttle("asset-001", action_id="act-001")
    result = executor.run(action, execution=_execution(action))
    assert result.status == "failed"
    assert "sin comando" in result.detail


def test_constructor_lee_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WAZUH_API_URL", BASE)
    monkeypatch.setenv("WAZUH_API_USER", "env-user")
    monkeypatch.setenv("WAZUH_API_PASSWORD", "env-pass")
    monkeypatch.setenv("WAZUH_VERIFY_SSL", "false")
    monkeypatch.setenv("WAZUH_AGENT_MAP", '{"asset-001":"001"}')
    executor = WazuhActiveResponseExecutor(client=httpx.Client())
    assert executor._url == BASE
