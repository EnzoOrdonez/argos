"""All Enums shared across argos_contracts modules. Single source of truth."""

from enum import Enum


class Severity(str, Enum):
    """Severity levels for alerts and triage responses."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Tier(str, Enum):
    """Confidence tiers for alert classification (per ADR-0003)."""

    T0 = "T0"  # Critical confirmed, >=0.95 confidence, auto-execute
    T1 = "T1"  # High confirmed, 0.80-0.95, auto-execute
    T2 = "T2"  # Medium uncertain, 0.60-0.80, awaiting human approval
    T3 = "T3"  # Low uncertain, 0.40-0.60, notification only


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
    """Channels available for sending approval requests (per ADR-0005)."""

    EMAIL = "email"
    SLACK = "slack"  # future
    TELEGRAM = "telegram"  # future
    TEAMS = "teams"  # future
