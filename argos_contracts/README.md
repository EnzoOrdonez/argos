# argos_contracts

Shared Pydantic v2 models that cross team boundaries in ARGOS. Contracts-first: locks the interfaces between layers so P1 (LLM/SOAR), P2 (ML), P3 (Detection), and P4 (Infra/UI) can implement their layers in parallel without integration friction. Currently **v1.1.0** (69 validation tests, TD-01 y TD-02 cerrados).

**Full specification:** [docs/architecture/CONTRACTS_SPECIFICATION.md](../docs/architecture/CONTRACTS_SPECIFICATION.md).

**Rule of inclusion:** if a class is consumed by more than one layer/owner, it lives here. If it is internal to one layer, it lives in that layer's module.

## Example import

```python
from datetime import datetime, timezone

from argos_contracts import (
    AlertContext,
    AlertSummary,
    Criticality,
    HostInfo,
    Layer,
    Severity,
    TriageResponse,
)

context = AlertContext(
    incident_id="INC-2026-04-30-001",
    created_at=datetime.now(timezone.utc),
    host=HostInfo(id="WIN-VICTIM-01", criticality=Criticality.STANDARD),
    alert_summary=AlertSummary(
        title="Suspicious vssadmin invocation",
        technique_mitre="T1490",
        severity_score=0.92,
        triggering_layers=[Layer.LAYER_1],
        raw_alert_id="wazuh-alert-12345",
    ),
)

response = TriageResponse(
    incident_id=context.incident_id,
    tecnica_mitre="T1486",
    confianza=0.92,
    severidad=Severity.CRITICAL,
    runbook_aplicable="NIST 800-61 §3.4 Containment, Eradication, Recovery",
    accion_recomendada="Isolate host, capture memory, preserve disk snapshot before remediation",
    indicadores_correlacionar=["vssadmin.exe", "high entropy writes"],
    llm_backend="openai/gpt-oss-120b",
    generated_at=datetime.now(timezone.utc),
)
```

## Run tests

```bash
pytest argos_contracts/tests/test_contracts.py -v
mypy argos_contracts/ --strict
```
