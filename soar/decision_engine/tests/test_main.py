"""Tests del daemon consumer (`python -m soar.decision_engine`, Fase 5a)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakeredis import FakeAsyncRedis

from argos_contracts.alert import NormalizedAlert
from argos_contracts.enums import Layer, Severity
from soar.audit.logger import AuditLogger
from soar.decision_engine import __main__ as daemon
from soar.decision_engine.consumer import GROUP, STREAM, SOARConsumer
from soar.decision_engine.scheduler import WindowScheduler
from soar.decision_engine.triage_hook import TriageClient
from soar.execution.journal import MemoryExecutionStore, ResponseExecutionJournal
from soar.execution.postgres import ExecutionJournalConfigurationError
from soar.playbooks.factory import ExecutorConfigurationError
from soar.playbooks.simulated import SimulatedExecutor


@pytest.fixture(autouse=True)
def explicit_test_executor(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ARGOS_EXECUTOR", "simulated")


def _t3_alert() -> NormalizedAlert:
    # L1 sola MEDIUM → Tier 3 (solo notifica): se procesa y ackea sin agendar relojes
    # (evita tasks de sleep huérfanas en el test).
    return NormalizedAlert(
        alert_id="a-1",
        source_layer=Layer.LAYER_1,
        timestamp=datetime.now(UTC),
        host_id="web-prod-01",
        severity_score=0.4,
        severity_label=Severity.MEDIUM,
        technique_mitre="T1110",
    )


def _journal() -> ResponseExecutionJournal:
    return ResponseExecutionJournal(MemoryExecutionStore())


def test_build_consumer_wires_collaborators(monkeypatch) -> None:
    monkeypatch.delenv("ARGOS_AUDIT_SQL_DSN", raising=False)
    monkeypatch.delenv("ARGOS_REQUIRE_APPROVAL", raising=False)
    r = FakeAsyncRedis(decode_responses=True)

    consumer = daemon.build_consumer(r, journal=_journal())

    assert isinstance(consumer, SOARConsumer)
    assert isinstance(consumer._executor, SimulatedExecutor)
    assert isinstance(consumer._scheduler, WindowScheduler)
    assert isinstance(consumer._audit, AuditLogger)
    assert isinstance(consumer._triage, TriageClient)
    assert consumer._notifier is not None
    # ARGOS_REQUIRE_APPROVAL default ON en el daemon → consumer Y scheduler
    assert consumer._require_approval is True
    assert consumer._scheduler._require_approval is True


def test_build_consumer_default_only_memory_sink(monkeypatch) -> None:
    monkeypatch.delenv("ARGOS_AUDIT_SQL_DSN", raising=False)
    consumer = daemon.build_consumer(
        FakeAsyncRedis(decode_responses=True), journal=_journal()
    )
    from soar.audit.postgres import PostgresSink

    assert not any(isinstance(s, PostgresSink) for s in consumer._audit._sinks)


def test_build_consumer_adds_postgres_sink_when_dsn(monkeypatch) -> None:
    monkeypatch.setenv("ARGOS_AUDIT_SQL_DSN", "postgresql://x:y@localhost:5432/z")
    consumer = daemon.build_consumer(
        FakeAsyncRedis(decode_responses=True), journal=_journal()
    )
    from soar.audit.postgres import PostgresSink

    assert any(isinstance(s, PostgresSink) for s in consumer._audit._sinks)


def test_build_consumer_require_approval_off_by_env(monkeypatch) -> None:
    monkeypatch.setenv("ARGOS_REQUIRE_APPROVAL", "false")
    consumer = daemon.build_consumer(
        FakeAsyncRedis(decode_responses=True), journal=_journal()
    )
    assert consumer._require_approval is False
    assert consumer._scheduler._require_approval is False


def test_build_consumer_wazuh_without_config_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ARGOS_EXECUTOR", "wazuh")
    for var in ("WAZUH_API_URL", "WAZUH_API_USER", "WAZUH_API_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ExecutorConfigurationError):
        daemon.build_consumer(FakeAsyncRedis(decode_responses=True))


def test_invalid_executor_fails_before_postgres_initialization(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ARGOS_EXECUTOR", "simulated")
    monkeypatch.setenv("ARGOS_AUDIT_SQL_DSN", "postgresql://unused")

    def must_not_initialize(_dsn: str) -> None:
        raise AssertionError("PostgresSink initialized before executor validation")

    monkeypatch.setattr("soar.audit.postgres.PostgresSink", must_not_initialize)

    with pytest.raises(ExecutorConfigurationError):
        daemon.build_consumer(FakeAsyncRedis(decode_responses=True))


async def test_amain_once_processes_and_returns(monkeypatch) -> None:
    monkeypatch.delenv("ARGOS_AUDIT_SQL_DSN", raising=False)
    monkeypatch.setenv("ARGOS_REQUIRE_APPROVAL", "true")
    r = FakeAsyncRedis(decode_responses=True)
    await r.xadd(STREAM, {"payload": _t3_alert().model_dump_json()})

    await daemon.amain(
        r, once=True, journal=_journal()
    )  # no cuelga: once=True procesa y retorna

    pending = await r.xpending(STREAM, GROUP)
    assert pending["pending"] == 0  # el entry se procesó y ackeó


async def test_amain_closes_audit_sinks(monkeypatch) -> None:
    monkeypatch.setenv("ARGOS_AUDIT_SQL_DSN", "postgresql://unused")
    r = FakeAsyncRedis(decode_responses=True)
    await r.xadd(STREAM, {"payload": _t3_alert().model_dump_json()})
    closed = False

    class ClosableSink:
        def __init__(self, _dsn: str) -> None:
            pass

        def emit(self, _event) -> None:
            pass

        def close(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setattr("soar.audit.postgres.PostgresSink", ClosableSink)

    await daemon.amain(r, once=True, journal=_journal())

    assert closed is True


async def test_amain_rejects_invalid_executor_before_opening_redis(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ARGOS_EXECUTOR", "simulated")

    def must_not_open_redis(*_args, **_kwargs):
        raise AssertionError("Redis opened before executor validation")

    monkeypatch.setattr(daemon.redis, "from_url", must_not_open_redis)

    with pytest.raises(ExecutorConfigurationError):
        await daemon.amain(once=True)


async def test_amain_requires_postgres_journal_before_opening_redis(monkeypatch) -> None:
    monkeypatch.delenv("ARGOS_EXECUTION_SQL_DSN", raising=False)

    def must_not_open_redis(*_args, **_kwargs):
        raise AssertionError("Redis opened before journal validation")

    monkeypatch.setattr(daemon.redis, "from_url", must_not_open_redis)

    with pytest.raises(ExecutionJournalConfigurationError):
        await daemon.amain(once=True)
