"""Constructores puros de `ProposedAction` (ADR-0012 §2.2/§2.5).

Cada builder arma la acción del catálogo contra el contrato v1.1.0 y nada más:
sin I/O, sin estado. El executor decide cómo ejecutarla.

Catálogo y momento de disparo (ADR-0012 §2.2):
- throttle + snapshot: inmediatos al clasificar T2 / production-critical,
  PRE-aprobación. Son los que acotan el daño durante la espera de ADR-0006
  Situación B (~25.000 archivos/min a ~100-500 con el throttle).
- isolation (+ kill): al resolverse EXECUTE_ISOLATION.

`reversible=True` en los cuatro, per tabla de reversibilidad de ADR-0003 y
ADR-0012 §7.3 (kill cuenta como reversible: el servicio se relanza). Así
`requires_two_person()` se activa solo por criticidad del host, no por acción.
"""

from __future__ import annotations

import os

from argos_contracts.enums import ActionType
from argos_contracts.incident import ProposedAction


def _throttle_parameters() -> dict[str, object]:
    return {
        "cpu_percent_limit": int(os.environ.get("THROTTLE_CPU_PERCENT_LIMIT", "10")),
        "io_priority": os.environ.get("THROTTLE_IO_PRIORITY", "idle"),
    }


def build_throttle(
    host_id: str, *, action_id: str, pid: int | None = None
) -> ProposedAction:
    """Limita CPU/IO del proceso ofensor (cpulimit/ionice o Process Mitigation)."""
    parameters = _throttle_parameters()
    if pid is not None:
        parameters["pid"] = pid
    return ProposedAction(
        id=action_id,
        type=ActionType.PROCESS_THROTTLE,
        target=host_id,
        reversible=True,
        parameters=parameters,
    )


def build_snapshot(host_id: str, *, action_id: str) -> ProposedAction:
    """Snapshot de disco previo a la contención (dd/VSS): evidencia forense
    y punto de recuperación, per NIST SP 800-86 (integración forense)."""
    return ProposedAction(
        id=action_id,
        type=ActionType.DISK_SNAPSHOT,
        target=host_id,
        reversible=True,  # revert es no-op: el snapshot no se "des-toma" (ADR-0012 §7.6)
        parameters={},
    )


def build_isolation(host_id: str, *, action_id: str) -> ProposedAction:
    """Aislamiento de red del host (iptables / Wazuh AR / NetFirewallRule)."""
    return ProposedAction(
        id=action_id,
        type=ActionType.HOST_ISOLATION,
        target=host_id,
        reversible=True,
        parameters={},
    )


def build_kill(
    host_id: str, *, action_id: str, pid: int | None = None
) -> ProposedAction:
    """Mata el proceso ofensor (SIGKILL / Stop-Process)."""
    parameters: dict[str, object] = {}
    if pid is not None:
        parameters["pid"] = pid
    return ProposedAction(
        id=action_id,
        type=ActionType.PROCESS_KILL,
        target=host_id,
        reversible=True,
        parameters=parameters,
    )


def build_block_ip(host_id: str, *, action_id: str, src_ip: str) -> ProposedAction:
    """Dropea la IP atacante en el host (iptables / netsh), sin aislar el host entero.

    Alternativa quirúrgica a `build_isolation` para vectores con IP de origen (p.ej.
    fuerza bruta SSH, T1110): bloquea solo al atacante y deja el resto del tráfico del
    host intacto. La IP viaja en `parameters["src_ip"]` → el executor la entrega al
    script AR (`alert.data.argos.src_ip`). `reversible=True` (se des-dropea la regla).
    """
    return ProposedAction(
        id=action_id,
        type=ActionType.BLOCK_IP,
        target=host_id,
        reversible=True,
        parameters={"src_ip": src_ip},
    )
