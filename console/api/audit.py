"""Lectura opcional del timeline de auditoría desde Postgres `argos_audit`.

La consola es funcional solo con Redis. Este módulo es un extra: si el Postgres
del audit está configurado (`ARGOS_AUDIT_SQL_DSN`, el mismo DSN que usa el sink
`soar.audit.PostgresSink`), la consola muestra el log evento-por-evento del
incidente (tabla `audit_events`). Si no lo está, degrada limpio: `timeline()`
devuelve `None` y el endpoint responde `{"available": false}`.

`psycopg` se importa de forma perezosa: un `console/` instalado sin esa dependencia
sigue arrancando, solo sin timeline.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol

logger = logging.getLogger(__name__)

AUDIT_DSN_ENV = "ARGOS_AUDIT_SQL_DSN"
_SCHEMA = "argos_audit"


class AuditReader(Protocol):
    """Lee el timeline de un incidente. `None` = subsistema no disponible."""

    def timeline(self, incident_id: str) -> list[dict[str, Any]] | None: ...


class PostgresAuditReader:
    """Lee `argos_audit.audit_events`. Deshabilitado (timeline -> None) si no conecta."""

    def __init__(self, dsn: str | None = None, *, conn: Any | None = None) -> None:
        self._conn = conn
        if self._conn is None and dsn:
            try:
                import psycopg

                self._conn = psycopg.connect(dsn, autocommit=True)
            except Exception as exc:  # degradar limpio, no tumbar la consola
                logger.warning("audit reader postgres no conectó (%s); timeline deshabilitado", exc)
                self._conn = None

    def timeline(self, incident_id: str) -> list[dict[str, Any]] | None:
        if self._conn is None:
            return None
        try:
            # _SCHEMA es constante; incident_id va parametrizado (%s).
            cur = self._conn.execute(
                f"SELECT ts, kind, payload FROM {_SCHEMA}.audit_events "  # noqa: S608
                f"WHERE incident_id = %s ORDER BY ts, id",
                (incident_id,),
            )
            rows = cur.fetchall()
        except Exception as exc:  # fail-soft: sin timeline, no error duro
            logger.warning("audit reader postgres falló para %s: %s", incident_id, exc)
            return None
        return [_row_to_event(row) for row in rows]


def _row_to_event(row: Any) -> dict[str, Any]:
    ts, kind, payload = row[0], row[1], row[2]
    return {
        "ts": ts.isoformat() if hasattr(ts, "isoformat") else ts,
        "kind": kind,
        "payload": payload if isinstance(payload, dict) else {},
    }


_reader: AuditReader | None = None


def get_reader() -> AuditReader:
    """Reader efectivo (cacheado). Seam de test: monkeypatch de `get_reader`."""
    global _reader
    if _reader is None:
        _reader = PostgresAuditReader(os.environ.get(AUDIT_DSN_ENV))
    return _reader
