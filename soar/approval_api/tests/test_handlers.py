"""Tests de record_approval_response sobre Redis (fakeredis async)."""

from __future__ import annotations

from fakeredis import FakeAsyncRedis

from argos_contracts.enums import ApproverStatus, NotificationChannelType
from argos_contracts.incident import FinalDecision, Incident
from soar.approval_api.handlers import load_incident, record_approval_response, save_incident

TG = NotificationChannelType.TELEGRAM


async def _seed(incident: Incident) -> FakeAsyncRedis:
    r = FakeAsyncRedis(decode_responses=True)
    await save_incident(r, incident)
    return r


async def test_record_appends_new_approver(make_incident):
    inc = make_incident()
    r = await _seed(inc)
    await record_approval_response(
        r, inc.incident_id, email="telegram:1", role="soc_lead", decision="approve", channel=TG
    )
    stored = await load_incident(r, inc.incident_id)
    assert len(stored.approvers) == 1
    assert stored.approvers[0].email == "telegram:1"
    assert stored.approvers[0].status == ApproverStatus.APPROVED
    assert stored.approvers[0].responded_at is not None


async def test_record_updates_existing_approver(make_incident):
    inc = make_incident()
    r = await _seed(inc)
    await record_approval_response(
        r, inc.incident_id, email="telegram:1", role="soc_lead", decision="approve", channel=TG
    )
    await record_approval_response(
        r, inc.incident_id, email="telegram:1", role="soc_lead", decision="reject", channel=TG
    )
    stored = await load_incident(r, inc.incident_id)
    assert len(stored.approvers) == 1  # mismo email -> actualiza, no duplica
    assert stored.approvers[0].status == ApproverStatus.REJECTED


async def test_record_unknown_incident_raises(make_incident):
    r = FakeAsyncRedis(decode_responses=True)
    try:
        await record_approval_response(
            r, "INC-2026-05-30-999", email="x", role="y", decision="approve", channel=TG
        )
        raised = False
    except KeyError:
        raised = True
    assert raised


async def test_record_ignored_after_final_decision(make_incident):
    inc = make_incident(
        final_decision=FinalDecision(
            outcome="NO_ACTION", policy_applied="two-person-rule", rationale="ya resuelto"
        )
    )
    r = await _seed(inc)
    await record_approval_response(
        r, inc.incident_id, email="telegram:1", role="soc_lead", decision="approve", channel=TG
    )
    stored = await load_incident(r, inc.incident_id)
    assert stored.approvers == []  # voto tardio ignorado
