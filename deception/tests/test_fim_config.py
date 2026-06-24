"""
test_fim_config.py — Valida que la configuración FIM cubra todas las
rutas declaradas en config.yaml y que la regla Wazuh de canarios
incluya severidad crítica (P3 — Angeles Castillo).
"""
import re
from pathlib import Path

import pytest
import yaml

DECEPTION_DIR = Path(__file__).parent.parent
CONFIG_PATH = DECEPTION_DIR / "canary-generator" / "config.yaml"
FIM_WINDOWS = DECEPTION_DIR / "fim-configs" / "ossec-windows.conf"
FIM_LINUX = DECEPTION_DIR / "fim-configs" / "ossec-linux.conf"
CANARY_RULES = DECEPTION_DIR / "wazuh-rules" / "canary_rules.xml"


@pytest.fixture()
def config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _host_entry(config: dict, name: str) -> dict:
    for entry in config["hosts"]:
        if entry["name"] == name:
            return entry
    raise KeyError(name)


def test_fim_windows_covers_all_windows_paths(config: dict) -> None:
    fim_content = FIM_WINDOWS.read_text(encoding="utf-8")
    host = _host_entry(config, "victim-windows-01")
    for raw_path in host["canary_paths"]:
        assert raw_path in fim_content, (
            f"ossec-windows.conf no cubre la ruta del canary: {raw_path}"
        )


def test_fim_linux_covers_all_linux_paths(config: dict) -> None:
    fim_content = FIM_LINUX.read_text(encoding="utf-8")
    host = _host_entry(config, "victim-linux-01")
    for raw_path in host["canary_paths"]:
        assert raw_path in fim_content, (
            f"ossec-linux.conf no cubre la ruta del canary: {raw_path}"
        )


def test_fim_windows_uses_whodata() -> None:
    fim_content = FIM_WINDOWS.read_text(encoding="utf-8")
    assert 'whodata="yes"' in fim_content, (
        "ossec-windows.conf debe usar whodata=\"yes\" en los bloques <directories>"
    )


def test_fim_configs_use_exact_paths_not_wildcards() -> None:
    """
    Disciplina de diseño de canaries: rutas exactas, no wildcards
    (ni '*' ni rutas de directorio genéricas sin nombre de archivo).
    """
    for fim_file in (FIM_WINDOWS, FIM_LINUX):
        content = fim_file.read_text(encoding="utf-8")
        directories_blocks = re.findall(
            r"<directories[^>]*>(.*?)</directories>", content, re.DOTALL
        )
        assert directories_blocks, f"{fim_file} no tiene bloques <directories>"
        for block in directories_blocks:
            path = block.strip()
            assert "*" not in path, f"{fim_file}: ruta con wildcard no permitida: {path}"
            # Debe apuntar a un archivo (tiene extensión), no solo a una carpeta
            assert "." in Path(path.replace("\\", "/")).name, (
                f"{fim_file}: la ruta '{path}' no parece apuntar a un archivo exacto"
            )


def test_canary_wazuh_rule_has_critical_severity() -> None:
    content = CANARY_RULES.read_text(encoding="utf-8")
    levels = [int(m) for m in re.findall(r'level="(\d+)"', content)]
    assert levels, "canary_rules.xml no define ningún nivel de severidad"
    assert max(levels) >= 12, (
        f"canary_rules.xml debe tener al menos una regla con level >= 12 (crítico), "
        f"encontrados: {levels}"
    )


def test_canary_wazuh_rule_declares_layer3_group() -> None:
    content = CANARY_RULES.read_text(encoding="utf-8")
    assert "argos_layer3" in content, (
        "canary_rules.xml debe declarar el grupo 'argos_layer3' para que "
        "el Decision Engine pueda mapear source_layer = Layer.LAYER_3"
    )


def test_canary_wazuh_rule_references_process_fields() -> None:
    """
    El manual P3 exige que la regla incluya, para downstream: ruta, usuario,
    proceso, PID, parent PID y command line. Verificamos que al menos los
    placeholders de campo ($(...)) estén presentes en las descripciones.
    """
    content = CANARY_RULES.read_text(encoding="utf-8")
    required_fields = [
        r"\$\(file\)",
        r"\$\(audit\.effective_user\.name\)",
        r"\$\(audit\.process\.id\)",
        r"\$\(audit\.process\.ppid\)",
    ]
    for pattern in required_fields:
        assert re.search(pattern, content), (
            f"canary_rules.xml no referencia el campo esperado: {pattern}"
        )
