"""Reset del estado de demo en Redis: empezar de cero (consola vacía).

Borra TODO el estado de la demo del Redis (incidentes, contadores, índices de
correlación `corr:*`, poison-guard y el stream `events:normalized`) con un
`FLUSHDB`, para que la próxima inyección —incluida `--live`— cree un incidente
FRESCO en vez de enriquecer el anterior (ADR-0013: la correlación por host vía
`corr:open:{host}` vive 600s y, en `--live`, el incidente queda sin resolver).

El grupo del stream (`soar-router`) se recrea solo vía `XGROUP CREATE ... MKSTREAM`
en la próxima inyección (`soar/decision_engine/consumer.py`), así que el flush es seguro.

Correr (apuntá explícito al Redis del demo):
    .venv\\Scripts\\python scripts\\demo_reset.py --redis-url redis://localhost:6379/0

Equivalente sin script (compose):
    docker compose exec redis redis-cli FLUSHALL

OJO: hace FLUSHDB sobre la db indicada por --redis-url. No lo corras contra un
Redis con datos que te importen.
"""

from __future__ import annotations

import argparse
import asyncio

import redis.asyncio as redis


async def reset(redis_url: str) -> int:
    r = redis.from_url(redis_url, decode_responses=True)
    try:
        before = int(await r.dbsize())
        await r.flushdb()
        print(f"[demo_reset] FLUSHDB ok en {redis_url} ({before} claves borradas). Consola vacía.")
        print("[demo_reset] el grupo del stream se recrea solo al inyectar (MKSTREAM).")
        return 0
    finally:
        await r.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset del estado de demo en Redis (FLUSHDB).")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    args = parser.parse_args()
    return asyncio.run(reset(args.redis_url))


if __name__ == "__main__":
    raise SystemExit(main())
