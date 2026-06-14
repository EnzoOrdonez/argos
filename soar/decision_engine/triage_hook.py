"""Hook al LLM Triage de P2 (ADR-0013 §2.5 + review §7.5).

El orquestador arma un `AlertContext` (contrato `triage.py`) y llama
`POST /triage` del servicio de P2. La respuesta (`TriageResponse`) se guarda
en `Incident.llm_analysis`. Solo el hook vive acá: la capa `llm_triage/` es
dominio de P2 y no se toca (ADR-0008 §Decisión punto 5).

Gate (ADR-0013 §7.5): se llama cuando hay espera humana, es decir tier T2
o `requires_two_person` (production-critical, el caso UC-04 con T1+crítico
donde el LLM es "decisivo" per ADR-0009 §2.6). Nunca para DDoS
(T1498/T1499, ADR-0009 §2.6: no hay ambigüedad que contextualizar).

Invariante R-2: el LLM jamás está en el camino crítico de contención.
Cualquier fallo (timeout, 5xx, red, respuesta inválida) deja
`llm_analysis = None` y el flujo sigue. Timeout corto a propósito: el
enriquecimiento no puede demorar la espera HITL.
"""

from __future__ import annotations

import logging
import os

import httpx

from argos_contracts.alert import NormalizedAlert
from argos_contracts.enums import Layer, Tier
from argos_contracts.incident import Incident
from argos_contracts.triage import AlertContext, AlertSummary, TriageResponse
from soar.approval_api.handlers import requires_two_person
from soar.audit.logger import AuditLogger

logger = logging.getLogger(__name__)

# ADR-0009 §2.6: la Capa 4 LLM no aplica a DDoS.
DDOS_TECHNIQUES: frozenset[str] = frozenset({"T1498", "T1499"})

DEFAULT_TIMEOUT_SECONDS = 5.0


def should_call_triage(incident: Incident) -> bool:
    """Espera humana (T2 o two-person) y no-DDoS (ADR-0013 §7.5)."""
    if incident.alert.technique_mitre in DDOS_TECHNIQUES:
        return False
    return incident.tier == Tier.T2 or requires_two_person(incident)


def build_alert_context(
    incident: Incident, fired_layers: frozenset[Layer]
) -> AlertContext:
    """Arma el `AlertContext` del contrato desde el incidente correlacionado."""
    alert: NormalizedAlert = incident.alert
    title = (
        f"{alert.triggering_rule or alert.technique_mitre or 'alerta'} "
        f"en {incident.host.id}"
    )
    telemetry: dict[str, object] = {}
    if alert.process_info:
        telemetry["process_tree"] = alert.process_info
    if alert.network_info:
        telemetry["network_connections"] = alert.network_info
    if alert.file_info:
        telemetry["file_modifications"] = alert.file_info
    return AlertContext(
        incident_id=incident.incident_id,
        created_at=incident.created_at,
        host=incident.host,
        alert_summary=AlertSummary(
            title=title,
            technique_mitre=alert.technique_mitre,
            severity_score=alert.severity_score,
            triggering_layers=sorted(fired_layers, key=lambda layer: layer.value),
            raw_alert_id=alert.alert_id,
        ),
        recent_telemetry=telemetry,
    )


class TriageClient:
    """Cliente del `POST /triage` de P2, no bloqueante y fail-soft (R-2)."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
        audit: AuditLogger | None = None,
    ) -> None:
        port = os.environ.get("LLM_TRIAGE_PORT", "8002")
        self._base = (base_url or f"http://localhost:{port}").rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._audit = audit

    async def fetch(
        self, incident: Incident, fired_layers: frozenset[Layer]
    ) -> TriageResponse | None:
        """Devuelve la `TriageResponse` o None. Nunca lanza (invariante R-2)."""
        if not should_call_triage(incident):
            return None
        context = build_alert_context(incident, fired_layers)
        try:
            response = await self._client.post(
                f"{self._base}/triage",
                json=context.model_dump(mode="json"),
            )
            response.raise_for_status()
            triage = TriageResponse.model_validate(response.json())
        except Exception as exc:
            # Timeout, 5xx, red caída o respuesta inválida (incl. técnica
            # alucinada que el whitelist rechaza): todo degrada a None.
            logger.warning(
                "triage hook fallo para %s: %s", incident.incident_id, exc
            )
            if self._audit is not None:
                self._audit.emit(
                    "llm_triage_failed",
                    incident.incident_id,
                    error=f"{type(exc).__name__}: {exc}",
                )
            return None
        if self._audit is not None:
            self._audit.emit(
                "llm_triage_ok",
                incident.incident_id,
                tecnica=triage.tecnica_mitre,
                confianza=triage.confianza,
                backend=triage.llm_backend,
            )
        return triage
