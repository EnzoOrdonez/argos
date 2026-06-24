"""
test_rule_syntax.py — Valida que cada regla Sigma en detection/sigma-rules/
sea YAML válido y contenga los campos obligatorios definidos en el manual P3.

No invoca argos_contracts/, ml/, soar/, llm_triage/ ni ui/.
"""
from pathlib import Path

import pytest
import yaml

SIGMA_RULES_DIR = Path(__file__).parent.parent / "sigma-rules"

REQUIRED_FIELDS = [
    "title",
    "id",
    "status",
    "description",
    "author",
    "date",
    "references",
    "logsource",
    "detection",
    "falsepositives",
    "level",
    "tags",
]


def _all_rule_files() -> list[Path]:
    return sorted(SIGMA_RULES_DIR.rglob("*.yml"))


@pytest.fixture(params=_all_rule_files(), ids=lambda p: p.stem)
def rule_path(request) -> Path:
    return request.param


def test_at_least_one_rule_exists() -> None:
    assert _all_rule_files(), "No se encontraron reglas Sigma en sigma-rules/"


def test_rule_is_valid_yaml(rule_path: Path) -> None:
    content = rule_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict), f"{rule_path} no es un mapeo YAML válido"


def test_rule_has_required_fields(rule_path: Path) -> None:
    parsed = yaml.safe_load(rule_path.read_text(encoding="utf-8"))
    missing = [f for f in REQUIRED_FIELDS if f not in parsed]
    assert not missing, f"{rule_path} le faltan campos obligatorios: {missing}"


def test_rule_author_is_p3(rule_path: Path) -> None:
    parsed = yaml.safe_load(rule_path.read_text(encoding="utf-8"))
    assert "Angeles Castillo" in parsed.get("author", ""), (
        f"{rule_path} debe declarar author: ARGOS / Angeles Castillo"
    )


def test_rule_id_is_uuid_format(rule_path: Path) -> None:
    import uuid

    parsed = yaml.safe_load(rule_path.read_text(encoding="utf-8"))
    rule_id = parsed.get("id", "")
    try:
        uuid.UUID(rule_id)
    except ValueError:
        pytest.fail(f"{rule_path} tiene un id que no es UUID válido: {rule_id}")


# NOTA: este test complementa (no reemplaza) `sigma-cli check detection/sigma-rules/`,
# que es la validación oficial contra el schema de Sigma. Correr ambos:
#   sigma-cli check detection/sigma-rules/
#   pytest detection/tests/test_rule_syntax.py -v
