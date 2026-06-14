# Manual P4 — Diego Jara · Infraestructura · UI · Evaluación

| Campo | Valor |
|-------|-------|
| Rol | Owner del lab, DB defendida, observabilidad, UI de aprobación |
| Owns | `lab/` (Vagrant + scripts) · `lab/postgres/` (PostgreSQL + pgAudit) · OpenSearch + Wazuh manager · `ui/streamlit_app/` · `ui/opensearch-dashboards/` · `evaluation/` |
| No owns | Detección/ataque (P3) · ML/LLM (P2) · SOAR Engine (P1) |
| Outputs blocking | Lab funcional (TODOS dependen) · Redis disponible · Streamlit Approval Console (centerpiece UC-04) |
| Entrega final | **13 de junio de 2026** — eres el operador del demo |

---

> **Conexión con el SOAR de P1 (ADR-0013 §3 · ver `_COORDINACION_INTERMEDIA.md`):** el SOAR de P1 ya está completo y testeado. Lo que necesita de vos: Redis disponible en el lab, las tablas de audit desde `soar/audit/schema.sql` más el índice OpenSearch `argos-audit-decisions`, y la Streamlit Approval Console que lee el `Incident` de Redis (clave `incident:{id}`) y muestra el HITL en vivo.

## 0. Tu charter

> Si tu laptop arranca el lab en menos de 5 minutos con `vagrant up`, el equipo trabaja. Si no, todos quedan bloqueados. Eres también el operador del demo: clickeas los botones en vivo mientras P1 narra. Tu UI es la pantalla que el profesor mirará 12 minutos seguidos.

### 0.1 Cómo leer cada sub-sección

Cada componente sigue: **Contexto** → **Pasos manuales** si aplica → **Comandos** → **Salida esperada** → **Verificación** → **Si algo falla**.

---

# Fase 1 — Cimientos: el lab

## 1.1 Prerequisites en tu laptop

### Comandos

```bash
VBoxManage --version
vagrant --version
df -h ~ | tail -1
free -h | head -2
```

### Salida esperada

```text
7.0.x
Vagrant 2.4.x
/dev/sda1     500G  100G  400G  20% /home/usuario
              total  used  free  shared  buff/cache  available
Mem:           15Gi  6.0Gi 3.0Gi 400Mi   6.0Gi       8.0Gi
```

### Verificación

```verify
VBoxManage --version | awk -F'r' '{print $1}' | awk -F'.' '{exit !($1>=7)}' && echo "VBox 7+ OK"
test $(df -BG ~ | tail -1 | awk '{print $4}' | tr -d 'G') -ge 60 && echo "Disk OK"
```

Esperado:

```text
VBox 7+ OK
Disk OK
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `VBoxManage: command not found` | VirtualBox no instalado o PATH | Instala desde `https://www.virtualbox.org/wiki/Downloads` |
| Disco < 60 GB libre | VMs no caben | Limpia downloads o usa SSD externo (USB-C 256 GB ≈ USD 30) |
| RAM < 16 GB | Sólo puedes levantar una VM a la vez | Levanta `lab-manager` + `linux-victim`, deja Windows abajo y comparte ese rato con P3 |

---

## 1.2 Clonar repo

### Comandos

```bash
mkdir -p ~/code && cd ~/code
git clone git@github.com:EnzoOrdonez/argos.git
cd argos
python3 -m venv .venv
source .venv/bin/activate
pip install -e ./argos_contracts
pip install -r ui/requirements.txt
pip install -r lab/requirements.txt
```

### Verificación

```verify
python -c "import argos_contracts, streamlit, redis; print('imports OK')"
```

Esperado:

```text
imports OK
```

---

## 1.3 Vagrantfile

### Contexto

Tres VMs: Linux manager (Wazuh + OpenSearch + Redis), Linux víctima (Postgres + Wazuh agent + auditd), Windows víctima (Sysmon + Wazuh agent).

### `lab/Vagrantfile`

```ruby
# Lab ARGOS: 1 Windows victim, 1 Linux victim + Postgres, 1 Linux manager.
# Red interna 192.168.56.0/24

Vagrant.configure("2") do |config|

  config.vm.define "lab-manager" do |m|
    m.vm.box      = "bento/ubuntu-22.04"
    m.vm.hostname = "lab-manager"
    m.vm.network "private_network", ip: "192.168.56.10"
    m.vm.synced_folder "..", "/vagrant"
    m.vm.provider "virtualbox" do |vb|
      vb.memory = 4096
      vb.cpus   = 2
    end
    m.vm.provision "shell", path: "provision/manager.sh"
  end

  config.vm.define "linux-victim" do |l|
    l.vm.box      = "bento/ubuntu-22.04"
    l.vm.hostname = "linux-victim"
    l.vm.network "private_network", ip: "192.168.56.21"
    l.vm.synced_folder "..", "/vagrant"
    l.vm.provider "virtualbox" do |vb|
      vb.memory = 3072
      vb.cpus   = 2
    end
    l.vm.provision "shell", path: "provision/linux_victim.sh"
  end

  config.vm.define "windows-victim" do |w|
    w.vm.box      = "gusztavvargadr/windows-10"
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

### Estructura

```text
lab/
├── Vagrantfile           ← arriba
├── provision/
│   ├── manager.sh        ← Wazuh + OpenSearch + Redis + Docker
│   ├── linux_victim.sh   ← Wazuh agent + Postgres + auditd
│   └── windows_victim.ps1 ← Sysmon + Wazuh agent (vía P3)
└── postgres/
    └── init.sql          ← schema audit
```

---

## 1.4 `vagrant up` y verificación

### Pasos manuales

1. La primera vez: `vagrant up --provider=virtualbox` tarda 10-15 min (descarga boxes + provision).
2. Reinicios sucesivos (después de `vagrant halt`): ~3-5 min.
3. Si algo se rompe sin causa clara: `vagrant destroy <vm> && vagrant up <vm>`.

### Comandos

```bash
cd lab/
vagrant up --provider=virtualbox

vagrant status
```

### Salida esperada

```text
==> lab-manager: Importing base box 'bento/ubuntu-22.04'...
... (mucho output)
==> windows-victim: Machine booted and ready!
==> linux-victim: Machine booted and ready!
==> lab-manager: Machine booted and ready!

Current machine states:
lab-manager               running (virtualbox)
linux-victim              running (virtualbox)
windows-victim            running (virtualbox)
```

### Verificación — smoke tests

```verify
curl -sk -u wazuh:wazuh https://192.168.56.10:55000/?pretty | jq .data.title
curl -sk -u admin:admin https://192.168.56.10:9200/_cluster/health | jq .status
redis-cli -h 192.168.56.10 ping
psql postgresql://argos:argos@192.168.56.21:5432/argos_audit -c "SELECT 1;"
```

Esperado:

```text
"Wazuh API REST"
"green"
PONG
 ?column?
----------
        1
(1 row)
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `Vagrant could not detect VBoxManage` | VirtualBox no en PATH | Agrega `C:\Program Files\Oracle\VirtualBox` (Windows) o `/usr/local/bin` (macOS) al PATH |
| VM Windows timeout WinRM | Provision Windows tarda | `vagrant reload windows-victim --provision`; si persiste: destroy + up |
| OpenSearch cluster red | OOM o disk full | `docker logs opensearch` y verifica `OPENSEARCH_JAVA_OPTS=-Xms1g -Xmx1g` |

---

## ✅ Checklist Fase 1

| # | Check | OK |
|---|-------|----|
| 1 | VirtualBox 7+ · Vagrant 2.4+ · 60 GB disk | ☐ |
| 2 | 3 VMs `running` | ☐ |
| 3 | Wazuh API responde con `"Wazuh API REST"` | ☐ |
| 4 | OpenSearch health green/yellow | ☐ |
| 5 | Redis pingable desde host | ☐ |
| 6 | Postgres conectable desde host | ☐ |
| 7 | `vagrant up` desde halted ≤ 5 min | ☐ |

---

# Fase 2 — Postgres defendido + observabilidad

## 2.1 PostgreSQL 15 + pgAudit

### Contexto

Postgres es el activo defendido. pgAudit registra todos los SELECT/INSERT/DDL para el audit log y como input a las Sigma rules de DB (UC-07, UC-08).

### `lab/postgres/init.sql`

```sql
-- DB de aplicación (target del ataque)
CREATE DATABASE app_prod;

-- DB de auditoría (consumida por audit sink de P1)
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

CREATE INDEX idx_audit_incidents_created  ON audit_incidents(created_at DESC);
CREATE INDEX idx_audit_responses_incident ON audit_responses(incident_id);

CREATE USER argos   WITH PASSWORD 'argos';
GRANT ALL PRIVILEGES ON DATABASE argos_audit TO argos;
GRANT ALL ON ALL TABLES IN SCHEMA public TO argos;

CREATE USER analyst WITH PASSWORD 'analyst_pwd';
GRANT CONNECT ON DATABASE app_prod TO analyst;
```

### Pasos manuales — habilitar pgAudit

1. En linux-victim, instalar `postgresql-15-pgaudit`.
2. Agregar `pgaudit` a `shared_preload_libraries` en `postgresql.conf`.
3. Configurar `pgaudit.log` y `listen_addresses`.
4. Permitir conexiones desde 192.168.56.0/24 en `pg_hba.conf`.
5. Reiniciar Postgres.
6. Crear la extensión en cada DB.

### Comandos (en linux-victim, via `vagrant ssh`)

```bash
sudo apt install -y postgresql-15-pgaudit

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

sudo -u postgres psql -c "CREATE EXTENSION IF NOT EXISTS pgaudit;" -d app_prod
sudo -u postgres psql -c "CREATE EXTENSION IF NOT EXISTS pgaudit;" -d argos_audit
```

### Verificación

```verify
sudo -u postgres psql -d app_prod -c "SELECT extname, extversion FROM pg_extension WHERE extname='pgaudit';"
sudo -u postgres psql -d app_prod -c "SELECT 1;"
sudo tail -3 /var/log/postgresql/postgresql-15-main.log | grep -i pgaudit
```

Esperado:

```text
 extname | extversion
---------+------------
 pgaudit | 1.7
(1 row)

LOG: AUDIT: SESSION,READ,SELECT,SELECT 1;
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `ERROR: pgaudit must be in shared_preload_libraries` | Modificaste `postgresql.conf` pero no reiniciaste | `sudo systemctl restart postgresql` |
| `psql: FATAL: password authentication failed` desde host | `pg_hba.conf` no permite tu rango | Confirma `host all all 192.168.56.0/24 md5` y `systemctl reload postgresql` |
| `Permission denied: postgresql.log` | Permisos | `sudo chmod 644 /var/log/postgresql/postgresql-15-main.log` |

---

## 2.2 OpenSearch + OpenSearch Dashboards (Docker Compose)

### Contexto

OpenSearch indexa los alerts del Wazuh manager y aporta los 3 dashboards visuales (Alerts Timeline, MITRE Heatmap, Layer Performance).

### Pasos manuales (en `provision/manager.sh`)

1. Instalar Docker + compose plugin.
2. Crear `/opt/opensearch/docker-compose.yml`.
3. `docker compose up -d`.
4. Esperar 30 s a que cluster esté ready.

### Comandos (en lab-manager, vía `vagrant ssh`)

```bash
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
      - OPENSEARCH_JAVA_OPTS=-Xms1g -Xmx1g
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
sleep 30
```

### Verificación

```verify
curl -sk https://localhost:9200/_cluster/health | jq .status
curl -s http://localhost:5601/api/status | jq .status.overall.state 2>/dev/null || echo "dashboards starting"
```

Esperado:

```text
"green"
"green"
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `bootstrap.memory_lock=true` warning | `ulimits memlock` no aplicado | Reinicia el container: `sudo docker compose restart` |
| `cluster.status: red` | OOM | Bajar heap: `OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m` |
| Dashboards no carga (404) | Aún arrancando | Espera 30-60 s más y reintenta |

---

## 2.3 Redis

### Comandos (en lab-manager)

```bash
sudo apt-get install -y redis-server
sudo sed -i 's/^bind 127.0.0.1.*/bind 0.0.0.0/' /etc/redis/redis.conf
sudo sed -i 's/^protected-mode yes/protected-mode no/' /etc/redis/redis.conf
sudo systemctl restart redis-server
```

### Verificación

```verify
redis-cli -h 192.168.56.10 ping
redis-cli -h 192.168.56.10 config get save
```

Esperado:

```text
PONG
1) "save"
2) "3600 1 300 100 60 10000"
```

---

## ✅ Checklist Fase 2

| # | Check | OK |
|---|-------|----|
| 1 | Postgres con pgAudit funcional | ☐ |
| 2 | SELECT genera entrada `AUDIT:` en log | ☐ |
| 3 | OpenSearch health green | ☐ |
| 4 | Dashboards UI abre en `http://192.168.56.10:5601` | ☐ |
| 5 | Redis pingable desde host | ☐ |

---

# Fase 3 — Bridge Wazuh→Redis + Streamlit UI

## 3.1 Bridge `alerts.json` → `events:raw_wazuh`

### Contexto

P3 produce alertas en `/var/ossec/logs/alerts/alerts.json`. P2 las consume desde Redis Stream. Tu bridge cierra ese gap: tail-ea el archivo y empuja a Redis.

### `lab/bridge/wazuh_to_redis.py`

```python
"""Tail alerts.json del Wazuh manager y push a Redis stream events:raw_wazuh."""

from __future__ import annotations
import json, time, os
from pathlib import Path
import redis

ALERTS_FILE = Path("/var/ossec/logs/alerts/alerts.json")
STREAM      = "events:raw_wazuh"


def tail_f(path: Path):
    with path.open() as f:
        f.seek(0, 2)  # ir al final
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
            if alert.get("rule", {}).get("level", 0) < 5:
                continue
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

### Pasos manuales — systemd service

1. Copiar el unit file a `/etc/systemd/system/argos-bridge.service`.
2. `systemctl daemon-reload`.
3. `systemctl enable --now argos-bridge`.
4. Verificar `systemctl status`.

### Comandos (en lab-manager)

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
```

### Salida esperada

```text
● argos-bridge.service - ARGOS Wazuh→Redis bridge
     Loaded: loaded (/etc/systemd/system/argos-bridge.service; enabled)
     Active: active (running) since ...
```

### Verificación (coordinar con P3 para disparar canary)

```verify
redis-cli -h 192.168.56.10 XLEN events:raw_wazuh
```

Esperado:

```text
1
```

(Crece tras cada alerta de level ≥ 5.)

---

## 3.2 Streamlit Approval Console (CENTERPIECE)

### Contexto

Tab 2 de la UI es el centerpiece visual del demo UC-04. Muestra Incident card, Decision Matrix con estado por aprobador, Consolidation Window countdown, y banner final.

### `ui/streamlit_app/app.py`

```python
"""Streamlit Analyst UI — 3 tabs (Alert Inspection / Approval Console / Audit)."""

import os, time, json

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import redis

st.set_page_config(page_title="ARGOS Analyst", layout="wide",
                   initial_sidebar_state="collapsed")
st_autorefresh(interval=1500, key="poll")

r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
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
                 if i.get("tier") == "T2" and i.get("final_decision") is None]

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

            approved = sum(1 for a in inc["approvers"] if a["status"] == "APPROVED")
            rejected = sum(1 for a in inc["approvers"] if a["status"] == "REJECTED")
            if approved >= 1 and rejected >= 1:
                st.warning("⚠️ CONFLICT — conservative-wins will apply.")

# Tab 1 y 3: ver `ui/streamlit_app/pages/` (smoke tests pasan).
```

### Comandos

```bash
cd ui/
pip install -r requirements.txt
streamlit run streamlit_app/app.py --server.address 0.0.0.0 --server.port 8501
```

### Salida esperada

```text
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501
```

### Verificación

```verify
curl -s http://localhost:8501/_stcore/health
```

Esperado:

```text
ok
```

Abre `http://localhost:8501`, ve a tab Approval Console. Si Redis vacío, muestra `"No active T2 incidents waiting for approval."`

---

## 3.3 OpenSearch Dashboards exportados a NDJSON

### Pasos manuales — crear los 3 dashboards en la UI

1. Abre `http://192.168.56.10:5601` y autentícate (admin/admin).
2. Crear index pattern `wazuh-alerts-*`.
3. Crear **Alerts Timeline** (visualización tipo histograma por `@timestamp` + `rule.level`).
4. Crear **MITRE Heatmap** (heatmap `rule.mitre.technique` vs día).
5. Crear **Layer Performance** (línea con conteo por `layer_origin` por minuto).
6. Exportar los 3 a NDJSON.

### Comandos (export)

```bash
for d in "Alerts Timeline" "MITRE Heatmap" "Layer Performance"; do
  slug=$(echo "$d" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
  echo "Exporting $d..."
  curl -X POST "http://localhost:5601/api/saved_objects/_export" \
    -H "osd-xsrf: true" \
    -H "Content-Type: application/json" \
    -d "{\"type\": \"dashboard\", \"includeReferencesDeep\": true}" \
    > "ui/opensearch-dashboards/${slug}.ndjson"
done
```

### Verificación

```verify
ls ui/opensearch-dashboards/*.ndjson | wc -l
head -1 ui/opensearch-dashboards/alerts-timeline.ndjson | jq .type
```

Esperado:

```text
3
"dashboard"
```

---

## ✅ Checklist Fase 3

| # | Check | OK |
|---|-------|----|
| 1 | `argos-bridge` service active | ☐ |
| 2 | Streamlit Approval Console renderiza con incident demo | ☐ |
| 3 | 3 OpenSearch dashboards exportados a NDJSON | ☐ |

---

# Fase 4 — Rehearsal + operador del demo

## 4.1 Rehearsal del rol de operador

### Contexto

El día del demo eres el operador. P1 narra, P2 y P3 aprueban en sus celulares, tú ejecutas los comandos. Ensaya esto al menos 2 veces solo y 1 vez con el equipo.

### Comandos pre-preparados (uno por terminal, listas para Enter)

```bash
# Terminal 1 (UC-01)
vagrant ssh linux-victim -c 'python /vagrant/attack-simulation/ransomware_simulator/lockbit_like.py --variant uc01 --target linux-victim'

# Terminal 2 (UC-02)
vagrant ssh linux-victim -c 'python /vagrant/attack-simulation/ransomware_simulator/lockbit_like.py --variant uc02 --target linux-victim'

# Terminal 3 (UC-04)
vagrant ssh linux-victim -c 'python /vagrant/attack-simulation/ransomware_simulator/postgres_attack.py --target linux-victim'

# Terminal 4 (UC-06 opcional si hay tiempo)
sudo timeout 5 hping3 -S --flood -p 80 192.168.56.21
```

### Tips del operador

- Tener 4 terminales con los comandos **pre-tipeados** (no tipear en vivo).
- Pantalla del proyector = sólo Streamlit Tab 2. NO mostrar terminales.
- Si algo falla, **no entres en pánico**: `make demo-reset` y reanudar en el último UC.

---

## 4.2 `Makefile` ayudante

### `Makefile` (raíz del repo)

```makefile
.PHONY: demo-up demo-down demo-reset soar-restart bridge-restart llm-restart

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

llm-restart:
	pkill -f 'ml.consumer' || true
	sleep 1
	nohup python -m ml.consumer > /tmp/ml.log 2>&1 &
```

### Verificación

```verify
make demo-up
sleep 5
make demo-reset
```

Esperado:

```text
... vagrant logs ...
Lab up. Waiting 10s for services...
Demo state reset.
```

---

## 4.3 Hot spare en laptop de P1

### Pasos manuales

P1 tiene un clon del lab. Tu trabajo es asegurar que él pueda hacer `cd ~/code/argos/lab && vagrant up` y obtener un lab idéntico. Coordina una prueba conjunta:

1. Tú apagas tu lab (`vagrant halt`).
2. P1 prende el suyo.
3. Cambia env var `WAZUH_HOST=p1-espejo.local` en los servicios SOAR/ML.
4. Corren un mini UC-01.
5. Documenta el tiempo de switchover en `docs/LESSONS_LEARNED.md`. Objetivo: ≤ 5 min.

---

## 4.4 Video respaldo

### Comandos

```bash
# Grabar pantalla completa de tu rehearsal final (OBS o vokoscreenNG)
# Output: docs/team/argos-demo-rehearsal.mp4
# NO commitear si > 100 MB; sube a Drive y comparte link en standup.
obs-studio   # o vokoscreenNG
```

### Verificación

```verify
ls -lah docs/team/argos-demo-rehearsal.mp4 2>/dev/null || echo "video pendiente"
```

---

## 4.5 Checklist pre-demo (T-2 h)

| # | Check | OK |
|---|-------|----|
| 1 | `vagrant status` → 3 running | ☐ |
| 2 | Wazuh API health 200 | ☐ |
| 3 | OpenSearch health green | ☐ |
| 4 | Streamlit Approval Console abre y muestra "No active" | ☐ |
| 5 | Bridge service activo | ☐ |
| 6 | Postgres conectable | ☐ |
| 7 | Hot spare P1 también `running` | ☐ |
| 8 | Video respaldo accesible offline | ☐ |
| 9 | Cargador laptop + cable HDMI/USB-C al proyector | ☐ |
| 10 | 4 terminales preparadas con comandos UC-01..04 | ☐ |

---

# Apéndice A — Troubleshooting

| # | Síntoma | Diagnóstico | Fix |
|---|---------|-------------|-----|
| A.1 | `vagrant up` falla con `Vagrant could not detect VBoxManage` | PATH | Agrega ruta de VirtualBox al PATH |
| A.2 | VM Windows no arranca (WinRM timeout) | Provision pesado | `vagrant reload windows-victim --provision`; si persiste: destroy + up |
| A.3 | OpenSearch OOM | Heap insuficiente | Subir `OPENSEARCH_JAVA_OPTS=-Xms1500m -Xmx1500m` |
| A.4 | Bridge no recibe alerts | `alerts.json` no existe (Wazuh down) | `sudo /var/ossec/bin/wazuh-control status` y restart si parado |
| A.5 | Streamlit no refresca | Polling pausado | F5 manual; los datos están en Redis |
| A.6 | Postgres `FATAL: password authentication failed` | `pg_hba.conf` no permite tu rango | Confirma `host all all 192.168.56.0/24 md5` |
| A.7 | Wazuh agent no aparece en manager | Server IP mal config | Editar `<server-ip>` en agent `ossec.conf` y restart |

---

# Apéndice B — Comandos de emergencia

```bash
# Lab caído mid-demo
make demo-reset

# Reload completo del manager (último recurso, ~30s downtime)
vagrant reload lab-manager

# Switch a lab espejo de P1
export WAZUH_HOST=p1-espejo.local
export REDIS_URL=redis://p1-espejo.local:6379/0
make soar-restart

# Postgres lleno
psql -U argos -d argos_audit -c "DELETE FROM audit_incidents WHERE created_at < NOW() - INTERVAL '24 hours';"

# OpenSearch indexes lentos
curl -X POST 'http://localhost:9200/_cache/clear?pretty'

# Streamlit muerto
pkill -f streamlit
nohup streamlit run ui/streamlit_app/app.py --server.port 8501 > /tmp/streamlit.log 2>&1 &
```

---

# Apéndice C — Referencias cruzadas

| Cuando estés en... | Lee |
|--------------------|-----|
| `lab/Vagrantfile` | SAD §13, `docs/team/manual-equipo.md` §1 |
| `lab/postgres/` | Manual P1 §3.2 |
| `ui/streamlit_app/` | SAD §9.2, ADR-0006 |
| `evaluation/` | EVALUATION_CRITERIA §1.3 |

---

## Change log

| Versión | Fecha | Cambio |
|---------|-------|--------|
| 3.0 | 2026-05-24 | Reestructurado: Contexto → Pasos manuales → Comandos → Salida → Verificación → Si algo falla. Vagrantfile, pgAudit, bridge, Streamlit completos. Bloques bash/sql/yaml listos para copy buttons. Sin referencias temporales. Renombrado de `sprint-week-1-p4-diego.md`. |
