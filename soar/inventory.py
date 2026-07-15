"""Inventario de criticidad por host (ADR-0013 §2.3 + review §7.4).

La `NormalizedAlert` trae `host_id`, no criticidad. Este inventario resuelve
el `HostInfo` completo que alimenta `requires_two_person` (ADR-0003 override).

Por defecto se usan los `HOST_INVENTORY` embebidos (el lab del curso). Para
apuntar ARGOS a otro entorno sin editar código, setear `ARGOS_HOST_INVENTORY`
al path de un JSON keyed by `host_id`:

    {
      "LIN-VICTIM-01": {"criticality": "production_critical", "ip": "10.0.0.5", "os": "Debian 12"},
      "WIN-WEB-01":    {"criticality": "standard", "ip": "10.0.0.9", "os": "Windows Server 2022"}
    }

El archivo REEMPLAZA los defaults por completo (no hay merge): es la única
fuente de verdad cuando está seteado. `criticality` acepta los valores del
enum `Criticality` (`standard` | `production_critical`).

Fuente de los datos embebidos: OPEN_QUESTIONS Q2 (la VM Linux con PostgreSQL
lleva el tag `criticality=production-critical`) y las IPs del lab en
`.env.example` (LAB_VICTIM_LINUX_IP=192.168.56.21, LAB_VICTIM_WINDOWS_IP=192.168.56.20).
El rango `10.10.50.x` de ADR-0009 §2.7 son servidores de aplicación de la red
ficticia para reglas Sigma, NO el host DB: por eso la clave acá es el `host_id`
(nombre de agente Wazuh), no la IP. `LIN-DB-01` se mantiene como alias del host
DB porque el conftest de Fase 2 ya lo usa; unificar el nombre canónico es deuda
con P4 (ADR-0013 §7.4).

Host desconocido cae a STANDARD: aislar por error un host estándar es barato
y reversible (ADR-0006 §Justificación); reservar el two-person para los
activos declarados evita que un typo en el agente bloquee la contención.
Ojo con la asimetría deliberada: el fallback per-host a STANDARD es seguro,
pero un ARCHIVO malformado NO cae a defaults en silencio — degradaría todos
los hosts PRODUCTION_CRITICAL a STANDARD y desactivaría el two-person rule sin
señal. Por eso `load_effective_inventory()` es fail-loud ante un archivo roto.

Alternativa a futuro (ADR-0013 §2.3): leer el label de criticidad del agente
Wazuh desde `raw_data` si P3 lo expone.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from pydantic import ValidationError

from argos_contracts.enums import Criticality
from argos_contracts.triage import HostInfo

logger = logging.getLogger(__name__)

_ENV_VAR = "ARGOS_HOST_INVENTORY"

HOST_INVENTORY: dict[str, HostInfo] = {
    # Host PostgreSQL de IntiBank (dos nombres en uso, ver docstring).
    "LIN-VICTIM-01": HostInfo(
        id="LIN-VICTIM-01",
        criticality=Criticality.PRODUCTION_CRITICAL,
        ip="192.168.56.21",
        os="Debian 12",
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
        ip="192.168.56.20",
        os="Windows 10",
    ),
    "LAB-MANAGER": HostInfo(
        id="LAB-MANAGER",
        criticality=Criticality.STANDARD,
        ip="192.168.56.10",
        os="Ubuntu Server 22.04",
    ),
}

# Inventario efectivo cacheado (defaults embebidos o el archivo de ARGOS_HOST_INVENTORY).
_effective: dict[str, HostInfo] | None = None


def _load_from_file(path: Path) -> dict[str, HostInfo]:
    """Carga el inventario desde un JSON keyed by host_id. Fail-loud ante cualquier problema."""
    if not path.exists():
        raise FileNotFoundError(f"ARGOS_HOST_INVENTORY apunta a un archivo inexistente: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"El inventario de hosts debe ser un objeto JSON (host_id -> campos): {path}"
        )

    inventory: dict[str, HostInfo] = {}
    for host_id, fields in raw.items():
        host_id_text = str(host_id).strip()
        if not host_id_text:
            raise ValueError(f"host_id vacío en {path}")
        if not isinstance(fields, dict):
            raise ValueError(f"La entrada de '{host_id_text}' debe ser un objeto en {path}")
        try:
            # El host_id de la clave manda sobre cualquier 'id' que traiga el objeto.
            inventory[host_id_text] = HostInfo.model_validate({**fields, "id": host_id_text})
        except ValidationError as exc:
            raise ValueError(f"Entrada inválida para '{host_id_text}' en {path}: {exc}") from exc

    return inventory


def load_effective_inventory() -> dict[str, HostInfo]:
    """Resuelve y cachea el inventario efectivo.

    Si `ARGOS_HOST_INVENTORY` está seteado, carga ese JSON (fail-loud); si no,
    usa los `HOST_INVENTORY` embebidos. Idempotente. Llamar una vez al arrancar
    el servicio para que una config malformada explote en el boot y no a mitad
    de un incidente (cuando ya sería tarde para el two-person rule).
    """
    global _effective
    if _effective is None:
        path = os.environ.get(_ENV_VAR)
        if path:
            _effective = _load_from_file(Path(path))
            logger.info("inventario de hosts cargado desde %s (%d hosts)", path, len(_effective))
        else:
            _effective = HOST_INVENTORY
    return _effective


def reset_inventory_cache() -> None:
    """Limpia el cache del inventario efectivo. Seam de test / recarga tras cambiar el env."""
    global _effective
    _effective = None


def resolve_host(host_id: str, *, ip: str | None = None) -> HostInfo:
    """HostInfo del inventario efectivo, o STANDARD si el host no está declarado."""
    known = load_effective_inventory().get(host_id)
    if known is not None:
        return known.model_copy()
    return HostInfo(id=host_id, criticality=Criticality.STANDARD, ip=ip, os=None)
