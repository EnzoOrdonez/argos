#!/usr/bin/env python3
"""
uc01_lockbit_like.py — Simulador controlado UC-01 (LockBit-like).

Owner: P3 — Angeles Castillo

Qué hace (TODO dentro de una carpeta sandbox, nunca fuera):
  1. Crea un set de archivos dummy en una carpeta sandbox aislada.
  2. "Enumera" los archivos (genera el patrón de discovery T1083 que la
     regla file_enumeration_powershell.yml busca, vía un proceso real de
     PowerShell si corre en Windows, o un log sintético equivalente si
     corre en Linux/macOS — ver --emit-synthetic-log).
  3. Renombra los archivos dummy a extensión .locked (NO cifra nada;
     es solo un rename, controlado y reversible).
  4. Deja una "nota de rescate" dummy (ransom_note_drop.yml).

Qué NO hace:
  - No cifra contenido real. Los archivos nunca contienen información
    sensible real ni se tocan archivos fuera del sandbox.
  - No ejecuta vssadmin/wmic reales contra shadow copies del sistema.
    Para validar esas reglas (T1490), usar Atomic Red Team directamente
    en el host de laboratorio (fuera de este script) — PENDIENTE DE
    CONFIRMAR CON P4 el acceso al host víctima.
  - No se conecta a ningún host remoto.

Guardrail de seguridad:
  - El script SIEMPRE valida que la carpeta destino esté dentro de
    --sandbox-root antes de crear, renombrar o borrar nada. Si la ruta
    resuelta queda fuera, aborta con error.

Uso:
    python uc01_lockbit_like.py --sandbox-root ./sandbox-uc01 --run
    python uc01_lockbit_like.py --sandbox-root ./sandbox-uc01 --cleanup
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

DUMMY_FILES = [
    "report_2025.docx",
    "invoice_october.pdf",
    "project_notes.txt",
    "presupuesto_anual.xlsx",
]

RANSOM_NOTE_NAMES = ["README_HOW_TO_DECRYPT.txt"]


def _assert_inside_sandbox(target: Path, sandbox_root: Path) -> None:
    resolved_target = target.resolve()
    resolved_sandbox = sandbox_root.resolve()
    if resolved_sandbox != resolved_target and resolved_sandbox not in resolved_target.parents:
        raise RuntimeError(
            f"Guardrail de seguridad: '{resolved_target}' está fuera de la carpeta "
            f"sandbox '{resolved_sandbox}'. Abortando para no tocar nada real."
        )


def setup_dummy_files(sandbox_root: Path) -> list[Path]:
    _assert_inside_sandbox(sandbox_root, sandbox_root)
    sandbox_root.mkdir(parents=True, exist_ok=True)
    created = []
    for name in DUMMY_FILES:
        p = sandbox_root / name
        _assert_inside_sandbox(p, sandbox_root)
        p.write_text(
            f"Contenido dummy de laboratorio ARGOS — archivo: {name}\n"
            "Este NO es un archivo real. Generado por uc01_lockbit_like.py (P3).\n"
        )
        created.append(p)
    return created


def emit_discovery_log_line(sandbox_root: Path, synthetic: bool) -> None:
    """
    Genera el evento que dispara discovery/file_enumeration_powershell.yml.
    En Windows real, esto se haría ejecutando PowerShell de verdad
    (Get-ChildItem -Recurse) sobre el sandbox. En este entorno (Linux),
    se escribe un log sintético equivalente para pruebas offline, y se
    marca explícitamente como tal.
    """
    log_path = sandbox_root / "_simulated_events.log"
    if synthetic:
        line = (
            f'[SYNTHETIC] Image=C:\\Windows\\System32\\powershell.exe '
            f'CommandLine="powershell.exe Get-ChildItem -Recurse {sandbox_root}" '
            f"User=LAB\\victim-user Hostname=<VICTIM_LAB_IP>\n"
        )
    else:
        import subprocess

        result = subprocess.run(
            ["powershell", "-Command", f"Get-ChildItem -Recurse '{sandbox_root}'"],
            capture_output=True,
            text=True,
        )
        line = f"[REAL] PowerShell stdout: {result.stdout[:200]}\n"

    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line)
    print(f"[+] Evento de discovery registrado en {log_path}")


def rename_to_locked(files: list[Path], sandbox_root: Path) -> list[Path]:
    renamed = []
    for f in files:
        _assert_inside_sandbox(f, sandbox_root)
        new_path = f.with_suffix(f.suffix + ".locked")
        _assert_inside_sandbox(new_path, sandbox_root)
        f.rename(new_path)
        renamed.append(new_path)
        print(f"[+] Renombrado (NO cifrado real): {f.name} -> {new_path.name}")
    return renamed


def drop_ransom_note(sandbox_root: Path) -> Path:
    note_path = sandbox_root / RANSOM_NOTE_NAMES[0]
    _assert_inside_sandbox(note_path, sandbox_root)
    note_path.write_text(
        "ESTE ES UN ARCHIVO DE LABORATORIO ARGOS — NO ES UNA NOTA DE RESCATE REAL.\n"
        "Generado para validar la regla detection/sigma-rules/ransomware/ransom_note_drop.yml\n"
        f"Timestamp: {time.ctime()}\n"
    )
    print(f"[+] Nota de rescate dummy creada: {note_path}")
    return note_path


def cleanup(sandbox_root: Path) -> None:
    _assert_inside_sandbox(sandbox_root, sandbox_root)
    if sandbox_root.exists():
        shutil.rmtree(sandbox_root)
        print(f"[*] Sandbox limpiado: {sandbox_root}")
    else:
        print(f"[*] Nada que limpiar, {sandbox_root} no existe.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulador controlado UC-01 (LockBit-like) — solo sandbox, reversible."
    )
    parser.add_argument("--sandbox-root", required=True, type=Path)
    parser.add_argument("--run", action="store_true", help="Ejecuta el escenario completo")
    parser.add_argument("--cleanup", action="store_true", help="Borra la carpeta sandbox")
    parser.add_argument(
        "--emit-synthetic-log",
        action="store_true",
        default=True,
        help="Genera log sintético de discovery en vez de ejecutar PowerShell real "
        "(usar real solo si este script corre en un host Windows del lab)",
    )
    args = parser.parse_args()

    if not args.run and not args.cleanup:
        parser.error("Especifica --run o --cleanup")

    sandbox_root = args.sandbox_root.resolve()

    if args.cleanup:
        cleanup(sandbox_root)
        return 0

    print(f"[*] UC-01 LockBit-like — sandbox: {sandbox_root}")
    print("[*] Advertencia: este script SOLO opera dentro del sandbox. No cifra archivos reales.")

    dummy_files = setup_dummy_files(sandbox_root)
    emit_discovery_log_line(sandbox_root, synthetic=args.emit_synthetic_log)
    rename_to_locked(dummy_files, sandbox_root)
    drop_ransom_note(sandbox_root)

    print(f"\n[*] Escenario UC-01 completo. {len(dummy_files)} archivos dummy procesados.")
    print("[*] Cero archivos reales fueron tocados — todo confinado al sandbox.")
    print(f"[*] Para limpiar: python uc01_lockbit_like.py --sandbox-root {sandbox_root} --cleanup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
