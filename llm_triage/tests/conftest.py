"""Fixtures de los tests de llm_triage."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from argos_contracts.enums import Criticality, Layer
from argos_contracts.triage import AlertContext, AlertSummary, HostInfo


@pytest.fixture
def alert_context() -> AlertContext:
    """AlertContext representativo de UC-04 (ataque a la DB), con datos sensibles
    para ejercitar la sanitización."""
    return AlertContext(
        incident_id="INC-2026-06-27-001",
        created_at=datetime(2026, 6, 27, 12, 0, 0, tzinfo=timezone.utc),
        host=HostInfo(
            id="LIN-VICTIM-01",
            criticality=Criticality.PRODUCTION_CRITICAL,
            ip="10.0.0.22",
            os="Debian 12",
        ),
        alert_summary=AlertSummary(
            title="SELECT masivo sospechoso en la DB del banco",
            technique_mitre="T1190",
            severity_score=0.85,
            triggering_layers=[Layer.LAYER_1, Layer.LAYER_2],
            raw_alert_id="alert-uc04",
        ),
        recent_telemetry={
            "command_line": (
                "psql -U argos_ro -h 10.0.0.22 -c 'SELECT * FROM customers' password=hunter2"
            ),
            "notified": "dba@intibank.local",
        },
    )
