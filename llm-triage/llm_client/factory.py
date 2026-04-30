"""Factory that returns the active `LLMClient` based on `LLM_BACKEND`.

The rest of the codebase depends only on this factory + the abstract
`LLMClient`, never on a concrete backend class. Swapping providers is a
one-line config change (env var) with no code modifications, per
ADR-0001.

References:
    - ADR-0001 §Plan de implementación (factory skeleton, env var name,
      and acceptance criterion: "Switch entre backends en demo en vivo
      funciona sin reinicio del servicio").
    - SAD §13.3 (vendor portability cross-cutting concern).

TODO:
    - Implement `get_llm_client() -> LLMClient`.
    - Read `LLM_BACKEND` env var, default `deepseek`.
    - Map `deepseek` -> DeepSeekClient, `qwen` -> QwenClient.
    - Raise `ValueError` for unknown backends.
    - (Future) Add `llama_local` backend per SAD §14 future work.
"""
