"""Tarjeta del incidente: tier, host y alerta representativa + análisis LLM."""

from __future__ import annotations

import streamlit as st

from argos_contracts.incident import Incident
from streamlit_app.components.widgets import badge_html
from streamlit_app.lib import view_model as vm


def render(incident: Incident) -> None:
    tier = incident.tier
    state = incident.state
    st.markdown(f"### {incident.incident_id}")
    st.markdown(
        badge_html(f"Tier {tier.value}", vm.tier_color(tier))
        + " "
        + badge_html(state.value, vm.state_color(state)),
        unsafe_allow_html=True,
    )
    st.caption(
        f"creado {incident.created_at:%Y-%m-%d %H:%M:%S} · "
        f"actualizado {incident.updated_at:%H:%M:%S}"
    )

    col_host, col_alert = st.columns(2)
    with col_host:
        host = incident.host
        st.markdown("**Host**")
        st.write(f"`{host.id}` · criticidad **{host.criticality.value}**")
        if host.ip:
            st.write(f"IP: {host.ip}")
        if host.os:
            st.write(f"OS: {host.os}")
    with col_alert:
        alert = incident.alert
        sev = alert.severity_label
        st.markdown("**Alerta**")
        st.markdown(
            f"capa `{alert.source_layer.value}` · "
            + badge_html(
                f"{sev.value} ({alert.severity_score:.2f})", vm.severity_color(sev)
            ),
            unsafe_allow_html=True,
        )
        st.write(f"MITRE: {alert.technique_mitre or '—'}")
        if alert.triggering_rule:
            st.write(f"regla: {alert.triggering_rule}")
        st.caption(f"{alert.alert_id} · {alert.timestamp:%H:%M:%S}")

    triage = incident.llm_analysis
    if triage is not None:
        with st.expander("Análisis LLM (Layer 4 triage)"):
            st.write(
                f"Técnica MITRE **{triage.tecnica_mitre}** · "
                f"confianza {triage.confianza:.2f} · severidad {triage.severidad.value}"
            )
            st.write(f"Acción recomendada: {triage.accion_recomendada}")
            st.write(f"Runbook: {triage.runbook_aplicable}")
            if triage.indicadores_correlacionar:
                st.write(
                    "IOCs a correlacionar: "
                    + ", ".join(triage.indicadores_correlacionar)
                )
            st.caption(f"backend {triage.llm_backend} · {triage.generated_at:%H:%M:%S}")
