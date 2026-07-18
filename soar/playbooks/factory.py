"""Factory del ResponseExecutor, conmutado por `ARGOS_EXECUTOR` (ADR-0015 §2.1).

Vive en el paquete `soar` (no en `scripts/`) para que el daemon consumer
(`python -m soar.decision_engine`) lo use sin importar de `scripts/`. `scripts/_runtime.py`
lo re-exporta para no duplicar. Default `simulated` (demo-safe); `wazuh` usa el
active-response real y degrada a simulated con warning si falta la config de Wazuh.
"""

from __future__ import annotations

import logging
import os

from soar.playbooks.base import ResponseExecutor

logger = logging.getLogger(__name__)


def make_executor() -> ResponseExecutor:
    """SimulatedExecutor por defecto; WazuhActiveResponseExecutor con
    `ARGOS_EXECUTOR=wazuh`. Degrada a simulated si el real no se puede construir."""
    mode = os.environ.get("ARGOS_EXECUTOR", "simulated").strip().lower()
    if mode == "wazuh":
        try:
            from soar.playbooks.wazuh import WazuhActiveResponseExecutor

            return WazuhActiveResponseExecutor()
        except KeyError as exc:  # falta WAZUH_API_URL/USER/PASSWORD en el entorno
            logger.warning(
                "ARGOS_EXECUTOR=wazuh pero falta %s en el entorno; uso simulated", exc
            )
        except Exception as exc:  # cualquier fallo construyendo el real -> degradar
            logger.warning(
                "no pude crear WazuhActiveResponseExecutor (%s); uso simulated", exc
            )
    elif mode != "simulated":
        logger.warning("ARGOS_EXECUTOR=%r desconocido; uso simulated", mode)

    from soar.playbooks.simulated import SimulatedExecutor

    return SimulatedExecutor()
