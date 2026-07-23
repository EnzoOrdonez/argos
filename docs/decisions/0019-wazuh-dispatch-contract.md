# ADR-0019: Wazuh dispatch contract without endpoint receipts

- Status: Accepted
- Date: 2026-07-23
- Scope: PR-01B3a
- Supersedes: ADR-0012 claims about in-memory idempotency and rollback no-ops

## Context

Wazuh manager acceptance of `PUT /active-response` is not a verifiable receipt
of the endpoint effect. The existing adapter also passed an ARGOS asset name as
an agent ID, kept idempotency only in memory, and could report a manager HTTP
200 as success. Those properties are unsafe across restarts and retries.

## Decision

- Derive a stable execution identity from `incident_id + action_id + operation`
  and propagate it in the argument and structured ARGOS payload.
- Resolve ARGOS assets through an explicit, one-to-one asset-to-agent mapping.
- Require the mapped Wazuh agent to exist and be active before dispatch.
- Apply one bounded timeout to authentication, preflight, and dispatch.
- Treat a verified manager rejection as `failed`.
- Treat HTTP 200 without an endpoint receipt, transport failure after dispatch,
  and manager 5xx as `partial`; the durable journal persists `ambiguous`.
- Never retry an ambiguous execution automatically. PostgreSQL remains the
  journal authority; Redis is not an effect receipt.
- Mark process kill and snapshot as irreversible.
- Block remote reverts until prior endpoint state and a restoration receipt can
  be captured and verified.

## Consequences and limits

This change does not provide exactly-once external effects. It does not prove
that an active-response script ran, verify postconditions, or implement safe
Windows/Linux rollback. Those are PR-01B3b gates and require isolated Wazuh,
disposable Linux and Windows VMs, snapshots, reset procedures, and an endpoint
evidence channel. Until then this capability is not E2E validated or production
ready.

Rollback of this software change is a code/config rollback only. Operators must
not infer endpoint rollback from reverting this commit.
