"""Fixtures compartidas para los tests de soar/.

`make_incident` arma un `Incident` válido contra el contrato congelado
argos_contracts v1.1.0 (incident_id con patrón INC-YYYY-MM-DD-NNN, datetimes
tz-aware, alert/host/proposed_actions requeridos). Reutilizable en §2.2-§2.8.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from argos_contracts.alert import NormalizedAlert
from argos_contracts.enums import Criticality, IncidentState, Layer, Severity, Tier
from argos_contracts.incident import Incident
from argos_contracts.triage import HostInfo


@pytest.fixture
def make_incident() -> Callable[..., Incident]:
    """Devuelve un factory: make_incident(tier=Tier.T2, **overrides) -> Incident."""

    def _make(*, tier: Tier = Tier.T2, **overrides: object) -> Incident:
        now = datetime.now(UTC)
        defaults: dict[str, object] = {
            "incident_id": "INC-2026-05-30-001",
            "created_at": now,
            "updated_at": now,
            "tier": tier,
            "state": IncidentState.AWAITING_APPROVAL,
            "host": HostInfo(
                id="LIN-DB-01",
                criticality=Criticality.PRODUCTION_CRITICAL,
                ip="10.10.50.10",
                os="Ubuntu 22.04",
            ),
            "alert": NormalizedAlert(
                alert_id="alert-001",
                source_layer=Layer.LAYER_1,
                timestamp=now,
                host_id="LIN-DB-01",
                severity_score=0.9,
                severity_label=Severity.HIGH,
                technique_mitre="T1486",
            ),
            "proposed_actions": [],
        }
        defaults.update(overrides)
        return Incident(**defaults)

    return _make
