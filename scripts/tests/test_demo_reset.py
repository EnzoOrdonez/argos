"""demo_reset hace FLUSHDB: limpia todo el estado de demo (fakeredis async)."""

from __future__ import annotations

import demo_reset
from fakeredis import FakeServer
from fakeredis import aioredis as fake_aioredis


async def test_reset_flushes_demo_state(monkeypatch) -> None:
    server = FakeServer()
    seed = fake_aioredis.FakeRedis(server=server, decode_responses=True)
    await seed.set("incident:INC-2026-06-27-001", "{}")
    await seed.set("incident:counter:2026-06-27", "1")
    await seed.set("corr:open:LIN-VICTIM-01", "INC-2026-06-27-001")
    await seed.set("poison:1-0", "2")
    await seed.xadd("events:normalized", {"payload": "{}"})
    assert await seed.dbsize() >= 5

    # demo_reset crea su propio cliente vía redis.from_url -> apuntarlo al server compartido
    monkeypatch.setattr(
        demo_reset.redis,
        "from_url",
        lambda url, **kw: fake_aioredis.FakeRedis(server=server, decode_responses=True),
    )
    rc = await demo_reset.reset("redis://demo")
    assert rc == 0

    checker = fake_aioredis.FakeRedis(server=server, decode_responses=True)
    assert await checker.dbsize() == 0
