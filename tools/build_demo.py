#!/usr/bin/env python3
"""Construit la démonstration TileForge sur plusieurs systèmes.

Choisit un jeu représentatif par machine, l'exécute dans un cœur libretro,
puis délègue à :mod:`tools.demo_extract` l'écriture des planches de tuiles et
des propositions de sprites.

    python tools/build_demo.py \\
        --roms-root /path/to/roms \\
        --cores /path/to/libretro-cores \\
        --output ../tileforge-demo

Les ROMs ne sont jamais copiées : seules les images produites, un extrait de
banque et les rapports JSON sont écrits.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from demo_extract import extract  # noqa: E402

#: Un jeu par machine. Les chemins sont relatifs à ``--roms-root``.
DEMO: list[dict] = [
    {
        "system": "nes", "core": "fceumm_libretro.so",
        "sprite_box": (24, 176, 40, 40),
        "rom": "nes/Super Mario Bros (E).nes",
        "frames": 900, "buttons": "start@300-320",
        "title": "Super Mario Bros. (NES)",
    },
    {
        "system": "snes", "core": "snes9x_libretro.so",
        "sprite_box": (112, 168, 40, 40),
        "rom": "snes/Super Mario World (U) [!].zip",
        "frames": 1500,
        "buttons": "start@300-320,a@600-620,start@700-720,start@900-920",
        "title": "Super Mario World (SNES)",
    },
    {
        "system": "megadrive", "core": "picodrive_libretro.so",
        "sprite_box": (16, 160, 64, 64),
        "rom": "megadrive/Sonic the Hedgehog (JUE) [!].zip",
        "frames": 1200, "buttons": "start@300-320,start@600-620",
        "title": "Sonic the Hedgehog (Mega Drive)",
    },
    {
        "system": "gameboy", "core": "sameboy_libretro.so",
        "sprite_box": (12, 32, 32, 32),
        "rom": "gb/Legend of Zelda, The - Link's Awakening (France).zip",
        "frames": 1200, "buttons": "start@300-320,start@700-720",
        "title": "The Legend of Zelda: Link's Awakening (Game Boy)",
    },
    {
        "system": "gba", "core": "mgba_libretro.so",
        "sprite_box": (8, 96, 48, 48),
        "rom": "gba/Classic NES Series - Super Mario Bros. (USA, Europe).zip",
        "frames": 900, "buttons": "start@300-320,a@600-620",
        "title": "Classic NES: Super Mario Bros. (GBA)",
    },
    {
        "system": "mastersystem", "core": "picodrive_libretro.so",
        "sprite_box": (44, 148, 40, 40),
        "rom": "mastersystem/Alex Kidd in Miracle World (1986)(Sega)(US).bin",
        "frames": 900, "buttons": "start@300-320",
        "title": "Alex Kidd in Miracle World (Master System)",
    },
    {
        "system": "pcengine", "core": "mednafen_pce_fast_libretro.so",
        "sprite_box": (16, 168, 64, 64),
        "rom": "pcengine/Bonk's Adventure (1990)(Hudson - NEC)(US).pce",
        "frames": 900, "buttons": "start@300-320",
        "title": "Bonk's Adventure (PC Engine)",
    },
    {
        "system": "zxspectrum", "core": "fuse_libretro.so",
        "sprite_box": (260, 96, 40, 40),
        "rom": "zxspectrum/Manic Miner (1983)(Bug-Byte).z80",
        "frames": 600, "buttons": "",
        "title": "Manic Miner (ZX Spectrum)",
    },
    {
        "system": "amstradcpc", "core": "crocods_libretro.so",
        "rom": "amstradcpc/Bubble Bobble (1987)(Firebird Software)[cr Enrique Soft].dsk",
        "frames": 1500, "buttons": "a@60-80,a@300-320",
        "title": "Bubble Bobble (Amstrad CPC)",
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Construit la démo TileForge")
    parser.add_argument("--roms-root", required=True)
    parser.add_argument("--cores", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--system-dir", default="")
    parser.add_argument("--only", nargs="*", default=[],
                        help="limiter à certains systèmes")
    parser.add_argument("--source", default="screenshot",
                        choices=["screenshot", "memory", "rom", "auto"])
    args = parser.parse_args(argv)

    roms = Path(args.roms_root).expanduser()
    cores = Path(args.cores).expanduser()
    output = Path(args.output).expanduser()
    output.mkdir(parents=True, exist_ok=True)
    system_dir = args.system_dir or str(cores / "system")

    reports = []
    for entry in DEMO:
        if args.only and entry["system"] not in args.only:
            continue
        core = cores / entry["core"]
        rom = roms / entry["rom"]
        if not core.exists() or not rom.exists():
            print(f"[skip] {entry['system']} : cœur ou ROM absent")
            continue
        print(f"[{entry['system']}] {entry['title']}")
        try:
            report = extract(
                entry["system"], str(core), str(rom),
                output / entry["system"], frames=entry["frames"],
                buttons=entry["buttons"], system_dir=system_dir,
                source=args.source, title=entry["title"],
                sprite_box=entry.get("sprite_box"))
        except Exception as exc:  # noqa: BLE001 - une machine ne bloque pas les autres
            print(f"  [erreur] {exc}")
            continue
        reports.append(report)
        print(f"  tuiles={report.get('tiles', 0)} "
              f"sprites={report.get('sprites', 0)}")

    (output / "demo.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=1), encoding="utf-8")
    (output / "README.md").write_text(render_index(reports), encoding="utf-8")
    print(f"\n{len(reports)} système(s) traité(s) dans {output}")
    return 0 if reports else 1


def render_index(reports: list[dict]) -> str:
    lines = [
        "# Démonstration TileForge — graphismes extraits de jeux 8/16 bits",
        "",
        "Chaque sous-dossier correspond à une machine. Pour chaque jeu :",
        "",
        "- `ecran.png` : capture de l'émulateur au moment du prélèvement ;",
        "- `tuiles.png` : planche de tuiles découpée par TileForge ;",
        "- `sprites.png` : extrait manuel de la zone de sprite (ou "
        "propositions automatiques) ;",
        "- `sprites_solveur.png` : propositions d'assemblage (grille 2 × 2) ;",
        "- `emulateur/` : mémoire brute lue dans le cœur libretro et capture ;",
        "- `rapport.json` : source, format, offset, note, notes.",
        "",
        "| Machine | Jeu | Source | Tuiles | Sprites |",
        "|---|---|---|---|---|",
    ]
    for report in reports:
        lines.append(
            f"| {report['system']} | {report['game']} | {report['source']} | "
            f"{report.get('tiles', 0)} | {report.get('sprites', 0)} |")
    lines.extend([
        "",
        "Les ROMs ne sont pas incluses. Les images sont produites localement "
        "par TileForge à partir du dossier de ROMs fourni.",
        "",
        "## Reproduire",
        "",
        "```bash",
        "python tools/build_demo.py \\",
        '    --roms-root /path/to/roms \\',
        "    --cores /path/to/libretro-cores \\",
        "    --output ../tileforge-demo",
        "```",
        "",
        "## Méthode",
        "",
        "La capture d'écran est la source la plus fiable pour les machines dont "
        "le cœur n'expose pas la VRAM (ZX Spectrum, CPC) et pour obtenir des "
        "couleurs justes. Les cœurs qui exposent la mémoire (Snes9x, Picodrive, "
        "SameBoy, mGBA, Mednafen PCE) écrivent aussi leurs régions dans "
        "`emulateur/` : c'est la matière première de l'extraction mémoire, à "
        "réutiliser avec `tileforge_emulator_memory` ou "
        "`tools/emulator_memory.py --import-memory`.",
        "",
        "Les sprites sont des **propositions** du solveur de TileForge, pas une "
        "vérité terrain validée par l'utilisateur.",
        "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
