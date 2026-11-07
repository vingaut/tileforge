#!/usr/bin/env python3
"""Rend un bloc de données (compressé ou non) en planche PNG, pour vérifier.

    python tools/render_blob.py rom.md 0x1234 --compress nemesis --format megadrive -o essai.png
    python tools/render_blob.py rom.bin 0x8000 --compress lz2 --format snes_4bpp -o essai.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tileforge.core import archives  # noqa: E402
from tileforge.core import compression as C  # noqa: E402
from tileforge.core.formats import FORMATS_BY_KEY, load_raw_bank  # noqa: E402
from tileforge.core.image import save_image  # noqa: E402
from tileforge.core.palettes import BUILTIN_PALETTES  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Rend un bloc en planche PNG")
    parser.add_argument("rom")
    parser.add_argument("offset", type=lambda v: int(v, 0))
    parser.add_argument("--member", default="",
                        help="membre à lire dans une archive zip/7z")
    parser.add_argument("--compress", default="", help="kosinski, nemesis, lz2…")
    parser.add_argument("--format", default="snes_4bpp")
    parser.add_argument("--palette", default="")
    parser.add_argument("--per-row", type=int, default=16)
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("-o", "--output", default="blob.png")
    args = parser.parse_args(argv)

    data = archives.read_rom(args.rom, args.member)
    if args.compress:
        data = C.decompress(args.compress, data, args.offset)
        offset = 0
        print(f"décompressé : {len(data)} octets")
    else:
        offset = args.offset

    fmt = FORMATS_BY_KEY[args.format]
    count = args.count or (len(data) - offset) // fmt.real_bytes
    count = min(count, 4096)
    palette = BUILTIN_PALETTES.get(args.palette) if args.palette else None
    bank = load_raw_bank(None, offset, count, fmt, per_row=args.per_row, gap=1,
                         palette=palette, data=data)
    save_image(args.output, bank.image)
    print(f"{count} tuiles → {args.output} ({bank.image.w}×{bank.image.h})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
