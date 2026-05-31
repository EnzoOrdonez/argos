"""Tests de la ventana de consolidacion de 60s (§2.8, ADR-0006 Situacion B + ADR-0003)."""

from __future__ import annotations

from fakeredis import FakeAsyncRedis

from argos_contracts.enums import (
    ApproverStatus,
    Criticality,
    IncidentState,
    NotificationChannelType,
)
from argos_contracts.incident import ApproverState, FinalDecision
from argos_contracts.triage import HostInfo
from soar.approval_api.consolidation import (
    close_window,
    consolidation_task,
    finalize_after_window,
)
from soar.approval_api.handlers import load_incident, save_incident

TG = NotificationChannelType.TELEGRAM
_STD_HOST = HostInfo(id="WIN-VICTIM-01", criticality=Criticality.STANDARD)


def _ap(email: str, status: ApproverStatus = ApproverStatus.PENDING) -> ApproverState:
    return ApproverState(email=email, role="approver", status=status, channel=TG)


# --- finalize_after_window (puro) ---
def test_finalize_two_person_quorum_executes(make_incident):
    inc = make_incident(
        approvers=[_ap("a", ApproverStatus.APPROVED), _ap("b", ApproverStatus.APPROVED)]
    )
    d = finalize_after_window(inc)
    assert d is not None and d.outcome == "EXECUTE_ISOLATION"
    assert d.policy_applied == "two-person-rule"


def test_finalize_two_person_no_quorum_waits(make_incident):
    # ADR-0006 Situacion B: 1 approve, sin reject, resto timeout -> NO auto-execute
    inc = make_incident(
        approvers=[_ap("a", ApproverStatus.APPROVED), _ap("b", ApproverStatus.TIMEOUT)]
    )
    assert finalize_after_window(inc) is None


def test_finalize_conservative_reject_only_no_action(make_incident):
    inc = make_incident(
        host=_STD_HOST,
        approvers=[_ap("a", ApproverStatus.REJECTED), _ap("b", ApproverStatus.TIMEOUT)],
    )
    d = finalize_after_window(inc)
    assert d is not None and d.outcome == "NO_ACTION"
    assert d.policy_applied == "conservative-wins"


def test_finalize_conservative_all_timeout_failsafe_executes(make_incident):
    inc = make_incident(
        host=_STD_HOST,
        approvers=[_ap("a", ApproverStatus.TIMEOUT), _ap("b", ApproverStatus.TIMEOUT)],
    )
    d = finalize_after_window(inc)
    assert d is not None and d.outcome == "EXECUTE_ISOLATION"
    assert d.policy_applied == "timeout-escalation"


def test_finalize_conservative_approve_executes(make_incident):
    inc = make_incident(host=_STD_HOST, approvers=[_ap("a", ApproverStatus.APPROVED)])
    d = finalize_after_window(inc)
    assert d is not None and d.outcome == "EXECUTE_ISOLATION"
    assert d.policy_applied == "conservative-wins"


# --- close_window (async: marca timeouts + resuelve) ---
async def test_close_marks_pending_timeout_and_failsafe_executes(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    inc = make_incident(host=_STD_HOST, approvers=[_ap("a"), _ap("b")])  # ambos PENDING
    await save_incident(r, inc)
    out = await close_window(r, inc.incident_id)
    assert all(a.status == ApproverStatus.TIMEOUT for a in out.approvers)
    assert out.final_decision is not None
    assert out.final_decision.policy_applied == "timeout-escalation"
    assert out.state == IncidentState.PENDING_EXECUTION


async def test_close_conservative_reject_only_no_action(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    inc = make_incident(host=_STD_HOST, approvers=[_ap("a", ApproverStatus.REJECTED), _ap("b")])
    await save_incident(r, inc)
    out = await close_window(r, inc.incident_id)
    assert out.final_decision is not None and out.final_decision.outcome == "NO_ACTION"
    assert out.state == IncidentState.REJECTED


async def test_close_two_person_waits_no_decision(make_incident):
    # production-critical (default): 1 approve + 1 pendiente -> Situacion B: espera
    r = FakeAsyncRedis(decode_responses=True)
    inc = make_incident(approvers=[_ap("a", ApproverStatus.APPROVED), _ap("b")])
    await save_incident(r, inc)
    out = await close_window(r, inc.incident_id)
    assert out.final_decision is None  # NO auto-execute por timeout (ADR-0006 Sit. B)
    assert out.state == IncidentState.AWAITING_APPROVAL
    assert any(a.status == ApproverStatus.TIMEOUT for a in out.approvers)  # pendiente marcado


async def test_close_is_idempotent_when_already_decided(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    pre = FinalDecision(
        outcome="EXECUTE_ISOLATION", policy_applied="two-person-rule", rationale="ya"
    )
    inc = make_incident(approvers=[_ap("a")], final_decision=pre)
    await save_incident(r, inc)
    out = await close_window(r, inc.incident_id)
    assert out.final_decision is not None and out.final_decision.rationale == "ya"
    assert out.approvers[0].status == ApproverStatus.PENDING  # no se tocó (ya decidido)


async def test_consolidation_task_closes_after_window(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    inc = make_incident(host=_STD_HOST, approvers=[_ap("a"), _ap("b")])
    await save_incident(r, inc)
    await consolidation_task(r, inc.incident_id, window_seconds=0)  # sin esperar 60s reales
    out = await load_incident(r, inc.incident_id)
    assert out.final_decision is not None
    assert out.final_decision.outcome == "EXECUTE_ISOLATION"
