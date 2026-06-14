"""Sink primario: OpenSearch, índice `argos-audit-decisions` (ADR-0013 §2.8).

Cada evento se indexa como documento suelto (POST /{index}/_doc). El sink
captura sus propios errores HTTP y los loguea: un OpenSearch caído no puede
afectar la decisión ni la contención (fail-soft).
"""

from __future__ import annotations

import logging
import os

import httpx

from soar.audit.base import AuditEvent

logger = logging.getLogger(__name__)

INDEX = "argos-audit-decisions"


class OpenSearchSink:
    def __init__(
        self,
        url: str | None = None,
        user: str | None = None,
        password: str | None = None,
        *,
        index: str = INDEX,
        client: httpx.Client | None = None,
        timeout: float = 3.0,
    ) -> None:
        self._url = (url or os.environ["OPENSEARCH_URL"]).rstrip("/")
        self._auth = (
            user or os.environ.get("OPENSEARCH_USER", "admin"),
            password or os.environ.get("OPENSEARCH_PASSWORD", ""),
        )
        self._index = index
        verify_ssl = os.environ.get("OPENSEARCH_VERIFY_SSL", "false").lower() == "true"
        self._client = client or httpx.Client(timeout=timeout, verify=verify_ssl)

    def emit(self, event: AuditEvent) -> None:
        try:
            response = self._client.post(
                f"{self._url}/{self._index}/_doc",
                json=event.as_document(),
                auth=self._auth,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "audit sink opensearch fallo para %s/%s: %s",
                event.incident_id,
                event.kind,
                exc,
            )
