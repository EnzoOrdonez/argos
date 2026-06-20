"""MITRE ATT&CK coverage utilities for ARGOS Layer 2."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MitreTechniqueCoverage:
    """Coverage summary for one MITRE ATT&CK technique."""

    technique_id: str
    name: str
    covered: bool
    supporting_cases: tuple[str, ...]


@dataclass(frozen=True)
class MitreCoverageReport:
    """Global MITRE coverage report."""

    covered_count: int
    total_count: int
    coverage_ratio: float
    techniques: tuple[MitreTechniqueCoverage, ...]


RANSOMWARE_MITRE_SCOPE: dict[str, str] = {
    "T1486": "Data Encrypted for Impact",
    "T1490": "Inhibit System Recovery",
    "T1083": "File and Directory Discovery",
    "T1562": "Impair Defenses",
    "T1059": "Command and Scripting Interpreter",
    "T1105": "Ingress Tool Transfer",
}


def build_mitre_coverage_report(
    detected_techniques_by_case: dict[str, set[str]],
    *,
    mitre_scope: dict[str, str] | None = None,
) -> MitreCoverageReport:
    """Build MITRE coverage from detected techniques per use case.

    Args:
        detected_techniques_by_case:
            Example:
            {
                "CU-01": {"T1486", "T1490"},
                "CU-03": {"T1486"},
            }

        mitre_scope:
            Techniques expected to be covered by the evaluation.

    Returns:
        Coverage report with ratio and supporting cases.
    """
    if mitre_scope is None:
        mitre_scope = RANSOMWARE_MITRE_SCOPE

    covered_techniques = set().union(*detected_techniques_by_case.values())

    techniques: list[MitreTechniqueCoverage] = []

    for technique_id, name in mitre_scope.items():
        supporting_cases = tuple(
            sorted(
                case_id
                for case_id, case_techniques in detected_techniques_by_case.items()
                if technique_id in case_techniques
            )
        )

        techniques.append(
            MitreTechniqueCoverage(
                technique_id=technique_id,
                name=name,
                covered=technique_id in covered_techniques,
                supporting_cases=supporting_cases,
            )
        )

    covered_count = sum(1 for technique in techniques if technique.covered)
    total_count = len(techniques)

    return MitreCoverageReport(
        covered_count=covered_count,
        total_count=total_count,
        coverage_ratio=round(covered_count / total_count, 4) if total_count else 0.0,
        techniques=tuple(techniques),
    )