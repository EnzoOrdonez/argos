"""CLI del bridge Wazuh → events:normalized (Camino A).

    python -m bridge --alerts-path /var/ossec/logs/alerts/alerts.json \\
                     --redis-url redis://localhost:6379/0

Env fallbacks: ARGOS_WAZUH_ALERTS_PATH, REDIS_URL. Corre indefinidamente (Ctrl-C para parar).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from bridge.wazuh_bridge import run


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--alerts-path",
        default=os.environ.get(
            "ARGOS_WAZUH_ALERTS_PATH", "/var/ossec/logs/alerts/alerts.json"
        ),
        help="ruta del alerts.json del Wazuh manager",
    )
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    )
    args = parser.parse_args()
    print(f"bridge: tail {args.alerts_path} -> events:normalized @ {args.redis_url}")
    run(Path(args.alerts_path), args.redis_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
