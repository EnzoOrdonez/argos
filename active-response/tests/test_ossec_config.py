"""Tests de los fragmentos ossec de active-response: XML válido + los <command>
coinciden con lo que el WazuhActiveResponseExecutor invoca por nombre (anti-drift)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from soar.playbooks.wazuh import DEFAULT_REVERT_COMMANDS, DEFAULT_RUN_COMMANDS

_OSSEC = Path(__file__).resolve().parents[1] / "ossec"


def _parse(name: str) -> ET.Element:
    # Envolver en <root> tolera el comentario inicial + un único <ossec_config>.
    text = (_OSSEC / name).read_text(encoding="utf-8")
    return ET.fromstring(f"<root>{text}</root>")


def _command_names() -> set[str]:
    root = _parse("argos-ar-commands.conf")
    return {c.findtext("name") for c in root.iter("command")}


def test_commands_conf_is_valid_xml() -> None:
    assert _command_names()  # parsea y define al menos un comando


def test_command_names_match_executor() -> None:
    expected = set(DEFAULT_RUN_COMMANDS.values()) | set(DEFAULT_REVERT_COMMANDS.values())
    assert expected <= _command_names(), (
        f"faltan comandos del executor en el ossec.conf: {expected - _command_names()}"
    )


def test_each_command_has_name_and_executable() -> None:
    root = _parse("argos-ar-commands.conf")
    for command in root.iter("command"):
        assert command.findtext("name")
        assert command.findtext("executable")


def test_active_response_references_defined_commands() -> None:
    ar = _parse("argos-ar-active-response.conf")
    used = {a.findtext("command") for a in ar.iter("active-response")}
    assert used
    assert used <= _command_names()  # cada <active-response> usa un <command> definido
