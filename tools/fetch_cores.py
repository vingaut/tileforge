#!/usr/bin/env python3
"""Télécharge les cœurs libretro utilisés par TileForge.

Les binaires ne sont pas dans le dépôt : ce script les récupère depuis le
buildbot officiel de libretro, vérifie leur empreinte SHA-256 et les installe
dans un dossier de cœurs.

    python tools/fetch_cores.py --list
    python tools/fetch_cores.py --output ~/.local/share/tileforge/cores
    python tools/fetch_cores.py --system nes --system snes
    python tools/fetch_cores.py --check --output ./cores

Le manifeste ``tools/cores_manifest.json`` contient l'URL, la taille, la
licence et l'empreinte de chaque cœur testé. Une URL ``latest`` peut évoluer :
si l'empreinte ne correspond plus, le script le signale et n'installe rien.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "cores_manifest.json"


def load_manifest(path: Path = MANIFEST) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def selected_cores(manifest: dict, systems: list[str]) -> list[dict]:
    cores = manifest["cores"]
    if not systems:
        return cores
    wanted = {system.lower() for system in systems}
    return [core for core in cores
            if wanted & {system.lower() for system in core["systems"]}]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_core(core: dict, base_url: str, output: Path,
                  force: bool = False) -> bool:
    """Télécharge, vérifie et extrait un cœur. Renvoie True si installé."""
    target = output / core["file"]
    if target.exists() and not force:
        actual = sha256_file(target)
        if actual == core["sha256"]:
            print(f"  [ok] {core['name']} déjà présent ({core['file']})")
            return True
        print(f"  [!!] {core['name']} présent mais empreinte différente")
        print(f"       attendu {core['sha256']}")
        print(f"       obtenu  {actual}")
        if not force:
            return False
    url = f"{base_url}/{core['key']}_libretro.so.zip"
    print(f"  {core['name']} : {url}")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tileforge-core-") as temp:
        archive = Path(temp) / "core.zip"
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                archive.write_bytes(response.read())
        except Exception as exc:  # noqa: BLE001 - message utilisateur
            print(f"  [!!] téléchargement impossible : {exc}")
            return False
        try:
            with zipfile.ZipFile(archive) as zf:
                names = [name for name in zf.namelist()
                         if name.endswith(core["file"])]
                if not names:
                    print(f"  [!!] {core['file']} absent de l'archive")
                    return False
                data = zf.read(names[0])
        except (zipfile.BadZipFile, OSError) as exc:
            print(f"  [!!] archive illisible : {exc}")
            return False
        actual = hashlib.sha256(data).hexdigest()
        if actual != core["sha256"]:
            print("  [!!] empreinte différente : le buildbot a peut-être changé")
            print(f"       attendu {core['sha256']}")
            print(f"       obtenu  {actual}")
            if not force:
                print("       utilisez --force pour installer quand même")
                return False
        target.write_bytes(data)
        target.chmod(0o755)
        print(f"  [ok] {core['name']} installé dans {target}")
        return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Télécharge les cœurs libretro de TileForge.")
    parser.add_argument("--output", default=str(Path.cwd() / "cores"),
                        help="dossier d'installation (défaut : ./cores)")
    parser.add_argument("--system", action="append", default=[],
                        help="limiter à un système (nes, snes, megadrive…)")
    parser.add_argument("--list", action="store_true",
                        help="liste les cœurs du manifeste")
    parser.add_argument("--check", action="store_true",
                        help="vérifie les cœurs déjà installés, sans télécharger")
    parser.add_argument("--force", action="store_true",
                        help="réinstalle même si l'empreinte diffère")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    cores = selected_cores(manifest, args.system)
    if args.list:
        for core in cores:
            systems = ", ".join(core["systems"])
            print(f"{core['key']:20s} {core['name']:22s} {systems}")
        return 0

    output = Path(args.output).expanduser()
    print(f"Cœurs libretro → {output}")
    ok = 0
    for core in cores:
        target = output / core["file"]
        if args.check:
            if not target.exists():
                print(f"  [--] {core['name']} absent ({core['file']})")
                continue
            actual = sha256_file(target)
            if actual == core["sha256"]:
                print(f"  [ok] {core['name']}")
                ok += 1
            else:
                print(f"  [!!] {core['name']} : empreinte différente")
            continue
        if download_core(core, manifest["base_url"], output, force=args.force):
            ok += 1
    print(f"\n{ok}/{len(cores)} cœur(s) prêt(s).")
    if not args.check:
        print("Ajoutez ce dossier à TILEFORGE_CORES ou passez --core aux outils.")
    return 0 if ok == len(cores) else 1


if __name__ == "__main__":
    sys.exit(main())
