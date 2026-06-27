"""Banner de decisión final (o pendiente) con la política aplicada verbatim.

``outcome`` y ``policy_applied`` son ``Literal[...]`` del contrato (no enums), así
que un valor inesperado falla en construcción del Incident, no acá (ui/README:81).
"""

from __future__ import annotations

import streamlit as st

from argos_contracts.incident import Incident
from streamlit_app.lib import view_model as vm


def render(incident: Incident) -> None:
    summary = vm.summary_line(incident)
    decision = incident.final_decision
    if decision is None:
        st.info(f"Decisión pendiente · {summary}")
        return

    text = (
        f"**{decision.outcome}** · política **{decision.policy_applied}**  \n"
        f"{summary}  \n"
        f"_{decision.rationale}_"
    )
    # EXECUTE_ISOLATION = contención ejecutada (rojo); NO_ACTION = verde; REVERTED = ámbar.
    render_fn = {
        "EXECUTE_ISOLATION": st.error,
        "NO_ACTION": st.success,
        "REVERTED": st.warning,
    }[decision.outcome]
    render_fn(text)

    if decision.execution_status is not None:
        when = f" · {decision.executed_at:%H:%M:%S}" if decision.executed_at else ""
        st.caption(f"Ejecución: {decision.execution_status}{when}")
