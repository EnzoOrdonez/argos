"""Tier Router — clasifica un evento correlacionado en T0/T1/T2/T3.

Pieza más crítica del SOAR: de su salida dependen las acciones automáticas y/o
la solicitud de aprobación humana. Función pura: sin I/O, determinística.

Autoridad de la lógica:
- ADR-0003 (confidence-tiered automation) — esquema de tiers + bandas de confianza.
- SAD §6.2 (fusion logic per layer combination) — combinaciones de capas.
- ADR-0008 — técnicas de impacto inequívoco (ransomware + DoS) → T0.
- Invariante R-2 (THREAT_MODEL / soar/README): la Capa 4 (LLM) NUNCA está en el
  camino crítico de contención. El router decide SOLO con Capas 1/2/3.

Adaptado al contrato congelado `argos_contracts` v1.1.0 (regla #2 del HANDOFF):
consume señales derivadas de `NormalizedAlert`, no del inexistente
`NormalizedEvent` que asumía el manual P1 §2.1.

Fuera de scope acá (se aplica aguas abajo, §2.7): el override por host
`Criticality.PRODUCTION_CRITICAL` → two-person rule (ADR-0003), que escala a
aprobación humana incluso un T0/T1. Este router devuelve el tier de *detección*;
la política de aprobación se decide después con el tier + criticidad + acción.
"""

from __future__ import annotations

from dataclasses import dataclass

from argos_contracts.enums import Layer, Severity, Tier
from soar.decision_engine.policies import (
    AUTO_T0_TECHNIQUES,
    HIGH_FIDELITY_SEVERITIES,
    L2_ALONE_T2_MIN_SCORE,
    T1_CORROBORATION_MIN_CONFIDENCE,
)


@dataclass(frozen=True)
class RoutingSignal:
    """Entrada del router: resultado de correlacionar uno o más `NormalizedAlert`
    del mismo host/incidente dentro de una ventana.

    Es local a `soar/` a propósito — NO es un contrato cross-team, así
    `argos_contracts` v1.1.0 queda intacto. El consumer (Fase 3) lo construye.
    """

    fired_layers: frozenset[Layer]
    technique_mitre: str | None = None
    # severity_label del alert de Capa 1 (proxy del `level:` Sigma). Solo se usa
    # cuando la Capa 1 dispara sola. None si la Capa 1 no disparó.
    l1_severity: Severity | None = None
    # severity_score del alert de Capa 2 (= ensemble_score ML, 0-1). Solo se usa
    # cuando la Capa 2 dispara sola. None si la Capa 2 no disparó.
    l2_score: float | None = None
    # Confianza fusionada de la corroboración Capa1+Capa2 (0-1), calculada por el
    # consumer. Si es None se trata como incierta -> T2 (fail-safe: en una DB
    # bancaria no auto-aislamos a ciegas sin confianza explícita).
    corroboration_confidence: float | None = None
    host_id: str = ""
    contributing_alert_ids: tuple[str, ...] = ()


def route(signal: RoutingSignal) -> Tier:
    """Devuelve el Tier asignado a la señal. Pura: sin I/O, determinística."""
    # 0. Fast-path: técnicas de impacto inequívoco -> T0 (sin HITL). ADR-0008.
    if signal.technique_mitre in AUTO_T0_TECHNIQUES:
        return Tier.T0

    l1 = Layer.LAYER_1 in signal.fired_layers
    l2 = Layer.LAYER_2 in signal.fired_layers
    l3 = Layer.LAYER_3 in signal.fired_layers

    # 1. Canary (Capa 3) es zero-FP por diseño -> siempre gana a T0.
    #    Cubre L3 sola, L1+L3, L2+L3 y L1+L2+L3 (SAD §6.2).
    if l3:
        return Tier.T0

    # 2. Corroboración Capa1+Capa2 sin canary (SAD §6.2 -> T1), modulada por la
    #    confianza fusionada (bandas ADR-0003): si es incierta -> T2 (humano).
    if l1 and l2:
        confidence = signal.corroboration_confidence or 0.0
        return Tier.T1 if confidence >= T1_CORROBORATION_MIN_CONFIDENCE else Tier.T2

    # 3. Capa 1 sola: la fidelidad de la regla Sigma decide (ADR-0003 level->tier).
    if l1:
        if signal.l1_severity in HIGH_FIDELITY_SEVERITIES:
            return Tier.T2
        return Tier.T3

    # 4. Capa 2 sola: el score del ensemble ML decide (SAD §6.2).
    if l2:
        score = signal.l2_score or 0.0
        return Tier.T2 if score >= L2_ALONE_T2_MIN_SCORE else Tier.T3

    # 5. Ninguna capa disparó: invariante violada (el router no debe llamarse así).
    raise ValueError("route() llamado sin capas en fired_layers")
