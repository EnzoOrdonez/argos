"""Camino B del bridge (ADR-0014 §2.1): publica un score ML (Layer 2) en el stream.

`ml.soar_adapter.ml_score_to_normalized_alert()` ya arma el `NormalizedAlert`; acá solo
se suma el `XADD` a `events:normalized`. Importa `ml/` (corre donde `[ml]` esté instalado),
por eso vive separado del camino Wazuh liviano.
"""

from __future__ import annotations

import redis

from argos_contracts import MLScore
from ml.soar_adapter import ml_score_to_normalized_alert
from soar.decision_engine.consumer import STREAM


def publish_ml_score(
    r: redis.Redis, score: MLScore, *, technique_mitre: str | None = None
) -> str:
    """Publica un `MLScore` como `NormalizedAlert` Layer 2. Devuelve el id del entry."""
    alert = ml_score_to_normalized_alert(score, technique_mitre=technique_mitre)
    return r.xadd(STREAM, {"payload": alert.model_dump_json()})
