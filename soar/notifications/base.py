"""Interfaz común a todos los canales de notificación (ADR-0005 strategy/adapter).

Cada canal concreto (Telegram, Discord, Twilio, Email) implementa `dispatch`.
Invariante del contrato: `dispatch()` NUNCA propaga una excepción al caller;
ante fallo devuelve `DispatchResult(success=False, error=...)`. El servicio
degrada en base a eso, sin caerse (ADR-0007 v2 escalation chain).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from argos_contracts.enums import NotificationChannelType
from argos_contracts.incident import Incident


@dataclass(frozen=True)
class DispatchResult:
    """Resultado de intentar enviar por un canal. Inmutable y auditable."""

    channel: NotificationChannelType
    success: bool
    latency_ms: int
    error: str | None = None


class NotificationChannel(ABC):
    """Canal concreto de notificación. La subclase fija `channel_type`."""

    channel_type: NotificationChannelType

    @abstractmethod
    def dispatch(self, incident: Incident) -> DispatchResult:
        """Envía la notificación del incidente. No lanza: degrada a DispatchResult."""
