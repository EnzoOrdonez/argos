# Sprint Semana 1 — Manual de P4 (Diego Jara)

| Field | Value |
|-------|-------|
| Owner | Diego Jara |
| Rol | P4 · Infraestructura + UI base + Demo |
| Goal de la semana | Vagrantfile + Wazuh Manager + OpenSearch + Redis + Windows VM (Sysmon) + Linux VM (auditd) + PostgreSQL con datos sintéticos + simuladores multi-vector (hping3 + slowhttptest + sqlmap) + UI Streamlit base + video demo. |
| Effort estimado | 6-7 horas/día × 7 días = ~45 horas (el más cargado por ser infrastructure) |
| Pre-requisitos | Leer `docs/team/sprint-week-1-common-intro.md` y `docs/decisions/0008-multi-vector-scope-expansion.md` |

---

## Antes de empezar — prerequisitos CRÍTICOS

P4 tiene el rol más exigente de hardware. Sin esto, el sprint se atasca para todos.

### Hardware MÍNIMO

- Laptop con **16 GB RAM mínimo** (8 GB NO aguanta 3 VMs simultáneas).
- **80 GB de disco libre** (para boxes Vagrant + VMs + dumps).
- CPU con **virtualization extensions** (Intel VT-x o AMD-V) **habilitado en BIOS**.
- Idealmente: SSD externo USB-C de 256 GB (~$30 USD) para portabilidad. Si tu laptop muere, conectas SSD a otro y bootean las VMs.

### Software base

```bash
# Vagrant 2.4+
vagrant --version

# VirtualBox 7.x (o Hyper-V provider)
VBoxManage --version
```

**Si estás en Windows con Hyper-V:** debes elegir uno solo. Vagrant + VirtualBox + Hyper-V chocan. Decide hoy:
```powershell
# Opción 1: usar VirtualBox (desactivar Hyper-V)
bcdedit /set hypervisorlaunchtype off
# reiniciar

# Opción 2: usar Hyper-V (Vagrant lo soporta)
vagrant init --box generic/ubuntu2204 --box-version 4.3.12
```

### Cuentas externas

- **Twilio trial** para UC-04 voice escalation (gratis ~$15 crédito): https://www.twilio.com/try-twilio

---

## Día 1 (Lunes) — Vagrantfile + boxes + Wazuh Manager skeleton

**Goal:** Vagrantfile que define 3 VMs (Wazuh manager + Win + Linux), `vagrant up` completa en <15 min, Wazuh manager arranca con servicio corriendo.

**Tiempo:** 7 horas (día más largo).

### Paso 1.1 — Setup repo (15 min)

```bash
cd ~/projects
git clone https://github.com/EnzoOrdonez/argos.git
cd argos
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest argos_contracts/tests/ -v
# Esperado: 69 passed
```

### Paso 1.2 — Vagrantfile básico (1.5 h)

`lab/Vagrantfile`:

```ruby
# -*- mode: ruby -*-
Vagrant.configure("2") do |config|
  # Network privada para el lab (sin internet)
  config.vm.network "private_network", type: "dhcp"

  # ===== Wazuh Manager =====
  config.vm.define "wazuh-mgr" do |mgr|
    mgr.vm.box = "generic/ubuntu2204"
    mgr.vm.hostname = "wazuh-mgr"
    mgr.vm.network "private_network", ip: "10.0.0.10"
    mgr.vm.provider "virtualbox" do |vb|
      vb.memory = "4096"
      vb.cpus = 2
      vb.name = "argos-wazuh-mgr"
    end
    mgr.vm.provision "shell", path: "provision/wazuh-manager.sh"
  end

  # ===== Linux Victim (PostgreSQL host) =====
  config.vm.define "linux-victim" do |lv|
    lv.vm.box = "generic/ubuntu2204"
    lv.vm.hostname = "linux-victim"
    lv.vm.network "private_network", ip: "10.0.0.22"
    lv.vm.provider "virtualbox" do |vb|
      vb.memory = "2048"
      vb.cpus = 2
      vb.name = "argos-linux-victim"
    end
    lv.vm.provision "shell", path: "provision/victim-linux.sh"
    lv.vm.provision "shell", path: "provision/postgres-setup.sh"
  end

  # ===== Windows Victim =====
  config.vm.define "windows-victim" do |wv|
    wv.vm.box = "gusztavvargadr/windows-10"
    wv.vm.hostname = "windows-victim"
    wv.vm.network "private_network", ip: "10.0.0.21"
    wv.vm.provider "virtualbox" do |vb|
      vb.memory = "4096"
      vb.cpus = 2
      vb.name = "argos-windows-victim"
      vb.gui = false
    end
    wv.vm.provision "shell", path: "provision/victim-windows.ps1"
  end
end
```

### Paso 1.3 — Provisioning Wazuh manager (2 h)

`lab/provision/wazuh-manager.sh`:

```bash
#!/bin/bash
set -e

echo "[1/4] Updating system..."
apt-get update -y

echo "[2/4] Installing Wazuh manager..."
curl -sO https://packages.wazuh.com/4.7/wazuh-install.sh
bash wazuh-install.sh --wazuh-server wazuh-1 --ignore-check

echo "[3/4] Installing OpenSearch..."
bash wazuh-install.sh --opensearch wazuh-1 --ignore-check

echo "[4/4] Installing Redis 7..."
apt-get install -y redis-server
sed -i 's/^bind 127.0.0.1.*/bind 0.0.0.0/' /etc/redis/redis.conf
systemctl restart redis-server

echo "Wazuh manager + OpenSearch + Redis ready on 10.0.0.10"
```

### Paso 1.4 — Primer `vagrant up` (2 h)

```bash
cd lab
vagrant up wazuh-mgr
# Esperado: ~15-20 min primera vez (descarga box + provisioning Wazuh)
vagrant status
# wazuh-mgr should be "running"

vagrant ssh wazuh-mgr -c "systemctl status wazuh-manager"
# Esperado: active (running)

vagrant ssh wazuh-mgr -c "curl -k https://localhost:55000"
# Esperado: JSON response (Wazuh API)
```

Si falla:
- VirtualBox / Hyper-V conflict → reiniciar con uno solo
- Memoria insuficiente → cerrar Chrome/IDE temporalmente
- Box no descarga → verificar internet, retry

### Paso 1.5 — Commit (15 min)

```bash
cd ..
git checkout -b feature/p4/lab-skeleton
git add lab/
git commit -m "feat(p4): Vagrantfile + Wazuh manager provisioning"
git push origin feature/p4/lab-skeleton
```

### Verificación EOD Día 1

- [ ] `vagrant up wazuh-mgr` completa sin errores
- [ ] Wazuh API responde en https://10.0.0.10:55000
- [ ] Redis acepta `PING` desde host

---

## Día 2 (Martes) — Linux + Windows victims con agentes

**Goal:** Las 3 VMs corriendo, agentes registrados en el manager, primera telemetría llegando.

**Tiempo:** 7 horas.

### Paso 2.1 — Provisioning Linux victim (2 h)

`lab/provision/victim-linux.sh`:

```bash
#!/bin/bash
set -e

echo "[1/3] Installing auditd..."
apt-get install -y auditd

echo "[2/3] Installing Wazuh agent..."
WAZUH_MANAGER="10.0.0.10" \
  bash -c "$(curl -sSL https://packages.wazuh.com/4.7/wazuh-install.sh) --wazuh-agent linux-victim"

echo "[3/3] Starting agent..."
systemctl enable wazuh-agent
systemctl start wazuh-agent
```

### Paso 2.2 — Provisioning Windows victim (2.5 h)

`lab/provision/victim-windows.ps1`:

```powershell
# Sysmon install
$sysmonConfig = "https://raw.githubusercontent.com/SwiftOnSecurity/sysmon-config/master/sysmonconfig-export.xml"
Invoke-WebRequest -Uri "https://download.sysinternals.com/files/Sysmon.zip" -OutFile "C:\sysmon.zip"
Expand-Archive -Path "C:\sysmon.zip" -DestinationPath "C:\sysmon\"
Invoke-WebRequest -Uri $sysmonConfig -OutFile "C:\sysmon\config.xml"
& C:\sysmon\Sysmon64.exe -accepteula -i C:\sysmon\config.xml

# Wazuh agent
$wazuhMsi = "https://packages.wazuh.com/4.x/windows/wazuh-agent-4.7.0-1.msi"
Invoke-WebRequest -Uri $wazuhMsi -OutFile "C:\wazuh-agent.msi"
Start-Process msiexec.exe -ArgumentList '/i C:\wazuh-agent.msi /q WAZUH_MANAGER=10.0.0.10 WAZUH_AGENT_NAME=windows-victim' -Wait
Start-Service WazuhSvc

Write-Host "Sysmon + Wazuh agent installed"
```

### Paso 2.3 — Levantar las 3 VMs (1.5 h)

```bash
vagrant up linux-victim
vagrant up windows-victim
vagrant status
# las 3 deben estar running

# Verificar agentes registrados en manager
vagrant ssh wazuh-mgr -c "sudo /var/ossec/bin/agent_control -l"
# Esperado: linux-victim + windows-victim listed
```

### Paso 2.4 — Commit (15 min)

```bash
git add lab/provision/
git commit -m "feat(p4): victim VMs + agents registered"
git push
```

### Verificación EOD Día 2

- [ ] 3 VMs running (`vagrant status`)
- [ ] 2 agentes registrados y activos
- [ ] Logs llegando al manager (`tail -f /var/ossec/logs/alerts/alerts.json` en mgr)

---

## Día 3 (Miércoles) — PostgreSQL + datos sintéticos + pgAudit

**Goal:** PostgreSQL 15 corriendo en Linux VM con esquema `argos_demo_prod` poblado.

**Tiempo:** 6 horas.

### Paso 3.1 — Provisioning PostgreSQL (2 h)

`lab/provision/postgres-setup.sh`:

```bash
#!/bin/bash
set -e

apt-get install -y postgresql-15 postgresql-contrib-15 postgresql-15-pgaudit

# Configurar pgAudit
echo "shared_preload_libraries = 'pgaudit'" >> /etc/postgresql/15/main/postgresql.conf
echo "pgaudit.log = 'read, write'" >> /etc/postgresql/15/main/postgresql.conf
echo "pgaudit.log_catalog = off" >> /etc/postgresql/15/main/postgresql.conf

systemctl restart postgresql

# Crear DB + user
sudo -u postgres psql <<EOF
CREATE DATABASE argos_demo_prod;
CREATE USER argos_app WITH PASSWORD 'change-me-in-env';
GRANT ALL PRIVILEGES ON DATABASE argos_demo_prod TO argos_app;
EOF

# Seed schema + data
sudo -u postgres psql -d argos_demo_prod -f /vagrant/provision/postgres-seed.sql
```

### Paso 3.2 — Schema + datos sintéticos (2 h)

`lab/provision/postgres-seed.sql`:

```sql
-- argos_demo_prod schema
CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100),
    department VARCHAR(50),
    salary NUMERIC(10, 2),
    hired_at DATE
);

CREATE TABLE payroll (
    id SERIAL PRIMARY KEY,
    employee_id INT REFERENCES employees(id),
    period DATE,
    gross_amount NUMERIC(10, 2),
    net_amount NUMERIC(10, 2),
    paid_at TIMESTAMP
);

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100),
    country VARCHAR(50),
    created_at TIMESTAMP
);

CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    customer_id INT REFERENCES customers(id),
    amount NUMERIC(10, 2),
    status VARCHAR(20),
    issued_at TIMESTAMP
);

CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    invoice_id INT REFERENCES invoices(id),
    amount NUMERIC(10, 2),
    paid_at TIMESTAMP
);

-- 1000 employees sintéticos
INSERT INTO employees (name, email, department, salary, hired_at)
SELECT
    'Employee ' || gs,
    'emp' || gs || '@argos-demo.local',
    (ARRAY['Engineering', 'Sales', 'Finance', 'HR', 'IT'])[1 + (gs % 5)],
    50000 + (random() * 100000)::int,
    date '2020-01-01' + (random() * 1500)::int
FROM generate_series(1, 1000) gs;

-- Similar inserts for payroll, customers, invoices, payments
-- (~10K rows each)
```

### Paso 3.3 — Dumps periódicos para canary (45 min)

`lab/provision/postgres-dumps.sh`:

```bash
#!/bin/bash
mkdir -p /var/backups/postgres
cat > /etc/cron.hourly/argos-pg-dump <<'EOF'
#!/bin/bash
sudo -u postgres pg_dump argos_demo_prod > /var/backups/postgres/dump-$(date +%Y%m%d-%H%M).sql
EOF
chmod +x /etc/cron.hourly/argos-pg-dump
```

### Paso 3.4 — Tag criticality production-critical en Wazuh (45 min)

En el manager:
```bash
# Editar ossec.conf en el agent linux-victim para añadir labels
sudo /var/ossec/bin/agent_control -i 002 -l
# añadir: <labels><label key="criticality">production-critical</label></labels>
```

### Paso 3.5 — Re-vagrant up linux-victim + commit (30 min)

```bash
vagrant reload linux-victim --provision
git add lab/provision/postgres-*.sh lab/provision/postgres-seed.sql
git commit -m "feat(p4): PostgreSQL 15 + pgAudit + schema argos_demo_prod"
git push
```

### Verificación EOD Día 3

- [ ] PostgreSQL responde en 10.0.0.22:5432
- [ ] Schema tiene 5 tablas con datos
- [ ] Dumps SQL apareciendo en /var/backups/postgres/

---

## Día 4 (Jueves) — Simuladores ransomware + DDoS + SQLi

**Goal:** 3 simuladores funcionales en `attack-simulation/`.

**Tiempo:** 6 horas.

### Paso 4.1 — Ransomware simulator wrapper (1.5 h)

P1 escribe el simulador en `attack-simulation/ransomware_simulator/`. Tú escribes el wrapper que lo ejecuta en la Windows VM remotamente:

```bash
# attack-simulation/run_uc01.sh
#!/bin/bash
vagrant ssh windows-victim -c "python C:\\argos\\ransomware_simulator\\lockbit_like.py --target localhost"
```

### Paso 4.2 — DDoS simulator (1.5 h)

`attack-simulation/network_attacks/run_ddos.sh`:

```bash
#!/bin/bash
TARGET_IP=${1:-10.0.0.22}
TARGET_PORT=${2:-5432}
sudo hping3 --flood --syn -p $TARGET_PORT $TARGET_IP &
SLOW_PID=$!
sleep 30
kill $SLOW_PID
```

### Paso 4.3 — Webapp + sqlmap setup (2 h)

`lab/provision/webapp-flask.sh`:

```bash
#!/bin/bash
apt-get install -y python3-pip
pip3 install flask psycopg2-binary
mkdir -p /opt/argos-webapp
cat > /opt/argos-webapp/app.py <<'PYEOF'
from flask import Flask, request
import psycopg2

app = Flask(__name__)

@app.route('/')
def index():
    user_id = request.args.get('id', '1')
    # INTENCIONALMENTE vulnerable a SQL injection — es para UC-08
    conn = psycopg2.connect("dbname=argos_demo_prod user=argos_app password=...")
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM employees WHERE id = {user_id}")
    return str(cur.fetchall())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
PYEOF
nohup python3 /opt/argos-webapp/app.py &
```

`attack-simulation/webapp_attacks/run_sqli.sh`:

```bash
#!/bin/bash
TARGET_URL=${1:-"http://10.0.0.22/?id=1"}
sqlmap -u "$TARGET_URL" --batch --dbs --threads=5
```

### Paso 4.4 — Commit (15 min)

```bash
git add attack-simulation/ lab/provision/webapp-flask.sh
git commit -m "feat(p4): simuladores DDoS + SQLi + ransomware wrapper"
git push
```

### Verificación EOD Día 4

- [ ] `bash run_ddos.sh` genera flood detectable
- [ ] `bash run_sqli.sh` ejecuta payloads sqlmap
- [ ] Webapp Flask responde en http://10.0.0.22/

---

## Día 5 (Viernes) — UI Streamlit base + OpenSearch dashboards

**Goal:** Streamlit Analyst UI con tabs base (la Approval Console la entrega P1) + 3 dashboards OpenSearch importados.

**Tiempo:** 6 horas.

### Paso 5.1 — Streamlit shell (2 h)

`ui/streamlit_app/app.py`:

```python
import streamlit as st

st.set_page_config(page_title="ARGOS Analyst UI", layout="wide")
st.title("🛡 ARGOS — Analyst Console")
st.write("Activo defendido: PostgreSQL Production DB")

st.sidebar.title("Navegación")
st.sidebar.info("Approval Console está en su propia página")
```

`ui/streamlit_app/pages/01_alert_inspection.py`:

```python
import streamlit as st
import redis

st.title("Alert Inspection")
r = redis.from_url("redis://10.0.0.10:6379/0", decode_responses=True)

# Mostrar últimas 10 alertas del stream
messages = r.xrevrange("wazuh:alerts", count=10)
for entry_id, fields in messages:
    with st.expander(f"Alert {entry_id}"):
        st.json(fields)
```

`ui/streamlit_app/pages/03_audit_forensics.py`:

```python
import streamlit as st
from opensearchpy import OpenSearch

st.title("Audit & Forensics")
client = OpenSearch([{"host": "10.0.0.10", "port": 9200}], use_ssl=True, verify_certs=False)

incidents = client.search(index="argos-incidents-*", body={"query": {"match_all": {}}, "size": 50})
for hit in incidents["hits"]["hits"]:
    st.json(hit["_source"])
```

### Paso 5.2 — OpenSearch dashboards JSON (2.5 h)

Diseñar 3 dashboards en OpenSearch Dashboards UI, exportar JSON:

- `ui/opensearch-dashboards/alerts-timeline.ndjson`
- `ui/opensearch-dashboards/mitre-heatmap.ndjson`
- `ui/opensearch-dashboards/layer-performance.ndjson`

### Paso 5.3 — Commit (15 min)

### Verificación EOD Día 5

- [ ] `streamlit run ui/streamlit_app/app.py` levanta sin error
- [ ] Las 3 pages cargan
- [ ] OpenSearch Dashboards importan correctamente

---

## Día 6 (Sábado) — Rehearsals + video demo

**Goal:** 3 corridas de cada UC con OBS grabando.

**Tiempo:** 6 horas.

### Paso 6.1 — OBS Studio setup (30 min)

Instalar OBS, configurar:
- Scene "Demo": pantalla completa + webcam pequeña abajo-derecha + mic
- Audio: micrófono USB calidad ≥ phone-level

### Paso 6.2 — Rehearsal UC-01 (1 h)

P1 narra, P4 ejecuta, los 4 con celulares. Grabar 3 takes. El mejor se queda como respaldo.

### Paso 6.3 — Rehearsals UC-02, UC-04, UC-06, UC-07 (3 h)

Mismo formato.

### Paso 6.4 — Edición rápida (1 h)

DaVinci Resolve free o iMovie. Cortar errores, juntar tomas, añadir subtítulos básicos. Output: video MP4 de 12-15 min.

### Verificación EOD Día 6

- [ ] Video MP4 de respaldo grabado
- [ ] Backup en USB + Google Drive

---

## Día 7 (Domingo) — Rehearsals finales + status

**Mañana:** 5 rehearsals seguidos cronometrados.

**Tarde:** Bug bash de infrastructure issues.

**Noche:** Update `docs/PROJECT_STATUS.md` con estado real.

---

## Apéndice A — Comandos diarios

```bash
# Estado del lab
cd ~/projects/argos/lab && vagrant status

# Restart Wazuh manager
vagrant ssh wazuh-mgr -c "sudo systemctl restart wazuh-manager"

# Logs Wazuh en tiempo real
vagrant ssh wazuh-mgr -c "sudo tail -f /var/ossec/logs/alerts/alerts.json"

# PostgreSQL queries
vagrant ssh linux-victim -c "sudo -u postgres psql -d argos_demo_prod -c '\dt'"

# Reset full
vagrant destroy -f && vagrant up
```

---

## Apéndice B — Troubleshooting

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `vagrant up` cuelga en "Booting VM..." | Hyper-V vs VirtualBox conflict | `bcdedit /set hypervisorlaunchtype off` + reboot |
| Box no descarga | Conexión lenta | Pre-descargar: `vagrant box add generic/ubuntu2204` |
| Wazuh agent "Disconnected" | Manager IP no accesible | Verificar `private_network` config |
| OpenSearch OOM | Heap default muy bajo | Aumentar `-Xms2g -Xmx2g` en jvm.options |
| PostgreSQL "permission denied" | pg_hba.conf no acepta el cliente | Editar pg_hba.conf, restart |

---

## Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 | 2026-05-24 | Initial manual P4 — Vagrant + Wazuh + OpenSearch + Redis + VMs + PostgreSQL + pgAudit + simuladores DDoS/SQLi + UI Streamlit base + video demo. | P1 |
