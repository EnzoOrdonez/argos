#!/usr/bin/env bash
#
# deception/integrity-check/verify_canaries.sh
#
# Verifica que todos los canary files declarados en config.yaml existan
# en el host. Si falta alguno, lo reporta y opcionalmente lo recrea
# llamando a generator.py.
#
# Uso manual (para demo):
#   bash verify_canaries.sh --config ../canary-generator/config.yaml --host victim-windows-01
#
# Cron (opcional, NO requerido para la demo):
#   0 * * * * /path/to/verify_canaries.sh --config /path/config.yaml --host victim-windows-01 >> /var/log/argos-canary-check.log 2>&1
#
# ⚠️ Este script asume que corre en el mismo host donde viven los
# canaries (o contra el sandbox local). Verificación remota contra hosts
# del laboratorio vía SSH queda PENDIENTE DE CONFIRMAR CON P4.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GENERATOR_DIR="$SCRIPT_DIR/../canary-generator"
CONFIG_PATH=""
HOST_NAME=""
LOCAL_SANDBOX=false
RECREATE=false

usage() {
    echo "Uso: $0 --config <ruta/config.yaml> --host <nombre_host> [--local-sandbox] [--recreate]"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)
            CONFIG_PATH="$2"; shift 2 ;;
        --host)
            HOST_NAME="$2"; shift 2 ;;
        --local-sandbox)
            LOCAL_SANDBOX=true; shift ;;
        --recreate)
            RECREATE=true; shift ;;
        *)
            echo "Argumento desconocido: $1"; usage ;;
    esac
done

if [[ -z "$CONFIG_PATH" || -z "$HOST_NAME" ]]; then
    usage
fi

echo "[*] Verificando integridad de canaries para host: $HOST_NAME"
echo "[*] Config: $CONFIG_PATH"

# Extraer rutas del host con un one-liner Python (evita depender de yq/jq externos)
PATHS=$(python3 - "$CONFIG_PATH" "$HOST_NAME" <<'PYEOF'
import sys
import yaml

config_path, host_name = sys.argv[1], sys.argv[2]
with open(config_path, encoding="utf-8") as fh:
    config = yaml.safe_load(fh)

for entry in config["hosts"]:
    if entry["name"] == host_name:
        for p in entry["canary_paths"]:
            print(p)
        break
PYEOF
)

if [[ -z "$PATHS" ]]; then
    echo "[!] No se encontraron rutas de canary para el host '$HOST_NAME' en $CONFIG_PATH"
    exit 1
fi

MISSING=0
TOTAL=0

while IFS= read -r raw_path; do
    [[ -z "$raw_path" ]] && continue
    TOTAL=$((TOTAL + 1))

    # En modo sandbox local, las rutas reales viven bajo
    # canary-generator/sandbox-output/ (mismo aplanado que usa generator.py)
    if [[ "$LOCAL_SANDBOX" == true ]]; then
        check_path="$GENERATOR_DIR/sandbox-output"
    else
        check_path="$raw_path"
    fi

    echo "[*] Verificando: $raw_path"

    if [[ "$LOCAL_SANDBOX" == true ]]; then
        # En modo sandbox no resolvemos ruta por ruta (eso vive en generator.py);
        # solo confirmamos que la carpeta sandbox tenga *algo* generado.
        if [[ ! -d "$check_path" ]]; then
            echo "    [MISSING] Carpeta sandbox no existe todavía: $check_path"
            MISSING=$((MISSING + 1))
        fi
    else
        if [[ ! -f "$check_path" ]]; then
            echo "    [MISSING] Canary no encontrado: $check_path"
            MISSING=$((MISSING + 1))
        else
            echo "    [OK] Canary presente."
        fi
    fi
done <<< "$PATHS"

echo ""
echo "[*] Resultado: $((TOTAL - MISSING))/$TOTAL canaries presentes."

if [[ "$MISSING" -gt 0 ]]; then
    echo "[!] Se detectaron $MISSING canary(s) faltante(s)."
    if [[ "$RECREATE" == true ]]; then
        echo "[*] --recreate activado: regenerando canaries con generator.py ..."
        SANDBOX_FLAG=""
        [[ "$LOCAL_SANDBOX" == true ]] && SANDBOX_FLAG="--local-sandbox"
        python3 "$GENERATOR_DIR/generator.py" --config "$CONFIG_PATH" --host "$HOST_NAME" $SANDBOX_FLAG
    else
        echo "[*] Ejecuta con --recreate para regenerarlos automáticamente,"
        echo "    o corre manualmente: python3 $GENERATOR_DIR/generator.py --config $CONFIG_PATH --host $HOST_NAME"
        exit 2
    fi
else
    echo "[*] Todo correcto. Sin acción requerida."
fi
