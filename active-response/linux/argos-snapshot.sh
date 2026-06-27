#!/bin/bash
# ARGOS active-response (Linux) — snapshot demo-safe: tar.gz del dir protegido.
# NO es un VSS/dd real (ADR-0012 §2.6): es evidencia + punto de recuperación liviano.
# Origen: $ARGOS_SNAPSHOT_DIR (default canaries). Destino: $ARGOS_SNAPSHOT_DEST.
set -u

cat >/dev/null   # consume el JSON de stdin
SRC="${ARGOS_SNAPSHOT_DIR:-/home/victim/Documents}"
DEST="${ARGOS_SNAPSHOT_DEST:-/var/backups/argos-snapshots}"
mkdir -p "$DEST" 2>/dev/null || true
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$DEST/argos-snapshot-$STAMP.tar.gz"

if tar -czf "$OUT" "$SRC" 2>/dev/null; then
  echo "argos-snapshot: $SRC -> $OUT"
else
  echo "argos-snapshot: fallo al crear el tar de $SRC" >&2
  exit 1
fi
