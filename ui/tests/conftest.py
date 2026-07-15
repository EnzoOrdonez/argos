"""Fixtures de los tests de la consola.

El factory arma ``Incident`` directo desde ``argos_contracts`` (no reusa
``soar/conftest.py``: la consola es independiente de ``soar``). Al final se suma
``ui/`` a ``sys.path`` para que los tests importen el paquete ``streamlit_app`` sin
instalar la consola como paquete pip (está excluida en ``pyproject``).
"""

from __future__ import annotations

import pathlib
import sys
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from argos_contracts.alert import NormalizedAlert
from argos_contracts.enums import (
    ActionType,
    ApproverStatus,
    Criticality,
    IncidentState,
    Layer,
    NotificationChannelType,
    Severity,
    Tier,
)
from argos_contracts.incident import (
    ApproverState,
    ConsolidationWindow,
    FinalDecision,
    Incident,
    ProposedAction,
)
from argos_contracts.triage import HostInfo

# argos_contracts está instalado, así que sus imports no necesitan el path hack;
# lo dejamos al final (sin imports después) para no disparar E402.
_UI_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_UI_ROOT) not in sys.path:
    sys.path.insert(0, str(_UI_ROOT))

_NOW = datetime(2026, 6, 24, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def now() -> datetime:
    return _NOW


@pytest.fixture
def make_incident() -> Callable[..., Incident]:
    def _make(
        *,
        incident_id: str = "INC-2026-06-24-001",
        tier: Tier = Tier.T2,
        state: IncidentState = IncidentState.AWAITING_APPROVAL,
        criticality: Criticality = Criticality.PRODUCTION_CRITICAL,
        approvers: list[ApproverState] | None = None,
        consolidation_window: ConsolidationWindow | None = None,
        final_decision: FinalDecision | None = None,
        proposed_actions: list[ProposedAction] | None = None,
    ) -> Incident:
        return Incident(
            incident_id=incident_id,
            created_at=_NOW,
            updated_at=_NOW,
            tier=tier,
            state=state,
            host=HostInfo(
                id="LIN-DB-01",
                criticality=criticality,
                ip="10.0.0.22",
                os="Ubuntu 22.04",
            ),
            alert=NormalizedAlert(
                alert_id="alert-001",
                source_layer=Layer.LAYER_1,
                timestamp=_NOW,
                host_id="LIN-DB-01",
                severity_score=0.9,
                severity_label=Severity.HIGH,
                technique_mitre="T1486",
                triggering_rule="sigma_ransomware_mass_rename",
            ),
            proposed_actions=(
                proposed_actions
                if proposed_actions is not None
                else [
                    ProposedAction(
                        id="act-001",
                        type=ActionType.HOST_ISOLATION,
                        target="LIN-DB-01",
                        reversible=True,
                    )
                ]
            ),
            approvers=approvers if approvers is not None else [],
            consolidation_window=consolidation_window,
            final_decision=final_decision,
        )

    return _make


@pytest.fixture
def approver() -> Callable[..., ApproverState]:
    def _make(
        *,
        email: str = "telegram:1",
        role: str = "soc_lead",
        status: ApproverStatus = ApproverStatus.APPROVED,
        latency_seconds: float | None = 18.0,
        channel: NotificationChannelType = NotificationChannelType.TELEGRAM,
        responded: bool = True,
    ) -> ApproverState:
        return ApproverState(
            email=email,
            role=role,
            status=status,
            latency_seconds=latency_seconds,
            channel=channel,
            responded_at=_NOW if responded else None,
        )

    return _make
