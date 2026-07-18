#!/bin/bash
# ARGOS active-response (Linux) — revierte el block-ip de argos-block-ip: borra la
# regla iptables que dropea la IP atacante. Idempotente. Lo invoca el SOAR con el
# comando "argos-unblock-ip" (revert del botón "Revert if false alarm", ADR-0003).
#
# La IP viene en .parameters.alert.data.argos.src_ip (la puebla el SOAR); si no
# viene, borra TODAS las reglas etiquetadas argos-block-ip. Requiere jq + iptables (root).
set -u

TAG="argos-block-ip"
INPUT=$(cat)
SRC_IP=$(printf '%s' "$INPUT" \
  | jq -r '.parameters.alert.data.argos.src_ip // .parameters.alert.data.srcip // .srcip // empty' \
  2>/dev/null || echo "")

if [ -z "$SRC_IP" ]; then
  while num=$(iptables -L INPUT --line-numbers -n 2>/dev/null | awk -v t="$TAG" '$0 ~ t {print $1; exit}'); [ -n "$num" ]; do
    iptables -D INPUT "$num" 2>/dev/null || break
  done
else
  while iptables -C INPUT -s "$SRC_IP" -j DROP -m comment --comment "$TAG:$SRC_IP" 2>/dev/null; do
    iptables -D INPUT -s "$SRC_IP" -j DROP -m comment --comment "$TAG:$SRC_IP" 2>/dev/null || break
  done
fi
echo "argos-unblock-ip: bloqueo de ${SRC_IP:-todas las IP del tag} removido"
