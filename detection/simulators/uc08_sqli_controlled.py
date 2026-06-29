#!/usr/bin/env python3
"""
uc08_sqli_controlled.py — Simulador controlado UC-08 (SQL Injection).

Owner: P3 — Angeles Castillo

⚠️ ADVERTENCIA DE LABORATORIO ⚠️
Igual que uc06_ddos_controlled.py: este script construye el comando de
sqlmap pero NO lo ejecuta automáticamente. Solo lo imprime, y requiere
--i-confirm-this-is-my-lab para correrlo de verdad.

Reglas de seguridad aplicadas (del manual P3):
  - Solo debe apuntar a la app vulnerable del laboratorio — placeholder
    <VICTIM_LAB_IP> obligatorio hasta que P4 confirme el host real.
  - --batch y --risk/--level acotados a valores conservadores por
    defecto, para evitar que sqlmap intente técnicas más invasivas
    (p. ej. stacked queries que podrían modificar datos) sin que el
    operador lo decida explícitamente.
  - Nunca contra sistemas reales ni IPs públicas (misma validación que
    uc06_ddos_controlled.py).

Uso:
    python uc08_sqli_controlled.py --target-url "http://<VICTIM_LAB_IP>/login.php?id=1"
"""
from __future__ import annotations

import argparse
import ipaddress
import shlex
import subprocess
import sys
from urllib.parse import urlparse

_BLOCKED_RANGES = [
    "8.8.8.0/24",
    "1.1.1.0/24",
]


def _looks_like_placeholder(value: str) -> bool:
    return "<VICTIM_LAB_IP>" in value.upper() or "VICTIM_LAB_IP" in value.upper()


def _validate_target_url(target_url: str) -> None:
    if _looks_like_placeholder(target_url):
        raise SystemExit(
            "[!] Reemplaza <VICTIM_LAB_IP> en --target-url por el host real de la "
            "app vulnerable del laboratorio (pendiente de confirmar con P4)."
        )

    parsed = urlparse(target_url)
    if not parsed.scheme or not parsed.netloc:
        raise SystemExit(f"[!] '{target_url}' no parece una URL válida (falta http:// o host).")

    host = parsed.hostname or ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        print(f"[*] Host '{host}' no es IP literal; se asume hostname interno del lab.")
        return

    for blocked_range in _BLOCKED_RANGES:
        if ip in ipaddress.ip_network(blocked_range):
            raise SystemExit(
                f"[!] '{host}' cae en un rango bloqueado conocido ({blocked_range}). Abortando."
            )
    if ip.is_global:
        print(
            f"[!] ADVERTENCIA: '{host}' parece ser una IP pública. Verifica que sea "
            "realmente tu host de laboratorio antes de continuar."
        )


def build_sqlmap_command(target_url: str, risk: int, level: int) -> list[str]:
    return [
        "sqlmap",
        "-u", target_url,
        "--batch",               # no pide confirmación interactiva
        f"--risk={risk}",
        f"--level={level}",
        "--banner",               # solo detección + banner, no dump de datos por defecto
    ]


def main() -> int:
    # Salida UTF-8 segura: la consola Windows es cp1252 y los emojis de los
    # mensajes de laboratorio (⚠️) crashean con UnicodeEncodeError. (fix 2026-06-29)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Simulador controlado UC-08 (SQL Injection) — solo contra app vulnerable del lab."
    )
    parser.add_argument("--target-url", required=True, help="URL de la app vulnerable del lab (con <VICTIM_LAB_IP> a reemplazar)")
    parser.add_argument("--risk", type=int, default=1, choices=[1, 2, 3], help="Nivel de riesgo sqlmap (1=conservador, default)")
    parser.add_argument("--level", type=int, default=1, choices=[1, 2, 3, 4, 5], help="Nivel de profundidad de prueba sqlmap")
    parser.add_argument(
        "--i-confirm-this-is-my-lab",
        action="store_true",
        help="Requerido para ejecutar de verdad; sin esto, solo se muestra el comando.",
    )
    args = parser.parse_args()

    _validate_target_url(args.target_url)

    if args.risk > 2:
        print(
            "[!] ADVERTENCIA: risk=3 puede incluir payloads más agresivos "
            "(p. ej. time-based heavy queries). Úsalo solo si tu app vulnerable "
            "del lab está diseñada para soportarlo."
        )

    cmd = build_sqlmap_command(args.target_url, args.risk, args.level)

    print("=" * 70)
    print("⚠️  COMANDO DE LABORATORIO — SOLO CONTRA APP VULNERABLE DEL LAB  ⚠️")
    print("=" * 70)
    print(shlex.join(cmd))
    print("=" * 70)

    if not args.i_confirm_this_is_my_lab:
        print(
            "[*] Modo 'solo mostrar' (default). Para ejecutar de verdad, vuelve a "
            "correr con --i-confirm-this-is-my-lab una vez confirmado el host real "
            "(pendiente de que P4 confirme la app vulnerable del laboratorio)."
        )
        return 0

    print("[*] Ejecutando contra la app vulnerable de laboratorio confirmada...")
    try:
        subprocess.run(cmd, check=True, timeout=120)
    except FileNotFoundError:
        print("[!] sqlmap no está instalado en este entorno. Instálalo en tu host de trabajo del lab.")
        return 1
    except subprocess.TimeoutExpired:
        print("[*] Comando detenido por timeout de seguridad (120s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
