#!/bin/bash
# ARGOS active-response (Linux) — limita CPU/IO del proceso ofensor para acotar el
# daño durante la espera HITL (ADR-0006 Sit.B). renice + ionice + cpulimit si está.
# params (alert.data.argos): pid, cpu_percent_limit. Requiere jq; cpulimit opcional.
set -u

INPUT=$(cat)
PID=$(printf '%s' "$INPUT" | jq -r '.parameters.alert.data.argos.pid // empty' 2>/dev/null)
LIMIT=$(printf '%s' "$INPUT" | jq -r '.parameters.alert.data.argos.cpu_percent_limit // 10' 2>/dev/null)

if [ -z "$PID" ]; then
  echo "argos-throttle: sin pid en la accion -> nada que limitar" >&2
  exit 0
fi

renice +19 -p "$PID" 2>/dev/null || true
if command -v ionice >/dev/null 2>&1; then
  ionice -c3 -p "$PID" 2>/dev/null || true
fi
if command -v cpulimit >/dev/null 2>&1; then
  cpulimit -p "$PID" -l "$LIMIT" -b 2>/dev/null || true
fi
echo "argos-throttle: pid $PID limitado a ${LIMIT}% CPU (renice+ionice+cpulimit)"
