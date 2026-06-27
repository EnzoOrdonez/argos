"""Tests del Camino A: parseo fail-soft, publish a Redis, fixture, tail."""

from __future__ import annotations

import json
from pathlib import Path

from fakeredis import FakeStrictRedis

from argos_contracts import Layer, NormalizedAlert
from bridge import wazuh_bridge
from soar.decision_engine.consumer import STREAM

_FIXTURE = Path(__file__).parent / "fixtures" / "alerts.json"


def _payloads(r: FakeStrictRedis) -> list[NormalizedAlert]:
    return [
        NormalizedAlert.model_validate_json(fields["payload"])
        for _entry_id, fields in r.xrange(STREAM)
    ]


def test_iter_alert_dicts_skips_malformed() -> None:
    lines = ['{"a": 1}', "", "   ", "{ no json", '{"b": 2}']
    assert list(wazuh_bridge.iter_alert_dicts(iter(lines))) == [{"a": 1}, {"b": 2}]


def test_publish_alert_canary() -> None:
    r = FakeStrictRedis(decode_responses=True)
    raw = json.loads(_FIXTURE.read_text(encoding="utf-8").splitlines()[0])
    entry_id = wazuh_bridge.publish_alert(r, raw)
    assert entry_id is not None
    assert r.xlen(STREAM) == 1
    alert = _payloads(r)[0]
    assert alert.source_layer == Layer.LAYER_3
    assert alert.technique_mitre == "T1486"
    assert alert.severity_score == 0.95


def test_publish_alert_skips_non_argos() -> None:
    r = FakeStrictRedis(decode_responses=True)
    raw = {
        "rule": {"id": "5715", "level": 3, "groups": ["sshd"], "mitre": {"id": []}},
        "agent": {"name": "h"},
        "timestamp": "2026-06-27T12:00:00+00:00",
        "id": "z",
    }
    assert wazuh_bridge.publish_alert(r, raw) is None
    assert r.xlen(STREAM) == 0


def test_bridge_over_fixture() -> None:
    r = FakeStrictRedis(decode_responses=True)
    lines = _FIXTURE.read_text(encoding="utf-8").splitlines()
    published = sum(
        wazuh_bridge.publish_alert(r, raw) is not None
        for raw in wazuh_bridge.iter_alert_dicts(iter(lines))
    )
    # 5 líneas: canary(L3) + sigma(L1) + non-argos(skip) + malformada(skip) + canary-del(L3)
    assert published == 3
    assert r.xlen(STREAM) == 3
    assert sorted(a.source_layer.value for a in _payloads(r)) == [
        "layer_1", "layer_3", "layer_3",
    ]
    assert {a.technique_mitre for a in _payloads(r)} == {"T1486", "T1190", "T1485"}


def test_tail_lines_reads_then_closes(tmp_path: Path) -> None:
    f = tmp_path / "alerts.json"
    f.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
    gen = wazuh_bridge.tail_lines(f, poll_seconds=0)
    first, second = next(gen).strip(), next(gen).strip()
    gen.close()  # corta el generador sin loop infinito
    assert (first, second) == ('{"a":1}', '{"b":2}')
