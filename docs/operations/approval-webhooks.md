# Approval webhook operation

## Required controls

Keep all secrets outside git and logs. Telegram voting requires
`ARGOS_JWT_SECRET`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_CHAT_ID`, and
`TELEGRAM_APPROVER_USER_IDS`. Configure Telegram `setWebhook.secret_token`
with the exact value of `TELEGRAM_WEBHOOK_SECRET`.
An accepted Telegram callback atomically writes the Incident and a version 1
`approval:telegram:vote:*` receipt, then deletes its
`approval:telegram:token:*` JTI in the same Redis transaction. Do not consume or
delete JTI keys in middleware or operational scripts.

Twilio voting requires `TWILIO_AUTH_TOKEN` and an exact
`APPROVAL_API_PUBLIC_URL`. Production URLs must use HTTPS. The URL is part of
Twilio's signature; proxy or path changes require updating this value.

Set `APPROVAL_CALLBACK_TTL_SECONDS` long enough to cover the voice escalation
and approval window. The default is 300 seconds. Redis must be shared by the
consumer and Approval API: the consumer stores a pre-call request correlation;
the signed TwiML callback consumes it and creates the CallSid binding.

## Migration

1. Generate new random secrets of at least 32 bytes.
2. Configure the Telegram webhook secret and individual numeric user IDs.
3. Configure the exact public HTTPS URL used by Twilio.
4. Deploy the Approval API and consumer with the same Redis and secrets.
5. Re-notify pending incidents; legacy buttons are intentionally invalid.
6. Allow legacy `approval:telegram:token:*` keys to expire. New confirmed votes
   create `approval:telegram:vote:*` receipts; do not pre-delete either key
   during a rolling deployment.
7. Remove or allow TTL expiry of legacy `approval:twilio:call:*` and
   `approval:twilio:vote:*` state created before ADR-0016. New receipts are
   JSON version 1 and are not compatible with the former `claimed` marker.
8. Verify forged, expired, replayed, concurrent, and unauthorized callbacks;
   inject a Redis transaction failure and verify retry before enabling a real
   executor.

## Deferred gates

PR-01A was implemented by PR #11 and merged into `main` as
`074c0be945b6755df2184b75eb4829b054fa9266`. The identifiers below are planned
work streams, not evidence that remote pull requests already exist:

- PR-01B1 owns fail-closed executor selection by deployment environment.
- PR-01B2 owns the durable execution journal and abandoned-effect reconciliation.
- PR-01B3 owns Wazuh/endpoint idempotency and Windows/Linux recovery validation.
- PR-R01 owns PostgresSink connection timeout and lifecycle.
- PR-Q01 owns the general mypy baseline.
- PR-SC01 owns Pillow/setuptools remediation.
- PR-D01 owns the complete Twilio dispatch outbox.

PR #11 CI validated the isolated callback behavior on Python 3.11 and 3.12,
Ruff, and `mypy argos_contracts`. It did not exercise live Telegram/Twilio
provider credentials, a real Wazuh response chain, or Windows/Linux
containment. Treat those as explicit E2E gates, not implied support.

## Safe rollback

Do not restore legacy callbacks. If rollback is necessary, remove external
access to the Approval API, disable provider voting, and keep the executor in
simulated development mode. Temporary Redis keys expire automatically.
Do not delete active JTI, request, CallSid, or vote receipt keys during rollback;
allow their TTL to expire so in-flight callbacks fail closed predictably.
