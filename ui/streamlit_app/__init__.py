"""ARGOS Approval Console (P4) — Streamlit, solo lectura.

Visualiza el estado del HITL leyendo el `Incident` desde Redis (`incident:{id}`)
por polling. No escribe nada ni importa `soar/`: las aprobaciones llegan por los
canales reales (Telegram/Discord/Twilio) y la consola las refleja.
"""
