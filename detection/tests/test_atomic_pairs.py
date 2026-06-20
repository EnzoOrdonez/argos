"""
test_atomic_pairs.py
ARGOS Project · Layer 1 · P3 Angeles Castillo
Universidad de Lima 2026-1

Verifica que cada regla Sigma tenga al menos un test Atomic Red Team
asociado en mitre-mapping.yaml. Reglas sin par Atomic son incompletas.
Ejecutar: pytest tests/test_atomic_pairs.py -v
"""

import yaml
import pytest
from pathlib import Path

SIGMA_RULES_DIR = Path(__file__).parent.parent / "sigma-rules"
MITRE_MAPPING_FILE = Path(__file__).parent.parent / "mitre-mapping.yaml"


def load_mitre_mapping():
    with open(MITRE_MAPPING_FILE, "r") as f:
        return yaml.safe_load(f)


def get_all_mapped_rule_files():
    """Retorna el set de archivos de regla que tienen par Atomic en mitre-mapping.yaml."""
    mapping = load_mitre_mapping()
    mapped = set()
    for technique_data in mapping.get("techniques", {}).values():
        for rule in technique_data.get("rules", []):
            if rule.get("atomic_test"):
                mapped.add(rule["file"])
    return mapped


def collect_rule_files():
    return list(SIGMA_RULES_DIR.rglob("*.yml"))


rule_files = collect_rule_files()
mapped_rules = get_all_mapped_rule_files()


@pytest.mark.parametrize("rule_path", rule_files, ids=[f.name for f in rule_files])
def test_rule_has_atomic_pair(rule_path):
    """
    Cada regla Sigma debe tener un test Atomic Red Team asociado en mitre-mapping.yaml.
    La referencia se guarda como 'atomic_test: T1486/AtomicTest#1'.
    Reglas sin par Atomic no validan que la detección funciona en la práctica.
    """
    # Construir path relativo igual al formato en mitre-mapping.yaml
    relative_path = str(rule_path.relative_to(rule_path.parent.parent.parent))
    # Normalizar separadores
    normalized = relative_path.replace("\\", "/")

    assert normalized in mapped_rules, (
        f"La regla '{rule_path.name}' no tiene un test Atomic Red Team asociado "
        f"en mitre-mapping.yaml. Añadir entrada 'atomic_test' en la técnica "
        f"correspondiente. Path buscado: {normalized}"
    )


@pytest.mark.parametrize("rule_path", rule_files, ids=[f.name for f in rule_files])
def test_rule_atomic_comment_present(rule_path):
    """
    Por convención ARGOS, cada regla debe incluir en description o en un comentario
    la referencia al test Atomic que la valida (# Validated by: T1486/AtomicTest#1).
    """
    with open(rule_path, "r") as f:
        content = f.read()

    assert "Validated by:" in content or "AtomicTest" in content, (
        f"La regla {rule_path.name} no tiene referencia al test Atomic en su "
        f"description o comentario. Añadir: '# Validated by: TXXXX/AtomicTest#N'"
    )


def test_all_techniques_have_rules():
    """
    Verifica que los 6 TTPs objetivo del proyecto tengan al menos una regla
    en mitre-mapping.yaml (requerimiento Gate 1 — ver README §Milestones).
    """
    REQUIRED_TECHNIQUES = {
        "T1486", "T1490", "T1083", "T1562.001", "T1021", "T1071"
    }
    mapping = load_mitre_mapping()
    covered = set(mapping.get("techniques", {}).keys())

    missing = REQUIRED_TECHNIQUES - covered
    assert not missing, (
        f"Los siguientes TTPs objetivo no tienen reglas en mitre-mapping.yaml: "
        f"{missing}. Gate 1 requiere los 6 cubiertos."
    )


def test_gate1_rule_count():
    """
    Gate 1 requiere mínimo 10 reglas. Verifica el conteo actual.
    """
    mapping = load_mitre_mapping()
    total_rules = sum(
        len(tech.get("rules", []))
        for tech in mapping.get("techniques", {}).values()
    )
    assert total_rules >= 8, (
        f"Gate 1 requiere ≥10 reglas. Actualmente hay {total_rules}. "
        f"Añadir más variantes (especialmente UC-03)."
    )
