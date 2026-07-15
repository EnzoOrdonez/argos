#!/usr/bin/env python3
"""
generator.py — Generador de canary files (honeypot files) para Layer 3
del proyecto ARGOS.

Owner: P3 — Angeles Castillo

Qué hace:
  - Lee config.yaml (hosts, rutas absolutas, tipo de SO).
  - Crea archivos dummy con contenido realista (no vacío) en cada ruta
    declarada.
  - Asigna timestamps (mtime/atime) realistas, entre 60 y 180 días atrás
    (configurable en config.yaml).
  - Evita tocar rutas fuera de la carpeta sandbox cuando se ejecuta con
    --local-sandbox (modo de desarrollo seguro).

Qué NO hace:
  - No se conecta por SSH/WinRM a hosts reales — eso requiere que P4
    tenga el laboratorio levantado. El parámetro --host solo selecciona
    la entrada de config.yaml a usar; el despliegue remoto real está
    fuera de este script (pendiente de confirmar con P4 cómo se
    materializa el acceso a los hosts víctima).

Uso:
    python generator.py --config config.yaml --host victim-windows-01 --local-sandbox
"""
from __future__ import annotations

import argparse
import csv
import io
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

import yaml

try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover
    Workbook = None  # type: ignore


@dataclass
class CanarySpec:
    host: str
    os_type: str
    path: str  # ruta absoluta tal como vendrá en config.yaml (puede ser windows o posix)


def load_config(config_path: Path) -> dict:
    with config_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_host_entry(config: dict, host: str) -> dict:
    for entry in config["hosts"]:
        if entry["name"] == host:
            return entry
    raise ValueError(f"Host '{host}' no encontrado en config.yaml")


def _is_windows_path(raw_path: str) -> bool:
    return "\\" in raw_path or (len(raw_path) > 1 and raw_path[1] == ":")


def resolve_output_path(raw_path: str, local_sandbox_root: Path | None) -> Path:
    """
    Si local_sandbox_root está definido (modo desarrollo), reescribe la ruta
    absoluta del canary para que viva DENTRO de la carpeta sandbox, evitando
    tocar rutas reales del sistema durante pruebas locales.

    En despliegue real contra un host del lab (sin --local-sandbox), la ruta
    se usa tal cual está en config.yaml — pero ese flujo de despliegue queda
    pendiente de confirmar con P4 (requiere acceso remoto al host víctima).
    """
    if local_sandbox_root is None:
        # Modo "real": se asume que este script corre en el host destino.
        if _is_windows_path(raw_path):
            return Path(PureWindowsPath(raw_path).as_posix().replace(":", ""))
        return Path(raw_path)

    # Modo sandbox: aplanar la ruta original como subcarpeta dentro del sandbox,
    # preservando la estructura para que sea reconocible, sin salir nunca de
    # local_sandbox_root.
    if _is_windows_path(raw_path):
        parts = PureWindowsPath(raw_path).parts
    else:
        parts = PurePosixPath(raw_path).parts

    # Quitar el separador de unidad/raíz (C:\\, /) para que no se interprete
    # como ruta absoluta al unir con el sandbox.
    safe_parts = [p for p in parts if p not in ("\\", "/", "C:\\", "C:")]
    target = local_sandbox_root.joinpath(*safe_parts)

    resolved_sandbox = local_sandbox_root.resolve()
    resolved_target = target.resolve()
    if resolved_sandbox not in resolved_target.parents and resolved_target != resolved_sandbox:
        raise RuntimeError(
            f"Ruta resuelta '{resolved_target}' queda fuera del sandbox "
            f"'{resolved_sandbox}' — abortando para evitar tocar rutas reales."
        )
    return target


def realistic_mtime(min_days: int, max_days: int) -> float:
    days_ago = random.randint(min_days, max_days)
    return time.time() - (days_ago * 86400)


def write_passwords_txt(path: Path) -> None:
    content = (
        "# credentials backup - DO NOT SHARE\n"
        "admin_panel:admin:P@ssw0rd2024!\n"
        "db_readonly:svc_report:R3p0rt_Only_99\n"
        "vpn_gateway:jsmith:Tr0ub4dor&3\n"
        "backup_share:backupsvc:B@ckup_Service_2024\n"
    )
    path.write_text(content, encoding="utf-8")


def write_db_backup_sql(path: Path) -> None:
    content = (
        "-- Dump dummy generado por ARGOS canary-generator (P3)\n"
        "-- NO es un backup real. Contenido sintético para honeypot.\n\n"
        "CREATE TABLE IF NOT EXISTS customers (\n"
        "    id INTEGER PRIMARY KEY,\n"
        "    full_name VARCHAR(120),\n"
        "    email VARCHAR(120),\n"
        "    account_balance DECIMAL(12,2)\n"
        ");\n\n"
        "INSERT INTO customers (id, full_name, email, account_balance) VALUES\n"
        "(1, 'Maria Gonzales', 'mgonzales@example-corp.test', 154320.50),\n"
        "(2, 'Carlos Rivera', 'crivera@example-corp.test', 89210.00),\n"
        "(3, 'Lucia Fernandez', 'lfernandez@example-corp.test', 234500.75);\n"
    )
    path.write_text(content, encoding="utf-8")


def write_accounts_admin_csv(path: Path) -> None:
    rows = [
        ["username", "role", "last_login", "department"],
        ["admin.root", "superadmin", "2025-11-02", "IT"],
        ["svc_backup", "service_account", "2025-12-15", "Infrastructure"],
        ["j.perez", "admin", "2025-10-28", "Finance"],
    ]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")


def write_financials_xlsx(path: Path) -> None:
    if Workbook is None:
        raise RuntimeError(
            "openpyxl no está instalado. Ejecuta: pip install -r deception/requirements.txt"
        )
    wb = Workbook()
    ws = wb.active
    ws.title = "Q4 2025"
    ws.append(["Mes", "Ingresos", "Gastos", "Utilidad Neta"])
    ws.append(["Octubre", 482000, 310500, 171500])
    ws.append(["Noviembre", 501200, 322100, 179100])
    ws.append(["Diciembre", 558900, 340800, 218100])
    wb.save(str(path))


WRITERS = {
    "passwords.txt": write_passwords_txt,
    "db_backup.sql": write_db_backup_sql,
    "accounts_admin.csv": write_accounts_admin_csv,
    "financials_Q4_2025.xlsx": write_financials_xlsx,
}


def generate_canary(raw_path: str, local_sandbox_root: Path | None, ts_range: dict) -> Path:
    output_path = resolve_output_path(raw_path, local_sandbox_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    filename = (PureWindowsPath(raw_path).name if _is_windows_path(raw_path)
                else PurePosixPath(raw_path).name)

    writer = WRITERS.get(filename)
    if writer is None:
        # Contenido genérico realista para cualquier otro nombre de canary
        # declarado en config.yaml que no tenga writer dedicado.
        output_path.write_text(
            f"# Archivo generado por ARGOS canary-generator\n"
            f"# Nombre original: {filename}\n"
            f"Contenido dummy de placeholder para honeypot.\n",
            encoding="utf-8",
        )
    else:
        writer(output_path)

    mtime = realistic_mtime(ts_range["min"], ts_range["max"])
    import os

    os.utime(output_path, (mtime, mtime))
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera canary files para ARGOS Layer 3")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--host", required=True, help="Nombre del host en config.yaml")
    parser.add_argument(
        "--local-sandbox",
        action="store_true",
        help="Modo desarrollo: confina la salida a local_sandbox_root del config.yaml, "
        "nunca toca rutas reales del sistema.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    host_entry = get_host_entry(config, args.host)
    ts_range = config.get("timestamp_range_days", {"min": 60, "max": 180})

    sandbox_root = None
    if args.local_sandbox:
        sandbox_root = (args.config.parent / config["local_sandbox_root"]).resolve()
        sandbox_root.mkdir(parents=True, exist_ok=True)
        print(f"[*] Modo sandbox local — todo se escribirá dentro de: {sandbox_root}")
    else:
        print(
            "[!] Modo real seleccionado (sin --local-sandbox). Este script asume que "
            "corre directamente en el host destino. El despliegue remoto contra "
            "hosts del laboratorio está PENDIENTE DE CONFIRMAR CON P4."
        )

    created = []
    for raw_path in host_entry["canary_paths"]:
        out = generate_canary(raw_path, sandbox_root, ts_range)
        created.append(out)
        print(f"[+] Canary creado: {out}")

    print(f"\n[*] Total canaries creados para '{args.host}': {len(created)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
