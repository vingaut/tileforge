#!/usr/bin/env python3
"""Chaîne Amiga en ligne de commande.

    python tools/amiga.py list disque.adf
    python tools/amiga.py extract disque.adf NIVEAU1/SPRITES.BIN -o sprites.bin
    python tools/amiga.py nested lv1f -o sortie/
    python tools/amiga.py screen ecran.bin --width 256 --height 256 \\
        --planes 5 --layout plane --stride 40 -o ecran.png
    python tools/amiga.py sprites planche.bin --width 640 --height 256 \\
        --planes 5 --layout plane --stride 80 -o planche.png
    python tools/amiga.py hunk executable
    python tools/amiga.py copper binaire

Aucun contenu de jeu n'est fourni : ces commandes travaillent sur vos fichiers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tileforge.core import amigadisk, amigasprites, copper, hunk, nested, planar  # noqa: E402
from tileforge.core.image import save_image  # noqa: E402


def _read(path: str) -> bytes:
    return Path(path).expanduser().read_bytes()


def cmd_list(args) -> int:
    volume = amigadisk.open_disk(args.disk)
    print(json.dumps(volume.summary(max_depth=args.depth), indent=2,
                     ensure_ascii=False))
    return 0


def cmd_extract(args) -> int:
    volume = amigadisk.open_disk(args.disk)
    data = volume.extract(args.node)
    target = Path(args.output).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    print(f"{args.node} → {target} ({len(data)} octets)")
    for warning in volume.warnings:
        print(f"  avertissement : {warning}")
    return 0


def cmd_nested(args) -> int:
    data = _read(args.file)
    blobs = nested.scan_nested(data, max_depth=args.depth, key=args.key)
    folder = Path(args.output).expanduser() if args.output else Path(".")
    folder.mkdir(parents=True, exist_ok=True)
    for index, blob in enumerate(blobs):
        print(f"[{index}] offset 0x{blob.offset:X} {blob.format} "
              f"profondeur {blob.depth} → {blob.decompressed_size} octets")
        for warning in blob.warnings:
            print(f"    {warning}")
        if blob.data is not None:
            name = f"{index:02d}_{blob.format}_d{blob.depth}_{blob.offset:08x}.bin"
            (folder / name).write_bytes(blob.data)
    print(f"{len(blobs)} bloc(s) trouvé(s), sortie dans {folder}")
    return 0


def _geometry(args):
    data = _read(args.file)
    if args.width and args.planes:
        return data, args.offset, args.width, args.height, args.planes, args.layout, args.stride
    candidates = planar.detect_geometry(
        data, start=max(0, args.offset), height=max(16, args.height),
        width=max(0, args.width), planes=max(0, args.planes),
        layout=args.layout or "", limit=1)
    if not candidates:
        raise SystemExit("aucune géométrie trouvée : préciser --width et --planes")
    best = candidates[0]
    print(f"géométrie détectée : {best.width}×{best.height}, {best.planes} plans, "
          f"{best.layout}, pas {best.stride} (note {best.score:.2f})")
    return (data, best.offset, best.width, best.height, best.planes,
            best.layout, best.stride)


def cmd_screen(args) -> int:
    data, offset, width, height, planes, layout, stride = _geometry(args)
    stride = stride or (width + 7) // 8
    index = planar.decode_indices(data, offset, width, height, planes,
                                  layout, stride)
    palette = (planar.read_palette(data, args.palette_offset,
                                   args.palette_count or (1 << planes))
               if args.palette_offset >= 0 else None)
    if palette is None:
        candidates = planar.scan_palettes(data, count=1 << planes, limit=8)
        best, _ = planar.best_palette(index, candidates)
        palette = best.palette if best else planar.DEFAULT_PALETTE
        if best:
            print(f"palette : 0x0RGB à 0x{best.offset:X}")
    image = planar.render_screen(data, offset, width, height, planes, layout,
                                 stride, palette)
    save_image(args.output, image)
    density = [float((index >> bit & 1).mean()) for bit in range(planes)]
    print(f"écrit {args.output} — densité par plan : "
          f"{', '.join(f'{value:.3f}' for value in density)}")
    return 0


def cmd_sprites(args) -> int:
    data, offset, width, height, planes, layout, stride = _geometry(args)
    stride = stride or (width + 7) // 8
    index = planar.decode_indices(data, offset, width, height, planes,
                                  layout, stride)
    palette = (planar.read_palette(data, args.palette_offset,
                                   args.palette_count or (1 << planes))
               if args.palette_offset >= 0 else None)
    if palette is None:
        candidates = planar.scan_palettes(data, count=1 << planes, limit=8)
        best, _ = planar.best_palette(index, candidates)
        palette = best.palette if best else planar.DEFAULT_PALETTE
    sprites = amigasprites.components(index, min_area=args.min_area,
                                      close_radius=args.close_radius)
    grid = amigasprites.detect_grid(index)
    shifts = amigasprites.detect_preshift(sprites)
    amigasprites.export_sheet(sprites, palette, args.output,
                              columns=max(1, args.columns))
    print(f"{len(sprites)} sprite(s) → {args.output}")
    print(f"grille : {grid.cell_w}×{grid.cell_h} (note {grid.score:.2f})")
    if shifts:
        print(f"pré-décalages : {len(shifts)} paire(s), "
              f"premier pas {shifts[0]['shift']}")
    return 0


def cmd_hunk(args) -> int:
    parsed = hunk.parse(_read(args.file), base=args.base)
    print(json.dumps(parsed.summary(), indent=2, ensure_ascii=False))
    return 0


def cmd_copper(args) -> int:
    data = _read(args.file)
    lists = copper.find_lists(data, limit=args.limit)
    if not lists:
        print("aucune liste copper reconnue")
        return 1
    print(json.dumps([item.summary() for item in lists], indent=2,
                     ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="liste un disque Amiga")
    p.add_argument("disk")
    p.add_argument("--depth", type=int, default=4)
    p.set_defaults(function=cmd_list)

    p = sub.add_parser("extract", help="extrait un fichier d'un disque")
    p.add_argument("disk")
    p.add_argument("node")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(function=cmd_extract)

    p = sub.add_parser("nested", help="décompresse les blocs imbriqués")
    p.add_argument("file")
    p.add_argument("-o", "--output")
    p.add_argument("--depth", type=int, default=4)
    p.add_argument("--key", type=lambda v: int(v, 0), default=0)
    p.set_defaults(function=cmd_nested)

    p = sub.add_parser("screen", help="rend un écran planaire")
    p.add_argument("file")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--offset", type=lambda v: int(v, 0), default=0)
    p.add_argument("--width", type=int, default=0)
    p.add_argument("--height", type=int, default=256)
    p.add_argument("--planes", type=int, default=0)
    p.add_argument("--layout", choices=("row", "plane"), default="")
    p.add_argument("--stride", type=int, default=0)
    p.add_argument("--palette-offset", type=lambda v: int(v, 0), default=-1)
    p.add_argument("--palette-count", type=int, default=0)
    p.set_defaults(function=cmd_screen)

    p = sub.add_parser("sprites", help="découpe une planche de sprites")
    p.add_argument("file")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--offset", type=lambda v: int(v, 0), default=0)
    p.add_argument("--width", type=int, default=0)
    p.add_argument("--height", type=int, default=256)
    p.add_argument("--planes", type=int, default=0)
    p.add_argument("--layout", choices=("row", "plane"), default="")
    p.add_argument("--stride", type=int, default=0)
    p.add_argument("--palette-offset", type=lambda v: int(v, 0), default=-1)
    p.add_argument("--palette-count", type=int, default=0)
    p.add_argument("--min-area", type=int, default=8)
    p.add_argument("--close-radius", type=int, default=1)
    p.add_argument("--columns", type=int, default=8)
    p.set_defaults(function=cmd_sprites)

    p = sub.add_parser("hunk", help="analyse un exécutable hunk")
    p.add_argument("file")
    p.add_argument("--base", type=lambda v: int(v, 0), default=0x8000)
    p.set_defaults(function=cmd_hunk)

    p = sub.add_parser("copper", help="cherche les listes copper")
    p.add_argument("file")
    p.add_argument("--limit", type=int, default=4)
    p.set_defaults(function=cmd_copper)

    args = parser.parse_args(argv)
    return args.function(args)


if __name__ == "__main__":
    sys.exit(main())
