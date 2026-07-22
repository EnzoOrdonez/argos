# ADR-0017: Executor runtime fail-closed

- **Status:** Accepted
- **Date:** 2026-07-22
- **Scope:** PR-01B1

## Context

The response executor defaulted to `simulated` and also fell back to it when Wazuh
configuration or construction failed. A deployment intended to perform real response
could therefore remain healthy while silently not executing actions.

## Decision

`ENVIRONMENT` and `ARGOS_EXECUTOR` are mandatory and independently validated.
`simulated` is an executor, not an environment. It is allowed only in explicit
`development` and `test` environments. `staging` and `production` require `wazuh`.
Missing, empty, unknown or incompatible values stop startup. Missing Wazuh credentials
or executor construction failures also stop startup and never create a simulated
executor. Error messages identify configuration keys but do not include secret values.

The Approval API validates this selection before opening Redis. The decision-engine
consumer validates it before constructing audit sinks or consuming events. Explicit
non-live demo paths may continue constructing `SimulatedExecutor` directly.

## Consequences

- Existing installs must set both variables before upgrading.
- Misconfigured live services become unavailable instead of reporting false execution.
- This ADR does not add Wazuh connectivity readiness, TLS policy, durable idempotency,
  effect reconciliation or recovery; those remain separate gates.
- ADR-0015 remains the historical source for the simulated/real prototype split, but
  its default-simulation statement is superseded by this decision.
