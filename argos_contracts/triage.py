"""Triage contracts. Input/output of the Layer 4 LLM Triage service."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from argos_contracts._mitre_data import MITRE_WHITELIST
from argos_contracts._validators import ensure_tz_aware
from argos_contracts.enums import Criticality, Layer, Severity

__all__ = [
    "MITRE_WHITELIST",
    "AlertContext",
    "AlertSummary",
    "HostInfo",
    "TriageResponse",
]


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
        description="Format: INC-YYYY-MM-DD-NNN per Q4.1",
    )
    created_at: datetime
    host: HostInfo
    alert_summary: AlertSummary
    recent_telemetry: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Open-schema dict with process_tree, network_connections, "
            "file_modifications. Sanitization is caller's responsibility "
            "before sending to external LLM API (per T-030 in threat model)."
        ),
    )

    _validate_created_at = field_validator("created_at")(ensure_tz_aware)


class TriageResponse(BaseModel):
    """
    Structured output from LLM Triage. Pydantic validation + MITRE whitelist
    are the primary defense against LLM hallucination (per SAD section 12.1 R-6).

    Owner: LLM Triage service (P1).
    Consumer: Decision Engine, Streamlit Approval Console (P4).
    """

    incident_id: str
    tecnica_mitre: str = Field(
        ...,
        description="MITRE ATT&CK ID. MUST be in MITRE_WHITELIST.",
    )
    confianza: float = Field(..., ge=0.0, le=1.0)
    severidad: Severity
    runbook_aplicable: str = Field(
        ...,
        min_length=10,
        description="Citation to NIST 800-61 or SANS playbook section",
    )
    accion_recomendada: str = Field(..., min_length=20)
    indicadores_correlacionar: list[str] = Field(default_factory=list)
    llm_backend: str = Field(
        ...,
        description=(
            "Identifier of backend used, e.g. 'openai/gpt-oss-120b' (NVIDIA NIM) "
            "or 'llama-3.1-8b-local' (per ADR-0001 v3)"
        ),
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

    _validate_generated_at = field_validator("generated_at")(ensure_tz_aware)
