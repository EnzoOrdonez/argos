#!/bin/bash
# ARGOS active-response (Linux) — aísla la víctima por red con iptables, PERO
# mantiene vivo el canal con el Wazuh manager (puertos 1514/1515). Sin esa
# whitelist el manager no podría revertir ni confirmar: auto-brick.
#
# Interfaz Wazuh AR: recibe el JSON de wazuh-execd por stdin (.command = add|delete).
# Lo invoca el SOAR (WazuhActiveResponseExecutor) con el comando "argos-isolate".
# MANAGER_IP: de $ARGOS_MANAGER_IP o /var/ossec/etc/argos-ar.conf. Requiere jq + iptables (root).
set -u

TAG="argos-isolate"
INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | jq -r '.command // "add"' 2>/dev/null || echo add)

MANAGER_IP="${ARGOS_MANAGER_IP:-}"
if [ -z "$MANAGER_IP" ] && [ -r /var/ossec/etc/argos-ar.conf ]; then
  MANAGER_IP=$(sed -n 's/^MANAGER_IP=//p' /var/ossec/etc/argos-ar.conf | head -n1)
fi

isolate() {
  if [ -z "$MANAGER_IP" ]; then
    echo "$TAG: MANAGER_IP sin configurar -> abort (evita auto-brick)" >&2
    exit 1
  fi
  # --- WHITELIST PRIMERO: el canal agente<->manager queda vivo (1514/1515) ---
  iptables -I INPUT  -i lo -j ACCEPT -m comment --comment "$TAG"
  iptables -I INPUT  -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT -m comment --comment "$TAG"
  iptables -I INPUT  -p tcp -s "$MANAGER_IP" -m multiport --sports 1514,1515 -j ACCEPT -m comment --comment "$TAG"
  iptables -I OUTPUT -p tcp -d "$MANAGER_IP" -m multiport --dports 1514,1515 -j ACCEPT -m comment --comment "$TAG"
  # --- BLOCK-ALL DESPUÉS: aísla el resto de la red ---
  iptables -A INPUT  -j DROP -m comment --comment "$TAG"
  iptables -A OUTPUT -j DROP -m comment --comment "$TAG"
  echo "$TAG: victima aislada; manager $MANAGER_IP en whitelist (1514/1515)"
}

unisolate() {
  # Borra solo las reglas etiquetadas argos-isolate (idempotente).
  for chain in INPUT OUTPUT; do
    while num=$(iptables -L "$chain" --line-numbers -n 2>/dev/null | awk -v t="$TAG" '$0 ~ t {print $1; exit}'); [ -n "$num" ]; do
      iptables -D "$chain" "$num" 2>/dev/null || break
    done
  done
  echo "$TAG: aislamiento revertido"
}

case "$COMMAND" in
  delete) unisolate ;;   # Wazuh timeout -> revierte solo
  *)      isolate ;;     # add (o invocación directa del SOAR)
esac
