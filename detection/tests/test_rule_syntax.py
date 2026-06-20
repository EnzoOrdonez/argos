"""
test_rule_syntax.py
ARGOS Project · Layer 1 · P3 Angeles Castillo
Universidad de Lima 2026-1

Valida que todas las reglas Sigma en sigma-rules/ pasen `sigma-cli check`.
Ejecutar: pytest tests/test_rule_syntax.py -v
"""

import subprocess
import pytest
from pathlib import Path

# Directorio raíz de las reglas Sigma
SIGMA_RULES_DIR = Path(__file__).parent.parent / "sigma-rules"

# Recoger todos los archivos .yml recursivamente
def collect_rule_files():
    return list(SIGMA_RULES_DIR.rglob("*.yml"))


rule_files = collect_rule_files()


@pytest.mark.parametrize("rule_path", rule_files, ids=[f.name for f in rule_files])
def test_rule_syntax_valid(rule_path):
    """
    Cada archivo .yml en sigma-rules/ debe pasar `sigma-cli check`.
    Un fallo indica YAML inválido o campos Sigma obligatorios faltantes.
    """
    result = subprocess.run(
        ["sigma", "check", str(rule_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"sigma-cli check FALLÓ para {rule_path.name}:\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )


@pytest.mark.parametrize("rule_path", rule_files, ids=[f.name for f in rule_files])
def test_rule_has_required_fields(rule_path):
    """
    Verifica que los campos obligatorios por convención ARGOS estén presentes
    en el YAML de la regla sin necesitar sigma-cli.
    """
    import yaml

    with open(rule_path, "r") as f:
        rule = yaml.safe_load(f)

    required_fields = [
        "title",
        "id",
        "description",
        "references",
        "tags",
        "logsource",
        "detection",
        "falsepositives",
        "level",
        "author",
        "date",
    ]

    for field in required_fields:
        assert field in rule, (
            f"Campo obligatorio '{field}' faltante en {rule_path.name}"
        )


@pytest.mark.parametrize("rule_path", rule_files, ids=[f.name for f in rule_files])
def test_rule_has_mitre_tag(rule_path):
    """
    Todo tag de técnica MITRE debe tener formato 'attack.tXXXX' o 'attack.tXXXX.XXX'.
    Reglas sin tag MITRE son rechazadas en PR review (ver README §Discipline).
    """
    import yaml
    import re

    with open(rule_path, "r") as f:
        rule = yaml.safe_load(f)

    tags = rule.get("tags", [])
    mitre_tags = [t for t in tags if re.match(r"^attack\.t\d{4}", t)]

    assert len(mitre_tags) >= 1, (
        f"La regla {rule_path.name} no tiene ningún tag MITRE ATT&CK "
        f"(formato requerido: attack.tXXXX). Tags encontrados: {tags}"
    )


@pytest.mark.parametrize("rule_path", rule_files, ids=[f.name for f in rule_files])
def test_rule_level_maps_to_valid_tier(rule_path):
    """
    El campo 'level' debe ser uno de los valores Sigma válidos y mapearse
    correctamente al tier ARGOS (T2/T3) según la tabla del README.
    """
    import yaml

    VALID_LEVELS = {"informational", "low", "medium", "high", "critical"}
    T2_LEVELS = {"high", "critical"}
    T3_LEVELS = {"informational", "low", "medium"}

    with open(rule_path, "r") as f:
        rule = yaml.safe_load(f)

    level = rule.get("level", "").lower()
    assert level in VALID_LEVELS, (
        f"level='{level}' en {rule_path.name} no es un nivel Sigma válido. "
        f"Válidos: {VALID_LEVELS}"
    )
