"""ARGOS Approval Console (P4) — entry point Streamlit (solo lectura).

Run:
    REDIS_URL=redis://localhost:6379/0 streamlit run ui/streamlit_app/app.py

Lee ``incident:{id}`` del mismo Redis que el SOAR y refleja el HITL en vivo por
polling. No escribe nada: las aprobaciones llegan por los canales reales
(Telegram/Discord/Twilio) y acá solo se visualizan.
"""

from __future__ import annotations

import pathlib
import sys

# ``streamlit run`` deja ui/streamlit_app/ en sys.path[0]; sumamos ui/ para
# importar el paquete ``streamlit_app`` igual que lo hacen los tests.
_UI_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_UI_ROOT) not in sys.path:
    sys.path.insert(0, str(_UI_ROOT))

import streamlit as st  # noqa: E402
from streamlit_autorefresh import st_autorefresh  # noqa: E402

from argos_contracts.incident import Incident  # noqa: E402
from streamlit_app.components import (  # noqa: E402
    action_timeline,
    countdown_clock,
    decision_matrix,
    final_decision_banner,
    incident_card,
)
from streamlit_app.lib import config, incident_loader  # noqa: E402
from streamlit_app.lib import view_model as vm  # noqa: E402


def _incident_label(incident: Incident) -> str:
    flag = "🟢 abierto" if not vm.is_settled(incident) else "⚪ cerrado"
    return f"{incident.incident_id} · {incident.tier.value} · {flag}"


def main() -> None:
    st.set_page_config(
        page_title="ARGOS · Approval Console", page_icon="🛡", layout="wide"
    )
    st.title("🛡 ARGOS · Approval Console")
    st.caption(
        "HITL en vivo (solo lectura). Las aprobaciones llegan por los canales reales."
    )

    url = config.redis_url()
    interval = config.refresh_ms()
    st_autorefresh(interval=interval, key="hitl-refresh")

    with st.sidebar:
        st.header("Conexión")
        st.code(config.masked_redis_url(url), language=None)
        st.caption(f"refresco cada {interval} ms")
        if st.button("Refrescar ahora"):
            st.rerun()

    # Fail-soft: si Redis no está, degradamos con mensaje en vez de crashear.
    try:
        client = incident_loader.get_client(url)
        incidents = incident_loader.enumerate_incidents(client)
    except Exception as exc:  # degradar ante cualquier fallo de Redis, no crashear
        st.error(
            f"SOAR/Redis no disponible en {config.masked_redis_url(url)} — {exc}"
        )
        return

    if not incidents:
        st.info(
            "Esperando incidentes… arrancá el demo con "
            "`python scripts/demo_injector.py uc04 --redis-url <REDIS_URL>` "
            "apuntando al mismo Redis."
        )
        return

    with st.sidebar:
        st.header("Incidentes")
        options = [inc.incident_id for inc in incidents]
        labels = {inc.incident_id: _incident_label(inc) for inc in incidents}
        selected_id = st.radio(
            "Seleccioná un incidente",
            options,
            format_func=lambda i: labels[i],
            key="selected-incident",
        )

    incident = next(
        (inc for inc in incidents if inc.incident_id == selected_id), incidents[0]
    )

    final_decision_banner.render(incident)
    incident_card.render(incident)
    st.divider()
    left, right = st.columns([3, 2])
    with left:
        decision_matrix.render(incident)
    with right:
        countdown_clock.render(incident)
    st.divider()
    action_timeline.render(incident)


main()
