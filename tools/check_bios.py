#!/usr/bin/env python3
"""Vérifie les BIOS et firmwares attendus par les cœurs libretro.

TileForge ne distribue aucun BIOS. Ce script compare le contenu d'un dossier
``system/`` au manifeste ``tools/bios_manifest.json``, indique ce qui est
présent, absent ou optionnel, et vérifie les empreintes connues.

    python tools/check_bios.py --list
    python tools/check_bios.py --system-dir /path/to/system
    python tools/check_bios.py --system-dir ./system --strict
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "bios_manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path = MANIFEST) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check(system_dir: Path, systems: list[str], strict: bool = False) -> int:
    manifest = load_manifest()
    wanted = {system.lower() for system in systems}
    missing_required = 0
    for entry in manifest["entries"]:
        if wanted and entry["system"].lower() not in wanted:
            continue
        files = entry.get("files", [])
        print(f"{entry['system']:14s} ({entry['core']})")
        if not files:
            print("  aucun BIOS nécessaire")
            continue
        for name in files:
            path = system_dir / name
            if path.exists():
                if entry.get("sha256") and len(files) == 1:
                    actual = sha256_file(path)
                    if actual == entry["sha256"]:
                        print(f"  [ok] {name}")
                    else:
                        print(f"  [!!] {name} : empreinte différente")
                else:
                    print(f"  [ok] {name}")
            elif entry.get("required"):
                missing_required += 1
                print(f"  [!!] {name} manquant (obligatoire)")
            else:
                print(f"  [--] {name} absent (optionnel)")
        if entry.get("status") == "free" and entry.get("url"):
            print(f"  téléchargement libre : {entry['url']}")
        elif entry.get("status") == "copyrighted":
            print("  fichier copyrighté : à extraire d'un matériel possédé")
        if entry.get("note"):
            print(f"  {entry['note']}")
    print()
    if missing_required:
        print(f"{missing_required} fichier(s) obligatoire(s) manquant(s).")
        return 1 if strict else 0
    print("Tous les fichiers obligatoires sont présents.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vérifie les BIOS attendus par TileForge.")
    parser.add_argument("--system-dir", default=str(Path.cwd() / "system"),
                        help="dossier des BIOS (défaut : ./system)")
    parser.add_argument("--system", action="append", default=[],
                        help="limiter à un système (zxspectrum, c64…)")
    parser.add_argument("--list", action="store_true",
                        help="liste les entrées du manifeste")
    parser.add_argument("--strict", action="store_true",
                        help="code de retour 1 si un BIOS obligatoire manque")
    args = parser.parse_args(argv)

    if args.list:
        for entry in load_manifest()["entries"]:
            files = ", ".join(entry.get("files", [])) or "aucun"
            print(f"{entry['system']:14s} {entry['core']:20s} {files}")
        return 0
    return check(Path(args.system_dir).expanduser(), args.system, args.strict)


if __name__ == "__main__":
    sys.exit(main())
