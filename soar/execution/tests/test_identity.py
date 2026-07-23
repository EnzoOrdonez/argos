"""Stable execution identity contract."""

import pytest

from soar.execution.identity import ExecutionIdentity


def test_execution_identity_uses_incident_action_and_operation() -> None:
    first = ExecutionIdentity("INC-2026-07-23-001", "act-001", "run")
    same = ExecutionIdentity("INC-2026-07-23-001", "act-001", "run")
    revert = ExecutionIdentity("INC-2026-07-23-001", "act-001", "revert")

    assert first.execution_id == same.execution_id
    assert first.execution_id != revert.execution_id
    assert first.as_payload() == {
        "execution_id": first.execution_id,
        "incident_id": "INC-2026-07-23-001",
        "action_id": "act-001",
        "operation": "run",
    }


@pytest.mark.parametrize(
    ("incident_id", "action_id", "operation"),
    [
        ("", "act-001", "run"),
        ("INC-001", "", "run"),
        ("   ", "act-001", "run"),
        ("INC-001", "   ", "run"),
        ("INC-001", "act-001", "retry"),
    ],
)
def test_execution_identity_rejects_incomplete_components(
    incident_id: str, action_id: str, operation: str
) -> None:
    with pytest.raises(ValueError, match="identity"):
        ExecutionIdentity(incident_id, action_id, operation)  # type: ignore[arg-type]
