# ADR-0016 - Authenticated approval callbacks

| Field | Value |
|-------|-------|
| Status | Accepted - 2026-07-20 |
| Deciders | Project owner and security architecture review |
| Related | ADR-0006, ADR-0007, ADR-0010, ADR-0013, Threat Model T-068/T-069 |

## Context

The Approval API accepted Telegram votes when the JWT signer was absent and
accepted Twilio DTMF without validating the provider. A reachable callback
endpoint could therefore turn attacker-controlled HTTP into a containment
decision. The daemon also emitted legacy Telegram buttons without persisting
signed tokens and did not compose the Twilio voice channel.

## Decision

- There is no unsigned or legacy approval mode.
- Telegram requires the provider webhook secret, a single-use JWT, the expected
  chat, and an explicit allowlist of individual Telegram user IDs. JWT
  validation occurs while its Redis token is watched; Incident mutation, a
  versioned vote receipt, and JTI deletion commit in one transaction. A failed
  commit leaves the JTI retryable, while a confirmed receipt rejects replay.
- Before creating a Twilio call, ARGOS persists a random TTL-bound request
  correlation. The provider-signed TwiML callback atomically consumes that
  correlation and binds CallSid to the incident.
- A Twilio vote atomically persists the Incident mutation and a versioned
  single-use receipt with Redis WATCH/MULTI/EXEC. Post-vote effects use a
  durable leased state (pending, processing, completed) so controlled failures
  can be retried without mutating the vote twice.
- Provider state is ephemeral, namespaced, and TTL-bound in Redis. Failure to
  persist it blocks the approval path.
- Missing or partial provider configuration disables the callback or fails
  channel composition; it never relaxes validation.
- OIDC remains the production identity target. Provider IDs are a temporary
  authorization boundary until OIDC subjects and ARGOS RBAC are introduced.

## Consequences

Existing unsigned buttons and calls become invalid and pending incidents must
be re-notified. Redis availability is required to issue or accept approvals;
loss of Redis safely blocks call creation or voting. A crash after an external
effect succeeds but before its receipt is marked completed can cause that
effect to be attempted again after the lease expires. Durable executor
idempotency remains a separate PR-01B requirement.

The following work remains deliberately separate from PR-01A:

- PR-01B: durable executor idempotency and recovery of abandoned effects.
- PR-R01: bounded PostgresSink connection and lifecycle reliability.
- PR-Q01: repository-wide mypy baseline remediation.
- PR-SC01: Pillow/setuptools dependency remediation and lock refresh.
- PR-D01: durable Twilio dispatch outbox and provider-side deduplication.

## Verification

Tests cover invalid provider signatures, unauthorized users/chats, expired or
replayed JWTs, Telegram commit failure/retry and concurrent receipt creation,
Twilio URL/body tampering, CallSid binding recovery, failed and ambiguous
Redis commits, concurrent callbacks,
single vote mutation, effects lease recovery, and untrusted Host headers.
