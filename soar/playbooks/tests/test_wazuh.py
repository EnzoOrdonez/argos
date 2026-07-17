"""WazuhActiveResponseExecutor contra un API mockeado con respx (sin lab)."""

from __future__ import annotations

import httpx
import pytest
import respx

from argos_contracts.enums import ActionType
from soar.playbooks.builders import build_block_ip, build_isolation, build_throttle
from soar.playbooks.wazuh import WazuhActiveResponseExecutor

BASE = "https://wazuh.test:55000"


def _executor() -> WazuhActiveResponseExecutor:
    return WazuhActiveResponseExecutor(
        api_url=BASE,
        user="api-user",
        password="api-pass",
        client=httpx.Client(),
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


@respx.mock
def test_run_exitoso_llama_active_response_con_bearer(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    ar = respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload())

    result = _executor().run(build_isolation("001", action_id="act-001"))

    assert result.ok
    assert ar.call_count == 1
    request = ar.calls.last.request
    assert request.headers["Authorization"] == "Bearer tok-123"
    assert request.url.params["agents_list"] == "001"


@respx.mock
def test_idempotencia_no_repite_la_llamada(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    ar = respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload())
    executor = _executor()
    isolation = build_isolation("001", action_id="act-001")

    executor.run(isolation)
    second = executor.run(isolation)

    assert second.ok
    assert "no-op" in second.detail
    assert ar.call_count == 1


@respx.mock
def test_api_500_devuelve_failed_sin_lanzar(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    respx_mock.put(f"{BASE}/active-response").respond(500)

    result = _executor().run(build_isolation("001", action_id="act-001"))

    assert result.status == "failed"


@respx.mock
def test_error_de_red_devuelve_failed(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    respx_mock.put(f"{BASE}/active-response").mock(
        side_effect=httpx.ConnectError("boom")
    )

    result = _executor().run(build_throttle("001", action_id="act-001"))

    assert result.status == "failed"
    assert "http" in result.detail


@respx.mock
def test_failed_items_produce_partial(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload(failed=1))

    result = _executor().run(build_isolation("001", action_id="act-001"))

    assert result.status == "partial"


@respx.mock
def test_revert_de_isolation_usa_comando_unisolate(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    ar = respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload())
    executor = _executor()
    isolation = build_isolation("001", action_id="act-001")
    executor.run(isolation)

    result = executor.revert(isolation)

    assert result.ok
    assert executor.applied == {}
    import json

    commands = [json.loads(call.request.content)["command"] for call in ar.calls]
    assert commands == ["argos-isolate", "argos-unisolate"]


@respx.mock
def test_block_ip_manda_srcip_y_comando_correcto(respx_mock: respx.Router):
    """block-ip: el PUT usa el comando argos-block-ip y lleva la IP atacante en
    alert.data.argos.src_ip (el script AR la lee de ahí para el iptables DROP)."""
    _mock_auth(respx_mock)
    ar = respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload())
    import json

    action = build_block_ip("web-prod-01", action_id="act-001", src_ip="203.0.113.7")
    result = _executor().run(action)

    assert result.ok
    body = json.loads(ar.calls.last.request.content)
    assert body["command"] == "argos-block-ip"
    assert body["alert"]["data"]["argos"]["src_ip"] == "203.0.113.7"
    assert ar.calls.last.request.url.params["agents_list"] == "web-prod-01"


@respx.mock
def test_revert_de_block_ip_usa_comando_unblock_ip(respx_mock: respx.Router):
    _mock_auth(respx_mock)
    ar = respx_mock.put(f"{BASE}/active-response").respond(200, json=_ar_payload())
    executor = _executor()
    block = build_block_ip("web-prod-01", action_id="act-001", src_ip="203.0.113.7")
    executor.run(block)

    result = executor.revert(block)

    assert result.ok
    assert executor.applied == {}
    import json

    commands = [json.loads(call.request.content)["command"] for call in ar.calls]
    assert commands == ["argos-block-ip", "argos-unblock-ip"]


@respx.mock
def test_401_reautentica_y_reintenta_una_vez(respx_mock: respx.Router):
    auth = _mock_auth(respx_mock)
    ar = respx_mock.put(f"{BASE}/active-response")
    ar.side_effect = [
        httpx.Response(401),
        httpx.Response(200, json=_ar_payload()),
    ]

    result = _executor().run(build_isolation("001", action_id="act-001"))

    assert result.ok
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
        run_commands={ActionType.HOST_ISOLATION: "argos-isolate"},
    )
    result = executor.run(build_throttle("001", action_id="act-001"))
    assert result.status == "failed"
    assert "sin comando" in result.detail


def test_constructor_lee_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WAZUH_API_URL", BASE)
    monkeypatch.setenv("WAZUH_API_USER", "env-user")
    monkeypatch.setenv("WAZUH_API_PASSWORD", "env-pass")
    monkeypatch.setenv("WAZUH_VERIFY_SSL", "false")
    executor = WazuhActiveResponseExecutor(client=httpx.Client())
    assert executor._url == BASE
