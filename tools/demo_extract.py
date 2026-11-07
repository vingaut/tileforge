#!/usr/bin/env python3
"""Extrait les graphismes d'un jeu et écrit une démonstration par système.

Le script enchaîne les briques de TileForge :

1. exécution de la ROM dans un cœur libretro (capture d'écran + mémoire) ;
2. choix de la source : mémoire décodée, ROM (compressée ou brute) ou capture ;
3. décodage d'une banque de tuiles avec le format de la machine ;
4. propositions de sprites par les solveurs de TileForge ;
5. écriture de ``ecran.png``, ``tuiles.png``, ``sprites.png``, ``rapport.json``
   et ``README.md``.

Exemple ::

    python tools/demo_extract.py --system snes \\
        --core ~/tileforge-cores/snes9x_libretro.so \\
        --rom "Super Mario World.zip" --frames 600 \\
        --output ../tileforge-demo/snes

Le dossier de sortie est autonome : il ne contient que des images produites par
TileForge, le rapport et un extrait de données, jamais la ROM complète.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tileforge.assemble import solvers  # noqa: E402
from tileforge.assemble.cost import build_cost_model  # noqa: E402
from tileforge.core import archives, compression, emulation, scan  # noqa: E402
from tileforge.core.formats import FORMATS_BY_KEY, load_raw_bank  # noqa: E402
from tileforge.core.image import Image, load_image, save_image  # noqa: E402
from tileforge.core.model import Sheet, Sprite  # noqa: E402
from tileforge.core.palettes import BUILTIN_PALETTES  # noqa: E402

#: Réglages par machine. ``tile`` est la taille logique d'une tuile.
SYSTEMS: dict[str, dict] = {
    "nes": {"format": "nes", "palette": "nes", "compressions": (),
            "cols": 2, "rows": 2, "source": "auto"},
    "snes": {"format": "snes_4bpp", "palette": "generic16",
             "compressions": ("lz2", "lz3"), "cols": 2, "rows": 2,
             "source": "auto"},
    "megadrive": {"format": "megadrive", "palette": "megadrive",
                  "compressions": ("kosinski", "nemesis", "comper",
                                   "saxman_len"),
                  "cols": 2, "rows": 2, "source": "auto"},
    "gameboy": {"format": "gameboy", "palette": "gameboy", "compressions": (),
                "cols": 2, "rows": 2, "source": "auto"},
    "gba": {"format": "gba_4bpp", "palette": "generic16",
            "compressions": ("gba_lz77",), "cols": 2, "rows": 2,
            "source": "auto"},
    "mastersystem": {"format": "master_system", "palette": "sms",
                     "compressions": (), "cols": 2, "rows": 2,
                     "source": "auto"},
    "pcengine": {"format": "pc_engine", "palette": "generic16",
                 "compressions": (), "cols": 2, "rows": 2, "source": "auto"},
    "zxspectrum": {"format": "zx_spectrum", "palette": "zx", "compressions": (),
                   "cols": 2, "rows": 2, "source": "screenshot"},
    "amstradcpc": {"format": "cpc_mode0", "palette": "cpc", "compressions": (),
                   "cols": 2, "rows": 2, "source": "screenshot"},
    "c64": {"format": "c64", "palette": "c64", "compressions": (),
            "cols": 2, "rows": 2, "source": "screenshot"},
}


# ---------------------------------------------------------------------------
# Utilitaires image
# ---------------------------------------------------------------------------


def crop_background(image: Image, margin: int = 0) -> Image:
    """Recadre autour des pixels qui diffèrent de la couleur du coin."""
    import numpy as np

    px = image.px
    if px.size == 0:
        return image
    background = px[0, 0].copy()
    mask = np.any(px != background, axis=2)
    if not mask.any():
        return image
    ys, xs = mask.any(axis=1), mask.any(axis=0)
    y0, y1 = int(np.argmax(ys)), int(len(ys) - np.argmax(ys[::-1]))
    x0, x1 = int(np.argmax(xs)), int(len(xs) - np.argmax(xs[::-1]))
    y0, x0 = max(0, y0 - margin), max(0, x0 - margin)
    y1, x1 = min(image.h, y1 + margin), min(image.w, x1 + margin)
    return image.cropped(x0, y0, x1 - x0, y1 - y0)


def contact_sheet(images: list[Image], per_row: int = 8,
                  gap: int = 2) -> Image:
    """Assemble des vignettes en planche régulière."""
    if not images:
        return Image.blank(8, 8)
    w = max(img.w for img in images)
    h = max(img.h for img in images)
    rows = (len(images) + per_row - 1) // per_row
    out = Image.blank(per_row * (w + gap) + gap, rows * (h + gap) + gap)
    for index, img in enumerate(images):
        x = gap + (index % per_row) * (w + gap)
        y = gap + (index // per_row) * (h + gap)
        out.paste(img, x, y)
    return out


def unique_tiles(image: Image, tile_w: int = 8, tile_h: int = 8,
                 max_tiles: int = 256) -> list[Image]:
    """Découpe une capture en tuiles uniques (dans l'ordre d'apparition)."""
    seen: set[bytes] = set()
    tiles: list[Image] = []
    cols, rows = image.w // tile_w, image.h // tile_h
    for row in range(rows):
        for col in range(cols):
            tile = image.cropped(col * tile_w, row * tile_h, tile_w, tile_h)
            key = tile.px.tobytes()
            if key in seen:
                continue
            seen.add(key)
            tiles.append(tile)
            if len(tiles) >= max_tiles:
                return tiles
    return tiles


def build_sheet(tiles: list[Image], tile_w: int, tile_h: int,
                per_row: int = 16, gap: int = 1) -> Sheet:
    """Construit une planche TileForge à partir d'une liste de tuiles."""
    image = contact_sheet(tiles, per_row=per_row, gap=gap)
    sheet = Sheet(image=image, source="", kind="raw",
                  info={"tile_w": tile_w, "tile_h": tile_h})
    for index in range(len(tiles)):
        x = gap + (index % per_row) * (tile_w + gap)
        y = gap + (index // per_row) * (tile_h + gap)
        sheet.add_tile((x, y, tile_w, tile_h), storage_index=index,
                       label=str(index))
    return sheet


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def scan_memory(snapshot: emulation.MemorySnapshot, fmt_key: str,
                budget: float = 20.0):
    """Meilleur candidat dans les régions mémoire (déjà décompressées)."""
    best = None
    for region in snapshot.regions.values():
        if not region.data:
            continue
        report = scan.scan_bytes(
            region.data, fmt_key, compressions=(), raw=True, compressed=False,
            budget=budget, threshold=0.40, max_candidates=5)
        for candidate in report.candidates:
            if best is None or candidate.score > best[0].score:
                best = (candidate, region)
    return best


def scan_rom(data: bytes, fmt_key: str, compressions: tuple[str, ...],
             budget: float = 20.0):
    """Meilleur candidat dans la ROM, compressé puis brut."""
    keys = tuple(key for key in compressions
                 if key in compression.DECOMPRESSORS_BY_KEY)
    report = scan.scan_bytes(
        data, fmt_key, compressions=keys, raw=True, compressed=bool(keys),
        budget=budget, threshold=0.40, max_candidates=5)
    best = report.best
    if best is None or best.score < 0.45:
        raw = scan.scan_bytes(
            data, fmt_key, compressions=(), raw=True, compressed=False,
            budget=budget, threshold=0.40, max_candidates=5)
        if raw.best is not None and (best is None or raw.best.score > best.score):
            best = raw.best
    return best


def candidate_payload(data: bytes, candidate) -> bytes:
    """Octets décompressés (ou bruts) du candidat."""
    if candidate.compression:
        return compression.decompress(candidate.compression, data,
                                      candidate.offset)
    return data[candidate.offset:candidate.offset + candidate.size]


# ---------------------------------------------------------------------------
# Composition de sprites
# ---------------------------------------------------------------------------


def propose_sprites(sheet: Sheet, fmt, cols: int, rows: int, groups: int,
                    method: str = "M3") -> list[Image]:
    """Propose quelques sprites avec les solveurs de TileForge."""
    tiles = [tile.id for tile in sheet.tiles_sorted()]
    need = cols * rows
    if need <= 0 or len(tiles) < need:
        return []
    sprites: list[Image] = []
    for group in range(min(groups, len(tiles) // need)):
        ids = tiles[group * need:(group + 1) * need]
        order = ids
        try:
            model = build_cost_model(sheet, ids)
            solutions = solvers.solve(method, model, cols, rows,
                                      {"width": 120})
            if solutions:
                order = solutions[0].order
        except Exception:
            pass
        sprite = Sprite(group, f"proposition_{group + 1}", cols, rows,
                        fmt.tile_w, fmt.tile_h)
        for slot, tile_id in enumerate(order[:need]):
            sprite.placements[slot] = tile_id
        sprites.append(sprite.render(sheet))
    return sprites


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract(system: str, core: str, rom: str, output: Path,
            member: str = "", frames: int = 600, buttons: str = "",
            system_dir: str = "", source: str = "", fmt_key: str = "",
            palette_key: str = "", scale: int = 3, max_tiles: int = 256,
            groups: int = 8, cols: int = 0, rows: int = 0,
            budget: float = 20.0, title: str = "",
            sprite_box: tuple[int, int, int, int] | None = None) -> dict:
    """Exécute la ROM, choisit une source et écrit la démonstration."""
    config = SYSTEMS[system]
    fmt_key = fmt_key or config["format"]
    palette_key = palette_key or config["palette"]
    cols = cols or config["cols"]
    rows = rows or config["rows"]
    fmt = FORMATS_BY_KEY[fmt_key]
    palette = BUILTIN_PALETTES.get(palette_key)

    output.mkdir(parents=True, exist_ok=True)
    emu_dir = output / "emulateur"
    emu_dir.mkdir(exist_ok=True)

    result = emulation.run_rom(
        core, rom, frames=frames, buttons=buttons, output_dir=emu_dir,
        screenshot=True, member=member, system_dir=system_dir or None)
    snapshot = emulation.MemorySnapshot.load(result["manifest"])
    screenshot = Path(result["screenshot"])
    screen_image = load_image(str(screenshot))
    save_image(str(output / "ecran.png"), screen_image)

    requested = source or config.get("source", "auto")
    report: dict = {
        "system": system, "game": title or Path(rom).stem,
        "core": Path(core).name, "rom": str(rom), "member": member,
        "frames": frames, "buttons": buttons, "tile_format": fmt_key,
        "palette": palette_key, "regions": [
            {"name": region.name, "size": len(region.data),
             "base": region.base} for region in snapshot.regions.values()],
        "notes": [],
    }

    data: bytes | None = None
    offset = 0
    score = 0.0
    source_used = requested
    sheet: Sheet | None = None
    tiles: list[Image] = []

    if requested in ("auto", "memory"):
        best = scan_memory(snapshot, fmt_key, budget=budget)
        if best is not None and (requested == "memory" or best[0].score >= 0.50):
            candidate, region = best
            data = candidate_payload(region.data, candidate)
            offset = 0
            score = candidate.score
            source_used = "memory"
            report["region"] = region.name
            report["region_offset"] = candidate.offset
        elif requested == "memory":
            report["notes"].append("aucun candidat mémoire au-dessus du seuil")

    if data is None and requested in ("auto", "rom"):
        rom_data = archives.read_rom(rom, member)
        candidate = scan_rom(rom_data, fmt_key, config["compressions"],
                             budget=budget)
        if candidate is not None:
            data = candidate_payload(rom_data, candidate)
            offset = 0
            score = candidate.score
            source_used = "rom"
            report["rom_offset"] = candidate.offset
            report["compression"] = candidate.compression or "brut"
        elif requested == "rom":
            report["notes"].append("aucun candidat ROM au-dessus du seuil")

    if data is None or (requested == "screenshot"):
        source_used = "screenshot"
        cropped = crop_background(screen_image)
        tiles = unique_tiles(cropped, fmt.tile_w, fmt.tile_h, max_tiles)
        sheet = build_sheet(tiles, fmt.tile_w, fmt.tile_h)
        report["screenshot_crop"] = [cropped.w, cropped.h]
        report["notes"].append(
            "capture recadrée puis découpée en tuiles uniques ; "
            "les sprites sont des propositions, pas la banque d'origine")
    else:
        count = min(max_tiles, len(data) // fmt.real_bytes)
        bank = load_raw_bank(None, 0, count, fmt, per_row=16, gap=1,
                             palette=palette, data=data)
        sheet = Sheet(image=bank.image, source=str(rom), kind="raw",
                      info={"format": fmt.key, "count": bank.count})
        for index, rect in enumerate(bank.tile_rects()):
            sheet.add_tile(rect, storage_index=index, label=str(index))
        save_image(str(output / "tuiles.png"), bank.image.scaled(scale))
        (output / "donnees.bin").write_bytes(data[:count * fmt.real_bytes])
        report["offset"] = offset
        report["score"] = round(score, 4)
        report["tiles"] = count

    if source_used == "screenshot":
        save_image(str(output / "tuiles.png"),
                   contact_sheet(tiles, per_row=16, gap=1).scaled(scale))
        (output / "tuiles.json").write_text(json.dumps(
            {"count": len(tiles), "tile_w": fmt.tile_w, "tile_h": fmt.tile_h},
            ensure_ascii=False, indent=1), encoding="utf-8")
        report["tiles"] = len(tiles)

    method = "M3" if source_used in ("memory", "rom") else "M1"
    sprites = propose_sprites(sheet, fmt, cols, rows, groups, method=method)
    if sprites:
        save_image(str(output / "sprites_solveur.png"),
                   contact_sheet(sprites, per_row=min(8, len(sprites)),
                                 gap=2).scaled(scale))
        report["sprites"] = len(sprites)
        report["sprite_grid"] = [cols, rows]
        report["sprite_method"] = method
    else:
        report["notes"].append("pas assez de tuiles pour proposer des sprites")

    if sprite_box is not None:
        x, y, w, h = (int(value) for value in sprite_box)
        crop = screen_image.cropped(x, y, w, h)
        save_image(str(output / "sprites.png"), crop.scaled(max(1, scale)))
        report["sprite_box"] = [x, y, w, h]
        report["notes"].append(
            "sprites.png est un extrait manuel de la capture (zone de sprite) ; "
            "sprites_solveur.png contient les propositions automatiques")
    elif sprites:
        save_image(str(output / "sprites.png"),
                   contact_sheet(sprites, per_row=min(8, len(sprites)),
                                 gap=2).scaled(scale))

    report["source"] = source_used
    report["screenshot"] = "ecran.png"
    (output / "rapport.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (output / "README.md").write_text(render_readme(report), encoding="utf-8")
    return report


def render_readme(report: dict) -> str:
    """Petite fiche lisible pour le dossier de démonstration."""
    lines = [
        f"# {report['system']} — {report['game']}",
        "",
        f"- **Cœur** : `{report['core']}`",
        f"- **ROM** : `{report['rom']}`"
        + (f" (membre `{report['member']}`)" if report.get("member") else ""),
        f"- **Trames exécutées** : {report['frames']}"
        + (f" (entrées : `{report['buttons']}`)" if report.get("buttons") else ""),
        f"- **Source des graphismes** : {report['source']}",
        f"- **Format de tuiles** : `{report['tile_format']}`",
        f"- **Palette** : `{report['palette']}`",
    ]
    if report.get("score"):
        lines.append(f"- **Note du bloc** : {report['score']:.3f}")
    if report.get("tiles"):
        lines.append(f"- **Tuiles extraites** : {report['tiles']}")
    if report.get("sprites"):
        grid = report.get("sprite_grid", [2, 2])
        lines.append(
            f"- **Sprites proposés** : {report['sprites']} "
            f"({grid[0]} × {grid[1]} tuiles, méthode {report['sprite_method']})")
    if report.get("notes"):
        lines.append("")
        lines.append("## Notes")
        lines.extend(f"- {note}" for note in report["notes"])
    lines.extend([
        "",
        "## Fichiers",
        "",
        "| Fichier | Contenu |",
        "|---|---|",
        "| `ecran.png` | capture de l'émulateur |",
        "| `tuiles.png` | banque de tuiles décodée (ou découpe de la capture) |",
        "| `sprites.png` | extrait manuel de la zone de sprite, ou propositions |",
        "| `sprites_solveur.png` | propositions automatiques du solveur |",
        "| `donnees.bin` | extrait binaire de la banque (si disponible) |",
        "| `rapport.json` | offset, note, format, source, notes |",
        "",
        "Les sprites sont des **propositions** du solveur : sans validation "
        "humaine, elles ne prétendent pas être l'assemblage d'origine.",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extrait les graphismes d'un jeu pour la démonstration "
                    "TileForge.")
    parser.add_argument("--system", required=True, choices=sorted(SYSTEMS))
    parser.add_argument("--core", required=True)
    parser.add_argument("--rom", required=True)
    parser.add_argument("--member", default="")
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--buttons", default="")
    parser.add_argument("--system-dir", default="")
    parser.add_argument("--source", default="",
                        choices=["", "auto", "memory", "rom", "screenshot"])
    parser.add_argument("--format", default="")
    parser.add_argument("--palette", default="")
    parser.add_argument("--scale", type=int, default=3)
    parser.add_argument("--max-tiles", type=int, default=256)
    parser.add_argument("--groups", type=int, default=8)
    parser.add_argument("--cols", type=int, default=0)
    parser.add_argument("--rows", type=int, default=0)
    parser.add_argument("--budget", type=float, default=20.0)
    parser.add_argument("--title", default="")
    parser.add_argument("--sprite-box", default="",
                        help="x,y,w,h : extrait manuel de la capture")
    parser.add_argument("--output", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    sprite_box = None
    if args.sprite_box:
        try:
            values = tuple(int(value) for value in args.sprite_box.split(","))
        except ValueError as exc:
            raise SystemExit("--sprite-box attend x,y,w,h") from exc
        if len(values) == 4:
            sprite_box = values
    report = extract(
        args.system, args.core, args.rom, Path(args.output).expanduser(),
        member=args.member, frames=args.frames, buttons=args.buttons,
        system_dir=args.system_dir, source=args.source, fmt_key=args.format,
        palette_key=args.palette, scale=args.scale, max_tiles=args.max_tiles,
        groups=args.groups, cols=args.cols, rows=args.rows,
        budget=args.budget, title=args.title, sprite_box=sprite_box)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(f"{report['system']} — {report['game']}")
        print(f"  source : {report['source']}")
        print(f"  tuiles : {report.get('tiles', 0)}")
        print(f"  sprites: {report.get('sprites', 0)}")
        print(f"  sortie : {Path(args.output).expanduser()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
