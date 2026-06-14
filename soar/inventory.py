"""Inventario estático de criticidad por host (ADR-0013 §2.3 + review §7.4).

La `NormalizedAlert` trae `host_id`, no criticidad. Este inventario resuelve
el `HostInfo` completo que alimenta `requires_two_person` (ADR-0003 override).

Fuente de los datos: OPEN_QUESTIONS Q2 (la VM Linux con PostgreSQL lleva el
tag `criticality=production-critical`) y las IPs del lab en `.env.example`
(LAB_VICTIM_LINUX_IP=10.0.0.22, LAB_VICTIM_WINDOWS_IP=10.0.0.21). El rango
`10.10.50.x` de ADR-0009 §2.7 son servidores de aplicación de la red ficticia
para reglas Sigma, NO el host DB: por eso la clave acá es el `host_id` (nombre
de agente Wazuh), no la IP. `LIN-DB-01` se mantiene como alias del host DB
porque el conftest de Fase 2 ya lo usa; unificar el nombre canónico es deuda
con P4 (ADR-0013 §7.4).

Host desconocido cae a STANDARD: aislar por error un host estándar es barato
y reversible (ADR-0006 §Justificación); reservar el two-person para los
activos declarados evita que un typo en el agente bloquee la contención.

Alternativa a futuro (ADR-0013 §2.3): leer el label de criticidad del agente
Wazuh desde `raw_data` si P3 lo expone.
"""

from __future__ import annotations

from argos_contracts.enums import Criticality
from argos_contracts.triage import HostInfo

HOST_INVENTORY: dict[str, HostInfo] = {
    # Host PostgreSQL de IntiBank (dos nombres en uso, ver docstring).
    "LIN-VICTIM-01": HostInfo(
        id="LIN-VICTIM-01",
        criticality=Criticality.PRODUCTION_CRITICAL,
        ip="10.0.0.22",
        os="Ubuntu Server 22.04",
    ),
    "LIN-DB-01": HostInfo(
        id="LIN-DB-01",
        criticality=Criticality.PRODUCTION_CRITICAL,
        ip="10.10.50.10",
        os="Ubuntu Server 22.04",
    ),
    "WIN-VICTIM-01": HostInfo(
        id="WIN-VICTIM-01",
        criticality=Criticality.STANDARD,
        ip="10.0.0.21",
        os="Windows 11",
    ),
    "LAB-MANAGER": HostInfo(
        id="LAB-MANAGER",
        criticality=Criticality.STANDARD,
        ip="10.0.0.10",
        os="Ubuntu Server 22.04",
    ),
}


def resolve_host(host_id: str, *, ip: str | None = None) -> HostInfo:
    """HostInfo del inventario, o STANDARD si el host no está declarado."""
    known = HOST_INVENTORY.get(host_id)
    if known is not None:
        return known.model_copy()
    return HostInfo(id=host_id, criticality=Criticality.STANDARD, ip=ip, os=None)
