#!/bin/bash
# ARGOS active-response (Linux) — revierte el throttle: mata el cpulimit del PID y
# restaura prioridad CPU/IO. param: pid. Requiere jq.
set -u

INPUT=$(cat)
PID=$(printf '%s' "$INPUT" | jq -r '.parameters.alert.data.argos.pid // empty' 2>/dev/null)
if [ -z "$PID" ]; then
  echo "argos-unthrottle: sin pid -> no-op" >&2
  exit 0
fi

pkill -f "cpulimit -p $PID" 2>/dev/null || true
renice 0 -p "$PID" 2>/dev/null || true
if command -v ionice >/dev/null 2>&1; then
  ionice -c2 -n4 -p "$PID" 2>/dev/null || true
fi
echo "argos-unthrottle: pid $PID restaurado"
