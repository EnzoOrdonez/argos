"""Tests del mapeo PURO Wazuh → NormalizedAlert (sin Redis ni I/O)."""

from __future__ import annotations

from argos_contracts import Layer, Severity
from bridge import mapping


def _canary_modified() -> dict:
    return {
        "timestamp": "2026-06-27T12:00:00.000+0000",
        "rule": {
            "id": "100101",
            "level": 12,
            "description": "Canary MODIFICADO",
            "groups": ["syscheck", "argos_canary", "argos_layer3"],
            "mitre": {"id": ["T1486"]},
        },
        "agent": {"id": "001", "name": "WIN-VICTIM-01", "ip": "10.0.0.21"},
        "id": "1719489600.111",
        "syscheck": {"path": "/canary/x.xlsx", "event": "modified"},
        "data": {
            "audit": {
                "effective_user": {"name": "attacker"},
                "process": {"id": "4321", "ppid": "1234", "name": "ps.exe"},
            }
        },
    }


def test_source_layer_from_groups() -> None:
    assert mapping.source_layer_from_groups(["syscheck", "argos_layer3"]) == Layer.LAYER_3
    assert mapping.source_layer_from_groups(["web", "argos_layer1"]) == Layer.LAYER_1
    assert mapping.source_layer_from_groups(["syslog", "sshd"]) is None
    assert mapping.source_layer_from_groups([]) is None


def test_severity_score_from_level() -> None:
    assert mapping.severity_score_from_level(15, Layer.LAYER_1) == 1.0
    assert mapping.severity_score_from_level(0, Layer.LAYER_1) == 0.0
    assert mapping.severity_score_from_level(10, Layer.LAYER_1) == 0.67
    assert mapping.severity_score_from_level(12, Layer.LAYER_1) == 0.8
    # canary L3 con level>=12 → piso 0.95 (zero-FP)
    assert mapping.severity_score_from_level(12, Layer.LAYER_3) == 0.95
    assert mapping.severity_score_from_level(13, Layer.LAYER_3) == 0.95


def test_severity_label_from_score() -> None:
    assert mapping.severity_label_from_score(0.95) == Severity.CRITICAL
    assert mapping.severity_label_from_score(0.80) == Severity.HIGH
    assert mapping.severity_label_from_score(0.67) == Severity.MEDIUM
    assert mapping.severity_label_from_score(0.30) == Severity.LOW


def test_technique_override_and_whitelist() -> None:
    assert mapping.technique_from_mitre_ids(["T1213"]) == "T1005"  # override documentado
    assert mapping.technique_from_mitre_ids(["T1486"]) == "T1486"
    # T1485 NO está en mitre-mapping.yaml pero SÍ en MITRE_WHITELIST → no se pierde.
    assert mapping.technique_from_mitre_ids(["T1485"]) == "T1485"
    assert mapping.technique_from_mitre_ids(["T9999"]) is None
    assert mapping.technique_from_mitre_ids([]) is None


def test_normalize_canary_modified() -> None:
    alert = mapping.normalize(_canary_modified())
    assert alert is not None
    assert alert.source_layer == Layer.LAYER_3
    assert alert.severity_score == 0.95
    assert alert.severity_label == Severity.CRITICAL
    assert alert.technique_mitre == "T1486"
    assert alert.host_id == "WIN-VICTIM-01"
    assert alert.host_ip == "10.0.0.21"
    assert alert.file_info == {"path": "/canary/x.xlsx", "event": "modified"}
    assert alert.process_info is not None
    assert alert.process_info["process_id"] == "4321"
    assert alert.process_info["user"] == "attacker"
    assert alert.raw_alert is not None
    assert alert.raw_alert.rule_id == 100101


def test_normalize_canary_deleted_keeps_t1485() -> None:
    raw = _canary_modified()
    raw["rule"]["id"] = "100102"
    raw["rule"]["level"] = 13
    raw["rule"]["mitre"]["id"] = ["T1485"]
    alert = mapping.normalize(raw)
    assert alert is not None
    assert alert.technique_mitre == "T1485"
    assert alert.severity_score == 0.95


def test_normalize_sigma_l1() -> None:
    raw = {
        "timestamp": "2026-06-27T12:00:05+00:00",
        "rule": {
            "id": "100200", "level": 10, "description": "SQLi",
            "groups": ["web", "argos_layer1"], "mitre": {"id": ["T1190"]},
        },
        "agent": {"id": "002", "name": "LIN-VICTIM-01"},
        "id": "x",
    }
    alert = mapping.normalize(raw)
    assert alert is not None
    assert alert.source_layer == Layer.LAYER_1
    assert alert.severity_score == 0.67
    assert alert.severity_label == Severity.MEDIUM
    assert alert.technique_mitre == "T1190"


def test_normalize_db_t1213_override() -> None:
    raw = {
        "timestamp": "2026-06-27T12:00:05+00:00",
        "rule": {
            "id": "100300", "level": 9, "description": "mass select",
            "groups": ["argos_layer1"], "mitre": {"id": ["T1213"]},
        },
        "agent": {"id": "002", "name": "LIN-VICTIM-01"},
        "id": "y",
    }
    alert = mapping.normalize(raw)
    assert alert is not None
    assert alert.technique_mitre == "T1005"


def test_normalize_non_argos_is_none() -> None:
    raw = {
        "timestamp": "2026-06-27T12:00:06+00:00",
        "rule": {"id": "5715", "level": 3, "groups": ["sshd"], "mitre": {"id": []}},
        "agent": {"id": "002", "name": "LIN-VICTIM-01"},
        "id": "z",
    }
    assert mapping.normalize(raw) is None


def test_normalize_unparseable_is_none() -> None:
    # group argos válido pero level no numérico → fail-soft None.
    raw = {"rule": {"groups": ["argos_layer1"], "level": "NaN", "mitre": {"id": []}}}
    assert mapping.normalize(raw) is None


def test_normalize_ssh_bruteforce_alert() -> None:
    """Contrato regla→bridge (Fase 1): la SALIDA de la regla Wazuh de fuerza bruta
    SSH (detection/wazuh-rules/ssh_bruteforce_rules.xml — group argos_layer1,
    mitre T1110, level 12) fluye a un NormalizedAlert L1 + T1110 + HIGH, que el
    Tier Router (Capa 1 sola, high-fidelity) rutea a Tier 2 (aprobación, RF-3)."""
    raw = {
        "timestamp": "2026-07-15T09:00:00+00:00",
        "rule": {
            "id": "100300",
            "level": 12,
            "description": "ARGOS Layer 1: fuerza bruta SSH detectada desde 203.0.113.7",
            "groups": ["syslog", "sshd", "argos_layer1", "authentication_failures"],
            "mitre": {"id": ["T1110"]},
        },
        "agent": {"id": "010", "name": "web-prod-01", "ip": "10.0.0.5"},
        "id": "ssh-bruteforce-1",
        "data": {"srcip": "203.0.113.7"},
    }
    alert = mapping.normalize(raw)
    assert alert is not None
    assert alert.source_layer == Layer.LAYER_1
    assert alert.technique_mitre == "T1110"
    assert alert.severity_score == 0.8  # level 12 / 15
    assert alert.severity_label == Severity.HIGH  # >= 0.74
    assert alert.host_id == "web-prod-01"
