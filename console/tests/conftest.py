"""Pone el repo root en sys.path para importar el paquete `console` (no está
pip-instalado). Con `python -m pytest` el cwd ya queda en path; esto cubre `pytest` pelado."""

from __future__ import annotations

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
