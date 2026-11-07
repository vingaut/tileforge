"""Tests de la lecture de mémoire d'émulateur.

Le cœur libretro utilisé ici est factice (``tests/fake_libretro.c``) : il
n'émule rien, mais il expose des blocs mémoire et une image, ce qui suffit à
vérifier le chargement, l'exécution, les entrées, l'instantané et la capture.
Le test est ignoré si aucun compilateur C n'est disponible.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import emulation as E

HERE = Path(__file__).resolve().parent
_FAKE_CORE: str | None = None


def _compile_fake_core() -> str | None:
    """Compile le cœur factice une fois, dans un dossier temporaire."""
    global _FAKE_CORE
    if _FAKE_CORE is not None:
        return _FAKE_CORE
    if not shutil.which("gcc") or sys.platform != "linux":
        return None
    folder = Path(tempfile.mkdtemp(prefix="tileforge-core-"))
    output = folder / "fake_libretro.so"
    source = HERE / "fake_libretro.c"
    result = subprocess.run(
        ["gcc", "-shared", "-fPIC", "-O2", "-o", str(output), str(source)],
        capture_output=True, text=True)
    if result.returncode != 0:
        return None
    _FAKE_CORE = str(output)
    return _FAKE_CORE


def _rom_file() -> str:
    folder = Path(tempfile.mkdtemp(prefix="tileforge-rom-"))
    path = folder / "jeu.bin"
    path.write_bytes(bytes(range(256)) * 4)
    return str(path)


def test_parse_buttons():
    presses = E.parse_buttons("start@120-140,a@200")
    assert presses[0].button == E.BUTTONS["start"]
    assert (presses[0].start, presses[0].end) == (120, 140)
    assert presses[1].button == E.BUTTONS["a"]
    assert (presses[1].start, presses[1].end) == (200, None)
    assert E._mask_at(presses, 130) == 1 << E.BUTTONS["start"]
    assert E._mask_at(presses, 140) == 0
    assert E._mask_at(presses, 250) == 1 << E.BUTTONS["a"]


def test_parse_buttons_inconnu():
    try:
        E.parse_buttons("touche-impossible")
    except E.EmulationError:
        return
    raise AssertionError("un bouton inconnu aurait dû être refusé")


def test_parse_buttons_trame_invalide():
    try:
        E.parse_buttons("start@abc")
    except E.EmulationError:
        return
    raise AssertionError("une trame non numérique aurait dû être refusée")


def test_guess_system():
    assert E.guess_system("mgba_libretro.so") == "gba"
    assert E.guess_system("snes9x_libretro.so") == "snes"
    assert E.guess_system("genesis_plus_gx_libretro.so") == "megadrive"
    assert E.guess_system("inconnu.so") == ""


def test_decouverte_d_un_dossier():
    folder = Path(tempfile.mkdtemp(prefix="tileforge-cores-"))
    (folder / "mgba_libretro.so").write_bytes(b"not a real core")
    cores = E.discover_cores([folder])
    assert any(core.path.endswith("mgba_libretro.so") for core in cores)
    core = next(core for core in cores if core.path.endswith("mgba_libretro.so"))
    assert core.system == "gba"
    assert core.name


def test_instantane_brut():
    folder = Path(tempfile.mkdtemp(prefix="tileforge-raw-"))
    path = folder / "ram.bin"
    path.write_bytes(bytes(range(32)))
    snapshot = E.MemorySnapshot.load(path)
    assert snapshot.frames == 0
    assert snapshot.regions["memory"].data == bytes(range(32))


def test_instantane_aller_retour():
    region = E.MemoryRegion("system_ram", bytes(range(64)), base=0x2000000,
                            region_id=2)
    snapshot = E.MemorySnapshot(core="Test", rom="jeu.bin", system="gba",
                                frames=12, regions={"system_ram": region})
    folder = Path(tempfile.mkdtemp(prefix="tileforge-mem-"))
    result = snapshot.save(folder, name="essai")
    assert Path(result["manifest"]).exists()
    assert Path(result["combined"]).exists()
    reloaded = E.MemorySnapshot.load(result["manifest"])
    assert reloaded.frames == 12
    assert reloaded.system == "gba"
    assert reloaded.regions["system_ram"].data == bytes(range(64))
    assert reloaded.regions["system_ram"].base == 0x2000000


def test_coeur_factice_metadonnees():
    core_path = _compile_fake_core()
    if core_path is None:
        return
    info = E.probe_core(core_path)
    assert info.name == "Fake Core"
    assert "bin" in info.extensions
    assert info.need_fullpath is False
    assert info.system == ""           # le nom « fake » n'est pas reconnu


def test_coeur_factice_memoire_et_image():
    core_path = _compile_fake_core()
    if core_path is None:
        return
    rom = _rom_file()
    folder = Path(tempfile.mkdtemp(prefix="tileforge-run-"))
    result = E.run_rom(core_path, rom, frames=4, output_dir=folder,
                       name="partie", screenshot=True)
    manifest = result["manifest"]
    assert Path(manifest).exists()
    assert Path(result["combined"]).exists()
    assert Path(result["screenshot"]).exists()
    assert Path(result["screenshot"]).read_bytes().startswith(b"\x89PNG")
    snapshot = E.MemorySnapshot.load(manifest)
    assert snapshot.frames == 4
    assert snapshot.regions["system_ram"].data[0] == 4
    assert snapshot.regions["system_ram"].data[2] == 0
    assert snapshot.regions["system_ram"].data[0x1000] == 7
    assert snapshot.regions["video_ram"].data[:2] == bytes([0xA5, 4])
    assert snapshot.regions["save_ram"].data[0] == 0x5A


def test_coeur_factice_entrees():
    core_path = _compile_fake_core()
    if core_path is None:
        return
    rom = _rom_file()
    snapshot = E.run_rom(core_path, rom, frames=6, buttons="start@1-4")
    assert snapshot.regions["system_ram"].data[2] == 1 << E.BUTTONS["start"]


def test_balayage_d_un_instantane():
    region = E.MemoryRegion("system_ram", bytes(4096), base=0, region_id=2)
    snapshot = E.MemorySnapshot(core="Test", rom="jeu.bin", system="snes",
                                frames=1, regions={"system_ram": region})
    result = E.scan_snapshot(snapshot, "snes_4bpp", compressions=[],
                             budget=5.0)
    assert result["system"] == "snes"
    assert result["regions"][0]["region"] == "system_ram"
