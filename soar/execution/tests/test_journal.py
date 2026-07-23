"""Behavioral contract for durable response execution."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest

from argos_contracts.enums import ActionType
from argos_contracts.incident import ProposedAction
from soar.execution.journal import (
    AmbiguousExecutionError,
    ExecutionInProgressError,
    ExecutionJournalError,
    MemoryExecutionStore,
    ResponseExecutionJournal,
)
from soar.playbooks.base import ExecutionResult


def test_intent_is_prepared_before_the_external_effect() -> None:
    store = MemoryExecutionStore()
    journal = ResponseExecutionJournal(store, owner="worker-a")
    action = ProposedAction(
        id="act-001",
        type=ActionType.HOST_ISOLATION,
        target="WIN-VICTIM-01",
        reversible=True,
    )

    def effect() -> ExecutionResult:
        record = journal.get("INC-2026-05-30-001", "act-001", "run")
        assert record is not None
        assert record.state == "executing"
        assert record.prepared_at <= datetime.now(UTC)
        return ExecutionResult(action_id="act-001", status="success")

    result = journal.execute(
        "INC-2026-05-30-001",
        action,
        operation="run",
        actor="decision-engine",
        effect=effect,
    )

    assert result.status == "success"
    assert journal.get("INC-2026-05-30-001", "act-001", "run").state == "succeeded"


def _action() -> ProposedAction:
    return ProposedAction(
        id="act-001",
        type=ActionType.HOST_ISOLATION,
        target="WIN-VICTIM-01",
        reversible=True,
    )


def _execute(journal: ResponseExecutionJournal, effect, *, operation="run"):
    return journal.execute(
        "INC-2026-05-30-001",
        _action(),
        operation=operation,
        actor="decision-engine",
        effect=effect,
    )


def test_failed_receipt_is_terminal_and_is_not_executed_twice() -> None:
    journal = ResponseExecutionJournal(MemoryExecutionStore(), owner="worker-a")
    calls = 0

    def effect() -> ExecutionResult:
        nonlocal calls
        calls += 1
        return ExecutionResult(action_id="act-001", status="failed", detail="denied")

    assert _execute(journal, effect).status == "failed"
    assert _execute(journal, effect).status == "failed"
    assert calls == 1
    assert journal.get("INC-2026-05-30-001", "act-001", "run").state == "failed"


def test_partial_receipt_is_ambiguous_and_is_never_retried_automatically() -> None:
    journal = ResponseExecutionJournal(MemoryExecutionStore(), owner="worker-a")
    calls = 0

    def effect() -> ExecutionResult:
        nonlocal calls
        calls += 1
        return ExecutionResult(action_id="act-001", status="partial")

    with pytest.raises(AmbiguousExecutionError):
        _execute(journal, effect)
    with pytest.raises(AmbiguousExecutionError):
        _execute(journal, effect)

    assert calls == 1


def test_crash_before_claim_leaves_prepared_work_retriable() -> None:
    store = MemoryExecutionStore()
    original_claim = store.claim
    crashed = False

    def crash_once(*args, **kwargs):
        nonlocal crashed
        if not crashed:
            crashed = True
            raise SystemExit("simulated process crash")
        return original_claim(*args, **kwargs)

    store.claim = crash_once  # type: ignore[method-assign]
    first = ResponseExecutionJournal(store, owner="worker-a")
    with pytest.raises(SystemExit):
        _execute(first, lambda: ExecutionResult("act-001", "success"))
    assert first.get("INC-2026-05-30-001", "act-001", "run").state == "prepared"

    calls = 0

    def effect() -> ExecutionResult:
        nonlocal calls
        calls += 1
        return ExecutionResult("act-001", "success")

    second = ResponseExecutionJournal(store, owner="worker-b")
    assert _execute(second, effect).status == "success"
    assert calls == 1


def test_lease_starts_after_prepared_is_persisted() -> None:
    store = MemoryExecutionStore()
    now = datetime(2026, 7, 22, tzinfo=UTC)
    original_prepare = store.prepare

    def slow_prepare(record):
        nonlocal now
        persisted = original_prepare(record)
        now += timedelta(seconds=10)
        return persisted

    store.prepare = slow_prepare  # type: ignore[method-assign]
    journal = ResponseExecutionJournal(
        store, owner="worker-a", lease_seconds=5, now_fn=lambda: now
    )

    def effect() -> ExecutionResult:
        record = journal.get("INC-2026-05-30-001", "act-001", "run")
        assert record is not None
        assert record.lease_expires_at == now + timedelta(seconds=5)
        return ExecutionResult("act-001", "success")

    assert _execute(journal, effect).status == "success"


def test_crash_after_effect_becomes_ambiguous_after_lease_expiry() -> None:
    store = MemoryExecutionStore()
    now = datetime(2026, 7, 22, tzinfo=UTC)
    calls = 0

    def clock() -> datetime:
        return now

    def effect() -> ExecutionResult:
        nonlocal calls
        calls += 1
        return ExecutionResult("act-001", "success")

    def crash_before_receipt(*_args, **_kwargs):
        raise SystemExit("effect happened; receipt was not committed")

    store.complete = crash_before_receipt  # type: ignore[method-assign]

    first = ResponseExecutionJournal(
        store, owner="worker-a", lease_seconds=5, now_fn=clock
    )
    with pytest.raises(SystemExit):
        _execute(first, effect)
    assert first.get("INC-2026-05-30-001", "act-001", "run").state == "executing"

    now += timedelta(seconds=6)
    second = ResponseExecutionJournal(
        store, owner="worker-b", lease_seconds=5, now_fn=clock
    )
    with pytest.raises(AmbiguousExecutionError):
        _execute(second, effect)
    assert calls == 1
    assert second.get("INC-2026-05-30-001", "act-001", "run").state == "ambiguous"


def test_two_workers_cannot_execute_the_same_effect_concurrently() -> None:
    store = MemoryExecutionStore()
    first = ResponseExecutionJournal(store, owner="worker-a")
    second = ResponseExecutionJournal(store, owner="worker-b")
    entered = threading.Event()
    release = threading.Event()
    calls = 0

    def slow_effect() -> ExecutionResult:
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(timeout=2)
        return ExecutionResult("act-001", "success")

    thread = threading.Thread(target=lambda: _execute(first, slow_effect))
    thread.start()
    assert entered.wait(timeout=2)
    with pytest.raises(ExecutionInProgressError):
        _execute(second, slow_effect)
    release.set()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert calls == 1
    assert _execute(second, slow_effect).status == "success"
    assert calls == 1


def test_same_identity_with_different_action_payload_fails_closed() -> None:
    journal = ResponseExecutionJournal(MemoryExecutionStore(), owner="worker-a")
    _execute(journal, lambda: ExecutionResult("act-001", "success"))
    conflicting = _action().model_copy(update={"target": "LIN-VICTIM-01"})
    called = False

    def effect() -> ExecutionResult:
        nonlocal called
        called = True
        return ExecutionResult("act-001", "success")

    with pytest.raises(ExecutionJournalError, match="identity conflicts"):
        journal.execute(
            "INC-2026-05-30-001",
            conflicting,
            operation="run",
            actor="decision-engine",
            effect=effect,
        )
    assert called is False
