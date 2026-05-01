"""Incident state machine. Lives in Redis, consumed by Streamlit, persisted to OpenSearch."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from argos_contracts._validators import ensure_tz_aware
from argos_contracts.alert import NormalizedAlert
from argos_contracts.enums import (
    ActionType,
    ApproverStatus,
    IncidentState,
    NotificationChannelType,
    Tier,
)
from argos_contracts.triage import TriageResponse


class ProposedAction(BaseModel):
    """An automated action proposed by the Decision Engine."""

    id: str = Field(..., description="Action ID, e.g. 'act-001'")
    type: ActionType
    target: str = Field(..., description="Host ID or process ID, depending on type")
    reversible: bool
    parameters: dict[str, Any] = Field(default_factory=dict)


class ApproverState(BaseModel):
    """
    State of one approver in a multi-recipient approval flow.
    Reference: ADR-0006 split-brain resolution.
    """

    email: str
    role: str = Field(..., description="e.g. 'it_lead', 'analyst', 'ciso'")
    status: ApproverStatus = ApproverStatus.PENDING
    responded_at: datetime | None = None
    latency_seconds: float | None = None
    channel: NotificationChannelType = NotificationChannelType.EMAIL

    _validate_responded_at = field_validator("responded_at")(ensure_tz_aware)


class ConsolidationWindow(BaseModel):
    """
    Window for collecting approver responses before applying conservative-wins.
    Reference: ADR-0006 §"For reversible actions".
    """

    started_at: datetime
    duration_seconds: int = Field(default=60)
    ended_at: datetime | None = None
    conflict_detected: bool = False

    _validate_dts = field_validator("started_at", "ended_at")(ensure_tz_aware)


class FinalDecision(BaseModel):
    """Final decision after approval flow completes (or auto-executes)."""

    outcome: str = Field(
        ...,
        description="'EXECUTE_ISOLATION' | 'NO_ACTION' | 'REVERTED'",
    )
    policy_applied: str = Field(
        ...,
        description=(
            "'auto-execute' | 'unanimous-approve' | 'conservative-wins' | "
            "'two-person-rule' | 'timeout-escalation'"
        ),
    )
    rationale: str
    executed_at: datetime | None = None
    execution_status: str | None = Field(
        None,
        description="'success' | 'failed' | 'partial'",
    )

    _validate_executed_at = field_validator("executed_at")(ensure_tz_aware)


class Incident(BaseModel):
    """
    Top-level incident state. This is what Decision Engine writes to Redis,
    Streamlit reads, and audit log persists to OpenSearch.

    Owner: Decision Engine (P1).
    Consumers: Streamlit Approval Console (P4), Audit Log (everyone).

    Reference: OPEN_QUESTIONS_RESOLUTION.md Q4.2 (canonical schema).
    """

    schema_version: str = Field(default="1.0")
    incident_id: str = Field(
        ...,
        pattern=r"^INC-\d{4}-\d{2}-\d{2}-\d{3}$",
        description="Format: INC-YYYY-MM-DD-NNN per Q4.1",
    )
    created_at: datetime
    updated_at: datetime
    tier: Tier
    state: IncidentState
    host: dict[str, Any]  # uses HostInfo-compatible structure
    alert: NormalizedAlert
    llm_analysis: TriageResponse | None = Field(
        None,
        description="None until LLM Triage service responds",
    )
    proposed_actions: list[ProposedAction]
    approvers: list[ApproverState] = Field(default_factory=list)
    consolidation_window: ConsolidationWindow | None = None
    final_decision: FinalDecision | None = None

    _validate_dts = field_validator("created_at", "updated_at")(ensure_tz_aware)
