"""Smoke test: la app arranca en frío sin excepción (requiere [ui] instalado).

Si streamlit / streamlit_autorefresh no están, se saltea (deps opcionales [ui]).
"""

from __future__ import annotations

import pathlib

import fakeredis
import pytest

pytest.importorskip("streamlit.testing.v1")
pytest.importorskip("streamlit_autorefresh")

from streamlit.testing.v1 import AppTest

_APP = str(pathlib.Path(__file__).resolve().parents[1] / "streamlit_app" / "app.py")


def test_app_renders_empty_state(monkeypatch) -> None:
    # Inyectamos un fakeredis vacío para no depender de un Redis real.
    from streamlit_app.lib import incident_loader

    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(incident_loader, "get_client", lambda url: fake)

    app = AppTest.from_file(_APP).run()

    assert not app.exception
    assert any("Esperando incidentes" in info.value for info in app.info)


def test_app_renders_incident(monkeypatch, make_incident) -> None:
    from streamlit_app.lib import incident_loader

    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    incident = make_incident()
    fake.set(f"incident:{incident.incident_id}", incident.model_dump_json())
    monkeypatch.setattr(incident_loader, "get_client", lambda url: fake)

    app = AppTest.from_file(_APP).run()

    assert not app.exception
    # El id del incidente aparece en algún markdown de la página.
    assert any(incident.incident_id in md.value for md in app.markdown)
