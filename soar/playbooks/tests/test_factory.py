"""Security contract for selecting the response executor."""

from __future__ import annotations

import pytest

from soar.playbooks.factory import ExecutorConfigurationError, make_executor
from soar.playbooks.simulated import SimulatedExecutor
from soar.playbooks.wazuh import WazuhActiveResponseExecutor


def test_executor_requires_explicit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("ARGOS_EXECUTOR", "simulated")

    with pytest.raises(ExecutorConfigurationError, match="ENVIRONMENT"):
        make_executor()


def test_executor_mode_must_be_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("ARGOS_EXECUTOR", raising=False)

    with pytest.raises(ExecutorConfigurationError, match="ARGOS_EXECUTOR"):
        make_executor()


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_simulated_executor_is_rejected_outside_non_live_environments(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("ARGOS_EXECUTOR", "simulated")

    with pytest.raises(ExecutorConfigurationError, match="simulated"):
        make_executor()


@pytest.mark.parametrize("environment", ["", "preview", "prod"])
def test_unknown_or_empty_environment_is_rejected(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("ARGOS_EXECUTOR", "simulated")

    with pytest.raises(ExecutorConfigurationError, match="ENVIRONMENT"):
        make_executor()


@pytest.mark.parametrize("mode", ["", "auto", "real"])
def test_unknown_or_empty_executor_mode_is_rejected(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ARGOS_EXECUTOR", mode)

    with pytest.raises(ExecutorConfigurationError, match="ARGOS_EXECUTOR"):
        make_executor()


@pytest.mark.parametrize(
    "missing_name",
    ["WAZUH_API_URL", "WAZUH_API_USER", "WAZUH_API_PASSWORD", "WAZUH_AGENT_MAP"],
)
def test_wazuh_missing_credentials_fails_closed(
    monkeypatch: pytest.MonkeyPatch, missing_name: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ARGOS_EXECUTOR", "wazuh")
    monkeypatch.setenv("WAZUH_API_URL", "https://wazuh.lab:55000")
    monkeypatch.setenv("WAZUH_API_USER", "argos")
    monkeypatch.setenv("WAZUH_API_PASSWORD", "placeholder")
    monkeypatch.setenv("WAZUH_AGENT_MAP", '{"asset-001":"001"}')
    monkeypatch.delenv(missing_name)

    with pytest.raises(ExecutorConfigurationError, match=missing_name):
        make_executor()


def test_wazuh_constructor_failure_is_sanitized_and_never_falls_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sensitive_value = "sentinel-value-that-must-not-appear"
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ARGOS_EXECUTOR", "wazuh")
    monkeypatch.setenv("WAZUH_API_URL", "https://wazuh.invalid:55000")
    monkeypatch.setenv("WAZUH_API_USER", "argos")
    monkeypatch.setenv("WAZUH_API_PASSWORD", sensitive_value)
    monkeypatch.setenv("WAZUH_AGENT_MAP", '{"asset-001":"001"}')

    def fail_to_construct() -> None:
        raise RuntimeError(f"constructor included {sensitive_value}")

    monkeypatch.setattr(
        "soar.playbooks.wazuh.WazuhActiveResponseExecutor", fail_to_construct
    )

    with pytest.raises(ExecutorConfigurationError) as caught:
        make_executor()

    assert sensitive_value not in str(caught.value)
    assert sensitive_value not in caplog.text


@pytest.mark.parametrize("environment", ["development", "test"])
def test_simulated_executor_is_explicitly_available_for_non_live_environments(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("ARGOS_EXECUTOR", "simulated")
    assert isinstance(make_executor(), SimulatedExecutor)


@pytest.mark.parametrize("environment", ["development", "test", "staging", "production"])
def test_wazuh_executor_is_available_in_every_environment(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("ARGOS_EXECUTOR", "wazuh")
    monkeypatch.setenv("WAZUH_API_URL", "https://wazuh.lab:55000")
    monkeypatch.setenv("WAZUH_API_USER", "argos")
    monkeypatch.setenv("WAZUH_API_PASSWORD", "placeholder")
    monkeypatch.setenv("WAZUH_AGENT_MAP", '{"asset-001":"001"}')
    executor = make_executor()
    assert isinstance(executor, WazuhActiveResponseExecutor)
    executor._client.close()
