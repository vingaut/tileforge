"""Invariants de publication du dépôt.

Le dépôt public ne doit contenir ni ROM, ni BIOS, ni image de jeu commercial.
Ces tests vérifient le `.gitignore`, les manifestes de cœurs/BIOS et la liste
des fichiers suivis quand le dépôt git est disponible.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_SUFFIXES = {
    ".stx", ".st", ".msa", ".adf", ".adz", ".ipf", ".dsk", ".d64", ".tap",
    ".tzx", ".z80", ".sna", ".cas", ".cdt",
    ".smc", ".sfc", ".nes", ".unf", ".gb", ".gbc", ".gba", ".sms", ".gg",
    ".pce", ".sgx", ".a26", ".a78", ".col", ".int", ".vec", ".smd", ".gen",
    ".32x", ".neo", ".rom", ".bin", ".zip", ".7z", ".rar",
}


def test_gitignore_couvre_les_contenus_commerciaux():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("*.stx", "*.smc", "*.nes", "*.zip", "extract/",
                    "graphisme/", "bios/", "system/", "cores/"):
        assert pattern in text, pattern


def test_manifestes_valides():
    cores = json.loads((ROOT / "tools" / "cores_manifest.json").read_text(
        encoding="utf-8"))
    assert cores["format"] == "tileforge/cores/1"
    assert len(cores["cores"]) >= 9
    for core in cores["cores"]:
        assert len(core["sha256"]) == 64
        assert core["file"].endswith("_libretro.so")
    bios = json.loads((ROOT / "tools" / "bios_manifest.json").read_text(
        encoding="utf-8"))
    assert bios["format"] == "tileforge/bios/1"
    assert any(entry["system"] == "zxspectrum" for entry in bios["entries"])


def test_documents_de_publication():
    for name in ("BIOS.md", "INSTALL.md", "PUBLISHING.md", "mcp-clients.md"):
        assert (ROOT / "docs" / name).exists(), name
    assert (ROOT / "MANIFEST.in").exists()
    assert (ROOT / ".mcp.json").exists()


def test_aucun_fichier_commercial_suivi():
    if not (ROOT / ".git").exists():
        return
    result = subprocess.run(["git", "ls-files"], cwd=ROOT,
                            capture_output=True, text=True)
    if result.returncode != 0:
        return
    offenders = [name for name in result.stdout.splitlines()
                 if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES]
    assert not offenders, offenders
    assert not any(name.startswith(("extract/", "graphisme/", "megadrive/",
                                    "snes/"))
                   for name in result.stdout.splitlines())


def test_captures_synthetiques_presentes():
    for name in ("capture_atelier.png", "capture_cartographie.png",
                 "capture_desassemblage.png", "planche_demo.png"):
        path = ROOT / "docs" / name
        assert path.exists(), name
        assert path.stat().st_size > 1000, name
