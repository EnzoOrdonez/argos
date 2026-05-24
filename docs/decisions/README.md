# Architecture Decision Records (ADRs)

This directory contains the architectural decisions made for ARGOS, following the [ADR pattern popularized by Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

Each ADR is a short document that captures:
- **Context:** what problem we faced.
- **Decision:** what we chose to do.
- **Alternatives considered:** what else we evaluated and why we rejected it.
- **Consequences:** trade-offs accepted, both positive and negative.

Rejected decisions are documented too — they show that the team evaluated alternatives rigorously rather than ignoring them.

---

## Index

| # | Title | Status | Summary |
|---|-------|--------|---------|
| [0001](./0001-llm-vendor-agnostic.md) | LLM vendor-agnostic via LLMClient interface (v2) | ✅ Accepted | Abstract LLM behind interface; OpenAI GPT-4o-mini primary (US-based) + Llama 3.1 8B local fallback (zero-egress). v2 reasignó primario por soberanía de datos. Swap via env var. |
| [0002](./0002-heartbeat-default-60s.md) | Wazuh agent heartbeat — keep default 60s | ✅ Accepted | Reject lowering heartbeat interval; alert fatigue cost outweighs marginal detection improvement. |
| [0003](./0003-confidence-tiered-automation.md) | Confidence-tiered automation with HITL SOAR | ✅ Accepted | 4-tier classification (T0-T3); auto-execute high confidence, human approval for medium-uncertain. T2 timeout 3min with throttle+snapshot during countdown. |
| [0004](./0004-auto-rollback-rejected.md) | Auto-rollback "dead man's switch" | ❌ Rejected | Rejected. Contradicts "fails closed" principle. Documented to show the team considered and consciously rejected the option. |
| [0005](./0005-notification-channel-abstraction.md) | Notification channel abstraction | ✅ Accepted | Strategy pattern for notification channels. Foundation para ADR-0007; canales concretos definidos allí. |
| [0006](./0006-split-brain-resolution.md) | Split-brain resolution — conservative-wins policy | ✅ Accepted | When approvers disagree, conservative-wins policy with 60s consolidation window. In containment context, conservative = isolate. |
| [0007](./0007-notification-multichannel-escalation.md) | Multi-channel notification escalation chain (v2) | ✅ Accepted | Telegram (primario) + Discord (visibilidad del equipo) en paralelo a t=0; Twilio Voice (DTMF) como escalación a t=60s; email degradado a notificación post-facto. v2 reemplazó ntfy.sh y Slack (canales que el equipo no usa) por Discord. |

---

## Closure document

| Document | Purpose |
|----------|---------|
| [OPEN_QUESTIONS_RESOLUTION.md](./OPEN_QUESTIONS_RESOLUTION.md) | Resolves 9 minor open questions in batch (Q1-Q9), including the corrected T2 timeout behavior with throttle and proactive snapshot during countdown. |

---

## Conventions

- ADRs are **immutable once accepted**. Changes happen via new ADRs that supersede earlier ones, OR via in-place version bumps (v2, v3) when the same decision needs to be revisited honestly — preserving the original rationale and the new one side-by-side.
- New ADR number = max existing + 1.
- Status values: `Proposed`, `Accepted`, `Rejected`, `Superseded by ADR-NNNN`, `Deprecated`.
- Format follows Michael Nygard's template adapted for our needs.

---

## Adding a new ADR

When making a significant architectural change post-design-freeze:

1. Copy an existing ADR as template.
2. Use next sequence number.
3. Fill in: context, decision, alternatives, consequences.
4. Update this README index.
5. Reference from related documents (SAD, threat model, use cases) as needed.
6. PR to `main` requires review by at least one other team member.
