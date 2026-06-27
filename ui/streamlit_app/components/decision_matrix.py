"""Matriz de decisión: una fila por aprobador con estado, latencia y canal."""

from __future__ import annotations

import streamlit as st

from argos_contracts.incident import Incident
from streamlit_app.lib import view_model as vm


def render(incident: Incident) -> None:
    st.markdown("#### Matriz de decisión")
    counts = vm.vote_counts(incident)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aprobaron", counts.approved)
    c2.metric("Rechazaron", counts.rejected)
    c3.metric("Pendientes", counts.pending)
    c4.metric("Timeout", counts.timeout)

    rows = vm.approver_rows(incident)
    if not rows:
        st.info("Aún sin respuestas de aprobadores.")
        return
    st.dataframe(
        [
            {
                "": row.status_emoji,
                "Aprobador": row.email,
                "Rol": row.role,
                "Estado": row.status.value,
                "Latencia": row.latency_label,
                "Canal": row.channel_label,
                "Respondió": row.responded_label,
            }
            for row in rows
        ],
        hide_index=True,
        use_container_width=True,
    )
