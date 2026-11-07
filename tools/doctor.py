#!/usr/bin/env python3
"""Diagnostic d'une installation TileForge.

    python tools/doctor.py
    python tools/doctor.py --cores ./cores --system-dir ./system

Vérifie Python, les dépendances, les archives 7z, les cœurs, les BIOS et le
serveur MCP. Ne télécharge rien.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def check_python() -> bool:
    ok = sys.version_info >= (3, 10)
    print(f"Python {sys.version.split()[0]} ({sys.executable}) "
          f"{'OK' if ok else 'TROP ANCIEN'}")
    return ok


def check_dependencies() -> bool:
    required = {"numpy": "numpy", "PIL": "Pillow"}
    optional = {"PySide6": "interface graphique", "py7zr": "archives 7z"}
    ok = True
    for module, label in required.items():
        present = has_module(module)
        print(f"  {'OK ' if present else 'MANQUANT'} {label}")
        ok = ok and present
    for module, label in optional.items():
        print(f"  {'OK ' if has_module(module) else '-- '} {label} (optionnel)")
    seven = shutil.which("7z") or shutil.which("7za") or shutil.which("7zr")
    print(f"  {'OK ' if seven else '-- '} commande 7z (optionnel)")
    return ok


def check_cores(path: Path) -> bool:
    manifest_path = HERE / "cores_manifest.json"
    if not manifest_path.exists():
        print("  manifeste des cœurs absent")
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not path.is_dir():
        print(f"  dossier de cœurs absent : {path}")
        print("  lancez tools/fetch_cores.py --output", path)
        return False
    ok = True
    for core in manifest["cores"]:
        target = path / core["file"]
        if target.exists():
            print(f"  OK  {core['name']}")
        else:
            print(f"  --  {core['name']} absent ({core['file']})")
            ok = False
    return ok


def check_bios(path: Path) -> bool:
    script = HERE / "check_bios.py"
    if not script.exists():
        return True
    print(f"  dossier système : {path}")
    result = subprocess.run([sys.executable, str(script),
                             "--system-dir", str(path)],
                            capture_output=True, text=True)
    tail = result.stdout.strip().splitlines()[-1:] or [""]
    print(f"  {tail[0]}")
    return result.returncode == 0


def check_mcp() -> bool:
    script = HERE / "mcp_config.py"
    if not script.exists():
        return True
    result = subprocess.run([sys.executable, str(script), "--check"],
                            capture_output=True, text=True)
    if result.returncode == 0:
        first = result.stdout.strip().splitlines()[0]
        print(f"  OK  {first}")
        return True
    print("  ECHEC du handshake MCP")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnostic TileForge")
    parser.add_argument("--cores", default=os.environ.get(
        "TILEFORGE_CORES", str(ROOT / "cores")))
    parser.add_argument("--system-dir", default=str(ROOT / "system"))
    args = parser.parse_args(argv)

    print("== Python")
    python_ok = check_python()
    print("\n== Dépendances")
    deps_ok = check_dependencies()
    print("\n== Cœurs libretro")
    cores_ok = check_cores(Path(args.cores).expanduser())
    print("\n== BIOS")
    bios_ok = check_bios(Path(args.system_dir).expanduser())
    print("\n== MCP")
    mcp_ok = check_mcp()
    print(f"\nCœurs : {'complets' if cores_ok else 'partiels'}")
    print(f"BIOS : {'complets' if bios_ok else 'à compléter'}")
    print("Résultat :",
          "OK" if (python_ok and deps_ok and mcp_ok) else "À COMPLÉTER")
    print("Les cœurs et BIOS manquants sont optionnels pour les tests ; "
          "ils sont nécessaires à la démonstration.")
    return 0 if (python_ok and deps_ok and mcp_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
