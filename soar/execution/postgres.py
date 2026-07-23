"""PostgreSQL authority for the response-execution journal."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

from argos_contracts.incident import ProposedAction
from soar.execution.journal import (
    ExecutionJournalError,
    ExecutionKey,
    ExecutionRecord,
    JournalState,
    ResponseExecutionJournal,
)
from soar.playbooks.base import ExecutionResult

DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_LEASE_SECONDS = 30
DSN_ENV = "ARGOS_EXECUTION_SQL_DSN"
CONNECT_TIMEOUT_ENV = "ARGOS_EXECUTION_SQL_CONNECT_TIMEOUT_SECONDS"
LEASE_ENV = "ARGOS_EXECUTION_LEASE_SECONDS"
class ExecutionJournalConfigurationError(RuntimeError):
    """Sanitized startup failure."""


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ExecutionJournalConfigurationError(
            f"{name} must be an integer between {minimum} and {maximum}"
        ) from exc
    if not minimum <= value <= maximum:
        raise ExecutionJournalConfigurationError(
            f"{name} must be an integer between {minimum} and {maximum}"
        )
    return value


class PostgresExecutionStore:
    def __init__(
        self,
        dsn: str,
        *,
        connection_factory: Callable[..., Any] | None = None,
        connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    ) -> None:
        self._dsn = dsn
        self._connection_factory = connection_factory
        self._connect_timeout_seconds = connect_timeout_seconds

    @staticmethod
    def _record(row: tuple[Any, ...]) -> ExecutionRecord:
        action_payload = row[3]
        if isinstance(action_payload, str):
            action_payload = json.loads(action_payload)
        result = None
        if row[11] is not None:
            result = ExecutionResult(
                action_id=row[1],
                status=row[11],
                detail=row[12] or "",
                latency_ms=row[13] or 0,
            )
        return ExecutionRecord(
            key=ExecutionKey(row[0], row[1], row[2]),
            action=ProposedAction.model_validate(action_payload),
            actor=row[4],
            state=row[5],
            attempt=row[6],
            prepared_at=row[7],
            updated_at=row[8],
            lease_owner=row[9],
            lease_expires_at=row[10],
            result=result,
        )

    def _connect(self) -> Any:
        factory = self._connection_factory
        if factory is None:
            import psycopg

            factory = psycopg.connect
        return factory(
            self._dsn,
            autocommit=False,
            connect_timeout=self._connect_timeout_seconds,
        )

    def check_ready(self) -> None:
        conn = None
        try:
            conn = self._connect()
            row = conn.execute(
                "SELECT to_regclass('argos_audit.execution_journal')"
            ).fetchone()
            if row is None or row[0] is None:
                raise ExecutionJournalConfigurationError(
                    "postgresql execution journal schema is not installed"
                )
        except ExecutionJournalConfigurationError:
            raise
        except Exception as exc:
            raise ExecutionJournalConfigurationError(
                "postgresql execution journal is unavailable"
            ) from exc
        finally:
            if conn is not None:
                conn.close()

    def _connect_safe(self) -> Any:
        try:
            return self._connect()
        except Exception as exc:
            raise ExecutionJournalError(
                "postgresql execution journal is unavailable"
            ) from exc

    @staticmethod
    def _key_params(key: ExecutionKey) -> dict[str, str]:
        return {
            "incident_id": key.incident_id,
            "action_id": key.action_id,
            "operation": key.operation,
        }

    def _select(
        self, conn: Any, key: ExecutionKey, *, for_update: bool = False
    ) -> tuple[Any, ...] | None:
        if for_update:
            query = """SELECT incident_id, action_id, operation, action_payload,
                       actor, state, attempt, prepared_at, updated_at, lease_owner,
                       lease_expires_at, result_status, result_detail, result_latency_ms
                  FROM argos_audit.execution_journal
                 WHERE incident_id=%(incident_id)s AND action_id=%(action_id)s
                   AND operation=%(operation)s
                   FOR UPDATE"""
        else:
            query = """SELECT incident_id, action_id, operation, action_payload,
                       actor, state, attempt, prepared_at, updated_at, lease_owner,
                       lease_expires_at, result_status, result_detail, result_latency_ms
                  FROM argos_audit.execution_journal
                 WHERE incident_id=%(incident_id)s AND action_id=%(action_id)s
                   AND operation=%(operation)s"""
        row = conn.execute(query, self._key_params(key)).fetchone()
        return cast(tuple[Any, ...] | None, row)

    def prepare(self, record: ExecutionRecord) -> ExecutionRecord:
        conn = self._connect_safe()
        try:
            with conn.transaction():
                conn.execute(
                    """INSERT INTO argos_audit.execution_journal
                    (incident_id, action_id, operation, action_payload, actor, state,
                     attempt, prepared_at, updated_at)
                    VALUES (%(incident_id)s, %(action_id)s, %(operation)s,
                            %(action_payload)s::jsonb, %(actor)s, 'prepared', 0,
                            %(prepared_at)s, %(updated_at)s)
                    ON CONFLICT (incident_id, action_id, operation) DO NOTHING""",
                    {
                        **self._key_params(record.key),
                        "action_payload": record.action.model_dump_json(),
                        "actor": record.actor,
                        "prepared_at": record.prepared_at,
                        "updated_at": record.updated_at,
                    },
                )
                row = self._select(conn, record.key, for_update=True)
                if row is None:
                    raise ExecutionJournalError(
                        "execution intent could not be persisted"
                    )
                return self._record(row)
        except ExecutionJournalError:
            raise
        except Exception as exc:
            raise ExecutionJournalError(
                "execution intent could not be persisted"
            ) from exc
        finally:
            conn.close()

    def _update_state(
        self,
        conn: Any,
        key: ExecutionKey,
        *,
        state: JournalState,
        now: datetime,
        lease_owner: str | None,
        lease_expires_at: datetime | None,
        increment_attempt: bool = False,
    ) -> ExecutionRecord:
        if increment_attempt:
            query = """UPDATE argos_audit.execution_journal
                          SET state=%(state)s, attempt=attempt+1,
                              lease_owner=%(lease_owner)s,
                              lease_expires_at=%(lease_expires_at)s,
                              updated_at=%(now)s
                        WHERE incident_id=%(incident_id)s
                          AND action_id=%(action_id)s
                          AND operation=%(operation)s
                    RETURNING incident_id, action_id, operation, action_payload,
                              actor, state, attempt, prepared_at, updated_at,
                              lease_owner, lease_expires_at, result_status,
                              result_detail, result_latency_ms"""
        else:
            query = """UPDATE argos_audit.execution_journal
                          SET state=%(state)s, lease_owner=%(lease_owner)s,
                              lease_expires_at=%(lease_expires_at)s,
                              updated_at=%(now)s
                        WHERE incident_id=%(incident_id)s
                          AND action_id=%(action_id)s
                          AND operation=%(operation)s
                    RETURNING incident_id, action_id, operation, action_payload,
                              actor, state, attempt, prepared_at, updated_at,
                              lease_owner, lease_expires_at, result_status,
                              result_detail, result_latency_ms"""
        row = conn.execute(
            query,
            {
                **self._key_params(key),
                "state": state,
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
                "now": now,
            },
        ).fetchone()
        if row is None:
            raise ExecutionJournalError("execution state could not be updated")
        return self._record(row)

    def claim(
        self,
        key: ExecutionKey,
        *,
        owner: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> ExecutionRecord:
        conn = self._connect_safe()
        try:
            with conn.transaction():
                row = self._select(conn, key, for_update=True)
                if row is None:
                    raise ExecutionJournalError("execution intent is missing")
                record = self._record(row)
                if record.state == "executing":
                    if record.lease_expires_at is not None and record.lease_expires_at <= now:
                        return self._update_state(
                            conn,
                            key,
                            state="ambiguous",
                            now=now,
                            lease_owner=None,
                            lease_expires_at=None,
                        )
                    return record
                if record.state != "prepared":
                    return record
                return self._update_state(
                    conn,
                    key,
                    state="executing",
                    now=now,
                    lease_owner=owner,
                    lease_expires_at=lease_expires_at,
                    increment_attempt=True,
                )
        except ExecutionJournalError:
            raise
        except Exception as exc:
            raise ExecutionJournalError(
                "execution lease could not be acquired"
            ) from exc
        finally:
            conn.close()

    def complete(
        self,
        key: ExecutionKey,
        *,
        owner: str,
        state: JournalState,
        result: ExecutionResult | None,
        now: datetime,
    ) -> ExecutionRecord:
        conn = self._connect_safe()
        try:
            with conn.transaction():
                row = conn.execute(
                    """UPDATE argos_audit.execution_journal
                       SET state=%(state)s, result_status=%(result_status)s,
                           result_detail=%(result_detail)s,
                           result_latency_ms=%(result_latency_ms)s,
                           lease_owner=NULL, lease_expires_at=NULL, updated_at=%(now)s
                     WHERE incident_id=%(incident_id)s AND action_id=%(action_id)s
                       AND operation=%(operation)s AND state='executing'
                       AND lease_owner=%(owner)s
                     RETURNING incident_id, action_id, operation, action_payload,
                               actor, state, attempt, prepared_at, updated_at,
                               lease_owner, lease_expires_at, result_status,
                               result_detail, result_latency_ms""",
                    {
                        **self._key_params(key),
                        "owner": owner,
                        "state": state,
                        "result_status": result.status if result else None,
                        "result_detail": result.detail if result else None,
                        "result_latency_ms": result.latency_ms if result else None,
                        "now": now,
                    },
                ).fetchone()
                if row is None:
                    raise ExecutionJournalError("execution lease is no longer owned")
                return self._record(row)
        except ExecutionJournalError:
            raise
        except Exception as exc:
            raise ExecutionJournalError(
                "execution receipt could not be persisted"
            ) from exc
        finally:
            conn.close()

    def get(self, key: ExecutionKey) -> ExecutionRecord | None:
        conn = self._connect_safe()
        try:
            row = self._select(conn, key)
            return self._record(row) if row is not None else None
        except ExecutionJournalError:
            raise
        except Exception as exc:
            raise ExecutionJournalError(
                "execution journal could not be read"
            ) from exc
        finally:
            conn.close()

    def close(self) -> None:
        return None


def execution_journal_from_env() -> ResponseExecutionJournal:
    dsn = os.environ.get(DSN_ENV)
    if dsn is None or not dsn.strip():
        raise ExecutionJournalConfigurationError(f"{DSN_ENV} is required")
    timeout = _bounded_int(CONNECT_TIMEOUT_ENV, DEFAULT_CONNECT_TIMEOUT_SECONDS, 1, 60)
    lease = _bounded_int(LEASE_ENV, DEFAULT_LEASE_SECONDS, 1, 3600)
    return ResponseExecutionJournal(
        PostgresExecutionStore(dsn, connect_timeout_seconds=timeout),
        lease_seconds=lease,
    )
