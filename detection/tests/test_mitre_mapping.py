"""
test_mitre_mapping.py — Valida que:
  1. Cada regla Sigma tenga al menos un tag `attack.tXXXX` válido.
  2. mitre-mapping.yaml referencie únicamente archivos de regla que existen.
  3. (Opcional) Si argos_contracts.MITRE_WHITELIST ya existe, cada técnica
     usada debe pertenecer a esa whitelist. Si el módulo no existe todavía
     (P1 aún no lo publicó), este check se salta y se marca como pendiente
     — no se debe instalar ni implementar argos_contracts/ desde aquí.
"""
import re
from pathlib import Path

import pytest
import yaml

DETECTION_DIR = Path(__file__).parent.parent
SIGMA_RULES_DIR = DETECTION_DIR / "sigma-rules"
MITRE_MAPPING_FILE = DETECTION_DIR / "mitre-mapping.yaml"

MITRE_TAG_PATTERN = re.compile(r"^attack\.t\d{4}(\.\d{3})?$", re.IGNORECASE)


def _all_rule_files() -> list[Path]:
    return sorted(SIGMA_RULES_DIR.rglob("*.yml"))


@pytest.fixture(params=_all_rule_files(), ids=lambda p: p.stem)
def rule_path(request) -> Path:
    return request.param


def test_rule_has_valid_mitre_tag(rule_path: Path) -> None:
    parsed = yaml.safe_load(rule_path.read_text(encoding="utf-8"))
    tags = parsed.get("tags", [])
    mitre_tags = [t for t in tags if MITRE_TAG_PATTERN.match(t)]
    assert mitre_tags, f"{rule_path} no tiene ningún tag MITRE válido (attack.tXXXX) en {tags}"


def test_mitre_mapping_file_is_valid_yaml() -> None:
    parsed = yaml.safe_load(MITRE_MAPPING_FILE.read_text(encoding="utf-8"))
    assert "mitre_mapping" in parsed
    assert isinstance(parsed["mitre_mapping"], list)
    assert parsed["mitre_mapping"], "mitre-mapping.yaml no debe estar vacío"


def test_mitre_mapping_references_existing_rule_files() -> None:
    parsed = yaml.safe_load(MITRE_MAPPING_FILE.read_text(encoding="utf-8"))
    repo_root = DETECTION_DIR.parent  # raíz del monorepo (asumida un nivel arriba de detection/)

    for entry in parsed["mitre_mapping"]:
        for rule_rel_path in entry.get("rules", []):
            rule_file = repo_root / rule_rel_path
            assert rule_file.exists(), (
                f"mitre-mapping.yaml referencia '{rule_rel_path}' "
                f"para {entry['technique_id']}, pero el archivo no existe"
            )


def test_mitre_whitelist_compliance_if_available() -> None:
    """
    Pendiente de confirmar con P1: argos_contracts.MITRE_WHITELIST debe
    existir y exponer una lista/set de IDs MITRE válidos. Mientras P1 no
    lo publique, este test se salta explícitamente (no se asume nada).
    """
    try:
        from argos_contracts import MITRE_WHITELIST  # type: ignore
    except ImportError:
        pytest.skip(
            "argos_contracts.MITRE_WHITELIST no disponible todavía — "
            "pendiente de confirmar con P1. No se instala ni implementa "
            "argos_contracts/ desde detection/."
        )
        return

    parsed = yaml.safe_load(MITRE_MAPPING_FILE.read_text(encoding="utf-8"))
    used_techniques = {entry["technique_id"] for entry in parsed["mitre_mapping"]}
    not_whitelisted = used_techniques - set(MITRE_WHITELIST)
    assert not not_whitelisted, (
        f"Técnicas usadas en mitre-mapping.yaml no están en MITRE_WHITELIST: {not_whitelisted}"
    )
