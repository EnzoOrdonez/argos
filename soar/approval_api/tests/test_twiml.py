"""Tests de los helpers TwiML (puros)."""

from __future__ import annotations

import pytest

from soar.approval_api.twiml import build_voice_gather_xml, dtmf_to_response


def test_gather_xml_embeds_incident_in_say_and_action():
    xml = build_voice_gather_xml("INC-2026-05-30-001")
    assert "<Response>" in xml and "<Gather" in xml
    assert "INC-2026-05-30-001" in xml
    # el incident viaja en la action URL (fix sobre el manual)
    assert 'action="/voice/dtmf?incident=INC-2026-05-30-001"' in xml


@pytest.mark.parametrize(
    "digits, expected",
    [("1", "approve"), ("2", "reject"), (" 1 ", "approve"), ("9", None), ("", None)],
)
def test_dtmf_to_response(digits, expected):
    assert dtmf_to_response(digits) == expected
