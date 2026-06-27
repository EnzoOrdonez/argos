"""Tests de los scripts AR: presencia por OS, el INVARIANTE whitelist (allow del
manager antes del block-all = anti auto-brick) y sintaxis bash."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_AR = Path(__file__).resolve().parents[1]
_ACTIONS = [
    "argos-isolate",
    "argos-unisolate",
    "argos-throttle",
    "argos-unthrottle",
    "argos-snapshot",
    "argos-kill",
]


def test_all_linux_scripts_present() -> None:
    for action in _ACTIONS:
        assert (_AR / "linux" / f"{action}.sh").is_file()


def test_all_windows_scripts_present() -> None:
    for action in _ACTIONS:
        assert (_AR / "windows" / f"{action}.ps1").is_file()


def test_linux_isolate_whitelists_manager_before_block() -> None:
    text = (_AR / "linux" / "argos-isolate.sh").read_text(encoding="utf-8")
    allow = text.find("1514,1515")   # regla ACCEPT del manager
    block = text.find("-j DROP")     # block-all
    assert allow != -1 and block != -1
    assert allow < block, "auto-brick: el allow del manager debe ir ANTES del DROP"


def test_windows_isolate_whitelists_manager_before_block() -> None:
    text = (_AR / "windows" / "argos-isolate.ps1").read_text(encoding="utf-8")
    allow = text.find("action=allow")
    block = text.find("blockinbound,blockoutbound")
    assert allow != -1 and block != -1
    assert allow < block, "auto-brick: el allow del manager debe ir ANTES del block-all"


def test_isolate_aborts_without_manager_ip() -> None:
    # Sin MANAGER_IP el isolate debe abortar (no aislar a ciegas), en los dos OS.
    sh = (_AR / "linux" / "argos-isolate.sh").read_text(encoding="utf-8")
    ps = (_AR / "windows" / "argos-isolate.ps1").read_text(encoding="utf-8")
    assert "auto-brick" in sh and "exit 1" in sh
    assert "auto-brick" in ps and "exit 1" in ps


def _working_bash() -> str | None:
    """Devuelve un bash FUNCIONAL, o None. En Windows `which` puede encontrar el
    shim WSL (bash.exe) que no ejecuta nada (execvpe falla); por eso se prueba."""
    bash = shutil.which("bash")
    if bash is None:
        return None
    try:
        probe = subprocess.run(
            [bash, "-c", "exit 0"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bash if probe.returncode == 0 else None


_BASH = _working_bash()


@pytest.mark.skipif(_BASH is None, reason="bash funcional no disponible (CI Linux lo corre)")
def test_linux_scripts_pass_bash_syntax() -> None:
    for action in _ACTIONS:
        script = _AR / "linux" / f"{action}.sh"
        result = subprocess.run(
            [_BASH, "-n", str(script)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"{script.name}: {result.stderr}"
