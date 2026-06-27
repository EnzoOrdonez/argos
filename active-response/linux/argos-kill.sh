#!/bin/bash
# ARGOS active-response (Linux) — mata el proceso ofensor (SIGKILL). param: pid.
# Reversible en el sentido de ADR-0012 §7.3 (el servicio se relanza). Requiere jq.
set -u

INPUT=$(cat)
PID=$(printf '%s' "$INPUT" | jq -r '.parameters.alert.data.argos.pid // empty' 2>/dev/null)
if [ -z "$PID" ]; then
  echo "argos-kill: sin pid en la accion -> no-op" >&2
  exit 0
fi

if kill -9 "$PID" 2>/dev/null; then
  echo "argos-kill: pid $PID terminado (SIGKILL)"
else
  echo "argos-kill: no pude matar pid $PID (ya no existe?)" >&2
fi
