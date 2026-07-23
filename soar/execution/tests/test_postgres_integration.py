"""Real PostgreSQL contract tests for the execution journal adapter."""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from argos_contracts.enums import ActionType
from argos_contracts.incident import ProposedAction
from soar.execution.journal import (
    AmbiguousExecutionError,
    ExecutionInProgressError,
    ExecutionKey,
    ExecutionRecord,
    ResponseExecutionJournal,
)
from soar.execution.postgres import PostgresExecutionStore
from soar.playbooks.base import ExecutionResult

DSN = os.environ.get("ARGOS_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(DSN is None, reason="ARGOS_TEST_POSTGRES_DSN is not set")


@pytest.fixture(autouse=True)
def clean_journal():
    assert DSN is not None
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("TRUNCATE argos_audit.execution_journal")
    yield


def _record() -> ExecutionRecord:
    now = datetime.now(UTC)
    return ExecutionRecord(
        key=ExecutionKey("INC-2026-05-30-001", "act-001", "run"),
        action=ProposedAction(
            id="act-001",
            type=ActionType.HOST_ISOLATION,
            target="WIN-VICTIM-01",
            reversible=True,
        ),
        actor="decision-engine",
        state="prepared",
        attempt=0,
        prepared_at=now,
        updated_at=now,
    )


def test_postgres_persists_prepared_then_atomically_claims_a_lease() -> None:
    assert DSN is not None
    store = PostgresExecutionStore(DSN)
    prepared = store.prepare(_record())
    assert prepared.state == "prepared"

    now = datetime.now(UTC)
    claimed = store.claim(
        prepared.key,
        owner="worker-a",
        now=now,
        lease_expires_at=now + timedelta(seconds=30),
    )
    assert claimed.state == "executing"
    assert claimed.attempt == 1
    assert claimed.lease_owner == "worker-a"


def test_restart_reclaims_prepared_work_before_any_effect() -> None:
    assert DSN is not None
    PostgresExecutionStore(DSN).prepare(_record())
    restarted = ResponseExecutionJournal(
        PostgresExecutionStore(DSN), owner="worker-after-restart"
    )
    calls = 0

    def effect() -> ExecutionResult:
        nonlocal calls
        calls += 1
        return ExecutionResult("act-001", "success")

    result = restarted.execute(
        "INC-2026-05-30-001",
        _record().action,
        operation="run",
        actor="decision-engine",
        effect=effect,
    )
    assert result.status == "success"
    assert calls == 1


@pytest.mark.parametrize(
    ("result_status", "journal_state"),
    [("success", "succeeded"), ("failed", "failed")],
)
def test_postgres_persists_terminal_receipts_without_repeating_effect(
    result_status: str, journal_state: str
) -> None:
    assert DSN is not None
    journal = ResponseExecutionJournal(PostgresExecutionStore(DSN), owner="worker-a")
    calls = 0

    def effect() -> ExecutionResult:
        nonlocal calls
        calls += 1
        return ExecutionResult("act-001", result_status)  # type: ignore[arg-type]

    first = journal.execute(
        "INC-2026-05-30-001",
        _record().action,
        operation="run",
        actor="decision-engine",
        effect=effect,
    )
    second = journal.execute(
        "INC-2026-05-30-001",
        _record().action,
        operation="run",
        actor="decision-engine",
        effect=effect,
    )

    assert first.status == result_status
    assert second.status == result_status
    assert calls == 1
    assert journal.get("INC-2026-05-30-001", "act-001", "run").state == journal_state


def test_partial_result_is_ambiguous_and_never_retried() -> None:
    assert DSN is not None
    journal = ResponseExecutionJournal(PostgresExecutionStore(DSN), owner="worker-a")
    calls = 0

    def effect() -> ExecutionResult:
        nonlocal calls
        calls += 1
        return ExecutionResult("act-001", "partial")

    with pytest.raises(AmbiguousExecutionError):
        journal.execute(
            "INC-2026-05-30-001",
            _record().action,
            operation="run",
            actor="decision-engine",
            effect=effect,
        )
    with pytest.raises(AmbiguousExecutionError):
        journal.execute(
            "INC-2026-05-30-001",
            _record().action,
            operation="run",
            actor="decision-engine",
            effect=effect,
        )
    assert calls == 1


def test_expired_executing_lease_becomes_ambiguous_after_restart() -> None:
    assert DSN is not None
    now = datetime(2026, 7, 22, tzinfo=UTC)
    calls = 0

    def clock() -> datetime:
        return now

    def effect_then_crash() -> ExecutionResult:
        nonlocal calls
        calls += 1
        raise SystemExit("simulated crash after external effect")

    first = ResponseExecutionJournal(
        PostgresExecutionStore(DSN),
        owner="worker-a",
        lease_seconds=5,
        now_fn=clock,
    )
    with pytest.raises(SystemExit):
        first.execute(
            "INC-2026-05-30-001",
            _record().action,
            operation="run",
            actor="decision-engine",
            effect=effect_then_crash,
        )

    now += timedelta(seconds=6)
    second = ResponseExecutionJournal(
        PostgresExecutionStore(DSN),
        owner="worker-b",
        lease_seconds=5,
        now_fn=clock,
    )
    with pytest.raises(AmbiguousExecutionError):
        second.execute(
            "INC-2026-05-30-001",
            _record().action,
            operation="run",
            actor="decision-engine",
            effect=effect_then_crash,
        )
    assert calls == 1
    assert second.get("INC-2026-05-30-001", "act-001", "run").state == "ambiguous"


def test_postgres_serializes_two_workers_without_double_effect() -> None:
    assert DSN is not None
    first = ResponseExecutionJournal(PostgresExecutionStore(DSN), owner="worker-a")
    second = ResponseExecutionJournal(PostgresExecutionStore(DSN), owner="worker-b")
    entered = threading.Event()
    release = threading.Event()
    calls = 0

    def slow_effect() -> ExecutionResult:
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(timeout=2)
        return ExecutionResult("act-001", "success")

    thread = threading.Thread(
        target=lambda: first.execute(
            "INC-2026-05-30-001",
            _record().action,
            operation="run",
            actor="decision-engine",
            effect=slow_effect,
        )
    )
    thread.start()
    assert entered.wait(timeout=2)
    with pytest.raises(ExecutionInProgressError):
        second.execute(
            "INC-2026-05-30-001",
            _record().action,
            operation="run",
            actor="decision-engine",
            effect=slow_effect,
        )
    release.set()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert calls == 1
