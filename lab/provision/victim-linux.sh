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
# Asegurar el manager en el config y registrar contra authd (1515)
sed -i "s#<address>.*</address>#<address>${MANAGER_IP}</address>#" "${OSSEC}/etc/ossec.conf" || true
"${OSSEC}/bin/agent-auth" -m "${MANAGER_IP}" -A "LIN-VICTIM-01" || true
systemctl daemon-reload
systemctl enable --now wazuh-agent

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
# 3. auditd: reglas básicas de actividad (ejecución + canary)
# ------------------------------------------------------------
cat > /etc/audit/rules.d/argos.rules <<'EOF'
-w /opt/argos/canary/ -p rwa -k argos_canary
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
# 6. Canary FIM whodata
# ------------------------------------------------------------
install -d -m 0755 /opt/argos/canary
echo "intibank-canary-do-not-touch" > /opt/argos/canary/passwords.csv
if ! grep -q "/opt/argos/canary" "${OSSEC}/etc/ossec.conf"; then
  sed -i "s#</syscheck>#  <directories whodata=\"yes\" report_changes=\"yes\">/opt/argos/canary</directories>\n</syscheck>#" \
    "${OSSEC}/etc/ossec.conf" || true
fi
systemctl restart wazuh-agent

echo "[lin] === provision OK. DB app_prod lista; agente reportando a ${MANAGER_IP} ==="
