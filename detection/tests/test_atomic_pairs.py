"""
test_atomic_pairs.py — Valida que cada regla Sigma tenga al menos una
referencia a un test de Atomic Red Team (o escenario equivalente),
según la convención del manual P3:

    # Validated by: <Txxxx>/<Txxxx>.md

Esta convención se busca dentro del campo `references` o como comentario
en el archivo crudo, ya que Sigma no tiene un campo nativo para esto.
"""
import re
from pathlib import Path

import pytest
import yaml

SIGMA_RULES_DIR = Path(__file__).parent.parent / "sigma-rules"
ATOMIC_PATTERN = re.compile(r"Validated by:\s*(T\d{4}(?:\.\d{3})?)/", re.IGNORECASE)


def _all_rule_files() -> list[Path]:
    return sorted(SIGMA_RULES_DIR.rglob("*.yml"))


@pytest.fixture(params=_all_rule_files(), ids=lambda p: p.stem)
def rule_path(request) -> Path:
    return request.param


def test_rule_has_atomic_reference(rule_path: Path) -> None:
    raw_text = rule_path.read_text(encoding="utf-8")
    match = ATOMIC_PATTERN.search(raw_text)
    assert match, (
        f"{rule_path} no tiene un comentario '# Validated by: Txxxx/Txxxx.md' "
        "que la asocie a un test de Atomic Red Team o escenario equivalente."
    )


def test_atomic_technique_matches_rule_tags(rule_path: Path) -> None:
    raw_text = rule_path.read_text(encoding="utf-8")
    match = ATOMIC_PATTERN.search(raw_text)
    if not match:
        pytest.skip("Sin referencia Atomic — ya falla en test_rule_has_atomic_reference")

    atomic_technique = match.group(1).lower()
    atomic_parent = atomic_technique.split(".")[0]  # T1490.001 -> T1490
    parsed = yaml.safe_load(raw_text)
    tags = [t.replace("attack.", "") for t in parsed.get("tags", [])]

    # Una sub-técnica Atomic (p. ej. T1490.001) valida tanto el tag exacto
    # como el tag de la técnica padre (T1490), ya que Atomic suele tener
    # tests granulares por sub-técnica mientras la regla Sigma puede taggear
    # solo la técnica padre.
    assert any(tag in (atomic_technique, atomic_parent) for tag in tags), (
        f"{rule_path}: la técnica Atomic referenciada ({atomic_technique}, "
        f"padre: {atomic_parent}) no coincide con ninguno de los tags MITRE "
        f"de la regla ({tags})"
    )
