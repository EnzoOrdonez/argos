# Manual P4 — Diego Jara (Infraestructura · UI · Evaluación)

| Campo | Valor |
|-------|-------|
| Rol | Owner del lab, DB defendida, observabilidad, UI de aprobación |
| Owns | `lab/` (Vagrant + scripts) · `lab/postgres/` (PostgreSQL + pgAudit) · OpenSearch + Wazuh manager · `ui/streamlit_app/` · `ui/opensearch-dashboards/` · `evaluation/` |
| No owns | Detección/ataque (P3) · ML/LLM (P2) · SOAR Engine (P1) |
| Outputs blocking otros | Lab funcional (TODOS dependen) · Redis disponible · Streamlit Approval Console (centerpiece UC-04) |
| Deadline | **2026-06-13 (sábado)** — eres el operador del demo |
| Cómo leer | Sin saltar: tu manual arranca el lab que los demás necesitan. Si la Fase 1 se demora, todo el equipo se atrasa. |

---

## 0. Tu charter

> Si tu laptop arranca el lab en menos de 5 minutos con `vagrant up`, el equipo trabaja. Si no, todos quedan bloqueados. Eres también el operador del demo: tú clickeas los botones en vivo mientras P1 narra. Tu UI es la pantalla que el profesor mirará 12 minutos seguidos.

### 0.1 Tu camino crítico

```
FASE 1 ────────→ FASE 2 ──────→ FASE 3 ──────→ FASE 4
Vagrantfile        Postgres + pgAudit  bridge Wazuh→Redis  rehearsal
VMs (Win + Lin)    OpenSearch+Dashboards Streamlit UI       hot spare
Wazuh manager      Redis              Approval Console      checklist
                                       OpenSearch dashboards demo operador
```

---

# FASE 1 — Cimientos: el lab

## 1.1 Prerequisites en tu laptop

```bash
# VirtualBox 7.x
VBoxManage --version
# OUTPUT ESPERADO: 7.0.x o superior

# Vagrant 2.4+
vagrant --version
# OUTPUT ESPERADO: Vagrant 2.4.x

# Espacio disco libre (≥ 60 GB recomendado)
df -h ~
# Necesitas ≥ 60 GB en home

# RAM mínima 16 GB (4 GB Windows VM + 4 GB Linux VM + 8 GB host)
free -h | head -2
```

| Check | Esperado |
|-------|----------|
| VirtualBox ≥ 7.0 | sí |
| Vagrant ≥ 2.4 | sí |
| Disk ≥ 60 GB free | sí |
| RAM ≥ 16 GB | sí (si solo tienes 8 GB, levanta una VM a la vez) |

## 1.2 Clonar repo

```bash
mkdir -p ~/code && cd ~/code
git clone git@github.com:enzizoor/argos.git
cd argos
python3 -m venv .venv
source .venv/bin/activate
pip install -e ./argos_contracts
pip install -r ui/requirements.txt
pip install -r lab/requirements.txt
```

## 1.3 Vagrantfile completo

Crear `lab/Vagrantfile`:

```ruby
# lab/Vagrantfile
# Lab ARGOS: 1 Windows victim, 1 Linux victim + Postgres, 1 Linux manager (Wazuh+OpenSearch+Redis).
# Red interna 192.168.56.0/24

Vagrant.configure("2") do |config|

  # === Wazuh + OpenSearch + Redis manager ===
  config.vm.define "lab-manager" do |m|
    m.vm.box = "bento/ubuntu-22.04"
    m.vm.hostname = "lab-manager"
    m.vm.network "private_network", ip: "192.168.56.10"
    m.vm.synced_folder "..", "/vagrant"
    m.vm.provider "virtualbox" do |vb|
      vb.memory = 4096
      vb.cpus   = 2
    end
    m.vm.provision "shell", path: "provision/manager.sh"
  end

  # === Linux victim (postgres + ssh) ===
  config.vm.define "linux-victim" do |l|
    l.vm.box = "bento/ubuntu-22.04"
    l.vm.hostname = "linux-victim"
    l.vm.network "private_network", ip: "192.168.56.21"
    l.vm.synced_folder "..", "/vagrant"
    l.vm.provider "virtualbox" do |vb|
      vb.memory = 3072
      vb.cpus   = 2
    end
    l.vm.provision "shell", path: "provision/linux_victim.sh"
  end

  # === Windows victim ===
  config.vm.define "windows-victim" do |w|
    w.vm.box = "gusztavvargadr/windows-10"
    w.vm.hostname = "win-victim"
    w.vm.network "private_network", ip: "192.168.56.20"
    w.vm.provider "virtualbox" do |vb|
      vb.memory = 4096
      vb.cpus   = 2
    end
    w.vm.provision "shell", path: "provision/windows_victim.ps1"
  end
end
```

### Provision scripts (esqueletos referenciados — completar)

```
lab/
├── Vagrantfile           ← arriba
├── provision/
│   ├── manager.sh        ← Wazuh manager + OpenSearch + Redis + Docker
│   ├── linux_victim.sh   ← Wazuh agent + Postgres + auditd
│   └── windows_victim.ps1 ← Sysmon (referencia P3 §2.1) + Wazuh agent
└── postgres/
    └── init.sql          ← schema audit (referencia P1 §3.2)
```

> Los provision scripts son largos (300+ líneas combinadas). Patrón estándar: instalar paquete → escribir config → restart servicio → smoke test. Si te trabas, copia patrones de [wazuh-vagrant](https://github.com/wazuh/wazuh-puppet) o de un Ansible público y adapta.

## 1.4 `vagrant up` y verificación

```bash
cd lab/
vagrant up --provider=virtualbox

# OUTPUT ESPERADO (resumen, ~10-15 min primera vez):
# ==> lab-manager: Importing base box 'bento/ubuntu-22.04'...
# ...
# ==> windows-victim: Machine booted and ready!
# ==> linux-victim: Machine booted and ready!
# ==> lab-manager: Machine booted and ready!

vagrant status
# OUTPUT ESPERADO:
# Current machine states:
# lab-manager               running (virtualbox)
# linux-victim              running (virtualbox)
# windows-victim            running (virtualbox)
```

### Smoke tests post-up

```bash
# Wazuh API responde
curl -sk -u wazuh:wazuh https://192.168.56.10:55000/?pretty | jq .data.title
# OUTPUT ESPERADO:
# "Wazuh API REST"

# OpenSearch responde
curl -sk -u admin:admin https://192.168.56.10:9200/_cluster/health | jq .status
# OUTPUT ESPERADO:
# "green"   (o "yellow" — aceptable single node)

# Redis responde
redis-cli -h 192.168.56.10 ping
# OUTPUT ESPERADO:
# PONG

# Postgres responde
psql postgresql://argos:argos@192.168.56.21:5432/argos_audit -c "SELECT 1;"
# OUTPUT ESPERADO:
#  ?column?
# ----------
#         1
# (1 row)
```

| Check Fase 1 | Esperado |
|-------------|----------|
| 3 VMs en `running` | sí |
| 4 smoke tests pasan | sí |
| Tiempo total `vagrant up` ≤ 20 min | sí |
| Tiempo de `vagrant up` desde halted (no destroy) ≤ 5 min | sí |

---

# FASE 2 — PostgreSQL defendido + observabilidad

## 2.1 PostgreSQL 15 + pgAudit

### En `lab/postgres/init.sql` (completo)

```sql
-- lab/postgres/init.sql
-- Schema y configuración de la DB defendida + audit DB.

-- DB de aplicación (target del ataque)
CREATE DATABASE app_prod;

-- DB de auditoría (consumida por P1 audit sink)
CREATE DATABASE argos_audit;

\c argos_audit

CREATE TABLE IF NOT EXISTS audit_incidents (
    incident_id   text PRIMARY KEY,
    tier          text NOT NULL,
    severity      text NOT NULL,
    host          text NOT NULL,
    technique     text NOT NULL,
    created_at    timestamptz NOT NULL,
    final_outcome text,
    final_policy  text,
    final_at      timestamptz,
    payload       jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_responses (
    id            bigserial PRIMARY KEY,
    incident_id   text REFERENCES audit_incidents(incident_id) ON DELETE CASCADE,
    approver_id   text NOT NULL,
    channel       text NOT NULL,
    decision      text NOT NULL,
    received_at   timestamptz NOT NULL
);

CREATE INDEX idx_audit_incidents_created ON audit_incidents(created_at DESC);
CREATE INDEX idx_audit_responses_incident ON audit_responses(incident_id);

-- Usuarios
CREATE USER argos WITH PASSWORD 'argos';
GRANT ALL PRIVILEGES ON DATABASE argos_audit TO argos;
GRANT ALL ON ALL TABLES IN SCHEMA public TO argos;

CREATE USER analyst WITH PASSWORD 'analyst_pwd';
GRANT CONNECT ON DATABASE app_prod TO analyst;
```

### Habilitar pgAudit (en `postgresql.conf`)

```bash
# En linux-victim, después de instalar postgresql-15-pgaudit:
sudo tee -a /etc/postgresql/15/main/postgresql.conf << 'EOF'
shared_preload_libraries = 'pgaudit'
pgaudit.log = 'read, write, ddl, role'
pgaudit.log_relation = on
pgaudit.log_parameter = on
pgaudit.log_catalog = off
listen_addresses = '*'
EOF

sudo tee -a /etc/postgresql/15/main/pg_hba.conf << 'EOF'
host    all    all    192.168.56.0/24    md5
EOF

sudo systemctl restart postgresql
sudo -u postgres psql -c "CREATE EXTENSION pgaudit;" -d app_prod
sudo -u postgres psql -c "CREATE EXTENSION pgaudit;" -d argos_audit
```

### Verificar pgAudit

```bash
sudo -u postgres psql -d app_prod -c "SELECT * FROM pg_extension WHERE extname='pgaudit';"
# OUTPUT ESPERADO:
#  oid  | extname | extowner | extnamespace | extrelocatable | extversion | ...
# ------+---------+----------+--------------+----------------+------------+...
#  ...  | pgaudit |       10 |         2200 | t              | 1.7        | ...

# Probar audit log
sudo -u postgres psql -d app_prod -c "SELECT 1;"
sudo tail -5 /var/log/postgresql/postgresql-15-main.log
# OUTPUT ESPERADO (línea final):
# LOG:  AUDIT: SESSION,READ,SELECT,SELECT 1;
```

| Check (2.1) | Esperado |
|-------------|----------|
| 2 DBs creadas (app_prod, argos_audit) | sí |
| pgAudit extension instalada en ambas | sí |
| SELECT genera entrada `AUDIT:` en postgresql log | sí |

---

## 2.2 OpenSearch + OpenSearch Dashboards

### En `provision/manager.sh` (extracto clave)

```bash
# OpenSearch 2.x via Docker
sudo apt-get install -y docker.io docker-compose-plugin
sudo mkdir -p /opt/opensearch && cd /opt/opensearch
sudo tee docker-compose.yml << 'EOF'
services:
  opensearch:
    image: opensearchproject/opensearch:2.11.0
    container_name: opensearch
    environment:
      - cluster.name=argos-cluster
      - node.name=opensearch-node1
      - discovery.type=single-node
      - bootstrap.memory_lock=true
      - "OPENSEARCH_JAVA_OPTS=-Xms1g -Xmx1g"
    ulimits:
      memlock: { soft: -1, hard: -1 }
    volumes:
      - opensearch-data:/usr/share/opensearch/data
    ports: ["9200:9200", "9600:9600"]
  dashboards:
    image: opensearchproject/opensearch-dashboards:2.11.0
    container_name: opensearch-dashboards
    environment:
      - 'OPENSEARCH_HOSTS=["https://opensearch:9200"]'
    ports: ["5601:5601"]
volumes:
  opensearch-data:
EOF

sudo docker compose up -d
sleep 30   # OpenSearch tarda ~20-30s en estar listo
curl -sk https://localhost:9200/_cluster/health | jq .status
# OUTPUT ESPERADO: "green" o "yellow"
```

### Importar dashboards desde `ui/opensearch-dashboards/*.ndjson`

```bash
for f in ui/opensearch-dashboards/*.ndjson; do
  echo "Importing $f"
  curl -X POST "http://localhost:5601/api/saved_objects/_import?overwrite=true" \
    -H "osd-xsrf: true" \
    --form file=@"$f"
done
# OUTPUT ESPERADO (por archivo):
# {"successCount":N,"success":true,...}
```

| Check (2.2) | Esperado |
|-------------|----------|
| OpenSearch responde en 9200 (health green/yellow) | sí |
| Dashboards UI abre en `http://192.168.56.10:5601` | sí |
| 3 dashboards importados (Alerts Timeline, MITRE Heatmap, Layer Performance) | sí |

---

## 2.3 Redis

```bash
# En manager.sh:
sudo apt-get install -y redis-server
sudo sed -i 's/^bind 127.0.0.1.*/bind 0.0.0.0/' /etc/redis/redis.conf
sudo sed -i 's/^protected-mode yes/protected-mode no/' /etc/redis/redis.conf
sudo systemctl restart redis-server

# Smoke
redis-cli -h 192.168.56.10 ping
# OUTPUT ESPERADO: PONG
```

| Check (2.3) | Esperado |
|-------------|----------|
| Redis 7 corriendo y accesible desde host | sí |
| Persistencia (RDB) habilitada | `redis-cli config get save` no vacío |

---

## ✅ Checklist Fase 2

| # | Check | OK |
|---|-------|----|
| 1 | Postgres con pgAudit funcional | ☐ |
| 2 | Audit log genera entradas para SELECT | ☐ |
| 3 | OpenSearch health verde/amarillo | ☐ |
| 4 | Dashboards importados | ☐ |
| 5 | Redis pingable desde host | ☐ |

---

# FASE 3 — Bridge Wazuh→Redis + Streamlit UI

## 3.1 Bridge Wazuh alerts → Redis stream

### Código (`lab/bridge/wazuh_to_redis.py`)

```python
# lab/bridge/wazuh_to_redis.py
"""
Tail alerts.json del Wazuh manager y push a Redis stream events:raw_wazuh.
Corre como service systemd en lab-manager.
"""

from __future__ import annotations

import json, time, os
from pathlib import Path
import redis

ALERTS_FILE = Path("/var/ossec/logs/alerts/alerts.json")
STREAM      = "events:raw_wazuh"


def tail_f(path: Path):
    with path.open() as f:
        f.seek(0, 2)   # ir al final
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5); continue
            yield line


def main():
    r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    for line in tail_f(ALERTS_FILE):
        try:
            alert = json.loads(line)
            # Filtrar bajo nivel (sólo level ≥ 5)
            if alert.get("rule", {}).get("level", 0) < 5:
                continue
            # Adaptar al schema esperado por P2
            payload = {
                "host":                alert.get("agent", {}).get("name", "unknown"),
                "mitre_technique":     (alert.get("rule", {}).get("mitre", {}).get("technique") or ["Unknown"])[0],
                "syscalls_per_min":    alert.get("data", {}).get("syscalls_per_min", 0),
                "files_touched_per_min": alert.get("data", {}).get("files_touched_per_min", 0),
                "entropy_of_written_bytes": alert.get("data", {}).get("entropy", 0.0),
                "network_kbps":        alert.get("data", {}).get("network_kbps", 0),
                "command_line":        alert.get("data", {}).get("win", {}).get("eventdata", {}).get("commandLine", ""),
                "raw":                 alert,
            }
            r.xadd(STREAM, {"data": json.dumps(payload)})
        except Exception as e:
            print(f"[!] {e}", flush=True)


if __name__ == "__main__":
    main()
```

### Servicio systemd

```bash
sudo tee /etc/systemd/system/argos-bridge.service << 'EOF'
[Unit]
Description=ARGOS Wazuh→Redis bridge
After=wazuh-manager.service

[Service]
ExecStart=/usr/bin/python3 /vagrant/lab/bridge/wazuh_to_redis.py
Restart=always
Environment=REDIS_URL=redis://localhost:6379/0

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now argos-bridge

systemctl status argos-bridge --no-pager
# OUTPUT ESPERADO:
# ● argos-bridge.service - ARGOS Wazuh→Redis bridge
#      Active: active (running)
```

| Check (3.1) | Esperado |
|-------------|----------|
| Service activo | sí |
| Cuando P3 dispara un canary, `XLEN events:raw_wazuh` crece | sí |
| Latencia alert→stream ≤ 2s | sí |

---

## 3.2 Streamlit Approval Console (CENTERPIECE)

### Código (`ui/streamlit_app/app.py`)

```python
# ui/streamlit_app/app.py
"""
Streamlit Analyst UI — 3 tabs.

Tab 2 (Approval Console) es el centerpiece visual del demo UC-04.
"""

import os, time, json
from datetime import datetime, timezone

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import redis

st.set_page_config(page_title="ARGOS Analyst", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=1500, key="poll")

r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
                   decode_responses=True)


def load_active_incidents() -> list[dict]:
    keys = sorted(r.scan_iter(match="incident:inc-*"), reverse=True)[:20]
    return [json.loads(r.get(k)) for k in keys if r.get(k)]


def tier_color(tier: str) -> str:
    return {"T0": "#E53935", "T1": "#FB8C00", "T2": "#FDD835", "T3": "#1E88E5"}.get(tier, "#888")


tab1, tab2, tab3 = st.tabs(["🔍 Alert Inspection", "✅ Approval Console", "📊 Audit & Forensics"])


# ============= TAB 2 — APPROVAL CONSOLE ==================================
with tab2:
    st.title("Approval Workflow Console")
    incidents = [i for i in load_active_incidents() if i.get("tier") == "T2"
                 and i.get("final_decision") is None]

    if not incidents:
        st.info("No active T2 incidents waiting for approval.")
    else:
        inc = incidents[0]
        st.markdown(
            f"<div style='background:{tier_color(inc['tier'])};padding:1rem;"
            f"border-radius:8px;color:white;'>"
            f"<h2>Incident {inc['incident_id']} — Tier {inc['tier']}</h2>"
            f"<p>Host: <b>{inc['host']['hostname']}</b> · "
            f"Technique: <b>{inc['mitre_technique']}</b> · "
            f"Layers firing: <b>{inc['num_layers_fired']}</b></p></div>",
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
                st.write(f"{emoji} **{ap['approver_id']}** — "
                         f"{ap['status']} via {ap['channel']} "
                         f"({latency:.1f}s)" if latency else "(pending)")

        with c2:
            st.subheader("Consolidation Window")
            cw = inc.get("consolidation_window") or {}
            if cw.get("opens_at") and cw.get("closes_at"):
                remaining = max(0, cw["closes_at"] - time.time())
                st.metric("Time remaining", f"{remaining:.0f}s")
                st.progress(min(1.0, 1 - remaining / 60))

            approved = sum(1 for a in inc["approvers"] if a["status"] == "APPROVED")
            rejected = sum(1 for a in inc["approvers"] if a["status"] == "REJECTED")
            if approved >= 1 and rejected >= 1:
                st.warning("⚠️ CONFLICT — conservative-wins will apply.")

# Tab 1 y 3 — read-only, ver código completo en repo
```

### `requirements.txt`

```
streamlit==1.30.0
streamlit-autorefresh==1.0.1
redis==5.0.1
plotly==5.18.0
pydantic==2.6.0
```

### Correr

```bash
cd ui/
pip install -r requirements.txt
streamlit run streamlit_app/app.py --server.address 0.0.0.0 --server.port 8501
# OUTPUT ESPERADO:
# You can now view your Streamlit app in your browser.
#   Local URL: http://localhost:8501
#   Network URL: http://192.168.x.x:8501
```

| Check (3.2) | Esperado |
|-------------|----------|
| Streamlit abre en 8501 | sí |
| Si Redis vacío: muestra "No active T2 incidents" | sí |
| Si P1 emite incident T2: aparece en ≤ 2s | sí |
| Decision Matrix actualiza al recibir respuesta | sí |

---

## 3.3 OpenSearch Dashboards exportados a NDJSON

Después de crear los dashboards manualmente en OpenSearch Dashboards UI:

```bash
# Export
curl -X POST "http://localhost:5601/api/saved_objects/_export" \
  -H "osd-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{"type": "dashboard", "includeReferencesDeep": true}' \
  > ui/opensearch-dashboards/alerts-timeline.ndjson
# Repetir para mitre-heatmap y layer-performance
```

| Check (3.3) | Esperado |
|-------------|----------|
| 3 `.ndjson` versionados en `ui/opensearch-dashboards/` | sí |
| Importar desde NDJSON en otra instancia limpia funciona | sí |

---

## ✅ Checklist Fase 3

| # | Check | OK |
|---|-------|----|
| 1 | Bridge alerts→Redis activo | ☐ |
| 2 | Streamlit Approval Console renderiza con incident demo | ☐ |
| 3 | OpenSearch dashboards exportados a ndjson | ☐ |

---

# FASE 4 — Rehearsal + operador del demo

## 4.1 Rehearsal del rol de operador

Tu rol durante el demo (~12 min):

| Tiempo | Acción | Comando | Pantalla |
|--------|--------|---------|----------|
| 0:00 | Anunciar UC-01 | (P1 narra) | Streamlit Tab 2 |
| 0:05 | Ejecutar | `vagrant ssh linux-victim -c 'python /vagrant/attack-simulation/ransomware_simulator/lockbit_like.py --variant uc01 --target linux-victim'` | Console muestra T0 incident |
| 2:00 | UC-02 | `vagrant ssh linux-victim -c '... --variant uc02 ...'` | Layer 3 fires alone |
| 3:30 | UC-04 | `vagrant ssh linux-victim -c '... postgres_attack.py ...'` | Two-person rule |
| 8:00 | UC-06 (opcional, si tiempo) | `sudo timeout 5 hping3 -S --flood -p 80 192.168.56.21` | Network panel |
| 10:00 | Q&A | mostrar Dashboard MITRE | OpenSearch Dashboards |

### Tips del operador

- Tener 4 ventanas terminal preparadas con los comandos pre-escritos (no tipear en vivo).
- Pantalla del proyector = solo Streamlit Tab 2. No mostrar terminales.
- Si algo falla, **no entres en pánico** — corre `make demo-reset` y reanuda en el último UC.

## 4.2 `Makefile` ayudante

```makefile
# Makefile (raíz del repo)
.PHONY: demo-up demo-down demo-reset soar-restart bridge-restart

demo-up:
	cd lab && vagrant up
	@echo "Lab up. Waiting 10s for services..."
	@sleep 10

demo-down:
	cd lab && vagrant halt

demo-reset:
	redis-cli -h 192.168.56.10 --scan --pattern 'incident:*' | xargs -r redis-cli -h 192.168.56.10 DEL
	vagrant ssh lab-manager -c "sudo systemctl restart argos-bridge"
	@echo "Demo state reset."

soar-restart:
	pkill -f 'soar.decision_engine.consumer' || true
	pkill -f 'uvicorn soar.approval_api' || true
	sleep 1
	nohup python -m soar.decision_engine.consumer > /tmp/soar-consumer.log 2>&1 &
	nohup uvicorn soar.approval_api.main:app --port 8001 > /tmp/soar-api.log 2>&1 &

bridge-restart:
	vagrant ssh lab-manager -c "sudo systemctl restart argos-bridge"
```

```bash
make demo-up
# OUTPUT ESPERADO: vagrant up logs + "Lab up. Waiting 10s for services..."

make demo-reset
# OUTPUT ESPERADO: "Demo state reset."
```

## 4.3 Hot spare en laptop de P1

P1 tiene un clon del lab. Tu trabajo es asegurar que:

```bash
# P1 puede hacer:
cd ~/code/argos/lab
vagrant up
# Y arranca un lab idéntico.
```

Coordinen una prueba conjunta: tú apagas tu lab, P1 prende el suyo, todos los servicios SOAR/ML cambian env `WAZUH_HOST=p1-espejo` y corren un mini UC-01. Documenta el tiempo de switchover (objetivo ≤ 5 min).

| Check (4.3) | Esperado |
|-------------|----------|
| Switchover P4→P1 sin reconfigurar nada manual | ≤ 5 min |
| Lab espejo de P1 corre los 5 UCs principales | sí |

## 4.4 Video respaldo

```bash
# Grabar pantalla completa de tu rehearsal final (OBS o vokoscreenNG)
# Output: docs/team/argos-demo-rehearsal.mp4 (NO commitear si > 100 MB)
# Subir a Drive/Cloud y compartir link en standup.
```

## 4.5 Checklist pre-demo (T-2h)

| # | Check | OK |
|---|-------|----|
| 1 | `vagrant status` → 3 running | ☐ |
| 2 | Wazuh API health 200 | ☐ |
| 3 | OpenSearch health green/yellow | ☐ |
| 4 | Streamlit Approval Console abre y muestra "No active" (estado limpio) | ☐ |
| 5 | Bridge service activo | ☐ |
| 6 | Postgres conectable | ☐ |
| 7 | Hot spare P1 también `running` | ☐ |
| 8 | Video respaldo accesible offline | ☐ |
| 9 | Cargador laptop + cable HDMI/USB-C al proyector | ☐ |
| 10 | 4 terminales preparadas con comandos UC-01..04 | ☐ |

---

# Apéndice A — Troubleshooting

### A.1 `vagrant up` falla con "Vagrant could not detect VBoxManage"

VirtualBox no instalado o PATH roto. `which VBoxManage` debe responder.

### A.2 VM Windows no arranca (timeout WinRM)

```bash
vagrant reload windows-victim --provision
# Si persiste: vagrant destroy + vagrant up
```

### A.3 OpenSearch container OOM

Aumentar Java heap (vía `OPENSEARCH_JAVA_OPTS`) o asignar más RAM a la VM manager.

### A.4 Bridge no recibe alerts

```bash
sudo journalctl -u argos-bridge -f
# Buscar errores de parsing. Si `alerts.json` no existe, el Wazuh manager no
# arrancó bien — `sudo /var/ossec/bin/wazuh-control status`.
```

### A.5 Streamlit no refresca

`st_autorefresh` requiere que la página esté en foco. Si fallo crítico,
ALT+F5 manual; los datos están en Redis y se vuelven a cargar.

### A.6 Postgres `FATAL: password authentication failed`

```bash
# Verificar pg_hba.conf permite tu rango
sudo cat /etc/postgresql/15/main/pg_hba.conf | grep 192.168
# Reset password si es necesario:
sudo -u postgres psql -c "ALTER USER argos PASSWORD 'argos';"
```

### A.7 Wazuh agent no aparece en manager

```bash
# En el agent
sudo /var/ossec/bin/agent_control -l
# Si "Never connected", revisar /var/ossec/etc/ossec.conf <server-ip>
sudo /var/ossec/bin/wazuh-control restart
```

---

# Apéndice B — Comandos de emergencia

```bash
# Lab caído mid-demo
make demo-reset            # limpia Redis, reinicia bridge
vagrant reload lab-manager # último recurso, ~30s downtime

# Switch a lab espejo P1
export WAZUH_HOST=p1-espejo.local
export REDIS_URL=redis://p1-espejo.local:6379/0
make soar-restart

# Postgres lleno
psql -U argos -d argos_audit -c "DELETE FROM audit_incidents WHERE created_at < NOW() - INTERVAL '24 hours';"

# OpenSearch indexes lentos
curl -X POST 'http://localhost:9200/_cache/clear?pretty'

# Streamlit no responde
pkill -f streamlit
nohup streamlit run ui/streamlit_app/app.py --server.port 8501 > /tmp/streamlit.log 2>&1 &
```

---

# Apéndice C — Referencias

| Cuando estés en... | Lee |
|--------------------|-----|
| `lab/Vagrantfile` | SAD §13 (deployment), `sprint-week-1-overview.md` §1 |
| `lab/postgres/` | Manual P1 §3.2 (audit consumer) |
| `ui/streamlit_app/` | SAD §9.2, ADR-0006 (split-brain visualization) |
| `evaluation/` | EVALUATION_CRITERIA §1.3 |

---

## Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 2.0 | 2026-05-24 | Reorganización day-by-day → feature-based. Vagrantfile completo, pgAudit setup explícito, bridge code completo, Streamlit Approval Console (centerpiece), Makefile demo-helper, checklists y comandos de emergencia. | P1 |
