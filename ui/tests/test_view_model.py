"""Tests del view-model puro (sin Streamlit ni Redis)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from streamlit_app.lib import view_model as vm

from argos_contracts.enums import (
    ApproverStatus,
    IncidentState,
    NotificationChannelType,
    Severity,
    Tier,
)
from argos_contracts.incident import ConsolidationWindow, FinalDecision

_START = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)


def test_consolidation_remaining_none() -> None:
    assert vm.consolidation_remaining(None) is None


def test_consolidation_remaining_midwindow() -> None:
    window = ConsolidationWindow(started_at=_START, duration_seconds=60)
    assert vm.consolidation_remaining(
        window, _START + timedelta(seconds=18)
    ) == pytest.approx(42.0)


def test_consolidation_remaining_past_clamps_to_zero() -> None:
    window = ConsolidationWindow(started_at=_START, duration_seconds=60)
    assert vm.consolidation_remaining(window, _START + timedelta(seconds=90)) == 0.0


def test_elapsed_fraction_half() -> None:
    window = ConsolidationWindow(started_at=_START, duration_seconds=60)
    assert vm.consolidation_elapsed_fraction(
        window, _START + timedelta(seconds=30)
    ) == pytest.approx(0.5)


def test_format_mmss() -> None:
    assert vm.format_mmss(42) == "0:42"
    assert vm.format_mmss(75) == "1:15"
    assert vm.format_mmss(-5) == "0:00"


def test_color_maps_cover_every_enum_member() -> None:
    # Disciplina ui/README: cada miembro del enum tiene color/label; un valor
    # nuevo del contrato rompe acá (test), no en el demo.
    for tier in Tier:
        assert vm.tier_color(tier)
    for state in IncidentState:
        assert vm.state_color(state)
    for severity in Severity:
        assert vm.severity_color(severity)
    for status in ApproverStatus:
        assert vm.APPROVER_STATUS_COLOR[status]
        assert vm.APPROVER_STATUS_EMOJI[status]
    for channel in NotificationChannelType:
        assert vm.channel_label(channel)


def test_approver_rows_fields(make_incident, approver) -> None:
    incident = make_incident(
        approvers=[
            approver(email="a", status=ApproverStatus.APPROVED, latency_seconds=18.0),
            approver(
                email="b",
                status=ApproverStatus.TIMEOUT,
                latency_seconds=None,
                responded=False,
            ),
        ]
    )
    rows = vm.approver_rows(incident)
    assert len(rows) == 2
    assert rows[0].status_emoji == "🟢"
    assert rows[0].latency_label == "18s"
    assert rows[1].latency_label == "—"
    assert rows[1].responded_label == "—"
    assert rows[1].channel_label == "Telegram"


def test_vote_counts(make_incident, approver) -> None:
    incident = make_incident(
        approvers=[
            approver(email="a", status=ApproverStatus.APPROVED),
            approver(email="b", status=ApproverStatus.APPROVED),
            approver(email="c", status=ApproverStatus.REJECTED),
            approver(email="d", status=ApproverStatus.TIMEOUT, responded=False),
        ]
    )
    counts = vm.vote_counts(incident)
    assert (counts.approved, counts.rejected, counts.timeout, counts.pending) == (
        2,
        1,
        1,
        0,
    )
    assert counts.total == 4


def test_summary_line_pending(make_incident, approver) -> None:
    incident = make_incident(
        approvers=[
            approver(email="a", status=ApproverStatus.APPROVED),
            approver(email="b", status=ApproverStatus.REJECTED),
        ]
    )
    assert vm.summary_line(incident) == "1 approve · 1 reject"


def test_summary_line_with_policy_verbatim(make_incident, approver) -> None:
    incident = make_incident(
        approvers=[
            approver(email="a", status=ApproverStatus.APPROVED),
            approver(email="b", status=ApproverStatus.REJECTED),
            approver(email="c", status=ApproverStatus.TIMEOUT, responded=False),
        ],
        final_decision=FinalDecision(
            outcome="EXECUTE_ISOLATION",
            policy_applied="conservative-wins",
            rationale="conservative-wins: aislar gana",
        ),
    )
    assert (
        vm.summary_line(incident)
        == "1 approve · 1 reject · 1 timeout · conservative-wins applied"
    )


def test_is_settled(make_incident) -> None:
    assert vm.is_settled(make_incident()) is False
    settled = make_incident(
        final_decision=FinalDecision(
            outcome="NO_ACTION", policy_applied="two-person-rule", rationale="x"
        )
    )
    assert vm.is_settled(settled) is True
