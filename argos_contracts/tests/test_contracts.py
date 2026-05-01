"""Validation tests for argos_contracts Pydantic models.

Coverage strategy (per CONTRACTS_SPECIFICATION.md "Tests required"):
    - Valid full + valid required-only construction per model.
    - Invalid construction raises ValidationError (wrong types, out-of-range,
      empty strings on min_length, naive datetimes, pattern mismatch).
    - Critical security validators have explicit dedicated tests.
    - Roundtrip JSON serialization for the most complex model (Incident).
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from argos_contracts import (
    MITRE_WHITELIST,
    ActionType,
    AlertContext,
    AlertSummary,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResponse,
    ApproverState,
    ApproverStatus,
    ConsolidationWindow,
    Criticality,
    FinalDecision,
    HostInfo,
    Incident,
    IncidentState,
    Layer,
    MLFeatures,
    MLScore,
    NormalizedAlert,
    NotificationChannelType,
    ProposedAction,
    Severity,
    Tier,
    TriageResponse,
    WazuhAlert,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UTC_NOW = datetime(2026, 4, 30, 15, 32, 14, tzinfo=timezone.utc)
UTC_LATER = datetime(2026, 4, 30, 15, 33, 15, tzinfo=timezone.utc)
NAIVE_DT = datetime(2026, 4, 30, 15, 32, 14)  # no tzinfo, used by tz-aware enforcement tests


def _wazuh_alert() -> WazuhAlert:
    return WazuhAlert(
        alert_id="wazuh-alert-12345",
        rule_id=100002,
        rule_description="vssadmin delete shadows detected",
        rule_level=12,
        timestamp=UTC_NOW,
        agent_id="001",
        agent_name="WIN-VICTIM-01",
    )


def _normalized_alert() -> NormalizedAlert:
    return NormalizedAlert(
        alert_id="wazuh-alert-12345",
        source_layer=Layer.LAYER_1,
        timestamp=UTC_NOW,
        host_id="WIN-VICTIM-01",
        severity_score=0.92,
        severity_label=Severity.CRITICAL,
        technique_mitre="T1490",
        triggering_rule="sigma_vssadmin_delete_shadows",
    )


def _ml_features() -> MLFeatures:
    return MLFeatures(
        file_write_rate=120.0,
        avg_entropy=7.4,
        extension_modification_ratio=0.85,
        crypto_api_calls=42,
        new_outbound_connections=3,
        cpu_burst_score=0.7,
        io_burst_score=0.9,
    )


def _triage_response(incident_id: str = "INC-2026-04-30-001") -> TriageResponse:
    return TriageResponse(
        incident_id=incident_id,
        tecnica_mitre="T1486",
        confianza=0.92,
        severidad=Severity.CRITICAL,
        runbook_aplicable="NIST 800-61 §3.4 Containment, Eradication, Recovery",
        accion_recomendada="Isolate host, capture memory, preserve disk snapshot before remediation",
        indicadores_correlacionar=["vssadmin.exe", "high entropy writes"],
        llm_backend="deepseek-v3",
        generated_at=UTC_NOW,
    )


def _proposed_action() -> ProposedAction:
    return ProposedAction(
        id="act-001",
        type=ActionType.HOST_ISOLATION,
        target="WIN-VICTIM-01",
        reversible=True,
    )


def _incident() -> Incident:
    return Incident(
        incident_id="INC-2026-04-30-001",
        created_at=UTC_NOW,
        updated_at=UTC_LATER,
        tier=Tier.T0,
        state=IncidentState.EXECUTED,
        host={
            "id": "WIN-VICTIM-01",
            "criticality": "standard",
            "ip": "10.0.0.21",
            "os": "Windows 10",
        },
        alert=_normalized_alert(),
        llm_analysis=_triage_response(),
        proposed_actions=[_proposed_action()],
        approvers=[
            ApproverState(
                email="enzo@demo.local",
                role="it_lead",
                status=ApproverStatus.APPROVED,
                responded_at=UTC_LATER,
                latency_seconds=18.0,
            )
        ],
        consolidation_window=ConsolidationWindow(
            started_at=UTC_NOW, duration_seconds=60
        ),
        final_decision=FinalDecision(
            outcome="EXECUTE_ISOLATION",
            policy_applied="conservative-wins",
            rationale="2 approve, 1 reject - conservative-wins applied per ADR-0006",
            executed_at=UTC_LATER,
            execution_status="success",
        ),
    )


# ---------------------------------------------------------------------------
# WazuhAlert
# ---------------------------------------------------------------------------


def test_wazuh_alert_valid_full() -> None:
    alert = WazuhAlert(
        alert_id="a1",
        rule_id=100,
        rule_description="desc",
        rule_level=10,
        timestamp=UTC_NOW,
        agent_id="001",
        agent_name="WIN",
        agent_ip="10.0.0.1",
        full_log="...",
        decoder_name="windows",
        location="EventChannel",
        mitre_technique_ids=["T1486"],
        raw_data={"k": "v"},
    )
    assert alert.rule_level == 10
    assert alert.mitre_technique_ids == ["T1486"]


def test_wazuh_alert_minimal_required() -> None:
    alert = _wazuh_alert()
    assert alert.agent_ip is None
    assert alert.mitre_technique_ids == []
    assert alert.raw_data == {}


def test_wazuh_alert_rule_level_out_of_range_rejects() -> None:
    with pytest.raises(ValidationError):
        WazuhAlert(
            alert_id="a1",
            rule_id=100,
            rule_description="d",
            rule_level=99,  # >15 invalid
            timestamp=UTC_NOW,
            agent_id="001",
            agent_name="WIN",
        )


# ---------------------------------------------------------------------------
# NormalizedAlert
# ---------------------------------------------------------------------------


def test_normalized_alert_valid() -> None:
    n = _normalized_alert()
    assert n.source_layer == Layer.LAYER_1
    assert n.severity_label == Severity.CRITICAL


def test_normalized_alert_severity_score_out_of_range_rejects() -> None:
    with pytest.raises(ValidationError):
        NormalizedAlert(
            alert_id="a1",
            source_layer=Layer.LAYER_2,
            timestamp=UTC_NOW,
            host_id="h",
            severity_score=1.5,  # >1.0 invalid
            severity_label=Severity.HIGH,
        )


def test_normalized_alert_minimal_required() -> None:
    n = NormalizedAlert(
        alert_id="a1",
        source_layer=Layer.LAYER_3,
        timestamp=UTC_NOW,
        host_id="h",
        severity_score=0.5,
        severity_label=Severity.MEDIUM,
    )
    assert n.process_info is None
    assert n.raw_alert is None


# ---------------------------------------------------------------------------
# MLFeatures
# ---------------------------------------------------------------------------


def test_ml_features_valid() -> None:
    f = _ml_features()
    assert f.crypto_api_calls == 42


def test_ml_features_negative_rate_rejects() -> None:
    with pytest.raises(ValidationError):
        MLFeatures(
            file_write_rate=-1.0,  # ge=0.0 violated
            avg_entropy=7.0,
            extension_modification_ratio=0.5,
            crypto_api_calls=10,
            new_outbound_connections=1,
            cpu_burst_score=0.5,
            io_burst_score=0.5,
        )


def test_ml_features_extension_ratio_above_one_rejects() -> None:
    with pytest.raises(ValidationError):
        MLFeatures(
            file_write_rate=10.0,
            avg_entropy=7.0,
            extension_modification_ratio=1.5,  # le=1.0 violated
            crypto_api_calls=10,
            new_outbound_connections=1,
            cpu_burst_score=0.5,
            io_burst_score=0.5,
        )


# ---------------------------------------------------------------------------
# MLScore
# ---------------------------------------------------------------------------


def test_ml_score_valid() -> None:
    s = MLScore(
        score_id="s1",
        timestamp=UTC_NOW,
        host_id="h",
        process_id=1234,
        process_name="ransom.exe",
        isolation_forest_score=0.91,
        one_class_svm_score=0.88,
        ensemble_score=0.90,
        features=_ml_features(),
        model_version="iforest-v1.2-svm-v1.0",
    )
    assert s.ensemble_score == 0.90


def test_ml_score_isolation_forest_score_out_of_range_rejects() -> None:
    with pytest.raises(ValidationError):
        MLScore(
            score_id="s1",
            timestamp=UTC_NOW,
            host_id="h",
            isolation_forest_score=1.2,  # >1.0
            one_class_svm_score=0.5,
            ensemble_score=0.5,
            features=_ml_features(),
            model_version="v1",
        )


# ---------------------------------------------------------------------------
# HostInfo
# ---------------------------------------------------------------------------


def test_host_info_valid() -> None:
    h = HostInfo(id="WIN-1", criticality=Criticality.STANDARD, ip="10.0.0.1", os="Windows 10")
    assert h.criticality == Criticality.STANDARD


def test_host_info_missing_required_rejects() -> None:
    with pytest.raises(ValidationError):
        HostInfo(criticality=Criticality.STANDARD)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# AlertSummary
# ---------------------------------------------------------------------------


def test_alert_summary_valid() -> None:
    s = AlertSummary(
        title="Suspicious vssadmin",
        technique_mitre="T1490",
        severity_score=0.85,
        triggering_layers=[Layer.LAYER_1, Layer.LAYER_2],
        raw_alert_id="wazuh-12345",
    )
    assert len(s.triggering_layers) == 2


def test_alert_summary_empty_layers_rejects() -> None:
    with pytest.raises(ValidationError):
        AlertSummary(
            title="x",
            severity_score=0.5,
            triggering_layers=[],  # min_length=1 violated
            raw_alert_id="r1",
        )


# ---------------------------------------------------------------------------
# AlertContext
# ---------------------------------------------------------------------------


def test_alert_context_valid() -> None:
    ctx = AlertContext(
        incident_id="INC-2026-04-30-001",
        created_at=UTC_NOW,
        host=HostInfo(id="WIN-1", criticality=Criticality.STANDARD),
        alert_summary=AlertSummary(
            title="t",
            severity_score=0.9,
            triggering_layers=[Layer.LAYER_3],
            raw_alert_id="r1",
        ),
        recent_telemetry={"process_tree": []},
    )
    assert ctx.recent_telemetry == {"process_tree": []}


def test_alert_context_default_telemetry_empty_dict() -> None:
    ctx = AlertContext(
        incident_id="INC-2026-04-30-001",
        created_at=UTC_NOW,
        host=HostInfo(id="WIN-1", criticality=Criticality.STANDARD),
        alert_summary=AlertSummary(
            title="t",
            severity_score=0.9,
            triggering_layers=[Layer.LAYER_3],
            raw_alert_id="r1",
        ),
    )
    assert ctx.recent_telemetry == {}


# ---------------------------------------------------------------------------
# TriageResponse — critical security validators
# ---------------------------------------------------------------------------


def test_triage_response_valid() -> None:
    r = _triage_response()
    assert r.tecnica_mitre == "T1486"
    assert r.severidad == Severity.CRITICAL


def test_triage_response_all_whitelisted_mitre_ids_pass() -> None:
    """Every ID in MITRE_WHITELIST must construct successfully."""
    for technique in MITRE_WHITELIST:
        r = TriageResponse(
            incident_id="INC-2026-04-30-001",
            tecnica_mitre=technique,
            confianza=0.5,
            severidad=Severity.MEDIUM,
            runbook_aplicable="NIST 800-61 §3.4",
            accion_recomendada="Investigate further with full forensic context",
            llm_backend="deepseek-v3",
            generated_at=UTC_NOW,
        )
        assert r.tecnica_mitre == technique


def test_triage_response_hallucinated_mitre_id_rejects() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TriageResponse(
            incident_id="INC-2026-04-30-001",
            tecnica_mitre="T9999",  # not in whitelist
            confianza=0.92,
            severidad=Severity.CRITICAL,
            runbook_aplicable="NIST 800-61 §3.4",
            accion_recomendada="Isolate host immediately and preserve memory",
            llm_backend="deepseek-v3",
            generated_at=UTC_NOW,
        )
    assert "not in whitelist" in str(exc_info.value)


def test_triage_response_mitre_id_case_sensitivity() -> None:
    """Lowercase MITRE IDs must be rejected (whitelist is case-sensitive)."""
    with pytest.raises(ValidationError):
        TriageResponse(
            incident_id="INC-2026-04-30-001",
            tecnica_mitre="t1486",  # lowercase, not in whitelist
            confianza=0.92,
            severidad=Severity.CRITICAL,
            runbook_aplicable="NIST 800-61 §3.4",
            accion_recomendada="Isolate host immediately and preserve memory",
            llm_backend="deepseek-v3",
            generated_at=UTC_NOW,
        )


def test_triage_response_naive_datetime_rejects() -> None:
    naive = datetime(2026, 4, 30, 15, 32, 14)  # no tzinfo
    with pytest.raises(ValidationError) as exc_info:
        TriageResponse(
            incident_id="INC-2026-04-30-001",
            tecnica_mitre="T1486",
            confianza=0.92,
            severidad=Severity.CRITICAL,
            runbook_aplicable="NIST 800-61 §3.4",
            accion_recomendada="Isolate host immediately and preserve memory",
            llm_backend="deepseek-v3",
            generated_at=naive,
        )
    assert "timezone-aware" in str(exc_info.value)


def test_triage_response_runbook_too_short_rejects() -> None:
    with pytest.raises(ValidationError):
        TriageResponse(
            incident_id="INC-2026-04-30-001",
            tecnica_mitre="T1486",
            confianza=0.92,
            severidad=Severity.CRITICAL,
            runbook_aplicable="too",  # min_length=10
            accion_recomendada="Isolate host immediately and preserve memory",
            llm_backend="deepseek-v3",
            generated_at=UTC_NOW,
        )


def test_triage_response_action_too_short_rejects() -> None:
    with pytest.raises(ValidationError):
        TriageResponse(
            incident_id="INC-2026-04-30-001",
            tecnica_mitre="T1486",
            confianza=0.92,
            severidad=Severity.CRITICAL,
            runbook_aplicable="NIST 800-61 §3.4 Containment",
            accion_recomendada="too short",  # min_length=20
            llm_backend="deepseek-v3",
            generated_at=UTC_NOW,
        )


def test_triage_response_confianza_out_of_range_rejects() -> None:
    with pytest.raises(ValidationError):
        TriageResponse(
            incident_id="INC-2026-04-30-001",
            tecnica_mitre="T1486",
            confianza=1.5,  # >1.0
            severidad=Severity.CRITICAL,
            runbook_aplicable="NIST 800-61 §3.4 Containment",
            accion_recomendada="Isolate host immediately and preserve memory",
            llm_backend="deepseek-v3",
            generated_at=UTC_NOW,
        )


# ---------------------------------------------------------------------------
# ProposedAction
# ---------------------------------------------------------------------------


def test_proposed_action_valid() -> None:
    a = _proposed_action()
    assert a.reversible is True
    assert a.parameters == {}


def test_proposed_action_missing_required_rejects() -> None:
    with pytest.raises(ValidationError):
        ProposedAction(  # type: ignore[call-arg]
            id="act-001",
            type=ActionType.HOST_ISOLATION,
            reversible=True,
        )  # missing target


# ---------------------------------------------------------------------------
# ApproverState
# ---------------------------------------------------------------------------


def test_approver_state_default_pending() -> None:
    a = ApproverState(email="x@y.local", role="analyst")
    assert a.status == ApproverStatus.PENDING
    assert a.channel == NotificationChannelType.EMAIL
    assert a.responded_at is None


def test_approver_state_with_response() -> None:
    a = ApproverState(
        email="x@y.local",
        role="analyst",
        status=ApproverStatus.APPROVED,
        responded_at=UTC_LATER,
        latency_seconds=18.5,
    )
    assert a.status == ApproverStatus.APPROVED


# ---------------------------------------------------------------------------
# ConsolidationWindow
# ---------------------------------------------------------------------------


def test_consolidation_window_default_duration() -> None:
    w = ConsolidationWindow(started_at=UTC_NOW)
    assert w.duration_seconds == 60
    assert w.conflict_detected is False


def test_consolidation_window_with_conflict() -> None:
    w = ConsolidationWindow(
        started_at=UTC_NOW,
        ended_at=UTC_LATER,
        conflict_detected=True,
    )
    assert w.conflict_detected is True


# ---------------------------------------------------------------------------
# FinalDecision
# ---------------------------------------------------------------------------


def test_final_decision_valid() -> None:
    d = FinalDecision(
        outcome="EXECUTE_ISOLATION",
        policy_applied="conservative-wins",
        rationale="2 approve vs 1 reject",
        executed_at=UTC_LATER,
        execution_status="success",
    )
    assert d.outcome == "EXECUTE_ISOLATION"


# ---------------------------------------------------------------------------
# Incident — pattern, roundtrip, tz preservation
# ---------------------------------------------------------------------------


def test_incident_valid_full_construction() -> None:
    i = _incident()
    assert i.tier == Tier.T0
    assert i.state == IncidentState.EXECUTED
    assert i.schema_version == "1.0"


def test_incident_id_pattern_valid() -> None:
    i = _incident()
    assert i.incident_id == "INC-2026-04-30-001"


@pytest.mark.parametrize(
    "bad_id",
    [
        "INC-2026-04-30-1",  # NNN must be 3 digits
        "INC-26-04-30-001",  # YYYY must be 4 digits
        "INC-2026-4-30-001",  # MM must be 2 digits
        "inc-2026-04-30-001",  # lowercase prefix
        "INC-2026-04-30",  # missing sequence
        "RANDOM-STRING",  # totally wrong
    ],
)
def test_incident_id_pattern_invalid_rejects(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        Incident(
            incident_id=bad_id,
            created_at=UTC_NOW,
            updated_at=UTC_LATER,
            tier=Tier.T0,
            state=IncidentState.RECEIVED,
            host={"id": "h"},
            alert=_normalized_alert(),
            proposed_actions=[_proposed_action()],
        )


def test_incident_json_roundtrip_preserves_fields() -> None:
    original = _incident()
    serialized = original.model_dump_json()
    restored = Incident.model_validate_json(serialized)
    assert restored == original
    assert restored.tier == original.tier
    assert restored.final_decision == original.final_decision


def test_incident_datetime_tz_preserved_through_roundtrip() -> None:
    original = _incident()
    restored = Incident.model_validate_json(original.model_dump_json())
    assert restored.created_at.tzinfo is not None
    assert restored.updated_at.tzinfo is not None
    assert restored.created_at == UTC_NOW
    assert restored.updated_at == UTC_LATER
    assert restored.llm_analysis is not None
    assert restored.llm_analysis.generated_at.tzinfo is not None


def test_incident_minimal_required_no_optional_blocks() -> None:
    i = Incident(
        incident_id="INC-2026-04-30-005",
        created_at=UTC_NOW,
        updated_at=UTC_NOW,
        tier=Tier.T3,
        state=IncidentState.RECEIVED,
        host={"id": "h"},
        alert=_normalized_alert(),
        proposed_actions=[],
    )
    assert i.llm_analysis is None
    assert i.consolidation_window is None
    assert i.final_decision is None
    assert i.approvers == []


# ---------------------------------------------------------------------------
# ApprovalRequest
# ---------------------------------------------------------------------------


def test_approval_request_valid() -> None:
    r = ApprovalRequest(
        incident_id="INC-2026-04-30-001",
        tier=Tier.T2,
        alert_summary="Suspicious activity on WIN-VICTIM-01",
        llm_analysis=_triage_response(),
        proposed_actions=[_proposed_action()],
        recipients=["enzo@demo.local", "p2@demo.local"],
        created_at=UTC_NOW,
        approval_url_template="https://argos.local/approve/{token}",
    )
    assert r.timeout_seconds == 180
    assert len(r.recipients) == 2


def test_approval_request_empty_recipients_rejects() -> None:
    with pytest.raises(ValidationError):
        ApprovalRequest(
            incident_id="INC-2026-04-30-001",
            tier=Tier.T2,
            alert_summary="x",
            proposed_actions=[],
            recipients=[],  # min_length=1 violated
            created_at=UTC_NOW,
            approval_url_template="https://x/{token}",
        )


def test_approval_request_default_timeout_180_seconds() -> None:
    r = ApprovalRequest(
        incident_id="INC-2026-04-30-001",
        tier=Tier.T2,
        alert_summary="x",
        proposed_actions=[],
        recipients=["a@b.local"],
        created_at=UTC_NOW,
        approval_url_template="https://x/{token}",
    )
    assert r.timeout_seconds == 180


# ---------------------------------------------------------------------------
# ApprovalResponse
# ---------------------------------------------------------------------------


def test_approval_response_valid_approve() -> None:
    r = ApprovalResponse(
        incident_id="INC-2026-04-30-001",
        responder_email="enzo@demo.local",
        decision=ApprovalDecision.APPROVE,
        timestamp=UTC_NOW,
        channel=NotificationChannelType.EMAIL,
        token_jti="jwt-id-abc",
    )
    assert r.decision == ApprovalDecision.APPROVE


def test_approval_response_decision_revert_supported() -> None:
    r = ApprovalResponse(
        incident_id="INC-2026-04-30-001",
        responder_email="enzo@demo.local",
        decision=ApprovalDecision.REVERT,
        timestamp=UTC_NOW,
        channel=NotificationChannelType.EMAIL,
        token_jti="jwt-id-xyz",
    )
    assert r.decision == ApprovalDecision.REVERT


def test_approval_response_invalid_decision_string_rejects() -> None:
    with pytest.raises(ValidationError):
        ApprovalResponse(
            incident_id="INC-2026-04-30-001",
            responder_email="enzo@demo.local",
            decision="maybe",  # type: ignore[arg-type]
            timestamp=UTC_NOW,
            channel=NotificationChannelType.EMAIL,
            token_jti="jwt-id-abc",
        )


# ---------------------------------------------------------------------------
# Timezone-aware enforcement across every datetime field
# (per CONTRACTS_SPECIFICATION.md §Conventions, applied via shared helper
# `argos_contracts._validators.ensure_tz_aware`).
# ---------------------------------------------------------------------------


# --- Required datetime fields: naive must reject ---------------------------


def test_wazuh_alert_naive_timestamp_rejects() -> None:
    with pytest.raises(ValidationError) as exc_info:
        WazuhAlert(
            alert_id="a1",
            rule_id=100,
            rule_description="d",
            rule_level=10,
            timestamp=NAIVE_DT,
            agent_id="001",
            agent_name="WIN",
        )
    assert "timezone-aware" in str(exc_info.value)


def test_normalized_alert_naive_timestamp_rejects() -> None:
    with pytest.raises(ValidationError):
        NormalizedAlert(
            alert_id="a1",
            source_layer=Layer.LAYER_1,
            timestamp=NAIVE_DT,
            host_id="h",
            severity_score=0.5,
            severity_label=Severity.MEDIUM,
        )


def test_ml_score_naive_timestamp_rejects() -> None:
    with pytest.raises(ValidationError):
        MLScore(
            score_id="s1",
            timestamp=NAIVE_DT,
            host_id="h",
            isolation_forest_score=0.5,
            one_class_svm_score=0.5,
            ensemble_score=0.5,
            features=_ml_features(),
            model_version="v1",
        )


def test_alert_context_naive_created_at_rejects() -> None:
    with pytest.raises(ValidationError):
        AlertContext(
            incident_id="INC-2026-04-30-001",
            created_at=NAIVE_DT,
            host=HostInfo(id="WIN-1", criticality=Criticality.STANDARD),
            alert_summary=AlertSummary(
                title="t",
                severity_score=0.5,
                triggering_layers=[Layer.LAYER_1],
                raw_alert_id="r1",
            ),
        )


def test_incident_naive_created_at_rejects() -> None:
    with pytest.raises(ValidationError):
        Incident(
            incident_id="INC-2026-04-30-001",
            created_at=NAIVE_DT,
            updated_at=UTC_LATER,
            tier=Tier.T0,
            state=IncidentState.RECEIVED,
            host={"id": "h"},
            alert=_normalized_alert(),
            proposed_actions=[],
        )


def test_incident_naive_updated_at_rejects() -> None:
    with pytest.raises(ValidationError):
        Incident(
            incident_id="INC-2026-04-30-001",
            created_at=UTC_NOW,
            updated_at=NAIVE_DT,
            tier=Tier.T0,
            state=IncidentState.RECEIVED,
            host={"id": "h"},
            alert=_normalized_alert(),
            proposed_actions=[],
        )


def test_consolidation_window_naive_started_at_rejects() -> None:
    with pytest.raises(ValidationError):
        ConsolidationWindow(started_at=NAIVE_DT)


def test_approval_request_naive_created_at_rejects() -> None:
    with pytest.raises(ValidationError):
        ApprovalRequest(
            incident_id="INC-2026-04-30-001",
            tier=Tier.T2,
            alert_summary="x",
            proposed_actions=[],
            recipients=["a@b.local"],
            created_at=NAIVE_DT,
            approval_url_template="https://x/{token}",
        )


def test_approval_response_naive_timestamp_rejects() -> None:
    with pytest.raises(ValidationError):
        ApprovalResponse(
            incident_id="INC-2026-04-30-001",
            responder_email="enzo@demo.local",
            decision=ApprovalDecision.APPROVE,
            timestamp=NAIVE_DT,
            channel=NotificationChannelType.EMAIL,
            token_jti="jwt-id",
        )


# --- Optional datetime fields: naive rejects + None passes -----------------


def test_approver_state_naive_responded_at_rejects() -> None:
    with pytest.raises(ValidationError):
        ApproverState(
            email="x@y.local",
            role="analyst",
            status=ApproverStatus.APPROVED,
            responded_at=NAIVE_DT,
        )


def test_approver_state_responded_at_none_passes() -> None:
    a = ApproverState(email="x@y.local", role="analyst", responded_at=None)
    assert a.responded_at is None


def test_consolidation_window_naive_ended_at_rejects() -> None:
    with pytest.raises(ValidationError):
        ConsolidationWindow(started_at=UTC_NOW, ended_at=NAIVE_DT)


def test_consolidation_window_ended_at_none_passes() -> None:
    w = ConsolidationWindow(started_at=UTC_NOW, ended_at=None)
    assert w.ended_at is None


def test_final_decision_naive_executed_at_rejects() -> None:
    with pytest.raises(ValidationError):
        FinalDecision(
            outcome="EXECUTE_ISOLATION",
            policy_applied="auto-execute",
            rationale="r",
            executed_at=NAIVE_DT,
        )


def test_final_decision_executed_at_none_passes() -> None:
    d = FinalDecision(
        outcome="NO_ACTION",
        policy_applied="auto-execute",
        rationale="false positive, no action taken",
    )
    assert d.executed_at is None
