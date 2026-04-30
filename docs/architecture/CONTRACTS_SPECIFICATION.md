# CONTRACTS SPECIFICATION — argos_contracts module

**Document type:** Module specification (input for implementation)
**Version:** 1.0
**Status:** Approved
**Owner:** P1
**Reviewers:** P2, P3, P4
**Related:** `OPEN_QUESTIONS_RESOLUTION.md` Q4.2, `SOLUTION_ARCHITECTURE_DOCUMENT.md` §6, ADRs 0001-0006

---

## Purpose

Define every Pydantic model that crosses team boundaries — these are the "interfaces" between layers that all four team members import. Implementing this module first (Week 2, before any layer-specific code) prevents integration friction in Weeks 7-9.

**Rule:** if a class is consumed by more than one layer/owner, it lives here. If it's internal to one layer, it lives in that layer's module.

**Stack convention:** Pydantic v2 (`from pydantic import BaseModel, Field, field_validator`). Python 3.11+. Type hints mandatory. Timezone-aware datetimes (UTC).

---

## Module structure

```
argos_contracts/
├── __init__.py              # Re-exports for convenience
├── enums.py                 # All Enums shared across modules
├── alert.py                 # WazuhAlert, NormalizedAlert
├── ml_score.py              # MLScore (Layer 2 output)
├── triage.py                # AlertContext, TriageResponse (Layer 4 IO)
├── incident.py              # Incident, ApproverState (Redis state, owned by SOAR)
├── approval.py              # ApprovalRequest, ApprovalResponse (notification IO)
└── tests/
    ├── __init__.py
    └── test_contracts.py    # Validation tests for each model
```

---

## File: `enums.py`

All Enums used across multiple modules. Single source of truth.

```python
from enum import Enum


class Severity(str, Enum):
    """Severity levels for alerts and triage responses."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Tier(str, Enum):
    """Confidence tiers for alert classification (per ADR-0003)."""
    T0 = "T0"  # Critical confirmed, ≥0.95 confidence, auto-execute
    T1 = "T1"  # High confirmed, 0.80–0.95, auto-execute
    T2 = "T2"  # Medium uncertain, 0.60–0.80, awaiting human approval
    T3 = "T3"  # Low uncertain, 0.40–0.60, notification only


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
```

---

## File: `alert.py`

What flows from Wazuh into the system. Two views: raw and normalized.

```python
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field

from argos_contracts.enums import Severity, Layer


class WazuhAlert(BaseModel):
    """
    Raw alert as received from Wazuh manager. Loose schema because Wazuh's
    payload varies by rule type. Used by Detection Engineer (P3) and
    consumed by Decision Engine (P1).

    Reference: Wazuh JSON output format.
    """
    alert_id: str = Field(..., description="Unique Wazuh alert identifier")
    rule_id: int = Field(..., description="Wazuh rule ID that fired")
    rule_description: str
    rule_level: int = Field(..., ge=0, le=15, description="Wazuh severity 0-15")
    timestamp: datetime  # MUST be timezone-aware (UTC)
    agent_id: str
    agent_name: str
    agent_ip: str | None = None
    full_log: str | None = None
    decoder_name: str | None = None
    location: str | None = None
    mitre_technique_ids: list[str] = Field(
        default_factory=list,
        description="MITRE ATT&CK IDs from rule mapping, may be empty"
    )
    raw_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Full Wazuh alert dict for any field not normalized above"
    )


class NormalizedAlert(BaseModel):
    """
    Alert after Decision Engine normalizes Wazuh raw payload. This is what
    flows into tier classification and the rest of the pipeline.

    Owned by: Decision Engine (P1).
    Consumed by: ML consumer (P2 normalizes input), LLM Triage (P1 Layer 4).
    """
    alert_id: str
    source_layer: Layer
    timestamp: datetime
    host_id: str
    host_ip: str | None = None
    severity_score: float = Field(..., ge=0.0, le=1.0)
    severity_label: Severity
    technique_mitre: str | None = Field(
        None,
        description="Primary MITRE technique inferred. Validated against whitelist downstream."
    )
    triggering_rule: str | None = Field(
        None,
        description="Rule name or ML model identifier that fired"
    )
    process_info: dict[str, Any] | None = None
    file_info: dict[str, Any] | None = None
    network_info: dict[str, Any] | None = None
    raw_alert: WazuhAlert | None = Field(
        None,
        description="Reference to original raw alert for forensic trace"
    )
```

---

## File: `ml_score.py`

What the ML consumer (P2) outputs back to the SOAR pipeline.

```python
from datetime import datetime
from pydantic import BaseModel, Field


class MLFeatures(BaseModel):
    """
    Features extracted per process per 60-second window for ML scoring.
    Reference: SAD §5.2.
    """
    file_write_rate: float = Field(..., ge=0.0)
    avg_entropy: float = Field(..., ge=0.0, description="Shannon entropy of files written")
    extension_modification_ratio: float = Field(..., ge=0.0, le=1.0)
    crypto_api_calls: int = Field(..., ge=0)
    new_outbound_connections: int = Field(..., ge=0)
    cpu_burst_score: float = Field(..., ge=0.0)
    io_burst_score: float = Field(..., ge=0.0)


class MLScore(BaseModel):
    """
    Output of Layer 2 ML pipeline. Consumed by Decision Engine for
    tier classification.

    Owner: P2.
    Consumer: Decision Engine (P1).
    """
    score_id: str
    timestamp: datetime
    host_id: str
    process_id: int | None = None
    process_name: str | None = None
    isolation_forest_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Anomaly score from Isolation Forest (1.0 = anomalous)"
    )
    one_class_svm_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Anomaly score from One-Class SVM"
    )
    ensemble_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Combined ensemble score, used for tier classification"
    )
    features: MLFeatures
    model_version: str = Field(
        ...,
        description="Versioned model identifier, e.g. 'iforest-v1.2-svm-v1.0'"
    )
```

---

## File: `triage.py`

Input/output of Layer 4 LLM Triage service.

```python
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, field_validator

from argos_contracts.enums import Severity, Layer, Criticality


# MITRE ATT&CK techniques in scope (per USE_CASES + project scope).
# Hardcoded whitelist for v1. Future: load from MITRE STIX bundle dynamically.
MITRE_WHITELIST: set[str] = {
    "T1486",      # Data Encrypted for Impact
    "T1490",      # Inhibit System Recovery
    "T1083",      # File and Directory Discovery
    "T1562",      # Impair Defenses
    "T1562.001",  # Disable or Modify Tools
    "T1021",      # Remote Services
    "T1071",      # Application Layer Protocol
    "T1070",      # Indicator Removal
    "T1070.001",  # Clear Windows Event Logs
    "T1070.004",  # File Deletion
    # Extend as new use cases require
}


class HostInfo(BaseModel):
    """Host metadata included in alert context."""
    id: str
    criticality: Criticality
    ip: str | None = None
    os: str | None = None


class AlertSummary(BaseModel):
    """Compact alert summary sent to LLM."""
    title: str
    technique_mitre: str | None = None
    severity_score: float = Field(..., ge=0.0, le=1.0)
    triggering_layers: list[Layer] = Field(..., min_length=1)
    raw_alert_id: str


class AlertContext(BaseModel):
    """
    Input to the LLM Triage service. Constructed by Decision Engine
    from a NormalizedAlert + recent telemetry.

    Owner: Decision Engine (P1).
    Consumer: LLM Triage service (P1, Layer 4).

    Reference: SAD §7, ADR-0001, OPEN_QUESTIONS Q4.2.
    """
    incident_id: str = Field(
        ...,
        description="Format: INC-YYYY-MM-DD-NNN per Q4.1"
    )
    created_at: datetime
    host: HostInfo
    alert_summary: AlertSummary
    recent_telemetry: dict[str, Any] = Field(
        default_factory=dict,
        description="Open-schema dict with process_tree, network_connections, "
                    "file_modifications. Sanitization is caller's responsibility "
                    "before sending to external LLM API (per T-030 in threat model)."
    )


class TriageResponse(BaseModel):
    """
    Structured output from LLM Triage. Pydantic validation + MITRE whitelist
    are the primary defense against LLM hallucination (per SAD §12.1 R-6).

    Owner: LLM Triage service (P1).
    Consumer: Decision Engine, Streamlit Approval Console (P4).
    """
    incident_id: str
    tecnica_mitre: str = Field(
        ...,
        description="MITRE ATT&CK ID. MUST be in MITRE_WHITELIST."
    )
    confianza: float = Field(..., ge=0.0, le=1.0)
    severidad: Severity
    runbook_aplicable: str = Field(
        ...,
        min_length=10,
        description="Citation to NIST 800-61 or SANS playbook section"
    )
    accion_recomendada: str = Field(..., min_length=20)
    indicadores_correlacionar: list[str] = Field(default_factory=list)
    llm_backend: str = Field(
        ...,
        description="Identifier of backend used: 'deepseek-v3' | 'qwen2.5-72b-instruct'"
    )
    generated_at: datetime

    @field_validator("tecnica_mitre")
    @classmethod
    def validate_mitre_id(cls, v: str) -> str:
        """Reject hallucinated MITRE technique IDs not in our whitelist."""
        if v not in MITRE_WHITELIST:
            raise ValueError(
                f"MITRE technique '{v}' not in whitelist. "
                f"LLM may have hallucinated. Valid IDs: {sorted(MITRE_WHITELIST)}"
            )
        return v

    @field_validator("generated_at")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure datetime is timezone-aware (UTC convention)."""
        if v.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware (UTC)")
        return v
```

---

## File: `incident.py`

The state machine of an incident. Lives in Redis, consumed by Streamlit.

```python
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field

from argos_contracts.enums import (
    Tier, IncidentState, Layer, Severity, ApproverStatus,
    NotificationChannelType, ActionType
)
from argos_contracts.alert import NormalizedAlert
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


class ConsolidationWindow(BaseModel):
    """
    Window for collecting approver responses before applying conservative-wins.
    Reference: ADR-0006 §"For reversible actions".
    """
    started_at: datetime
    duration_seconds: int = Field(default=60)
    ended_at: datetime | None = None
    conflict_detected: bool = False


class FinalDecision(BaseModel):
    """Final decision after approval flow completes (or auto-executes)."""
    outcome: str = Field(
        ...,
        description="'EXECUTE_ISOLATION' | 'NO_ACTION' | 'REVERTED'"
    )
    policy_applied: str = Field(
        ...,
        description="'auto-execute' | 'unanimous-approve' | 'conservative-wins' | "
                    "'two-person-rule' | 'timeout-escalation'"
    )
    rationale: str
    executed_at: datetime | None = None
    execution_status: str | None = Field(
        None,
        description="'success' | 'failed' | 'partial'"
    )


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
        description="Format: INC-YYYY-MM-DD-NNN per Q4.1"
    )
    created_at: datetime
    updated_at: datetime
    tier: Tier
    state: IncidentState
    host: dict[str, Any]  # uses HostInfo-compatible structure
    alert: NormalizedAlert
    llm_analysis: TriageResponse | None = Field(
        None,
        description="None until LLM Triage service responds"
    )
    proposed_actions: list[ProposedAction]
    approvers: list[ApproverState] = Field(default_factory=list)
    consolidation_window: ConsolidationWindow | None = None
    final_decision: FinalDecision | None = None
```

---

## File: `approval.py`

What flows through the notification system (email v1, multi-channel future).

```python
from datetime import datetime
from pydantic import BaseModel, Field

from argos_contracts.enums import (
    Tier, ApprovalDecision, NotificationChannelType
)
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
        description="URL template with {token} placeholder for JWT-signed approval link"
    )


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
        description="JWT ID claim, used for replay prevention (per T-063 in threat model)"
    )
    user_agent: str | None = None
    source_ip: str | None = None
```

---

## File: `__init__.py`

Re-export commonly used models for ergonomic imports.

```python
"""
argos_contracts — Shared Pydantic models that cross team boundaries.

Usage:
    from argos_contracts import AlertContext, TriageResponse, Severity, Tier

For full module specification, see docs/architecture/CONTRACTS_SPECIFICATION.md.
"""

from argos_contracts.enums import (
    Severity,
    Tier,
    Layer,
    Criticality,
    IncidentState,
    ApprovalDecision,
    ApproverStatus,
    ActionType,
    NotificationChannelType,
)
from argos_contracts.alert import WazuhAlert, NormalizedAlert
from argos_contracts.ml_score import MLScore, MLFeatures
from argos_contracts.triage import (
    AlertContext,
    TriageResponse,
    HostInfo,
    AlertSummary,
    MITRE_WHITELIST,
)
from argos_contracts.incident import (
    Incident,
    ProposedAction,
    ApproverState,
    ConsolidationWindow,
    FinalDecision,
)
from argos_contracts.approval import ApprovalRequest, ApprovalResponse

__all__ = [
    # enums
    "Severity", "Tier", "Layer", "Criticality", "IncidentState",
    "ApprovalDecision", "ApproverStatus", "ActionType", "NotificationChannelType",
    # alert
    "WazuhAlert", "NormalizedAlert",
    # ml
    "MLScore", "MLFeatures",
    # triage
    "AlertContext", "TriageResponse", "HostInfo", "AlertSummary", "MITRE_WHITELIST",
    # incident
    "Incident", "ProposedAction", "ApproverState",
    "ConsolidationWindow", "FinalDecision",
    # approval
    "ApprovalRequest", "ApprovalResponse",
]

__version__ = "1.0.0"
```

---

## Tests required

`tests/test_contracts.py` must include:

### Per-model coverage (minimum)

For each model, test:
1. Valid construction with all fields.
2. Valid construction with only required fields (defaults work).
3. Invalid construction raises `ValidationError`:
   - Wrong types.
   - Out-of-range numerics (severity_score > 1.0, etc.).
   - Empty strings where `min_length` enforced.
   - Naive datetimes where `tzinfo` required.
   - Pattern mismatches (incident_id format).

### Critical security validators (must have explicit tests)

- **`TriageResponse.tecnica_mitre` whitelist:** test with valid ID (passes), test with hallucinated ID (rejects), test case sensitivity.
- **`TriageResponse.generated_at` timezone-aware:** test with naive datetime (rejects), test with UTC datetime (passes).
- **`Incident.incident_id` regex:** test valid format passes, test invalid formats reject.
- **`ApprovalRequest.recipients` non-empty:** test with empty list (rejects), with ≥1 recipient (passes).

### Roundtrip tests

For Incident (which is the most complex), test:
- Serialize to JSON and deserialize back, equality preserved.
- All `datetime` fields preserve timezone info through roundtrip.

---

## Acceptance criteria

The module is considered done when:

1. All 6 model files implemented per this specification.
2. `from argos_contracts import *` works for any of the re-exported names.
3. `pytest tests/test_contracts.py -v` passes 100% (target ≥30 tests).
4. `mypy argos_contracts/` passes with no errors (strict mode).
5. Each model has a docstring explaining purpose, owner, and consumer.
6. README.md at module root with one-paragraph summary + link to this spec.

---

## Conventions

- **Naming:** snake_case for fields. Spanish names (`tecnica_mitre`, `confianza`) preserved where they originate from the LLM output schema (per Q4.2). English elsewhere.
- **Datetime:** all timezone-aware UTC. Validators enforce on input.
- **Optional vs required:** required by default. Use `| None = None` only when truly optional.
- **`dict[str, Any]`:** used sparingly for open-schema fields (raw_data, recent_telemetry). Document why each instance is necessary in its docstring.
- **No business logic:** these are data classes. No methods other than validators. No I/O. No side effects.
