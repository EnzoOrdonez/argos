"""Smoke de todos los escenarios del injector: cada uno alcanza su desenlace
esperado (`run_scenario` devuelve 0) por el pipeline real en fakeredis, sin lab.
Cubre uc01/02/03/04/05/06/07/08 — la regresión que evita que un cambio de tiers,
políticas o del injector rompa un UC en silencio."""

from __future__ import annotations

import demo_injector
import pytest


@pytest.mark.parametrize("uc", sorted(demo_injector._scenarios()))
async def test_scenario_reaches_expected_outcome(uc: str) -> None:
    code = await demo_injector.run_scenario(uc, "", in_process=True)
    assert code == 0, f"{uc} no alcanzó el desenlace esperado"
