"""Durable state machine around external response effects.

The journal prevents duplicate *logical* execution.  It deliberately does not
claim exactly-once delivery to an external endpoint: an expired ``executing``
lease is ambiguous and requires reconciliation before another attempt.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from argos_contracts.incident import ProposedAction
from soar.playbooks.base import ExecutionResult

Operation = Literal["run", "revert"]
JournalState = Literal["prepared", "executing", "succeeded", "failed", "ambiguous"]


@dataclass(frozen=True)
class ExecutionKey:
    incident_id: str
    action_id: str
    operation: Operation


@dataclass(frozen=True)
class ExecutionRecord:
    key: ExecutionKey
    action: ProposedAction
    actor: str
    state: JournalState
    attempt: int
    prepared_at: datetime
    updated_at: datetime
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    result: ExecutionResult | None = None


class ExecutionStore(Protocol):
    def prepare(self, record: ExecutionRecord) -> ExecutionRecord: ...

    def claim(
        self, key: ExecutionKey, *, owner: str, now: datetime, lease_expires_at: datetime
    ) -> ExecutionRecord: ...

    def complete(
        self,
        key: ExecutionKey,
        *,
        owner: str,
        state: JournalState,
        result: ExecutionResult | None,
        now: datetime,
    ) -> ExecutionRecord: ...

    def get(self, key: ExecutionKey) -> ExecutionRecord | None: ...

    def check_ready(self) -> None: ...

    def close(self) -> None: ...


class ExecutionJournalError(RuntimeError):
    """Base error whose messages are safe to expose in operational logs."""


class ExecutionInProgressError(ExecutionJournalError):
    pass


class AmbiguousExecutionError(ExecutionJournalError):
    pass


class MemoryExecutionStore:
    """Thread-safe store for deterministic unit tests and non-live demos only."""

    def __init__(self) -> None:
        self._records: dict[ExecutionKey, ExecutionRecord] = {}
        self._lock = threading.Lock()

    def prepare(self, record: ExecutionRecord) -> ExecutionRecord:
        with self._lock:
            return self._records.setdefault(record.key, record)

    def claim(
        self, key: ExecutionKey, *, owner: str, now: datetime, lease_expires_at: datetime
    ) -> ExecutionRecord:
        with self._lock:
            record = self._records[key]
            if record.state == "executing":
                if record.lease_expires_at is not None and record.lease_expires_at <= now:
                    record = replace(
                        record,
                        state="ambiguous",
                        lease_owner=None,
                        lease_expires_at=None,
                        updated_at=now,
                    )
                    self._records[key] = record
                    return record
                return record
            if record.state != "prepared":
                return record
            record = replace(
                record,
                state="executing",
                attempt=record.attempt + 1,
                lease_owner=owner,
                lease_expires_at=lease_expires_at,
                updated_at=now,
            )
            self._records[key] = record
            return record

    def complete(
        self,
        key: ExecutionKey,
        *,
        owner: str,
        state: JournalState,
        result: ExecutionResult | None,
        now: datetime,
    ) -> ExecutionRecord:
        with self._lock:
            record = self._records[key]
            if record.state != "executing" or record.lease_owner != owner:
                raise ExecutionJournalError("execution lease is no longer owned")
            record = replace(
                record,
                state=state,
                result=result,
                lease_owner=None,
                lease_expires_at=None,
                updated_at=now,
            )
            self._records[key] = record
            return record

    def get(self, key: ExecutionKey) -> ExecutionRecord | None:
        with self._lock:
            return self._records.get(key)

    def check_ready(self) -> None:
        return None

    def close(self) -> None:
        return None


class ResponseExecutionJournal:
    """Small public interface that owns ordering around an external effect."""

    def __init__(
        self,
        store: ExecutionStore,
        *,
        owner: str | None = None,
        lease_seconds: int = 30,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        self._store = store
        self._owner = owner or str(uuid.uuid4())
        self._lease_seconds = lease_seconds
        self._now = now_fn or (lambda: datetime.now(UTC))

    def get(
        self, incident_id: str, action_id: str, operation: Operation
    ) -> ExecutionRecord | None:
        return self._store.get(ExecutionKey(incident_id, action_id, operation))

    def execute(
        self,
        incident_id: str,
        action: ProposedAction,
        *,
        operation: Operation,
        actor: str,
        effect: Callable[[], ExecutionResult],
    ) -> ExecutionResult:
        key = ExecutionKey(incident_id, action.id, operation)
        now = self._now()
        prepared = ExecutionRecord(
            key=key,
            action=action.model_copy(deep=True),
            actor=actor,
            state="prepared",
            attempt=0,
            prepared_at=now,
            updated_at=now,
        )
        persisted = self._store.prepare(prepared)
        if persisted.action.model_dump(mode="json") != action.model_dump(mode="json"):
            raise ExecutionJournalError(
                "execution identity conflicts with the persisted action"
            )
        claim_now = self._now()
        record = self._store.claim(
            key,
            owner=self._owner,
            now=claim_now,
            lease_expires_at=claim_now + timedelta(seconds=self._lease_seconds),
        )
        if record.state in ("succeeded", "failed") and record.result is not None:
            return record.result
        if record.state == "ambiguous":
            raise AmbiguousExecutionError("external effect outcome is ambiguous")
        if record.state != "executing" or record.lease_owner != self._owner:
            raise ExecutionInProgressError("execution is already in progress")

        try:
            result = effect()
        except Exception as exc:
            self._store.complete(
                key,
                owner=self._owner,
                state="ambiguous",
                result=None,
                now=self._now(),
            )
            raise AmbiguousExecutionError("external effect raised before a receipt") from exc

        terminal: JournalState
        if result.status == "success":
            terminal = "succeeded"
        elif result.status == "failed":
            terminal = "failed"
        else:
            terminal = "ambiguous"
        self._store.complete(
            key,
            owner=self._owner,
            state=terminal,
            result=result,
            now=self._now(),
        )
        if terminal == "ambiguous":
            raise AmbiguousExecutionError("external effect returned a partial result")
        return result

    def check_ready(self) -> None:
        self._store.check_ready()

    def close(self) -> None:
        self._store.close()
