# TECHNICAL DEBT — argos_contracts and related modules

| Field | Value |
|-------|-------|
| Document type | Technical debt log |
| Status | Open items |
| Owner | P1 |
| Related | `CONTRACTS_SPECIFICATION.md` |

## Purpose

Track type-safety and contract gaps that were knowingly accepted during the contracts-first sealing exercise (Week 2). Each entry names the spec ambiguity that produced it, the runtime risk, why it was deferred, and the concrete resolution path. Reviewing this file before bumping `argos_contracts.__version__` is mandatory.

---

## TD-01 — `Incident.host` typed as `dict[str, Any]` instead of `HostInfo`

**Spec source:** `CONTRACTS_SPECIFICATION.md` §incident.py.

**Current state:** `Incident.host: dict[str, Any]` per the literal type hint, with the inline comment `# uses HostInfo-compatible structure`. Any dict shape is accepted.

**Risk:** type-safety gap. A producer can write `incident.host = {"hsot_id": "..."}` (typo) and the model validates clean. A consumer reading `incident.host["criticality"]` against a malformed dict raises `KeyError` at runtime instead of `ValidationError` at construction. Diverges from the strong typing applied everywhere else in `argos_contracts` (e.g. `AlertContext.host: HostInfo`).

**Why deferred:** the spec is internally inconsistent (type hint says `dict`, comment says HostInfo). Resolving means changing the spec, not just the code, which is out of scope for the Week 2 sealing exercise. The user accepted the literal reading on review.

**Resolution path (when promoted):**
1. Change the field declaration to `host: HostInfo` (already defined in `triage.py`, importable from `argos_contracts`).
2. Update the test fixture `_incident()` to construct `HostInfo(id=..., criticality=...)` instead of a literal dict.
3. Confirm the JSON roundtrip test still passes (Pydantic serializes nested models to dicts and rebuilds them on `model_validate_json`).
4. Bump `argos_contracts.__version__` to 1.1.0; this is breaking for any producer that was sending stray keys.

---

## TD-02 — `FinalDecision` string fields not constrained as `Literal[...]`

**Spec source:** `CONTRACTS_SPECIFICATION.md` §incident.py.

**Current state:** `FinalDecision.outcome`, `FinalDecision.policy_applied`, and `FinalDecision.execution_status` are typed as plain `str` (or `str | None`). The allowed values are documented in the field descriptions only:

| Field | Allowed values (documented in `description=`) |
|-------|-----------------------------------------------|
| `outcome` | `EXECUTE_ISOLATION`, `NO_ACTION`, `REVERTED` |
| `policy_applied` | `auto-execute`, `unanimous-approve`, `conservative-wins`, `two-person-rule`, `timeout-escalation` |
| `execution_status` | `success`, `failed`, `partial` |

**Risk:** type-safety gap. A producer can write `outcome="executed"` (typo) and the model accepts it. The Streamlit Approval Console (P4) and audit-log consumers branch on these strings; an unknown value silently routes to a default branch and breaks rendering or aggregation queries.

**Why deferred:** the spec types these as `str`. Tightening to `Literal[...]` is a contract change, not just a code change, and was outside the literal scope of the sealing exercise. We may also discover additional valid values during tier calibration (Week 9 per `OPEN_QUESTIONS_RESOLUTION.md` Q5) — committing to the v1 enumeration now risks needing a second breaking change.

**Resolution path (when promoted):**
1. Define `Literal["EXECUTE_ISOLATION", "NO_ACTION", "REVERTED"]` for `outcome`, equivalent literals for `policy_applied` and `execution_status`.
2. Add explicit tests asserting that values outside the literal set reject with `ValidationError`.
3. Coordinate with P4 (Streamlit) before merging — the front end branches on these strings, so a literal-tighten that drops a value the UI emits is a runtime regression.
4. Bump `argos_contracts.__version__` to 1.1.0; this is breaking for any producer that was emitting non-canonical values.

---

## How to use this file

When adding an entry, include:
1. **Spec source** — the exact section of `CONTRACTS_SPECIFICATION.md` (or other authoritative doc) that left the ambiguity.
2. **Current state** — the literal field declaration as it exists today.
3. **Risk** — the concrete failure mode at runtime, named with the consumer it would break.
4. **Why deferred** — the reason this was not fixed in the original sealing exercise.
5. **Resolution path** — the exact code/spec changes required, plus the version bump implication.
