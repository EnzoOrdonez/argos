"""Acciones propuestas + estado del ciclo de vida del incidente."""

from __future__ import annotations

import streamlit as st

from argos_contracts.incident import Incident
from streamlit_app.components.widgets import badge_html
from streamlit_app.lib import view_model as vm


def render(incident: Incident) -> None:
    st.markdown("#### Acciones propuestas")
    if not incident.proposed_actions:
        st.caption("Sin acciones propuestas.")
    else:
        st.dataframe(
            [
                {
                    "ID": action.id,
                    "Tipo": action.type.value,
                    "Objetivo": action.target,
                    "Reversible": "sí" if action.reversible else "no",
                }
                for action in incident.proposed_actions
            ],
            hide_index=True,
            use_container_width=True,
        )

    state = incident.state
    st.markdown(
        "Estado actual: " + badge_html(state.value, vm.state_color(state)),
        unsafe_allow_html=True,
    )
