"""Tests de la logica de decision HITL: two-person rule + conservative-wins (ADR-0006).

Cada caso cita la regla del ADR que valida. Distingue las dos politicas por criticidad:
host production-critical -> two-person ; host estandar reversible -> conservative-wins.
"""

from __future__ import annotations

from fakeredis import FakeAsyncRedis

from argos_contracts.enums import (
    ActionType,
    ApproverStatus,
    Criticality,
    IncidentState,
    NotificationChannelType,
)
from argos_contracts.incident import ApproverState, FinalDecision, ProposedAction
from argos_contracts.triage import HostInfo
from soar.approval_api.handlers import (
    _evaluate,
    build_final_decision_if_ready,
    requires_two_person,
    save_incident,
)

TG = NotificationChannelType.TELEGRAM
_STD_HOST = HostInfo(id="WIN-VICTIM-01", criticality=Criticality.STANDARD)


def _ap(email: str, status: ApproverStatus) -> ApproverState:
    return ApproverState(email=email, role="approver", status=status, channel=TG)


def _approved(email: str) -> ApproverState:
    return _ap(email, ApproverStatus.APPROVED)


def _rejected(email: str) -> ApproverState:
    return _ap(email, ApproverStatus.REJECTED)


# --- Seleccion de politica (ADR-0006 Situacion A/B) ---
def test_two_person_for_production_critical_host(make_incident):
    assert requires_two_person(make_incident()) is True  # default = production-critical (DB)


def test_conservative_for_standard_reversible_host(make_incident):
    assert requires_two_person(make_incident(host=_STD_HOST)) is False


def test_two_person_for_irreversible_action(make_incident):
    inc = make_incident(
        host=_STD_HOST,
        proposed_actions=[
            ProposedAction(id="a1", type=ActionType.HOST_ISOLATION, target="x", reversible=False)
        ],
    )
    assert requires_two_person(inc) is True


# --- Two-person rule (host production-critical) ---
def test_tp_no_responses_waits(make_incident):
    assert _evaluate(make_incident(approvers=[])) is None


def test_tp_single_approve_waits(make_incident):
    assert _evaluate(make_incident(approvers=[_approved("a")])) is None  # falta el 2do


def test_tp_two_approves_execute(make_incident):
    d = _evaluate(make_incident(approvers=[_approved("a"), _approved("b")]))
    assert d is not None
    assert d.outcome == "EXECUTE_ISOLATION" and d.policy_applied == "two-person-rule"


def test_tp_single_reject_cancels(make_incident):
    d = _evaluate(make_incident(approvers=[_rejected("a")]))
    assert d is not None
    assert d.outcome == "NO_ACTION" and d.policy_applied == "two-person-rule"


def test_tp_reject_vetoes_even_with_approve(make_incident):
    # UC-07: un rechazo cancela aunque haya un approve (ADR-0006 Situacion B)
    d = _evaluate(make_incident(approvers=[_approved("a"), _rejected("b")]))
    assert d is not None and d.outcome == "NO_ACTION"


# --- Conservative-wins (host estandar reversible) ---
def test_cw_single_reject_waits(make_incident):
    # solo-reject espera el cierre de ventana (§2.8): un approve aun puede voltearlo
    assert _evaluate(make_incident(host=_STD_HOST, approvers=[_rejected("a")])) is None


def test_cw_any_approve_isolates(make_incident):
    d = _evaluate(make_incident(host=_STD_HOST, approvers=[_approved("a")]))
    assert d is not None
    assert d.outcome == "EXECUTE_ISOLATION" and d.policy_applied == "conservative-wins"


def test_cw_approve_wins_over_multiple_rejects(make_incident):
    # 1 approve vs 2 reject -> aislar igual (conservative = aislar, ADR-0006 §3)
    inc = make_incident(
        host=_STD_HOST, approvers=[_approved("a"), _rejected("b"), _rejected("c")]
    )
    d = _evaluate(inc)
    assert d is not None and d.outcome == "EXECUTE_ISOLATION"


# --- build_final_decision_if_ready (async, fakeredis) ---
async def test_build_executes_on_quorum(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    inc = make_incident(approvers=[_approved("a"), _approved("b")])
    await save_incident(r, inc)
    out = await build_final_decision_if_ready(r, inc.incident_id)
    assert out.final_decision is not None
    assert out.final_decision.outcome == "EXECUTE_ISOLATION"
    assert out.state == IncidentState.PENDING_EXECUTION


async def test_build_rejects_on_veto(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    inc = make_incident(approvers=[_rejected("a")])
    await save_incident(r, inc)
    out = await build_final_decision_if_ready(r, inc.incident_id)
    assert out.final_decision is not None
    assert out.final_decision.outcome == "NO_ACTION"
    assert out.state == IncidentState.REJECTED


async def test_build_waits_when_undecided(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    inc = make_incident(approvers=[_approved("a")])  # 1 approve, two-person -> espera
    await save_incident(r, inc)
    out = await build_final_decision_if_ready(r, inc.incident_id)
    assert out.final_decision is None
    assert out.state == IncidentState.AWAITING_APPROVAL  # sin cambio


async def test_build_is_idempotent_when_already_decided(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    pre = FinalDecision(outcome="NO_ACTION", policy_applied="two-person-rule", rationale="x")
    inc = make_incident(approvers=[_approved("a"), _approved("b")], final_decision=pre)
    await save_incident(r, inc)
    out = await build_final_decision_if_ready(r, inc.incident_id)
    assert out.final_decision is not None and out.final_decision.rationale == "x"  # no re-evalua
