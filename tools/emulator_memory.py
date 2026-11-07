#!/usr/bin/env python3
"""Lit la mémoire décodée par un émulateur libretro.

Quand un jeu compresse ses graphismes avec un algorithme maison, l'analyse
statique de la ROM peut échouer. Ce script lance la ROM dans un cœur libretro,
avance de quelques centaines de trames, puis écrit la RAM système, la VRAM et
la SRAM dans un dossier. Les fichiers produits se rouvrent comme n'importe
quelle banque brute dans TileForge.

Exemples :

    python tools/emulator_memory.py --list-cores

    python tools/emulator_memory.py \\
        --core ~/.config/retroarch/cores/mgba_libretro.so \\
        --rom jeu.gba --frames 900 --buttons "start@120-140" \\
        --output memoire/jeu --screenshot

    python tools/emulator_memory.py --core ... --rom jeu.sfc \\
        --frames 600 --scan --tile-format snes_4bpp

Le cœur et la ROM ne sont pas fournis : utilisez ceux que vous possédez.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tileforge.core import emulation  # noqa: E402


def _print_cores(cores) -> None:
    if not cores:
        print("Aucun cœur libretro trouvé.")
        print("Dossiers cherchés :")
        for folder in emulation.default_core_paths():
            print(f"  {folder}")
        print("Définissez TILEFORGE_CORES ou passez --core CHEMIN.")
        return
    for core in cores:
        system = core.system or "machine inconnue"
        print(f"{system:12s}  {core.path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lit la mémoire d'un jeu exécuté dans un émulateur libretro.")
    parser.add_argument("--list-cores", action="store_true",
                        help="liste les cœurs installés et quitte")
    parser.add_argument("--core", help="chemin du cœur libretro (.so, .dll)")
    parser.add_argument("--rom", help="ROM à exécuter (archive zip/7z acceptée)")
    parser.add_argument("--archive-member", default="",
                        help="membre à lire dans l'archive (défaut : automatique)")
    parser.add_argument("--system-dir", default="",
                        help="dossier des BIOS/firmwares du cœur (Fuse, VICE, Cap32…)")
    parser.add_argument("--import-memory", metavar="FICHIER",
                        help="analyse un dump mémoire existant (.bin brut ou "
                             "manifeste .memory.json) au lieu d'exécuter un cœur")
    parser.add_argument("--base", type=lambda value: int(value, 0), default=0,
                        help="adresse de base d'un dump brut (défaut : 0)")
    parser.add_argument("--system", default="",
                        help="machine d'un dump importé (gba, snes, atarist…)")
    parser.add_argument("--frames", type=int, default=600,
                        help="nombre de trames à exécuter (défaut : 600)")
    parser.add_argument("--buttons", default="",
                        help='script d’entrée, par exemple "start@120-140,a@200"')
    parser.add_argument("--output", default="",
                        help="dossier de sortie (défaut : memoire/<nom de la ROM>)")
    parser.add_argument("--name", default="", help="nom des fichiers produits")
    parser.add_argument("--screenshot", action="store_true",
                        help="enregistre aussi la dernière image en PNG")
    parser.add_argument("--scan", action="store_true",
                        help="balaye la mémoire avec le moteur de TileForge")
    parser.add_argument("--tile-format", default="",
                        help="format de tuiles pour le balayage")
    parser.add_argument("--compression", default="auto",
                        help="auto, aucune, ou une clé de décompresseur")
    parser.add_argument("--extended", action="store_true",
                        help="essaie aussi les décompresseurs de la famille "
                             "(LC_LZ3, LZ77/LZ11) : plus lent")
    parser.add_argument("--budget", type=float, default=30.0,
                        help="budget du balayage, en secondes")
    parser.add_argument("--json", action="store_true",
                        help="affiche le résultat complet en JSON")
    args = parser.parse_args(argv)

    if args.list_cores:
        _print_cores(emulation.discover_cores())
        return 0

    if args.import_memory:
        try:
            snapshot = emulation.MemorySnapshot.load(args.import_memory)
        except (OSError, ValueError, KeyError) as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            return 1
        if snapshot.system == "" and args.system:
            snapshot.system = args.system
        if args.base:
            for region in snapshot.regions.values():
                region.base = args.base
        result = {"manifest": "", "combined": "", "directory": "",
                  "regions": [region.as_dict()
                              for region in snapshot.regions.values()],
                  "screenshot": ""}
        if args.output:
            result.update(snapshot.save(args.output, name=args.name))
    else:
        if not args.core or not args.rom:
            parser.error("--core et --rom sont nécessaires "
                         "(ou --list-cores, ou --import-memory)")
        output = args.output or str(ROOT / "memoire" / Path(args.rom).stem)
        try:
            result = emulation.run_rom(
                args.core, args.rom, frames=args.frames, buttons=args.buttons,
                output_dir=output, name=args.name, screenshot=args.screenshot,
                member=args.archive_member,
                system_dir=args.system_dir or None)
        except emulation.EmulationError as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            return 1
        snapshot = emulation.MemorySnapshot.load(result["manifest"])
    if args.scan:
        defaults = {"gba": "gba_4bpp", "gameboy": "gameboy",
                    "snes": "snes_4bpp", "nes": "nes",
                    "megadrive": "megadrive", "atarist": "st_sprite_4pl"}
        tile_format = (args.tile_format or defaults.get(snapshot.system)
                       or "snes_4bpp")
        # La mémoire est déjà décompressée : le balayage brut est le défaut.
        if args.compression in ("", "auto", "aucune", "none"):
            from tileforge.core.scan import compressions_for
            keys = (compressions_for(tile_format, extended=True)
                    if args.extended else [])
        else:
            keys = [args.compression]
        result["scan"] = emulation.scan_snapshot(
            snapshot, tile_format, compressions=keys, budget=args.budget,
            max_candidates=8)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    print(f"Cœur      : {snapshot.core or 'import'}")
    print(f"ROM       : {snapshot.rom}")
    print(f"Machine   : {snapshot.system or 'inconnue'}")
    print(f"Trames    : {snapshot.frames}")
    if args.import_memory:
        print(f"Source    : {args.import_memory}")
        if result.get("manifest"):
            print(f"Manifeste : {result['manifest']}")
    else:
        print(f"Dossier   : {result['directory']}")
        print(f"Manifeste : {result['manifest']}")
    for region in snapshot.regions.values():
        print(f"  {region.name:11s} {len(region.data):8d} octets  "
              f"base {region.base:#010x}")
    if result.get("screenshot"):
        print(f"Capture   : {result['screenshot']}")
    if args.scan:
        for region in result["scan"]["regions"]:
            print(f"\n{region['region']} ({region['size']} octets) :")
            if not region["candidates"]:
                print("  aucun candidat")
            for candidate in region["candidates"]:
                print(f"  0x{candidate['offset']:06X}  note {candidate['score']:.3f}  "
                      f"{candidate['size']} octets  {candidate['tile_format']}")
    print("\nOuvrez un fichier .bin comme banque brute dans TileForge, "
          "ou relancez avec --scan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
