"""Sanity de las constantes de política (fuente de verdad del Tier Router).

Incluye un guard de coherencia con el contrato congelado: toda técnica auto-T0
debe existir en MITRE_WHITELIST v1.1.0.
"""

from __future__ import annotations

from argos_contracts._mitre_data import MITRE_WHITELIST
from argos_contracts.enums import Severity
from soar.decision_engine import policies


def test_auto_t0_techniques_are_in_mitre_whitelist():
    # Coherencia con argos_contracts v1.1.0 (regla #2 HANDOFF).
    assert policies.AUTO_T0_TECHNIQUES.issubset(MITRE_WHITELIST)


def test_auto_t0_covers_ransomware_and_dos():
    assert {"T1485", "T1486", "T1490"} <= policies.AUTO_T0_TECHNIQUES  # ransomware
    assert {"T1498", "T1499"} <= policies.AUTO_T0_TECHNIQUES  # denial of service


def test_t1561_excluded_as_dead_config():
    # No está en MITRE_WHITELIST v1.1.0 -> no debe estar en el set.
    assert "T1561" not in policies.AUTO_T0_TECHNIQUES


def test_high_fidelity_severities():
    assert Severity.HIGH in policies.HIGH_FIDELITY_SEVERITIES
    assert Severity.CRITICAL in policies.HIGH_FIDELITY_SEVERITIES
    assert Severity.MEDIUM not in policies.HIGH_FIDELITY_SEVERITIES
    assert Severity.LOW not in policies.HIGH_FIDELITY_SEVERITIES


def test_thresholds_match_adr0003_bands():
    assert policies.T1_CORROBORATION_MIN_CONFIDENCE == 0.80
    assert policies.L2_ALONE_T2_MIN_SCORE == 0.74
