#!/usr/bin/env python3
"""Vérifie que l'arbre courant peut être publié.

Contrôle les fichiers suivis (ou un arbre git donné) : aucune ROM/BIOS/image
de jeu, aucun chemin personnel, les documents de publication et les manifestes
sont présents.

    python tools/verify_publication.py
    python tools/verify_publication.py --ref publication
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_SUFFIXES = {
    ".stx", ".st", ".msa", ".adf", ".adz", ".ipf", ".dsk", ".d64", ".tap",
    ".tzx", ".z80", ".sna", ".cas", ".cdt",
    ".smc", ".sfc", ".nes", ".unf", ".gb", ".gbc", ".gba", ".sms", ".gg",
    ".pce", ".sgx", ".a26", ".a78", ".col", ".int", ".vec", ".smd", ".gen",
    ".32x", ".neo", ".rom", ".bin", ".zip", ".7z", ".rar",
}

FORBIDDEN_PREFIXES = ("extract/", "graphisme/", "megadrive/", "snes/")

REQUIRED = (
    "LICENSE", "README.md", "README.en.md", "pyproject.toml", "MANIFEST.in",
    ".mcp.json", ".vscode/mcp.json", ".cursor/mcp.json",
    "docs/INSTALL.md", "docs/BIOS.md", "docs/PUBLISHING.md",
    "docs/THIRD_PARTY.md", "docs/planche_demo.png",
    "tools/cores_manifest.json", "tools/bios_manifest.json",
    "tools/fetch_cores.py", "tools/check_bios.py",
)

LOCAL_PATH = re.compile(r"(/home/[A-Za-z0-9_.-]+/|/Users/[A-Za-z0-9_.-]+/|freebox-server)")


def git_files(ref: str = "") -> list[str]:
    command = ["git", "ls-tree", "-r", "--name-only", ref] if ref else ["git", "ls-files"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "git a échoué")
    return [line for line in result.stdout.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vérifie l'arbre publiable")
    parser.add_argument("--ref", default="",
                        help="branche ou commit à vérifier (défaut : index)")
    args = parser.parse_args(argv)

    files = git_files(args.ref)
    problems: list[str] = []
    for name in files:
        suffix = Path(name).suffix.lower()
        if suffix in FORBIDDEN_SUFFIXES:
            problems.append(f"fichier interdit : {name}")
        if name.startswith(FORBIDDEN_PREFIXES):
            problems.append(f"dossier commercial : {name}")
    for name in REQUIRED:
        if name not in files:
            problems.append(f"fichier requis absent : {name}")
    for name in files:
        if Path(name).suffix.lower() not in (".md", ".py", ".json", ".toml",
                                             ".yml", ".yaml", ".txt", ".in",
                                             ".sh", ".desktop", ".spec"):
            continue
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in LOCAL_PATH.finditer(text):
            if name in ("docs/PUBLISHING.md", "tools/verify_publication.py"):
                continue  # les motifs d'audit sont volontaires
            problems.append(f"chemin personnel dans {name} : {match.group(1)}")
    for name in ("tools/cores_manifest.json", "tools/bios_manifest.json"):
        try:
            json.loads((ROOT / name).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"manifeste illisible {name} : {exc}")

    if problems:
        print("Publication impossible :")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"Arbre publiable : {len(files)} fichier(s), aucun contenu interdit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
