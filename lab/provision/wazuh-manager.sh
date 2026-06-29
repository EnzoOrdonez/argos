#!/usr/bin/env bash
# ============================================================
# ARGOS lab — provision del CORE (192.168.56.10).
# Wazuh manager (systemd, Perfil A manager-only, sin indexer/dashboard, ADR-0015)
# + reglas canary + registro de comandos AR + docker compose --profile real.
#
# Idempotente: se puede re-correr. Falla ruidoso (set -euo pipefail).
# El repo está montado read-only en /argos (ver Vagrantfile synced_folder).
# ============================================================
set -euo pipefail

MANAGER_IP="${MANAGER_IP:-192.168.56.10}"
REPO=/argos
OSSEC=/var/ossec

echo "[core] === provision Wazuh manager @ ${MANAGER_IP} ==="

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y curl gnupg apt-transport-https lsb-release ca-certificates jq

# ------------------------------------------------------------
# 1. Wazuh manager 4.x via apt (systemd, manager-only)
# ------------------------------------------------------------
if ! dpkg -s wazuh-manager >/dev/null 2>&1; then
  curl -s https://packages.wazuh.com/key/GPG-KEY-WAZUH \
    | gpg --no-default-keyring --keyring gnupg-ring:/usr/share/keyrings/wazuh.gpg --import
  chmod 644 /usr/share/keyrings/wazuh.gpg
  echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" \
    > /etc/apt/sources.list.d/wazuh.list
  apt-get update -y
  apt-get install -y wazuh-manager
fi
systemctl daemon-reload
systemctl enable --now wazuh-manager

# ------------------------------------------------------------
# 2. Reglas: canary L3 (las Sigma DB van cuando P3 cierre C18: sigma-cli -> local_rules.xml)
# ------------------------------------------------------------
install -m 0640 -o root -g wazuh \
  "${REPO}/deception/wazuh-rules/canary_rules.xml" \
  "${OSSEC}/etc/rules/canary_rules.xml"

# ------------------------------------------------------------
# 3. Registrar comandos AR (cada fragmento es un <ossec_config> completo y válido;
#    Wazuh concatena múltiples bloques). Marcado para poder re-aplicar idempotente.
# ------------------------------------------------------------
MARK="<!-- ARGOS-AR-APPENDED -->"
if ! grep -qF "${MARK}" "${OSSEC}/etc/ossec.conf"; then
  {
    echo ""
    echo "${MARK}"
    cat "${REPO}/active-response/ossec/argos-ar-commands.conf"
    cat "${REPO}/active-response/ossec/argos-ar-active-response.conf"
  } >> "${OSSEC}/etc/ossec.conf"
fi

# ------------------------------------------------------------
# 4. Enrolamiento: authd escucha 1515; comunicación de agentes 1514.
#    En 4.x el manager trae <auth> habilitado. Aseguramos el servicio y el firewall.
# ------------------------------------------------------------
if command -v ufw >/dev/null 2>&1; then
  ufw allow 1514/tcp || true
  ufw allow 1515/tcp || true
fi
systemctl restart wazuh-manager

# ------------------------------------------------------------
# 5. Docker + servicios ARGOS (docker compose --profile real).
#    El bridge montea ${OSSEC}/logs/alerts:ro y publica a events:normalized.
# ------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

# Asegurar el dir de alertas que el bridge montea (existe tras el primer evento,
# pero lo creamos para que el mount no falle en frío).
mkdir -p "${OSSEC}/logs/alerts"

echo "[core] docker compose --profile real up -d (desde ${REPO})"
( cd "${REPO}" && docker compose --profile real up -d )

# ------------------------------------------------------------
# 6. Smoke
# ------------------------------------------------------------
echo "[core] agentes registrados:"
"${OSSEC}/bin/agent_control" -l || true
echo "[core] === provision OK. Validar: agent_control -l muestra los agentes Active ==="
