"""
test_ssh_bruteforce_rule.py — Valida la regla Wazuh de fuerza bruta SSH
(detection/wazuh-rules/ssh_bruteforce_rules.xml): severidad que la rutea a Tier 2
(aprobación humana, RF-3), grupo argos_layer1 para el bridge, MITRE T1110 y
encadenamiento a una regla nativa de sshd.

Validación por contenido (regex sobre el texto), mismo patrón que
deception/tests/test_fim_config.py::test_canary_wazuh_rule_* — no usa un parser
XML de stdlib (XXE/billion-laughs) ni invoca argos_contracts/, ml/, soar/, etc.
"""
import re
from pathlib import Path

RULE_FILE = Path(__file__).parent.parent / "wazuh-rules" / "ssh_bruteforce_rules.xml"

# Reglas nativas de sshd de Wazuh (ruleset 0095) que señalan fuerza bruta /
# múltiples fallos de autenticación. La regla de ARGOS debe encadenar a una.
_NATIVE_SSHD_SIDS = {"5710", "5712", "5720", "5763"}


def _content() -> str:
    return RULE_FILE.read_text(encoding="utf-8")


def test_rule_file_exists() -> None:
    assert RULE_FILE.is_file(), f"no existe la regla SSH brute-force: {RULE_FILE}"


def test_has_at_least_one_rule() -> None:
    assert re.search(r"<rule\b", _content()), "el archivo no define ninguna <rule>"


def test_rule_level_forces_tier2() -> None:
    """level >= 12 -> severity_score 0.8 -> HIGH -> Capa 1 sola = Tier 2 (aprobación).
    Con level 10 (nativo) caería a MEDIUM -> T3 (solo notifica), no cumpliría RF-3."""
    levels = [int(m) for m in re.findall(r'<rule\b[^>]*\blevel="(\d+)"', _content())]
    assert levels, "ninguna <rule> declara level"
    assert max(levels) >= 12, f"la regla debe tener level >= 12 (T2); encontrados: {levels}"


def test_declares_argos_layer1() -> None:
    """El bridge (bridge/mapping.py::_GROUP_TO_LAYER) mapea 'argos_layer1' a Layer.LAYER_1."""
    assert "argos_layer1" in _content(), (
        "la regla debe declarar el grupo 'argos_layer1' para que el bridge "
        "asigne source_layer = Layer.LAYER_1"
    )


def test_has_mitre_t1110() -> None:
    """Las reglas nativas de sshd no traen <mitre>; la de ARGOS agrega T1110."""
    assert re.search(r"<id>\s*T1110\s*</id>", _content()), (
        "la regla debe declarar <mitre><id>T1110</id>"
    )


def test_chains_native_sshd_rule() -> None:
    """<if_sid> debe encadenar a una regla nativa de sshd (no reinventa el parsing)."""
    if_sids: set[str] = set()
    for block in re.findall(r"<if_sid>([^<]+)</if_sid>", _content()):
        if_sids.update(sid.strip() for sid in block.split(","))
    assert if_sids & _NATIVE_SSHD_SIDS, (
        f"la regla debe encadenar (if_sid) a una regla nativa de sshd "
        f"{sorted(_NATIVE_SSHD_SIDS)}; encontrados: {sorted(if_sids)}"
    )


def test_description_carries_srcip() -> None:
    """La contención downstream (HU-8) necesita la IP atacante: $(srcip) en la descripción."""
    assert "$(srcip)" in _content(), (
        "la descripción de la regla debe referenciar $(srcip) para llevar la IP "
        "atacante a la contención downstream (HU-8)"
    )
