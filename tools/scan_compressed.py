#!/usr/bin/env python3
"""Cherche les blocs de graphismes compressés dans une ROM.

Le script essaie chaque décompresseur à chaque position du fichier et ne garde
que les résultats plausibles : taille suffisante, multiple de la taille d'une
tuile, et contenu qui ressemble à des graphismes.

    python tools/scan_compressed.py megadrive/*.md snes/*.bin
    python tools/scan_compressed.py --format kosinski --min 4096 rom.bin
    python tools/scan_compressed.py --extract 0x1234 --format nemesis rom.md sortie.bin

Les résultats servent ensuite à ouvrir la banque dans TileForge avec l'offset
indiqué et le format de compression correspondant.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tileforge.core import archives  # noqa: E402
from tileforge.core import compression as C  # noqa: E402
from tileforge.core.formats import FORMATS_BY_KEY  # noqa: E402


def scan(data: bytes, key: str, start: int = 0, end: int | None = None,
         min_size: int = 512, max_size: int = 1 << 18,
         fmt_key: str = "megadrive", step: int = 1, threshold: float = 0.45,
         progress=None) -> list[dict]:
    """Balaye un décompresseur et renvoie les blocs plausibles.

    Délègue au moteur commun :mod:`tileforge.core.scan`, pour que la ligne de
    commande et l'interface donnent exactement les mêmes résultats.
    """
    from tileforge.core.scan import Scanner

    fmt = FORMATS_BY_KEY.get(fmt_key)
    if fmt is None:
        raise SystemExit(f"format de tuile inconnu : {fmt_key}")
    scanner = Scanner(data, [fmt], [key])
    candidates = scanner.scan_compressed(
        key, start=start, end=end, step=step, threshold=threshold,
        max_size=max_size, min_size=min_size,
        progress=progress)
    candidates.sort(key=lambda c: -c.score)
    return [{"offset": c.offset, "size": c.size, "format": key,
             "score": c.score} for c in candidates]


def extract(path: str, offset: int, key: str, output: str,
            member: str = "") -> int:
    data = archives.read_rom(path, member)
    result = C.decompress(key, data, offset)
    with open(output, "wb") as f:
        f.write(result)
    return len(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cherche des blocs compressés")
    parser.add_argument("files", nargs="*", help="ROMs à analyser")
    parser.add_argument("--member", default="",
                        help="membre à lire dans une archive zip/7z")
    parser.add_argument("--format", default="all",
                        choices=["all"] + [d.key for d in C.DECOMPRESSORS])
    parser.add_argument("--min", type=int, default=1024, help="taille minimale")
    parser.add_argument("--max", type=int, default=1 << 18, help="taille maximale")
    parser.add_argument("--start", type=lambda v: int(v, 0), default=0)
    parser.add_argument("--end", type=lambda v: int(v, 0), default=None)
    parser.add_argument("--step", type=int, default=1)
    parser.add_argument("--tile-format", default="",
                        help="format de tuile pour la notation (défaut : megadrive ou snes_4bpp)")
    parser.add_argument("--threshold", type=float, default=0.6,
                        help="note graphique minimale (0 à 1)")
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--extract", type=lambda v: int(v, 0), default=None,
                        help="extrait à cet offset au lieu de scanner")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)

    if args.extract is not None:
        if not args.files or args.format == "all":
            parser.error("--extract demande un fichier et --format")
        out = args.output or f"extract_{args.extract:x}.bin"
        size = extract(args.files[0], args.extract, args.format, out,
                       args.member)
        print(f"{args.format} @ 0x{args.extract:X} → {size} octets dans {out}")
        return 0

    formats = ([d.key for d in C.DECOMPRESSORS] if args.format == "all"
               else [args.format])
    for path in args.files:
        source = archives.open_rom(path, args.member)
        data = source.data
        print(f"\n=== {source.display_name} ({len(data)} octets) ===")
        for key in formats:
            started = time.time()
            fmt_key = args.tile_format or ("snes_4bpp" if "snes" in path.lower()
                                           else "megadrive")
            hits = scan(data, key, args.start, args.end, args.min, args.max,
                        fmt_key, args.step, args.threshold)
            elapsed = time.time() - started
            if not hits:
                print(f"  {key:10s} : rien ({elapsed:.1f} s)")
                continue
            print(f"  {key:10s} : {len(hits)} bloc(s) en {elapsed:.1f} s")
            for hit in hits[:args.top]:
                print(f"      offset 0x{hit['offset']:06X}  "
                      f"{hit['size']:7d} octets  note {hit['score']:.2f}  "
                      f"({hit['size'] // 32} tuiles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
