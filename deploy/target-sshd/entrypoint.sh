#!/usr/bin/env bash
# Enrola el agente Wazuh al manager (WAZUH_MANAGER) y arranca agente + sshd en foreground.
# Host de prueba descartable — ver deploy/target-sshd/README.md.
set -euo pipefail

if [ -n "${WAZUH_MANAGER:-}" ]; then
  # Fija la dirección del manager en ossec.conf y enrola vía authd (puerto 1515).
  sed -i "s|<address>.*</address>|<address>${WAZUH_MANAGER}</address>|" \
    /var/ossec/etc/ossec.conf || true
  /var/ossec/bin/agent-auth -m "${WAZUH_MANAGER}" \
    || echo "[target] agent-auth falló; revisar que el manager esté arriba y 1515 accesible"
  /var/ossec/bin/wazuh-control start || echo "[target] wazuh-control start falló"
else
  echo "[target] WAZUH_MANAGER no seteado: el agente NO se enrola (solo sshd)."
fi

# sshd en foreground (mantiene el contenedor vivo; -e loguea a stderr, -D no forkea).
exec /usr/sbin/sshd -D -e
