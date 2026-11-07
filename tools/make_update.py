#!/usr/bin/env python3
"""Construit un paquet de mise à jour et le manifeste qui va avec.

Exemple :

    python tools/make_update.py --version 1.2.0 --notes "Nouvelles machines" \
        --url-base https://exemple.org/tileforge

Produit dans ``dist/updates`` :

* ``tileforge-1.2.0.zip`` — le paquet ``tileforge/`` complet (sans les caches) ;
* ``manifest.json`` — description de la version, empreinte SHA-256 et taille.

Le manifeste existant est fusionné : les autres canaux déjà publiés sont
conservés.  Déposez ensuite les deux fichiers au même endroit que l'adresse
``--url-base``, ou sur une clé USB : TileForge sait aussi lire un manifeste
local.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PACKAGE = ROOT / "tileforge"


def package_version() -> str:
    sys.path.insert(0, str(ROOT))
    from tileforge.version import __version__
    return __version__


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build_archive(version: str, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"tileforge-{version}.zip"
    files = [p for p in PACKAGE.rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(files):
            zf.write(path, Path("tileforge") / path.relative_to(PACKAGE))
    return archive


def load_manifest(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"format": "tileforge/update/1", "app": "tileforge", "channels": {}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Construit un paquet de mise à jour")
    parser.add_argument("--version", default="", help="version publiée (défaut : celle du code)")
    parser.add_argument("--channel", default="stable", choices=["stable", "beta"])
    parser.add_argument("--notes", default="", help="notes de version (texte libre)")
    parser.add_argument("--output", default=str(ROOT / "dist" / "updates"))
    parser.add_argument("--url-base", default="",
                        help="préfixe d'URL à inscrire dans le manifeste "
                             "(le nom du fichier est ajouté)")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args(argv)

    version = args.version or package_version()
    output = Path(args.output)
    archive = build_archive(version, output)
    size = archive.stat().st_size
    digest = sha256_of(archive)

    manifest_path = output / "manifest.json"
    manifest = load_manifest(manifest_path)
    manifest.setdefault("channels", {})
    manifest["format"] = "tileforge/update/1"
    manifest["app"] = "tileforge"
    manifest["generated"] = date.today().isoformat()

    if args.url_base:
        base = args.url_base.rstrip("/")
        url = f"{base}/{archive.name}" if not base.endswith(".zip") else base
    else:
        url = archive.name
    manifest["channels"][args.channel] = {
        "version": version,
        "date": args.date,
        "url": url,
        "sha256": digest,
        "size": size,
        "notes": args.notes or f"Version {version}.",
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    print(f"Archive   : {archive}  ({size / 1024:.1f} Ko)")
    print(f"SHA-256   : {digest}")
    print(f"Manifeste : {manifest_path}  (canal {args.channel}, version {version})")
    print()
    print("Publication : déposez les deux fichiers sur votre serveur, ou pointez")
    print("TileForge vers le manifeste local via Aide ▸ Mises à jour ▸ Manifeste.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
