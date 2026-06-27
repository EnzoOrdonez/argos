"""Reloj de la ventana de consolidación (60s, ADR-0006)."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from argos_contracts.incident import Incident
from streamlit_app.lib import view_model as vm


def render(incident: Incident) -> None:
    st.markdown("#### Ventana de consolidación")
    window = incident.consolidation_window
    if window is None:
        st.caption("Sin ventana de consolidación todavía (arranca con el primer voto).")
        return

    now = datetime.now(timezone.utc)
    remaining = vm.consolidation_remaining(window, now) or 0.0
    fraction = vm.consolidation_elapsed_fraction(window, now)
    label = f"{vm.format_mmss(remaining)} / {vm.format_mmss(window.duration_seconds)}"

    if window.ended_at is not None:
        st.success(f"Ventana cerrada · {label}")
    else:
        st.progress(fraction, text=f"⏱ {label}")

    if window.conflict_detected:
        st.warning("⚠ CONFLICT DETECTED — respuestas de signo opuesto en la ventana.")
