"""Camino A del bridge (ADR-0015 §2.2): tailea el `alerts.json` del Wazuh manager,
normaliza cada alerta del proyecto y la publica en `events:normalized`.

Fail-soft: líneas malformadas o parciales se saltean; la rotación del log se maneja
reabriendo; un fallo de Redis se loguea y se sigue. Nunca tumba el pipeline.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import redis

from bridge.mapping import load_group_map, normalize
from soar.decision_engine.consumer import STREAM

logger = logging.getLogger(__name__)

StopFn = Callable[[], bool]


def iter_alert_dicts(lines: Iterator[str]) -> Iterator[dict]:
    """Parsea líneas JSON, salteando vacías y malformadas (fail-soft). Testeable."""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            yield json.loads(stripped)
        except json.JSONDecodeError:
            logger.warning("línea no-JSON en alerts.json, se descarta")


def publish_alert(r: redis.Redis, raw: dict) -> str | None:
    """Normaliza y publica una alerta. Devuelve el id del entry, o None si se descartó
    (alerta ajena al proyecto / no parseable)."""
    alert = normalize(raw)
    if alert is None:
        return None
    return r.xadd(STREAM, {"payload": alert.model_dump_json()})


def tail_lines(
    path: Path, *, poll_seconds: float = 0.5, stop: StopFn | None = None
) -> Iterator[str]:
    """Sigue un archivo estilo `tail -F`: emite líneas completas a medida que aparecen y
    maneja la rotación (truncado/reemplazo) reabriendo. `stop` permite cortar (tests)."""
    while not (stop and stop()):
        if not path.exists():
            time.sleep(poll_seconds)
            continue
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            inode = path.stat().st_ino
            buffer = ""
            while not (stop and stop()):
                chunk = handle.readline()
                if chunk:
                    buffer += chunk
                    if buffer.endswith("\n"):
                        yield buffer
                        buffer = ""
                    continue
                if _rotated(path, inode, handle.tell()):
                    break  # reabrir el archivo
                time.sleep(poll_seconds)


def _rotated(path: Path, inode: int, position: int) -> bool:
    """True si el archivo fue rotado/truncado/reemplazado (hay que reabrir)."""
    try:
        stat = path.stat()
    except OSError:
        return True
    return stat.st_ino != inode or stat.st_size < position


def run(path: Path, redis_url: str, *, stop: StopFn | None = None) -> int:
    """Loop principal del bridge. Devuelve cuántas alertas publicó (para tests/daemon)."""
    # Fail-loud al arrancar si ARGOS_BRIDGE_GROUP_MAP apunta a un archivo malformado
    # (un mapeo roto silenciaría toda la detección) — no a mitad del tail.
    load_group_map()
    client = redis.Redis.from_url(redis_url, decode_responses=True)
    published = 0
    for raw in iter_alert_dicts(tail_lines(path, stop=stop)):
        try:
            if publish_alert(client, raw) is not None:
                published += 1
        except redis.RedisError as exc:  # degradar, no tumbar el tail
            logger.warning("Redis no disponible, alerta no publicada: %s", exc)
    return published
