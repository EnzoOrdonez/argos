"""Regresión del inventario de lab (C1 subnet + C2 OS, decisión 2026-06-29).

Bloquea un revert silencioso del esquema de IPs/OS antes de la demo 1-jul.
El lab real es 192.168.56.0/24 (mgr .10 / win .20 / lin .21), Windows 10.
La criticidad se resuelve por host_id, no por IP (inventory.py docstring),
así que estos campos son metadata — pero el provisioning del lab depende de
que coincidan con el Vagrantfile y los provision scripts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from argos_contracts.enums import Criticality
from soar.inventory import (
    load_effective_inventory,
    reset_inventory_cache,
    resolve_host,
)


@pytest.fixture(autouse=True)
def _clean_inventory_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cada test arranca sin ARGOS_HOST_INVENTORY y con el cache limpio."""
    monkeypatch.delenv("ARGOS_HOST_INVENTORY", raising=False)
    reset_inventory_cache()
    yield
    reset_inventory_cache()


def test_lab_manager_ip() -> None:
    assert resolve_host("LAB-MANAGER").ip == "192.168.56.10"


def test_windows_victim_ip_and_os() -> None:
    host = resolve_host("WIN-VICTIM-01")
    assert host.ip == "192.168.56.20"
    assert host.os == "Windows 10"  # C2: era "Windows 11"
    assert host.criticality is Criticality.STANDARD


def test_linux_victim_ip_and_criticality() -> None:
    host = resolve_host("LIN-VICTIM-01")
    assert host.ip == "192.168.56.21"
    assert host.os == "Debian 12"  # la VM es debian/bookworm64, no Ubuntu
    assert host.criticality is Criticality.PRODUCTION_CRITICAL


def test_fictional_overlay_alias_untouched() -> None:
    """LIN-DB-01 es el overlay ficticio ADR-0009 §2.7, NO un host físico."""
    assert resolve_host("LIN-DB-01").ip == "10.10.50.10"


# -- inventario config-driven (ARGOS_HOST_INVENTORY) --------------------------


def _write_inventory(tmp_path: Path, data: object) -> str:
    path = tmp_path / "hosts.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_env_unset_usa_defaults_embebidos() -> None:
    """Sin ARGOS_HOST_INVENTORY, el inventario efectivo son los defaults del módulo."""
    from soar.inventory import HOST_INVENTORY

    assert load_effective_inventory() is HOST_INVENTORY
    assert resolve_host("LIN-VICTIM-01").criticality is Criticality.PRODUCTION_CRITICAL


def test_archivo_override_criticidad(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El archivo puede cambiar la criticidad de un host respecto al default."""
    path = _write_inventory(
        tmp_path,
        {"LIN-VICTIM-01": {"criticality": "standard", "ip": "10.0.0.5", "os": "Debian 12"}},
    )
    monkeypatch.setenv("ARGOS_HOST_INVENTORY", path)
    host = resolve_host("LIN-VICTIM-01")
    assert host.criticality is Criticality.STANDARD
    assert host.ip == "10.0.0.5"


def test_archivo_reemplaza_no_mergea(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un host default ausente del archivo cae a STANDARD (el archivo reemplaza, no mergea)."""
    path = _write_inventory(
        tmp_path,
        {"OTRO-HOST": {"criticality": "production_critical", "ip": "10.0.0.9", "os": "RHEL 9"}},
    )
    monkeypatch.setenv("ARGOS_HOST_INVENTORY", path)
    # LIN-VICTIM-01 es PRODUCTION_CRITICAL en los defaults, pero no está en el archivo.
    assert resolve_host("LIN-VICTIM-01").criticality is Criticality.STANDARD
    assert resolve_host("OTRO-HOST").criticality is Criticality.PRODUCTION_CRITICAL


def test_host_desconocido_sigue_standard_con_archivo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un host no declarado cae a STANDARD aun con un archivo cargado (fallback per-host seguro)."""
    path = _write_inventory(
        tmp_path,
        {"OTRO-HOST": {"criticality": "production_critical", "ip": "10.0.0.9", "os": "RHEL 9"}},
    )
    monkeypatch.setenv("ARGOS_HOST_INVENTORY", path)
    host = resolve_host("NO-EXISTE", ip="1.2.3.4")
    assert host.criticality is Criticality.STANDARD
    assert host.ip == "1.2.3.4"


def test_clave_manda_sobre_id_embebido(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El host_id de la clave del JSON gana sobre cualquier 'id' dentro del objeto."""
    path = _write_inventory(
        tmp_path,
        {"REAL-KEY": {"id": "IGNORADO", "criticality": "standard", "ip": "10.0.0.1"}},
    )
    monkeypatch.setenv("ARGOS_HOST_INVENTORY", path)
    assert resolve_host("REAL-KEY").id == "REAL-KEY"


def test_archivo_faltante_falla_ruidoso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARGOS_HOST_INVENTORY", str(tmp_path / "no_existe.json"))
    with pytest.raises(FileNotFoundError, match=r"no_existe\.json"):
        load_effective_inventory()


def test_json_malformado_falla_ruidoso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "roto.json"
    path.write_text("{ esto no es json", encoding="utf-8")
    monkeypatch.setenv("ARGOS_HOST_INVENTORY", str(path))
    with pytest.raises(json.JSONDecodeError):
        load_effective_inventory()


def test_criticidad_invalida_falla_ruidoso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un valor fuera del enum Criticality revienta al cargar, no en silencio."""
    path = _write_inventory(
        tmp_path,
        {"HOST-X": {"criticality": "ultra-mega-critical", "ip": "10.0.0.2"}},
    )
    monkeypatch.setenv("ARGOS_HOST_INVENTORY", path)
    with pytest.raises(ValueError, match="HOST-X"):
        load_effective_inventory()


def test_json_no_objeto_falla_ruidoso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_inventory(tmp_path, ["no", "es", "un", "objeto"])
    monkeypatch.setenv("ARGOS_HOST_INVENTORY", path)
    with pytest.raises(ValueError, match="objeto JSON"):
        load_effective_inventory()
