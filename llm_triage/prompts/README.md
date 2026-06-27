# prompts/ — Jinja2 templates for the triage LLM

Versioned, reviewable prompt templates rendered with Jinja2 and fed to the active `LLMClient`. Keeping prompts as files (not inline strings) makes them diffable in PRs, swappable per backend (el primario NVIDIA usa `response_format=json_object`; el fallback Ollama, diferido, necesita prompts de formato más explícitos — ADR-0001 v3), and easy to A/B test against the labelled dataset built in Q5.

## Planned templates

- `system_triage.j2` — system prompt establishing the analyst persona, output contract, and refusal rules (no action recommendations beyond the schema fields, no free-form prose).
- `user_triage.j2` — user prompt that injects the alert context, retrieved RAG passages, and the JSON schema the response must conform to.
- `injection_guard.j2` — sanitization wrapper for fields that may contain attacker-controlled strings (process names, command lines, file paths). Hardens against EV-05 (adversarial probes against LLM).

## Status

**Implementado (Fase 4):** `system_triage.j2` + `user_triage.j2` los renderiza `prompts/__init__.py` y los usa
`OpenAIClient`. `injection_guard.j2` no se materializó como template: la defensa anti-inyección vive en
`llm_triage/sanitizer.py` (T-030) + las reglas del system prompt.

## References

- SAD §7.4 (structured output contract the prompt must enforce).
- SAD §12.1 R-06 (LLM output validated, never trusted blindly — prompt is the first line; Pydantic + MITRE whitelist is the second).
- USE_CASES.md EV-05 (adversarial probe evaluation; prompts must be hardened against prompt injection).
