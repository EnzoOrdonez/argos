"""Alert contracts. What flows from Wazuh into the system: raw + normalized views."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from argos_contracts._validators import ensure_tz_aware
from argos_contracts.enums import Layer, Severity


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
        description="MITRE ATT&CK IDs from rule mapping, may be empty",
    )
    raw_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Full Wazuh alert dict for any field not normalized above",
    )

    _validate_timestamp = field_validator("timestamp")(ensure_tz_aware)


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
        description="Primary MITRE technique inferred. Validated against whitelist downstream.",
    )
    triggering_rule: str | None = Field(
        None,
        description="Rule name or ML model identifier that fired",
    )
    process_info: dict[str, Any] | None = None
    file_info: dict[str, Any] | None = None
    network_info: dict[str, Any] | None = None
    raw_alert: WazuhAlert | None = Field(
        None,
        description="Reference to original raw alert for forensic trace",
    )

    _validate_timestamp = field_validator("timestamp")(ensure_tz_aware)
