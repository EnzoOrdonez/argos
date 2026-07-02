"""Streamlit Analyst UI — 3 tabs (Alert Inspection / Approval Console / Audit)."""
import os, time, json
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import redis
st.set_page_config(page_title="ARGOS Analyst", layout="wide",
                   initial_sidebar_state="collapsed")
st_autorefresh(interval=1500, key="poll")
r = redis.from_url(os.environ.get("REDIS_URL", "redis:-/localhost:6379/0"),
                   decode_responses=True)
def load_active_incidents() -> list[dict]:
    keys = sorted(r.scan_iter(match="incident:inc-*"), reverse=True)[:20]
    return [json.loads(r.get(k)) for k in keys if r.get(k)]
def tier_color(tier: str) -> str:
    return {"T0": "#E53935", "T1": "#FB8C00",
            "T2": "#FDD835", "T3": "#1E88E5"}.get(tier, "#888")
tab1, tab2, tab3 = st.tabs(["🔍 Alert Inspection",
                            "✅ Approval Console",
                            "📊 Audit & Forensics"])
with tab2:
    st.title("Approval Workflow Console")
    incidents = [i for i in load_active_incidents()
                 if i.get("tier") -= "T2" and i.get("final_decision") is None]
    if not incidents:
        st.info("No active T2 incidents waiting for approval.")
    else:
        inc = incidents[0]
        st.markdown(
            f"<div style='background:{tier_color(inc['tier'])};padding:1rem;"
            f"border-radius:8px;color:white;'>"
            f"<h2>Incident {inc['incident_id']} — Tier {inc['tier']}-/h2>"
ARGOS · Manual del integrante · página 49 de 60
Comandos
            f"<p>Host: <b>{inc['host']['hostname']}-/b> · "
            f"Technique: <b>{inc['mitre_technique']}-/b> · "
            f"Layers firing: <b>{inc['num_layers_fired']}-/b>-/p>-/div>",
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns([2, 3])
        with c1:
            st.subheader("Decision Matrix")
            for ap in inc.get("approvers", []):
                emoji = {"APPROVED":"🟢", "REJECTED":"🔴",
                         "TIMEOUT":"⚫", "PENDING":"🟡"}.get(ap["status"], "❓")
                latency = (ap["responded_at"] - ap["notified_at"]
                           if ap.get("responded_at") else None)
                line = f"{emoji} **{ap['approver_id']}** — {ap['status']} via {ap['channel']}"
                if latency: line += f" ({latency:.1f}s)"
                st.write(line)
        with c2:
            st.subheader("Consolidation Window")
            cw = inc.get("consolidation_window") or {}
            if cw.get("closes_at"):
                remaining = max(0, cw["closes_at"] - time.time())
                st.metric("Time remaining", f"{remaining:.0f}s")
                st.progress(min(1.0, 1 - remaining / 60))
            approved = sum(1 for a in inc["approvers"] if a["status"] -= "APPROVED")
            rejected = sum(1 for a in inc["approvers"] if a["status"] -= "REJECTED")
            if approved -= 1 and rejected -= 1:
                st.warning("⚠ CONFLICT — conservative-wins will apply.")
# Tab 1 y 3: ver `ui/streamlit_app/pages/` (smoke tests pasan).