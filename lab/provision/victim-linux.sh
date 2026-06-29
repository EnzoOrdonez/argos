#!/usr/bin/env bash
# ============================================================
# ARGOS lab — provision de la VÍCTIMA Linux (192.168.56.21, production-critical).
# Wazuh agent + auditd + PostgreSQL app_prod (IntiBank) + pgAudit + scripts AR.
#
# Anti-brick: escribe /var/ossec/etc/argos-ar.conf con MANAGER_IP (argos-isolate.sh
# aborta sin él). Idempotente. set -euo pipefail. Repo montado ro en /argos.
# ============================================================
set -euo pipefail

MANAGER_IP="${MANAGER_IP:-192.168.56.10}"
REPO=/argos
OSSEC=/var/ossec
PGVER=15                      # Debian 12 bookworm

echo "[lin] === provision víctima Linux; manager=${MANAGER_IP} ==="

# F4: el provision necesita salida a internet (apt Wazuh/PostgreSQL, pip Faker).
# Fallar ruidoso y claro si no hay egress, en vez de morir 50 líneas más abajo.
if ! curl -fsS -m 10 https://packages.wazuh.com/ >/dev/null 2>&1 \
   && ! curl -fsS -m 10 https://deb.debian.org/ >/dev/null 2>&1; then
  echo "[lin] FATAL: sin salida a internet en la VM — el apt/pip del provision no van." >&2
  echo "[lin]   Opciones: habilitar NAT en la VM, o pre-generar lab/postgres/seed_snapshot.sql.gz" >&2
  echo "[lin]   + un mirror apt local. Ver lab/RUNBOOK_BOOT_1A.md (sección offline)." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y curl gnupg apt-transport-https ca-certificates lsb-release \
  jq iptables cpulimit auditd python3-venv \
  postgresql postgresql-contrib

# pgAudit NO está en Debian main (vive en PGDG apt.postgresql.org). Best-effort:
# su consumidor (reglas Sigma DB) está deferido (C17), así que NO debe bloquear el
# provision si el paquete falta. Si está, lo activamos abajo.
PGAUDIT_OK=0
if apt-get install -y "postgresql-${PGVER}-pgaudit"; then
  PGAUDIT_OK=1
else
  echo "[lin] WARN: pgAudit no disponible en repos (PGDG no agregado); sigo sin él (C17 deferido)"
fi

# ------------------------------------------------------------
# 1. Wazuh agent -> manager, registrar, enable
# ------------------------------------------------------------
if ! dpkg -s wazuh-agent >/dev/null 2>&1; then
  curl -s https://packages.wazuh.com/key/GPG-KEY-WAZUH \
    | gpg --no-default-keyring --keyring gnupg-ring:/usr/share/keyrings/wazuh.gpg --import
  chmod 644 /usr/share/keyrings/wazuh.gpg
  echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" \
    > /etc/apt/sources.list.d/wazuh.list
  apt-get update -y
  WAZUH_MANAGER="${MANAGER_IP}" WAZUH_AGENT_NAME="LIN-VICTIM-01" apt-get install -y wazuh-agent
fi
# Asegurar el manager en el config
sed -i "s#<address>.*</address>#<address>${MANAGER_IP}</address>#" "${OSSEC}/etc/ossec.conf" || true

# F2: esperar a que el authd del manager (1515) escuche ANTES de enrolar (Vagrant
# provisiona core primero, pero el authd puede tardar en levantar).
echo "[lin] esperando authd ${MANAGER_IP}:1515 ..."
for i in $(seq 1 60); do
  if (echo > "/dev/tcp/${MANAGER_IP}/1515") 2>/dev/null; then echo "[lin] authd up"; break; fi
  [ "$i" = 60 ] && { echo "[lin] FATAL: authd ${MANAGER_IP}:1515 no respondió en 120s" >&2; exit 1; }
  sleep 2
done

# Enrolar (fail-loud, sin || true)
"${OSSEC}/bin/agent-auth" -m "${MANAGER_IP}" -A "LIN-VICTIM-01" \
  || { echo "[lin] FATAL: agent-auth falló contra ${MANAGER_IP}" >&2; exit 1; }
systemctl daemon-reload
systemctl enable --now wazuh-agent

# F2: verificar la conexión real al manager (lado agente = equivalente a Active).
echo "[lin] verificando conexión al manager ..."
for i in $(seq 1 30); do
  if grep -q "Connected to the server" "${OSSEC}/logs/ossec.log" 2>/dev/null; then
    echo "[lin] agente conectado al manager (OK)"; break
  fi
  [ "$i" = 30 ] && { echo "[lin] FATAL: el agente no se conectó al manager en 60s (ver ${OSSEC}/logs/ossec.log)" >&2; exit 1; }
  sleep 2
done

# ------------------------------------------------------------
# 2. Scripts AR (nombre SIN extensión = el <executable> del manager) + anti-brick
# ------------------------------------------------------------
install -d -m 0750 -o root -g wazuh "${OSSEC}/active-response/bin"
for f in "${REPO}"/active-response/linux/argos-*.sh; do
  base=$(basename "$f" .sh)
  install -m 0750 -o root -g wazuh "$f" "${OSSEC}/active-response/bin/${base}"
done

# *** INVARIANTE ANTI-BRICK: sin esto argos-isolate aborta (no aísla a ciegas) ***
cat > "${OSSEC}/etc/argos-ar.conf" <<EOF
MANAGER_IP=${MANAGER_IP}
EOF
chmod 0640 "${OSSEC}/etc/argos-ar.conf"
grep -q "^MANAGER_IP=${MANAGER_IP}$" "${OSSEC}/etc/argos-ar.conf" \
  || { echo "[lin] FATAL: argos-ar.conf no quedó con MANAGER_IP" >&2; exit 1; }

# ------------------------------------------------------------
# 3. Canary files + auditd (F1: los 4 paths canónicos = deception/canary-generator/
#    config.yaml (victim-linux-01) = fim-configs/ossec-linux.conf = regex de
#    canary_rules.xml id 100100, que matchea por FILENAME). Crear los archivos ANTES
#    de cargar auditd para que los watches `-w` resuelvan el inode.
# ------------------------------------------------------------
id victim >/dev/null 2>&1 || useradd -m -s /bin/bash victim
install -d -o victim -g victim /home/victim/Documents
install -d /var/backups
gen_canary() {  # $1=path  $2=owner
  printf 'CONFIDENCIAL IntiBank — senuelo de laboratorio (ARGOS canary). NO tocar.\n' > "$1"
  chown "$2":"$2" "$1" 2>/dev/null || true
  touch -d "90 days ago" "$1"
}
gen_canary /home/victim/Documents/financials_Q4_2025.xlsx victim
gen_canary /home/victim/passwords.txt                     victim
gen_canary /home/victim/Documents/accounts_admin.csv      victim
gen_canary /var/backups/db_backup.sql                     root

cat > /etc/audit/rules.d/argos.rules <<'EOF'
-w /home/victim/Documents/financials_Q4_2025.xlsx -p rwxa -k argos_canary
-w /home/victim/passwords.txt -p rwxa -k argos_canary
-w /var/backups/db_backup.sql -p rwxa -k argos_canary
-w /home/victim/Documents/accounts_admin.csv -p rwxa -k argos_canary
-a always,exit -F arch=b64 -S execve -k argos_exec
EOF
augenrules --load || true
systemctl restart auditd || true

# ------------------------------------------------------------
# 4. PostgreSQL app_prod (IntiBank) — escucha en la subred del lab
# ------------------------------------------------------------
PGCONF="/etc/postgresql/${PGVER}/main"
sed -i "s/^#\?listen_addresses.*/listen_addresses = '*'/" "${PGCONF}/postgresql.conf"
# pgAudit (su consumidor -reglas DB- está deferido a P3/P1, pero la infra queda)
if [ "${PGAUDIT_OK}" = 1 ] && ! grep -q "shared_preload_libraries.*pgaudit" "${PGCONF}/postgresql.conf"; then
  echo "shared_preload_libraries = 'pgaudit'" >> "${PGCONF}/postgresql.conf"
  echo "pgaudit.log = 'read,write,ddl'"        >> "${PGCONF}/postgresql.conf"
fi
# pg_hba: password auth desde localhost (seed) y desde la subred (simuladores)
if ! grep -q "ARGOS-LAB" "${PGCONF}/pg_hba.conf"; then
  cat >> "${PGCONF}/pg_hba.conf" <<EOF
# ARGOS-LAB
host    all   all   127.0.0.1/32        scram-sha-256
host    all   all   192.168.56.0/24     scram-sha-256
EOF
fi
systemctl restart postgresql

# DDL + roles (ADR-0009). Idempotente: CREATE DATABASE protegido.
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='app_prod'" | grep -q 1 \
  || sudo -u postgres createdb app_prod
sudo -u postgres psql -d app_prod -v ON_ERROR_STOP=1 -f "${REPO}/lab/postgres/init.sql"

# ------------------------------------------------------------
# 5. Seed: snapshot si existe (rápido), si no generar con seed.py
# ------------------------------------------------------------
SNAP="${REPO}/lab/postgres/seed_snapshot.sql.gz"
if sudo -u postgres psql -d app_prod -tc "SELECT count(*) FROM intibank.customers" | grep -qE '[1-9]'; then
  echo "[lin] DB ya tiene datos; salto el seed"
elif [ -r "${SNAP}" ]; then
  echo "[lin] cargando snapshot ${SNAP}"
  gunzip -c "${SNAP}" | sudo -u postgres psql -d app_prod
else
  echo "[lin] generando seed con Faker (venv aislado)"
  python3 -m venv /opt/argos-seed/venv
  /opt/argos-seed/venv/bin/pip -q install faker numpy psycopg2-binary
  VICTIM_PG_HOST=127.0.0.1 VICTIM_PG_DB=app_prod \
    VICTIM_PG_SEED_USER=inti_dba VICTIM_PG_SEED_PASSWORD=inti_dba_secret_2026 \
    /opt/argos-seed/venv/bin/python "${REPO}/lab/postgres/seed.py"
fi

# Dump para targets de canary/ransomware (ADR-0009 §3.3 narrativa)
mkdir -p /var/backups/postgres
sudo -u postgres pg_dump --no-owner app_prod | gzip > /var/backups/postgres/app_prod_$(hostname).sql.gz || true

# ------------------------------------------------------------
# 6. Canary FIM whodata (F1: usa el <syscheck> canónico de deception/fim-configs/
#    ossec-linux.conf — single source of truth, los MISMOS 4 paths que auditd y la
#    regla 100100. Es un <ossec_config> completo, se appendea como bloque.)
# ------------------------------------------------------------
MARK_FIM="<!-- ARGOS-CANARY-FIM -->"
if ! grep -qF "${MARK_FIM}" "${OSSEC}/etc/ossec.conf"; then
  {
    echo ""
    echo "${MARK_FIM}"
    cat "${REPO}/deception/fim-configs/ossec-linux.conf"
  } >> "${OSSEC}/etc/ossec.conf"
fi
systemctl restart wazuh-agent

echo "[lin] === provision OK. DB app_prod lista; agente reportando a ${MANAGER_IP} ==="
