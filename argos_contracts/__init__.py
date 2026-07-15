"""
argos_contracts - Shared Pydantic models that cross team boundaries.

Usage:
    from argos_contracts import AlertContext, TriageResponse, Severity, Tier

For full module specification, see docs/architecture/CONTRACTS_SPECIFICATION.md.
"""

from argos_contracts.alert import NormalizedAlert, WazuhAlert
from argos_contracts.approval import ApprovalRequest, ApprovalResponse
from argos_contracts.enums import (
    ActionType,
    ApprovalDecision,
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
from argos_contracts.ml_score import MLFeatures, MLScore
from argos_contracts.triage import (
    MITRE_WHITELIST,
    AlertContext,
    AlertSummary,
    HostInfo,
    TriageResponse,
)

__all__ = [  # noqa: RUF022  agrupado por módulo a propósito, no alfabético
    # enums
    "Severity",
    "Tier",
    "Layer",
    "Criticality",
    "IncidentState",
    "ApprovalDecision",
    "ApproverStatus",
    "ActionType",
    "NotificationChannelType",
    # alert
    "WazuhAlert",
    "NormalizedAlert",
    # ml
    "MLScore",
    "MLFeatures",
    # triage
    "AlertContext",
    "TriageResponse",
    "HostInfo",
    "AlertSummary",
    "MITRE_WHITELIST",
    # incident
    "Incident",
    "ProposedAction",
    "ApproverState",
    "ConsolidationWindow",
    "FinalDecision",
    # approval
    "ApprovalRequest",
    "ApprovalResponse",
]

__version__ = "1.1.0"
