"""Pone `scripts/` en sys.path para que los tests importen los módulos de los
scripts (`demo_injector`, `live_approve`, `_runtime`) igual que cuando se corren
con `python scripts/<x>.py` (scripts/ es sys.path[0])."""

from __future__ import annotations

import pathlib
import sys

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
