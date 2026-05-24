"""All Enums shared across argos_contracts modules. Single source of truth."""

from enum import Enum


class Severity(str, Enum):
    """Severity levels for alerts and triage responses."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Tier(str, Enum):
    """Confidence tiers for alert classification (per ADR-0003).

    Threshold values (>=0.95, 0.80-0.95, 0.60-0.80, 0.40-0.60) are
    preliminary working values pending empirical calibration per Q5
    of OPEN_QUESTIONS_RESOLUTION.md.
    """

    T0 = "T0"  # Critical confirmed, auto-execute
    T1 = "T1"  # High confirmed, auto-execute
    T2 = "T2"  # Medium uncertain, awaiting human approval
    T3 = "T3"  # Low uncertain, notification only


class Layer(str, Enum):
    """Detection layers that can fire alerts."""

    LAYER_1 = "layer_1"  # Sigma rules
    LAYER_2 = "layer_2"  # ML anomaly detection
    LAYER_3 = "layer_3"  # Canary deception


class Criticality(str, Enum):
    """Host criticality classification (per ADR-0003 + Q2 of OPEN_QUESTIONS)."""

    STANDARD = "standard"
    PRODUCTION_CRITICAL = "production_critical"  # triggers two-person rule


class IncidentState(str, Enum):
    """State machine values for incident lifecycle (per SAD §6.5)."""

    RECEIVED = "received"
    AWAITING_APPROVAL = "awaiting_approval"
    PENDING_EXECUTION = "pending_execution"
    PENDING_REJECTION = "pending_rejection"
    EXECUTING = "executing"
    EXECUTED = "executed"
    REVERTED = "reverted"
    REJECTED = "rejected"
    TIMEOUT_ESCALATED = "timeout_escalated"


class ApprovalDecision(str, Enum):
    """Possible decisions an approver can give."""

    APPROVE = "approve"
    REJECT = "reject"
    REVERT = "revert"  # post-facto reversion of an executed action


class ApproverStatus(str, Enum):
    """Status of an individual approver's response."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class ActionType(str, Enum):
    """Types of automated response actions."""

    HOST_ISOLATION = "host_isolation"
    PROCESS_KILL = "process_kill"
    DISK_SNAPSHOT = "disk_snapshot"
    PROCESS_THROTTLE = "process_throttle"
    NOTIFICATION = "notification"


class NotificationChannelType(str, Enum):
    """Channels available for sending approval requests (per ADR-0007 v2).

    Channel chain (T2 / production-critical):
    - TELEGRAM   → primary, t=0, with inline JWT buttons
    - DISCORD    → public visibility in team server, t=0
    - TWILIO_VOICE → escalation, t=60s if no response, DTMF input
    - EMAIL      → post-facto summary only, never in critical path
    """

    TELEGRAM = "telegram"
    DISCORD = "discord"
    TWILIO_VOICE = "twilio_voice"
    EMAIL = "email"
