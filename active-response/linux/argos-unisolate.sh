#!/bin/bash
# ARGOS active-response (Linux) — revierte el aislamiento de argos-isolate: borra
# solo las reglas iptables etiquetadas "argos-isolate". Idempotente.
# Lo invoca el SOAR con el comando "argos-unisolate". Requiere iptables (root).
set -u

TAG="argos-isolate"
cat >/dev/null   # consume el JSON de stdin (no se necesita acá)

for chain in INPUT OUTPUT; do
  while num=$(iptables -L "$chain" --line-numbers -n 2>/dev/null | awk -v t="$TAG" '$0 ~ t {print $1; exit}'); [ -n "$num" ]; do
    iptables -D "$chain" "$num" 2>/dev/null || break
  done
done
echo "argos-unisolate: reglas de aislamiento removidas"
