"""Fail-closed configuration and readiness for the PostgreSQL authority."""

from __future__ import annotations

import pytest

from soar.execution.postgres import (
    ExecutionJournalConfigurationError,
    PostgresExecutionStore,
    execution_journal_from_env,
)


def test_execution_journal_dsn_is_required(monkeypatch) -> None:
    monkeypatch.delenv("ARGOS_EXECUTION_SQL_DSN", raising=False)
    with pytest.raises(ExecutionJournalConfigurationError, match="ARGOS_EXECUTION_SQL_DSN"):
        execution_journal_from_env()

    monkeypatch.setenv("ARGOS_EXECUTION_SQL_DSN", "   ")
    with pytest.raises(ExecutionJournalConfigurationError, match="ARGOS_EXECUTION_SQL_DSN"):
        execution_journal_from_env()


def test_invalid_timeout_and_lease_are_rejected(monkeypatch) -> None:
    monkeypatch.setenv("ARGOS_EXECUTION_SQL_DSN", "postgresql://unused")
    monkeypatch.setenv("ARGOS_EXECUTION_SQL_CONNECT_TIMEOUT_SECONDS", "0")
    with pytest.raises(ExecutionJournalConfigurationError):
        execution_journal_from_env()

    monkeypatch.setenv("ARGOS_EXECUTION_SQL_CONNECT_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("ARGOS_EXECUTION_LEASE_SECONDS", "unknown")
    with pytest.raises(ExecutionJournalConfigurationError):
        execution_journal_from_env()


def test_readiness_failure_is_sanitized() -> None:
    marker = "not-for-logs"

    def fail_connect(*_args, **_kwargs):
        raise RuntimeError(f"driver leaked {marker}")

    store = PostgresExecutionStore(
        f"postgresql://argos:{marker}@localhost/argos",
        connection_factory=fail_connect,
    )
    with pytest.raises(ExecutionJournalConfigurationError) as captured:
        store.check_ready()

    assert marker not in str(captured.value)
    assert "postgresql execution journal is unavailable" in str(captured.value)
