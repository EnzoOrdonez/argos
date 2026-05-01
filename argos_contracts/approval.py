"""Approval contracts. What flows through the notification system (email v1, multi-channel future)."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from argos_contracts._validators import ensure_tz_aware
from argos_contracts.enums import ApprovalDecision, NotificationChannelType, Tier
from argos_contracts.incident import ProposedAction
from argos_contracts.triage import TriageResponse


class ApprovalRequest(BaseModel):
    """
    Request sent to approvers via notification channel(s).
    Reference: ADR-0003, ADR-0005.

    Owner: Notification service (P1).
    Consumer: Email/Slack/Telegram channel implementations.
    """

    incident_id: str
    tier: Tier
    alert_summary: str
    llm_analysis: TriageResponse | None = None
    proposed_actions: list[ProposedAction]
    recipients: list[str] = Field(..., min_length=1)
    timeout_seconds: int = Field(default=180, description="3 minutes per ADR-0003 Q9")
    created_at: datetime
    approval_url_template: str = Field(
        ...,
        description="URL template with {token} placeholder for JWT-signed approval link",
    )

    _validate_created_at = field_validator("created_at")(ensure_tz_aware)


class ApprovalResponse(BaseModel):
    """
    Response from an approver, validated server-side.
    Reference: ADR-0006.

    Owner: Approval API (P1).
    Consumer: Decision Engine, Audit log.
    """

    incident_id: str
    responder_email: str
    decision: ApprovalDecision
    timestamp: datetime
    channel: NotificationChannelType
    token_jti: str = Field(
        ...,
        description="JWT ID claim, used for replay prevention (per T-063 in threat model)",
    )
    user_agent: str | None = None
    source_ip: str | None = None

    _validate_timestamp = field_validator("timestamp")(ensure_tz_aware)
