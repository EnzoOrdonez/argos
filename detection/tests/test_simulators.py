"""
test_simulators.py — Valida las salvaguardas de seguridad de los
simuladores controlados (P3 — Angeles Castillo).

No ejecuta ataques reales: solo prueba la lógica de validación/guardrails
y, para uc01, el ciclo completo dentro de un sandbox temporal de pytest.
"""
import subprocess
import sys
from pathlib import Path

import pytest

SIMULATORS_DIR = Path(__file__).parent.parent / "simulators"
sys.path.insert(0, str(SIMULATORS_DIR))

import uc01_lockbit_like  # noqa: E402
import uc06_ddos_controlled  # noqa: E402
import uc08_sqli_controlled  # noqa: E402

# ---------------------------------------------------------------------------
# UC-01 — sandbox guard + ciclo completo
# ---------------------------------------------------------------------------

def test_uc01_full_cycle_stays_in_sandbox(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox-uc01"
    files = uc01_lockbit_like.setup_dummy_files(sandbox)
    assert files, "Debe crear al menos un archivo dummy"
    for f in files:
        assert sandbox.resolve() in f.resolve().parents

    uc01_lockbit_like.emit_discovery_log_line(sandbox, synthetic=True)
    locked = uc01_lockbit_like.rename_to_locked(files, sandbox)
    assert all(p.suffix == ".locked" for p in locked)

    note = uc01_lockbit_like.drop_ransom_note(sandbox)
    assert note.exists()
    assert note.stat().st_size > 0

    uc01_lockbit_like.cleanup(sandbox)
    assert not sandbox.exists()


def test_uc01_guard_blocks_path_outside_sandbox(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox-uc01"
    sandbox.mkdir()
    outside_path = tmp_path / "outside.txt"
    with pytest.raises(RuntimeError):
        uc01_lockbit_like._assert_inside_sandbox(outside_path, sandbox)


# ---------------------------------------------------------------------------
# UC-06 — validación de target y rate
# ---------------------------------------------------------------------------

def test_uc06_rejects_unreplaced_placeholder() -> None:
    with pytest.raises(SystemExit):
        uc06_ddos_controlled._validate_target("<VICTIM_LAB_IP>")


def test_uc06_rejects_known_public_ip() -> None:
    with pytest.raises(SystemExit):
        uc06_ddos_controlled._validate_target("8.8.8.8")


def test_uc06_accepts_lab_hostname() -> None:
    # No debe lanzar excepción para un hostname interno del lab
    uc06_ddos_controlled._validate_target("victim-web-01")


def test_uc06_hping3_command_respects_rate(tmp_path: Path) -> None:
    cmd = uc06_ddos_controlled.build_hping3_command("victim-web-01", rate_pps=50, duration_s=10)
    assert "hping3" in cmd
    assert "victim-web-01" in cmd
    # -c (count) debe ser exactamente rate_pps * duration_s
    count_index = cmd.index("-c") + 1
    assert cmd[count_index] == str(50 * 10)


def test_uc06_cli_default_mode_does_not_execute(monkeypatch) -> None:
    """
    Sin --i-confirm-this-is-my-lab, el script nunca debe llegar a
    subprocess.run. Lo verificamos invocando el script real como
    subproceso y confirmando que no falla por falta de hping3 (porque
    nunca debería intentar ejecutarlo).
    """
    result = subprocess.run(
        [sys.executable, str(SIMULATORS_DIR / "uc06_ddos_controlled.py"),
         "--target", "victim-web-01", "--mode", "hping3", "--rate-pps", "50"],
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    assert result.returncode == 0
    assert "Modo 'solo mostrar'" in result.stdout
    assert "hping3" in result.stdout  # el comando se imprime


def test_uc06_rejects_excessive_rate() -> None:
    result = subprocess.run(
        [sys.executable, str(SIMULATORS_DIR / "uc06_ddos_controlled.py"),
         "--target", "victim-web-01", "--mode", "hping3", "--rate-pps", "500"],
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# UC-08 — validación de target URL
# ---------------------------------------------------------------------------

def test_uc08_rejects_unreplaced_placeholder() -> None:
    with pytest.raises(SystemExit):
        uc08_sqli_controlled._validate_target_url("http://<VICTIM_LAB_IP>/login.php?id=1")


def test_uc08_rejects_known_public_ip() -> None:
    with pytest.raises(SystemExit):
        uc08_sqli_controlled._validate_target_url("http://8.8.8.8/login.php?id=1")


def test_uc08_rejects_malformed_url() -> None:
    with pytest.raises(SystemExit):
        uc08_sqli_controlled._validate_target_url("not-a-url")


def test_uc08_accepts_lab_hostname() -> None:
    uc08_sqli_controlled._validate_target_url("http://victim-webapp-01/login.php?id=1")


def test_uc08_sqlmap_command_uses_conservative_defaults() -> None:
    cmd = uc08_sqli_controlled.build_sqlmap_command(
        "http://victim-webapp-01/login.php?id=1", risk=1, level=1
    )
    assert "--risk=1" in cmd
    assert "--level=1" in cmd
    assert "--batch" in cmd


def test_uc08_cli_default_mode_does_not_execute() -> None:
    result = subprocess.run(
        [sys.executable, str(SIMULATORS_DIR / "uc08_sqli_controlled.py"),
         "--target-url", "http://victim-webapp-01/login.php?id=1"],
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    assert result.returncode == 0
    assert "Modo 'solo mostrar'" in result.stdout
    assert "sqlmap" in result.stdout
