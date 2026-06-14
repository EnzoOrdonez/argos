"""Tests del Tier Router. Objetivo: 100% coverage (pieza crítica, ADR-0003/SAD §6.2).

Cada caso cita el UC o la regla de fusión que valida.
"""

from __future__ import annotations

import pytest

from argos_contracts.enums import Layer, Severity, Tier
from soar.decision_engine.tier_router import RoutingSignal, route

L1, L2, L3 = Layer.LAYER_1, Layer.LAYER_2, Layer.LAYER_3


def sig(layers, **kw) -> RoutingSignal:
    return RoutingSignal(fired_layers=frozenset(layers), **kw)


# --- Regla 0: fast-path por técnica de impacto inequívoco -> T0 (ADR-0008) ---
@pytest.mark.parametrize("technique", ["T1485", "T1486", "T1490", "T1498", "T1499"])
def test_auto_t0_techniques_force_t0(technique):
    # Incluso con una sola capa y severidad baja, la técnica fuerza T0.
    assert route(sig([L1], technique_mitre=technique, l1_severity=Severity.LOW)) == Tier.T0


def test_ddos_technique_beats_single_layer_path():
    # UC-06: DDoS dispara solo Capa 1; sin el fast-path caería en T2. Con él -> T0.
    assert route(sig([L1], technique_mitre="T1498", l1_severity=Severity.HIGH)) == Tier.T0


def test_non_auto_technique_follows_normal_fusion():
    # UC-08: T1190 (SQLi) NO está en el fast-path -> sigue la fusión (L1+L2 -> T1).
    assert (
        route(sig([L1, L2], technique_mitre="T1190", corroboration_confidence=0.9))
        == Tier.T1
    )


# --- Regla 1: canary (Capa 3) zero-FP siempre gana a T0 (SAD §6.2) ---
@pytest.mark.parametrize("layers", [[L3], [L1, L3], [L2, L3], [L1, L2, L3]])
def test_layer3_always_t0(layers):
    assert route(sig(layers, corroboration_confidence=0.1)) == Tier.T0


# --- Regla 2: corroboración L1+L2 modulada por confianza (ADR-0003 bandas) ---
def test_corroboration_high_confidence_t1():
    # UC-08 sqlmap: señales high-fidelity -> T1 (auto-isolate).
    assert route(sig([L1, L2], corroboration_confidence=0.88)) == Tier.T1


def test_corroboration_threshold_boundary_is_t1():
    assert route(sig([L1, L2], corroboration_confidence=0.80)) == Tier.T1


def test_corroboration_uncertain_confidence_t2():
    # UC-07 falso positivo: L1+L2 pero confianza incierta -> T2 (humano cancela).
    assert route(sig([L1, L2], corroboration_confidence=0.65)) == Tier.T2


def test_corroboration_none_confidence_defaults_t2():
    # Sin confianza explícita -> fail-safe a T2 (no auto-aislar la DB a ciegas).
    assert route(sig([L1, L2])) == Tier.T2


# --- Regla 3: Capa 1 sola, fidelidad Sigma (ADR-0003 level->tier) ---
@pytest.mark.parametrize("sev", [Severity.HIGH, Severity.CRITICAL])
def test_l1_alone_high_fidelity_t2(sev):
    assert route(sig([L1], l1_severity=sev)) == Tier.T2


@pytest.mark.parametrize("sev", [Severity.MEDIUM, Severity.LOW])
def test_l1_alone_experimental_t3(sev):
    assert route(sig([L1], l1_severity=sev)) == Tier.T3


def test_l1_alone_no_severity_t3():
    assert route(sig([L1])) == Tier.T3


# --- Regla 4: Capa 2 sola, score ML (SAD §6.2) ---
def test_l2_alone_high_score_t2():
    assert route(sig([L2], l2_score=0.80)) == Tier.T2


def test_l2_alone_boundary_score_is_t2():
    assert route(sig([L2], l2_score=0.74)) == Tier.T2


def test_l2_alone_low_score_t3():
    assert route(sig([L2], l2_score=0.50)) == Tier.T3


def test_l2_alone_no_score_t3():
    assert route(sig([L2])) == Tier.T3


# --- Regla 5: invariante, ninguna capa -> error ---
def test_no_layers_raises():
    with pytest.raises(ValueError, match="sin capas"):
        route(sig([]))
