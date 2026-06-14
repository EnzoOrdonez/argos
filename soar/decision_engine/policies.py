"""Constantes de política del Tier Router (SOAR Decision Engine).

Única fuente de verdad de los umbrales y conjuntos que determinan el Tier.
Cualquier cambio acá cambia el comportamiento del demo.

Autoridad:
- ADR-0003 (confidence-tiered automation) — esquema de tiers + bandas.
- SAD §6.1/§6.2 — fusion logic per layer combination.
- ADR-0008 — expansión multi-vector (técnicas DDoS T1498/T1499 → T0).
- ADR-0009 §2.6 — matriz capa-por-UC.
"""

from __future__ import annotations

from argos_contracts.enums import Severity

# Técnicas MITRE de impacto inequívoco → T0 automático, sin HITL.
# Ransomware / destrucción de datos + Denial-of-Service volumétrico/endpoint.
# Fundamento: ADR-0008 (UC-06 DDoS "Tier T0 si rate excede umbral"; expansión
# MITRE con T1498/T1499) + kill-chain de ransomware (T1485/T1486/T1490).
# NOTA: T1561 (Disk Wipe) se EXCLUYE a propósito — no está en MITRE_WHITELIST
# v1.1.0, así que sería config muerta (ver test_policies.py).
AUTO_T0_TECHNIQUES: frozenset[str] = frozenset(
    {
        "T1485",  # Data Destruction
        "T1486",  # Data Encrypted for Impact (ransomware)
        "T1490",  # Inhibit System Recovery
        "T1498",  # Network Denial of Service (DDoS)
        "T1499",  # Endpoint Denial of Service
    }
)

# Severidades que cuentan como regla Sigma "high-fidelity" cuando la Capa 1
# dispara sola. Proxy del campo canónico `level:` de Sigma, per ADR-0003:
# critical|high -> high-fidelity -> T2 ; medium|low|informational -> experimental -> T3.
HIGH_FIDELITY_SEVERITIES: frozenset[Severity] = frozenset(
    {Severity.CRITICAL, Severity.HIGH}
)

# Confianza fusionada mínima para que una corroboración Capa1+Capa2 cuente como
# "High confirmed" (T1) en vez de "Medium uncertain" (T2).
# Bandas ADR-0003 §Esquema de tiers (preliminares, calibración Q5): T1 = 0.80-0.95.
T1_CORROBORATION_MIN_CONFIDENCE: float = 0.80

# Score ML mínimo para que la Capa 2 sola escale a T2 (SAD §6.2 / soar/README).
L2_ALONE_T2_MIN_SCORE: float = 0.74
