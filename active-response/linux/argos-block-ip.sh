#!/bin/bash
# ARGOS active-response (Linux) — block-ip QUIRÚRGICO: dropea SOLO la IP atacante
# con iptables, sin aislar el host entero (a diferencia de argos-isolate). Para
# vectores con IP de origen: fuerza bruta SSH / T1110 (HU-8). El host sigue
# operativo; únicamente el atacante queda sin ruta hacia él.
#
# Interfaz Wazuh AR: recibe el JSON de wazuh-execd por stdin (.command = add|delete).
# Lo invoca el SOAR (WazuhActiveResponseExecutor) con el comando "argos-block-ip".
# La IP viene en .parameters.alert.data.argos.src_ip (la puebla el SOAR); fallback a
# la srcip nativa de la alerta. Requiere jq + iptables (root).
set -u

TAG="argos-block-ip"
INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | jq -r '.command // "add"' 2>/dev/null || echo add)
SRC_IP=$(printf '%s' "$INPUT" \
  | jq -r '.parameters.alert.data.argos.src_ip // .parameters.alert.data.srcip // .srcip // empty' \
  2>/dev/null || echo "")

block() {
  if [ -z "$SRC_IP" ]; then
    echo "$TAG: src_ip ausente en el alert -> abort (no hay a quién bloquear)" >&2
    exit 1
  fi
  # Idempotente: no duplica la regla si ya existe.
  if iptables -C INPUT -s "$SRC_IP" -j DROP -m comment --comment "$TAG:$SRC_IP" 2>/dev/null; then
    echo "$TAG: IP $SRC_IP ya estaba bloqueada (no-op)"
    return 0
  fi
  iptables -I INPUT -s "$SRC_IP" -j DROP -m comment --comment "$TAG:$SRC_IP"
  echo "$TAG: IP $SRC_IP bloqueada (INPUT DROP)"
}

unblock() {
  # Borra las reglas etiquetadas para esta IP (o todas las del tag si no vino IP).
  if [ -z "$SRC_IP" ]; then
    while num=$(iptables -L INPUT --line-numbers -n 2>/dev/null | awk -v t="$TAG" '$0 ~ t {print $1; exit}'); [ -n "$num" ]; do
      iptables -D INPUT "$num" 2>/dev/null || break
    done
  else
    while iptables -C INPUT -s "$SRC_IP" -j DROP -m comment --comment "$TAG:$SRC_IP" 2>/dev/null; do
      iptables -D INPUT -s "$SRC_IP" -j DROP -m comment --comment "$TAG:$SRC_IP" 2>/dev/null || break
    done
  fi
  echo "$TAG: bloqueo de ${SRC_IP:-todas las IP del tag} revertido"
}

case "$COMMAND" in
  delete) unblock ;;   # Wazuh timeout -> revierte solo
  *)      block ;;     # add (o invocación directa del SOAR)
esac
