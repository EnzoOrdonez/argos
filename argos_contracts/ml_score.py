"""ML scoring contracts. What the Layer 2 ML consumer (P2) outputs to the SOAR pipeline."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from argos_contracts._validators import ensure_tz_aware


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

    # Disable Pydantic v2 protected namespace check so that the spec field
    # `model_version` does not trigger a warning. The contract field name is
    # mandated by CONTRACTS_SPECIFICATION.md and intentionally preserved.
    model_config = ConfigDict(protected_namespaces=())

    score_id: str
    timestamp: datetime
    host_id: str
    process_id: int | None = None
    process_name: str | None = None
    isolation_forest_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Anomaly score from Isolation Forest (1.0 = anomalous)",
    )
    one_class_svm_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Anomaly score from One-Class SVM",
    )
    ensemble_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Combined ensemble score, used for tier classification",
    )
    features: MLFeatures
    model_version: str = Field(
        ...,
        description="Versioned model identifier, e.g. 'iforest-v1.2-svm-v1.0'",
    )

    _validate_timestamp = field_validator("timestamp")(ensure_tz_aware)
