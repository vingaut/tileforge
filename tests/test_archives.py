"""Tests de lecture des archives zip/7z.

Les ROMs des packs sont presque toujours compressées. Ces tests fabriquent
leurs propres archives pour ne dépendre d'aucun fichier de jeu : un zip avec
une ROM et une notice, un 7z si l'outil ``7z`` est installé.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import archives as A


def _folder() -> Path:
    return Path(tempfile.mkdtemp(prefix="tileforge-archive-"))


def test_zip_liste_et_choisit_la_rom():
    folder = _folder()
    archive = folder / "jeu.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("jeu.nes", b"ROMDATA")
        zf.writestr("readme.txt", b"notice")
    entries = A.list_archive(archive)
    assert [entry.name for entry in entries] == ["jeu.nes", "readme.txt"]
    assert entries[0].is_rom and not entries[1].is_rom
    source = A.open_rom(archive)
    assert source.member == "jeu.nes"
    assert source.data == b"ROMDATA"
    assert source.archive
    assert A.read_member(archive, "readme.txt") == b"notice"


def test_zip_membre_explicite():
    folder = _folder()
    archive = folder / "jeu.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("disque1.bin", b"UN")
        zf.writestr("disque2.bin", b"DEUX")
    assert A.open_rom(archive, "disque2.bin").data == b"DEUX"


def test_fichier_nu():
    folder = _folder()
    path = folder / "jeu.sfc"
    path.write_bytes(b"ROM")
    source = A.open_rom(path)
    assert not source.archive
    assert source.member == ""
    assert source.data == b"ROM"


def test_archive_invalide():
    folder = _folder()
    path = folder / "casse.zip"
    path.write_bytes(b"pas un zip")
    try:
        A.list_archive(path)
    except A.ArchiveError:
        return
    raise AssertionError("un zip invalide aurait dû être refusé")


def test_membre_absent():
    folder = _folder()
    archive = folder / "jeu.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("jeu.nes", b"ROM")
    try:
        A.open_rom(archive, "absent.nes")
    except A.ArchiveError:
        return
    raise AssertionError("un membre absent aurait dû être refusé")


def test_extraction_temporaire():
    folder = _folder()
    archive = folder / "jeu.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("jeu.gba", b"GBA")
    source = A.open_rom(archive)
    temp = A.extract_to_temp(source, folder)
    try:
        assert Path(temp).read_bytes() == b"GBA"
        assert Path(temp).suffix == ".gba"
    finally:
        Path(temp).unlink(missing_ok=True)


def test_7z_si_disponible():
    tool = shutil.which("7z") or shutil.which("7za") or shutil.which("7zr")
    if tool is None:
        return
    folder = _folder()
    rom = folder / "jeu.md"
    rom.write_bytes(b"SEGADATA")
    (folder / "readme.txt").write_text("notice")
    archive = folder / "jeu.7z"
    result = subprocess.run(
        [tool, "a", "-t7z", str(archive), str(rom), str(folder / "readme.txt")],
        capture_output=True)
    if result.returncode != 0:
        return
    entries = A.list_archive(archive)
    names = {entry.name for entry in entries}
    assert "jeu.md" in names
    source = A.open_rom(archive)
    assert source.member == "jeu.md"
    assert source.data == b"SEGADATA"
