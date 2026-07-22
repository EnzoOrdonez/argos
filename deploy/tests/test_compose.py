"""Tests estructurales del docker-compose Perfil A (sin levantar Docker).

Verifica los servicios + healthchecks esperados y que NO haya secretos hardcodeados
(los secretos vienen de `.env` vía `env_file`)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE = _ROOT / "docker-compose.yml"


def _load() -> dict:
    return yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))


def test_compose_is_valid_yaml() -> None:
    assert "services" in _load()


def test_core_services_present() -> None:
    services = _load()["services"]
    for name in ("redis", "postgres", "soar", "console", "llm-triage"):
        assert name in services, f"falta el servicio {name}"


def test_bridge_and_streamlit_are_optional_profiles() -> None:
    services = _load()["services"]
    assert services["bridge"]["profiles"] == ["real"]
    assert services["streamlit"]["profiles"] == ["fallback"]


def test_postgres_pinned_to_17_5() -> None:
    assert _load()["services"]["postgres"]["image"] == "postgres:17.5-bookworm"


def test_runtime_environment_and_executor_are_required_for_soar_services() -> None:
    services = _load()["services"]
    for name in ("soar", "soar-consumer"):
        environment = services[name]["environment"]
        assert environment["ENVIRONMENT"] == "${ENVIRONMENT:?set ENVIRONMENT in .env}"
        assert environment["ARGOS_EXECUTOR"] == (
            "${ARGOS_EXECUTOR:?set ARGOS_EXECUTOR in .env}"
        )


def test_core_services_have_healthchecks() -> None:
    services = _load()["services"]
    for name in ("redis", "postgres", "soar", "console", "llm-triage"):
        assert "healthcheck" in services[name], f"{name} sin healthcheck"


def test_bridge_mounts_wazuh_alerts_readonly() -> None:
    volumes = _load()["services"]["bridge"]["volumes"]
    assert any("/var/ossec/logs/alerts" in v and v.endswith(":ro") for v in volumes)


def test_no_hardcoded_secrets() -> None:
    text = _COMPOSE.read_text(encoding="utf-8")
    assert "nvapi-" not in text
    assert not re.search(r"sk-[A-Za-z0-9]{20,}", text)
    # OPENAI_API_KEY nunca inline: viaja por env_file
    assert not re.search(r"OPENAI_API_KEY\s*:\s*\S", text)
    assert any("env_file" in service for service in _load()["services"].values())


def test_soar_consumer_service_present() -> None:
    """El daemon consumer (blocker Fase 0) corre como servicio propio en el profile default."""
    consumer = _load()["services"]["soar-consumer"]
    assert consumer["command"] == "python -m soar.decision_engine"
    assert consumer["environment"]["ARGOS_REQUIRE_APPROVAL"] == "${ARGOS_REQUIRE_APPROVAL:-true}"
    assert "profiles" not in consumer  # default profile: siempre corre


def test_wazuh_manager_manager_only_real_profile() -> None:
    mgr = _load()["services"]["wazuh-manager"]
    assert mgr["profiles"] == ["real"]
    assert mgr["image"].startswith("wazuh/wazuh-manager")


def test_manager_and_bridge_share_alerts_volume() -> None:
    services = _load()["services"]

    def _mounts_shared(svc: dict) -> bool:
        return any("wazuh-alerts:/var/ossec/logs/alerts" in v for v in svc.get("volumes", []))

    assert _mounts_shared(services["wazuh-manager"])
    assert _mounts_shared(services["bridge"])
    assert "wazuh-alerts" in _load()["volumes"]


def test_console_loads_env_file_for_basic_auth() -> None:
    """CONSOLE_BASIC_* llegan al servicio console vía env_file (Fase 4/5b)."""
    assert _load()["services"]["console"]["env_file"] == ".env"
