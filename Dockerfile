# Imagen única para los servicios ARGOS (soar, bridge, llm-triage, console, streamlit).
# Cada servicio override su `command` en docker-compose.yml. Sin el extra [ml] (sklearn):
# los servicios que corren no importan ml -> imagen liviana. El install editable de la raíz
# pone /app en sys.path, así que console/bridge/ui (paquetes top-level) quedan importables.
FROM python:3.11-slim

# curl para los healthchecks HTTP del compose.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e ".[soar,llm,ui]"

# Default (override-eado por servicio en el compose).
CMD ["uvicorn", "soar.approval_api.main:app", "--host", "0.0.0.0", "--port", "8003"]
