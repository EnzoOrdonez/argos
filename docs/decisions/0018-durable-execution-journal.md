# ADR-0018: PostgreSQL authoritative execution journal

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-07-23 |
| Scope | PR-01B2 |
| Related | ADR-0012, ADR-0013, ADR-0017 |

## Context

The incident projection in Redis was written only after response effects. A
process crash in that interval could execute the same logical action again
after restart. Executor-local memory could not close that window.

## Decision

PostgreSQL is the authority for response execution. Redis remains the
operational incident projection and coordination store; it is not the source
of truth for whether an external effect was attempted.

The stable identity is '(incident_id, action_id, operation)', where operation
is 'run' or 'revert'. The order is:

1. insert 'prepared' in PostgreSQL;
2. atomically claim 'executing' with an owner and bounded lease;
3. invoke the external executor outside the database transaction;
4. persist the receipt as 'succeeded' or 'failed';
5. update the Redis incident projection.

If step 5 fails, a retry reads the terminal PostgreSQL receipt and rebuilds the
Redis projection without invoking the effect again.

An exception, a partial receipt, or an expired 'executing' lease is
'ambiguous'. ARGOS does not retry ambiguous effects automatically. A future
reconciler must inspect the endpoint before an operator can choose a new
attempt. This is at-most-one automatic attempt, not exactly-once delivery.

PostgreSQL and the journal schema are mandatory, fail-closed dependencies for
processes capable of executing actions. Read-only services do not require the
journal. 'MemoryExecutionStore' is restricted to tests and explicit non-live
demos.

## Consequences

- PostgreSQL unavailability blocks action-capable processes before Redis is
  opened.
- Each transition uses a bounded, independently closed connection.
- Action payload collisions under the same stable identity are rejected.
- PostgreSQL HA, TLS, backup/restore, and operator reconciliation UI remain
  separate gates; this ADR does not claim production readiness.

## Migration and rollback

The migration adds 'argos_audit.execution_journal' and one partial recovery
index. It does not alter or delete existing rows. Existing volumes must apply
'soar/audit/schema.sql' before restarting action-capable services.

Rollback is application-first: stop action-capable services, restore the
previous application version, then optionally retain the table for evidence.
Dropping the table is not required and would destroy execution history.
