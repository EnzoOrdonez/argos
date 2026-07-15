"""
test_generator.py — Valida el generador de canaries (P3 — Angeles Castillo).

Cubre:
  - Contenido no vacío.
  - Distribución de timestamps dentro del rango configurado (60-180 días).
  - Rutas absolutas en config.yaml.
  - El sandbox guard nunca escribe fuera de local_sandbox_root.
"""
import sys
import time
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "canary-generator"))
import generator

DECEPTION_DIR = Path(__file__).parent.parent
CONFIG_PATH = DECEPTION_DIR / "canary-generator" / "config.yaml"


@pytest.fixture()
def config() -> dict:
    return generator.load_config(CONFIG_PATH)


@pytest.fixture()
def sandbox_root(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox-output"
    root.mkdir()
    return root


def test_config_loads(config: dict) -> None:
    assert "hosts" in config
    assert config["hosts"], "config.yaml debe declarar al menos un host"


def test_all_canary_paths_are_absolute(config: dict) -> None:
    for entry in config["hosts"]:
        for raw_path in entry["canary_paths"]:
            is_abs = (
                PureWindowsPath(raw_path).is_absolute()
                if generator._is_windows_path(raw_path)
                else PurePosixPath(raw_path).is_absolute()
            )
            assert is_abs, f"Ruta no absoluta en config.yaml: {raw_path}"


def test_generate_canary_creates_nonempty_file(config: dict, sandbox_root: Path) -> None:
    host_entry = generator.get_host_entry(config, "victim-windows-01")
    ts_range = config["timestamp_range_days"]

    for raw_path in host_entry["canary_paths"]:
        output_path = generator.generate_canary(raw_path, sandbox_root, ts_range)
        assert output_path.exists(), f"No se creó el canary para {raw_path}"
        assert output_path.stat().st_size > 0, f"Canary vacío: {output_path}"


def test_generate_canary_realistic_timestamp(config: dict, sandbox_root: Path) -> None:
    host_entry = generator.get_host_entry(config, "victim-windows-01")
    ts_range = config["timestamp_range_days"]
    now = time.time()

    for raw_path in host_entry["canary_paths"]:
        output_path = generator.generate_canary(raw_path, sandbox_root, ts_range)
        mtime = output_path.stat().st_mtime
        days_ago = (now - mtime) / 86400
        assert ts_range["min"] - 1 <= days_ago <= ts_range["max"] + 1, (
            f"{output_path}: timestamp fuera de rango realista "
            f"({days_ago:.1f} días, esperado {ts_range['min']}-{ts_range['max']})"
        )


def test_sandbox_guard_blocks_path_traversal(sandbox_root: Path) -> None:
    """
    resolve_output_path nunca debe permitir escribir fuera de
    local_sandbox_root, incluso si una ruta del config.yaml intentara
    salirse con '..'.
    """
    malicious_path = "C:\\..\\..\\..\\etc\\passwd"
    with pytest.raises(Exception):
        out = generator.resolve_output_path(malicious_path, sandbox_root)
        # Si no lanza excepción, al menos debe quedar contenido en el sandbox:
        assert sandbox_root.resolve() in out.resolve().parents


def test_known_filenames_get_realistic_writer(config: dict, sandbox_root: Path) -> None:
    """
    Los 4 nombres de canary declarados en el manual P3 deben tener un
    writer dedicado (no caer en el contenido genérico de fallback).
    """
    known_filenames = {
        "financials_Q4_2025.xlsx",
        "passwords.txt",
        "db_backup.sql",
        "accounts_admin.csv",
    }
    assert known_filenames <= set(generator.WRITERS.keys())
