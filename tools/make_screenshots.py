#!/usr/bin/env python3
"""Génère les captures d'écran de la documentation, sans contenu commercial.

Les images de `docs/` doivent pouvoir être publiées avec le code. Ce script
fabrique une planche de tuiles synthétique, un projet factice et un faux ROM,
puis capture l'interface et les dialogues en mode hors écran.

    QT_QPA_PLATFORM=offscreen python tools/make_screenshots.py

Aucune ROM, aucun sprite de jeu n'est lu : tout est généré ici.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="tileforge-shots-"))

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tileforge.core import cartography as cartography_mod  # noqa: E402
from tileforge.core.image import Image, save_image  # noqa: E402
from tileforge.core.model import Grid, Project, Sheet, Sprite  # noqa: E402
from tileforge.core.settings import Settings  # noqa: E402
from tileforge.ui.cartography_dialog import CartographyDialog  # noqa: E402
from tileforge.ui.disasm_dialog import DisasmDialog  # noqa: E402
from tileforge.ui.help_dialog import HelpDialog  # noqa: E402
from tileforge.ui.main_window import MainWindow  # noqa: E402

PALETTE = [
    (34, 40, 52), (220, 70, 70), (70, 180, 100), (70, 120, 220),
    (240, 200, 70), (200, 90, 200), (80, 210, 210), (245, 245, 245),
]


def synthetic_sheet(tile_w: int = 16, tile_h: int = 16,
                    cols: int = 16, rows: int = 8) -> Sheet:
    """Planche de tuiles abstraites, sans aucun contenu de jeu."""
    px = np.zeros((rows * tile_h, cols * tile_w, 4), np.uint8)
    for ty in range(rows):
        for tx in range(cols):
            base = np.array(PALETTE[(tx + 2 * ty) % len(PALETTE)], np.uint8)
            tile = np.zeros((tile_h, tile_w, 4), np.uint8)
            tile[..., :3] = base
            tile[..., 3] = 255
            yy, xx = np.mgrid[0:tile_h, 0:tile_w]
            kind = (tx + ty) % 4
            fg = np.array(PALETTE[(tx + 2 * ty + 3) % len(PALETTE)], np.uint8)
            if kind == 0:
                mask = (xx - 7.5) ** 2 + (yy - 7.5) ** 2 < 30
            elif kind == 1:
                mask = abs(xx - yy) < 3
            elif kind == 2:
                mask = ((xx // 4 + yy // 4) % 2) == 0
            else:
                mask = (xx < 3) | (yy < 3) | (xx > 12) | (yy > 12)
            tile[mask, :3] = fg
            px[ty * tile_h:(ty + 1) * tile_h,
               tx * tile_w:(tx + 1) * tile_w] = tile
    image = Image.from_rgb(px[..., :3])
    sheet = Sheet(image=image, source="démo synthétique", kind="raw", info={})
    for index in range(cols * rows):
        x = (index % cols) * tile_w
        y = (index // cols) * tile_h
        sheet.add_tile((x, y, tile_w, tile_h), storage_index=index,
                       label=str(index))
    return sheet


def synthetic_project() -> Project:
    """Projet factice avec deux sprites validés et un sprite courant."""
    sheet = synthetic_sheet()
    project = Project()
    project.sheet = sheet
    project.grid = Grid(2, 4, 16, 16)
    project.game = "Démo synthétique"
    tiles = [tile.id for tile in sheet.tiles_sorted()]
    for index, name in enumerate(("pose_01", "pose_02")):
        sprite = Sprite(index + 1, name, 2, 4, 16, 16)
        for slot, tile_id in enumerate(tiles[index * 8:(index + 1) * 8]):
            sprite.placements[slot] = tile_id
        sprite.cost = 0.12 + index * 0.03
        project.current = sprite
        project.validate_current()
    current = Sprite(3, "pose_03", 2, 4, 16, 16)
    for slot, tile_id in enumerate(tiles[16:24]):
        current.placements[slot] = tile_id
    project.current = current
    return project


def save_demo_sheet(output: Path) -> None:
    """Planche de tuiles synthétique pour le démarrage rapide du README."""
    image = synthetic_sheet().image.scaled(4)
    path = output / "planche_demo.png"
    save_image(str(path), image)
    print(f"  {path.name}")


def capture_main_window(app: QApplication, output: Path) -> None:
    settings = Settings(path=Path(os.environ["XDG_CONFIG_HOME"]) / "settings.json")
    settings.update({"show_welcome": False, "help_interactive": False,
                     "check_updates": False}, save=False)
    window = MainWindow(settings)
    window.project = synthetic_project()
    window.history = type(window.history)(lambda: window.project,
                                          window._on_history_change)
    window.resize(1440, 900)
    window.show()
    app.processEvents()
    window.sheet_view.refresh()
    window.assembly.refresh()
    window.atlas_view.refresh()
    window.analysis.refresh()
    for index, name in ((0, "planche"), (1, "atelier"), (2, "atlas"),
                        (3, "analyse")):
        window.tabs.setCurrentIndex(index)
        app.processEvents()
        path = output / f"capture_{name}.png"
        window.grab().save(str(path))
        print(f"  {path.name}")
    window.project.dirty = False
    window.hide()


def capture_help(app: QApplication, output: Path) -> None:
    dialog = HelpDialog(section="mcp")
    dialog.resize(1040, 760)
    dialog.show()
    app.processEvents()
    path = output / "capture_aide.png"
    dialog.grab().save(str(path))
    print(f"  {path.name}")
    dialog.close()


def capture_cartography(app: QApplication, output: Path) -> None:
    rng = np.random.default_rng(7)
    data = bytearray(rng.integers(0, 256, 0x10000, dtype=np.uint8).tobytes())
    title = b"DEMO SYNTHETIQUE".ljust(21, b" ")
    data[0x7FC0:0x7FC0 + 21] = title
    report = cartography_mod.cartography(bytes(data))
    dialog = CartographyDialog(None, report, source="demo-synthetique.sfc")
    dialog.show()
    app.processEvents()
    path = output / "capture_cartographie.png"
    dialog.grab().save(str(path))
    print(f"  {path.name}")
    dialog.close()


def capture_disasm(app: QApplication, output: Path) -> None:
    code = bytes.fromhex(
        "78 18 FB C2 30 A9 00 80 8D 00 21 A9 0F 8D 01 21 "
        "4C 00 80 EA EA EA EA EA EA EA EA EA EA EA EA EA EA")
    with tempfile.NamedTemporaryFile(prefix="tileforge-demo-", suffix=".bin",
                                     delete=False) as handle:
        handle.write(code)
        temp_name = handle.name
    try:
        dialog = DisasmDialog(None, temp_name)
        dialog.resize(1116, 620)
        dialog.load(temp_name)
        dialog.show()
        app.processEvents()
        path = output / "capture_desassemblage.png"
        dialog.grab().save(str(path))
        print(f"  {path.name}")
        dialog.close()
    finally:
        Path(temp_name).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    output = Path(argv[0]) if argv else ROOT / "docs"
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    print(f"Captures synthétiques dans {output}")
    save_demo_sheet(output)
    capture_main_window(app, output)
    capture_help(app, output)
    capture_cartography(app, output)
    capture_disasm(app, output)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
