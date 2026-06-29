"""Regresión del inventario de lab (C1 subnet + C2 OS, decisión 2026-06-29).

Bloquea un revert silencioso del esquema de IPs/OS antes de la demo 1-jul.
El lab real es 192.168.56.0/24 (mgr .10 / win .20 / lin .21), Windows 10.
La criticidad se resuelve por host_id, no por IP (inventory.py docstring),
así que estos campos son metadata — pero el provisioning del lab depende de
que coincidan con el Vagrantfile y los provision scripts.
"""

from __future__ import annotations

from argos_contracts.enums import Criticality
from soar.inventory import resolve_host


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
    assert host.criticality is Criticality.PRODUCTION_CRITICAL


def test_fictional_overlay_alias_untouched() -> None:
    """LIN-DB-01 es el overlay ficticio ADR-0009 §2.7, NO un host físico."""
    assert resolve_host("LIN-DB-01").ip == "10.10.50.10"
