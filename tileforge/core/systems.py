"""Catalogue des machines 8/16 bits prises en charge par TileForge.

Chaque entrée décrit une plateforme (console, ordinateur ou borne d'arcade)
avec ses résolutions natives, sa palette, la profondeur typique des tuiles et
les tailles de tuile/métatuile utiles au réassemblage.

Les valeurs sont volontairement conservatrices : une seule résolution très
documentée par machine, ou la liste courte des modes réellement courants.
``bpp`` désigne la profondeur des données de tuile/sprite, pas celle de
l'affichage.  ``colors`` donne le nombre de couleurs simultanées (ou la taille
de palette quand elle est la référence usuelle, comme sur CPS-1 ou Neo Geo).
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Modèle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SystemSpec:
    """Description figée d'une machine et de son format graphique."""

    key: str
    name: str
    family: str
    year: int
    resolutions: tuple[tuple[int, int], ...]
    colors: int
    bpp: int
    tile_sizes: tuple[tuple[int, int], ...]
    notes: str = ""
    pixel_aspect: float = 1.0


FAMILIES: tuple[str, ...] = ("console", "computer", "arcade")


# ---------------------------------------------------------------------------
# Consoles
# ---------------------------------------------------------------------------

SYSTEMS: tuple[SystemSpec, ...] = (
    SystemSpec(
        "atari-2600",
        "Atari 2600 (VCS)",
        "console",
        1977,
        ((160, 192),),
        128,
        1,
        ((8, 8),),
        notes="Pas de framebuffer : playfield 1 bit, sprites de 8 pixels, palette de 128.",
    ),
    SystemSpec(
        "intellivision",
        "Intellivision",
        "console",
        1979,
        ((160, 96),),
        16,
        1,
        ((8, 8),),
        notes="STIC : cartes 8x8 monochromes, deux couleurs par carte, sprites 8x16.",
    ),
    SystemSpec(
        "colecovision",
        "ColecoVision",
        "console",
        1982,
        ((256, 192),),
        16,
        1,
        ((8, 8),),
        notes="VDP TMS9928A : motifs 8x8 en 1 bit, deux couleurs par ligne de huit pixels.",
    ),
    SystemSpec(
        "nes",
        "Nintendo Entertainment System (NES)",
        "console",
        1983,
        ((256, 240),),
        25,
        2,
        ((8, 8),),
        notes="Tuiles 8x8 en 2 plans, quatre couleurs par tuile via les palettes.",
    ),
    SystemSpec(
        "sg-1000",
        "Sega SG-1000",
        "console",
        1983,
        ((256, 192),),
        16,
        1,
        ((8, 8),),
        notes="VDP TMS9918A proche du ColecoVision, tuiles 8x8 en 1 bit.",
    ),
    SystemSpec(
        "pv-1000",
        "Casio PV-1000",
        "console",
        1983,
        ((240, 192),),
        8,
        3,
        ((8, 8),),
        notes="VDP : tuiles 8x8 en 3 plans RGB111, 240x192 et 8 couleurs.",
    ),
    SystemSpec(
        "master-system",
        "Sega Master System",
        "console",
        1985,
        ((256, 192), (256, 224)),
        32,
        4,
        ((8, 8),),
        notes="Mode 4 : tuiles 8x8 en 4 bits, 32 couleurs à l'écran sur 64.",
    ),
    SystemSpec(
        "atari-7800",
        "Atari 7800",
        "console",
        1986,
        ((160, 240), (320, 240)),
        25,
        2,
        ((8, 8),),
        notes="MARIA : 160x240 ou 320x240, jusqu'à 25 couleurs sur une palette de 256.",
    ),
    SystemSpec(
        "pc-engine",
        "PC Engine / TurboGrafx-16",
        "console",
        1987,
        ((256, 240), (320, 240), (352, 240)),
        256,
        4,
        ((8, 8),),
        notes="HuC6260 : tuiles 8x8 en 4 plans, 16 palettes de 16 couleurs.",
    ),
    SystemSpec(
        "mega-drive",
        "Mega Drive / Genesis",
        "console",
        1988,
        ((320, 224), (256, 224)),
        61,
        4,
        ((8, 8),),
        notes="VDP : tuiles 8x8 en 4 bits, 61 couleurs à l'écran sur 64.",
    ),
    SystemSpec(
        "game-boy",
        "Game Boy",
        "console",
        1989,
        ((160, 144),),
        4,
        2,
        ((8, 8),),
        notes="Tuiles 8x8 en 2 plans, quatre nuances de gris sur la DMG.",
    ),
    SystemSpec(
        "atari-lynx",
        "Atari Lynx",
        "console",
        1989,
        ((160, 102),),
        16,
        4,
        ((8, 8),),
        notes="Suzy : sprites matériels de taille variable, écran 160x102 en 16 couleurs.",
    ),
    SystemSpec(
        "snes",
        "Super Nintendo (SNES)",
        "console",
        1990,
        ((256, 224), (512, 224), (256, 239)),
        256,
        4,
        ((8, 8),),
        notes="Mode 1 : tuiles 8x8 en 4 plans, 256 couleurs parmi 32768.",
    ),
    SystemSpec(
        "neo-geo-aes",
        "Neo Geo AES",
        "console",
        1990,
        ((320, 224),),
        4096,
        4,
        ((16, 16),),
        notes="Tuiles 16x16 en 4 bits, palette de 4096 couleurs, sprites jusqu'à 16x512.",
    ),
    SystemSpec(
        "game-gear",
        "Sega Game Gear",
        "console",
        1990,
        ((160, 144),),
        32,
        4,
        ((8, 8),),
        notes="Même VDP que la Master System en 4 bits, écran 160x144.",
    ),
    SystemSpec(
        "supervision",
        "Watara Supervision",
        "console",
        1992,
        ((160, 160),),
        4,
        2,
        ((8, 8),),
        notes="Écran 160x160 en quatre nuances de gris, tuiles 8x8.",
    ),
    SystemSpec(
        "sega-32x",
        "Sega 32X",
        "console",
        1994,
        ((320, 224), (320, 240)),
        32768,
        8,
        ((8, 8),),
        notes="Framebuffer 8 ou 16 bits, 32768 couleurs, tuiles 8x8.",
    ),
    SystemSpec(
        "saturn",
        "Sega Saturn",
        "console",
        1994,
        ((320, 224), (640, 224), (704, 224)),
        16777216,
        8,
        ((8, 8),),
        notes="VDP1/VDP2 : sprites et plans, 320x224 courant, palette 24 bits.",
    ),
    SystemSpec(
        "playstation",
        "Sony PlayStation",
        "console",
        1994,
        ((320, 240), (640, 480), (512, 240), (256, 240)),
        16777216,
        8,
        ((8, 8),),
        notes="GOU : textures 4 ou 8 bits, framebuffer 15 bits, 320x240 courant.",
    ),
    SystemSpec(
        "virtual-boy",
        "Virtual Boy",
        "console",
        1995,
        ((384, 224),),
        4,
        2,
        ((8, 8),),
        notes="Écran LED rouge : quatre nuances, tuiles 8x8 en 2 bits.",
    ),
    SystemSpec(
        "game-boy-color",
        "Game Boy Color",
        "console",
        1998,
        ((160, 144),),
        56,
        2,
        ((8, 8),),
        notes="Tuiles 8x8 en 2 bits, 56 couleurs à l'écran sur 32768.",
    ),
    SystemSpec(
        "game-boy-advance",
        "Game Boy Advance",
        "console",
        2001,
        ((240, 160),),
        32768,
        4,
        ((8, 8),),
        notes="Modes 0 à 2 : tuiles 8x8 en 4 ou 8 bits, 32768 couleurs.",
    ),

    # -----------------------------------------------------------------------
    # Ordinateurs
    # -----------------------------------------------------------------------

    SystemSpec(
        "apple-ii",
        "Apple II",
        "computer",
        1977,
        ((280, 192), (140, 192), (560, 192)),
        16,
        1,
        ((8, 8),),
        notes="HGR 280x192 en 1 bit avec artefacts couleur, 16 couleurs en lo-res.",
    ),
    SystemSpec(
        "atari-8bit",
        "Atari 8-bit (400/800/XL/XE)",
        "computer",
        1979,
        ((320, 192), (160, 192), (80, 192)),
        256,
        2,
        ((8, 8),),
        notes="ANTIC/GTIA : modes bitmap de 320x192 (1 bit) à 80x192 (4 bits).",
    ),
    SystemSpec(
        "vic-20",
        "VIC-20",
        "computer",
        1980,
        ((176, 184),),
        16,
        1,
        ((8, 8),),
        notes="VIC : 22x23 caractères 8x8, 176x184, 16 couleurs.",
    ),
    SystemSpec(
        "zx81",
        "ZX81",
        "computer",
        1981,
        ((256, 192),),
        2,
        1,
        ((8, 8),),
        notes="Pas de mode bitmap : blocs 8x8 monochromes en 32x24 caractères.",
    ),
    SystemSpec(
        "bbc-micro",
        "BBC Micro",
        "computer",
        1981,
        ((640, 256), (320, 256), (160, 256)),
        16,
        2,
        ((8, 8),),
        notes="Modes de 640x256 (2 couleurs) à 160x256 (16 couleurs), tuiles 8x8.",
    ),
    SystemSpec(
        "ibm-cga",
        "IBM PC CGA",
        "computer",
        1981,
        ((320, 200), (640, 200)),
        4,
        2,
        ((8, 8),),
        notes="320x200 en 2 bits (4 couleurs) ou 640x200 en 1 bit, palette de 16.",
    ),
    SystemSpec(
        "pc-8801",
        "NEC PC-8801",
        "computer",
        1981,
        ((640, 400), (640, 200), (320, 200)),
        16,
        4,
        ((8, 8),),
        notes="Mode 640x400 en 16 couleurs (4 plans), tuiles 8x8.",
    ),
    SystemSpec(
        "ti-99-4a",
        "TI-99/4A",
        "computer",
        1981,
        ((256, 192),),
        16,
        1,
        ((8, 8),),
        notes="VDP TMS9918A : tuiles 8x8 en 1 bit, 16 couleurs, sprites 16x16.",
    ),
    SystemSpec(
        "zx-spectrum",
        "ZX Spectrum",
        "computer",
        1982,
        ((256, 192),),
        15,
        1,
        ((8, 8),),
        notes="Attributs par bloc 8x8 : 1 bit par pixel, deux couleurs par case.",
    ),
    SystemSpec(
        "c64",
        "Commodore 64",
        "computer",
        1982,
        ((320, 200), (160, 200)),
        16,
        1,
        ((8, 8),),
        notes="Tuiles 8x8 en 1 bit (2 en multicolore), 16 couleurs.",
    ),
    SystemSpec(
        "dragon-32",
        "Dragon 32 / TRS-80 CoCo",
        "computer",
        1982,
        ((256, 192), (128, 192)),
        4,
        2,
        ((8, 8),),
        notes="MC6847 : 256x192 en 2 couleurs ou 128x192 en 4 couleurs.",
    ),
    SystemSpec(
        "pc-9801",
        "NEC PC-9801",
        "computer",
        1982,
        ((640, 400), (640, 480), (320, 400)),
        16,
        4,
        ((8, 8),),
        notes="640x400 en 16 couleurs (4 plans), tuiles 8x8.",
    ),
    SystemSpec(
        "msx1",
        "MSX1",
        "computer",
        1983,
        ((256, 192),),
        16,
        1,
        ((8, 8),),
        notes="VDP TMS9918A : tuiles 8x8 en 1 bit, 16 couleurs.",
    ),
    SystemSpec(
        "oric-1",
        "Oric-1 / Atmos",
        "computer",
        1983,
        ((240, 200),),
        8,
        1,
        ((8, 8),),
        notes="Hires 240x200 en 1 bit avec attributs, 8 couleurs.",
    ),
    SystemSpec(
        "amstrad-cpc",
        "Amstrad CPC",
        "computer",
        1984,
        ((320, 200), (160, 200), (640, 200)),
        16,
        2,
        ((8, 8),),
        notes="Mode 1 : 320x200 en 4 couleurs, tuiles 8x8 en 2 plans.",
    ),
    SystemSpec(
        "ibm-ega",
        "IBM PC EGA",
        "computer",
        1984,
        ((640, 350), (320, 200), (640, 200), (640, 480)),
        16,
        4,
        ((8, 8),),
        notes="16 couleurs sur 64, 640x350 en 4 plans, tuiles 8x8.",
    ),
    SystemSpec(
        "thomson-mo5",
        "Thomson MO5 / TO7",
        "computer",
        1984,
        ((320, 200),),
        16,
        1,
        ((8, 8),),
        notes="320x200 en 1 bit avec attributs 8x1, palette de 16 couleurs.",
    ),
    SystemSpec(
        "atari-st",
        "Atari ST",
        "computer",
        1985,
        ((320, 200), (640, 200), (640, 400)),
        16,
        4,
        ((8, 8),),
        notes="Tuiles 8x8 en 4 plans (16 couleurs), modes 320x200, 640x200 et 640x400.",
    ),
    SystemSpec(
        "amiga",
        "Commodore Amiga (OCS/AGA)",
        "computer",
        1985,
        ((320, 256), (320, 200), (640, 256), (640, 200), (640, 512)),
        32,
        4,
        ((16, 16), (32, 32)),
        notes="OCS/ECS : 32 couleurs ; AGA monte à 256 couleurs en 8 plans.",
    ),
    SystemSpec(
        "amstrad-pcw",
        "Amstrad PCW",
        "computer",
        1985,
        ((720, 256),),
        2,
        1,
        ((8, 8),),
        notes="Écran monochrome 720x256, texte 90x32 en caractères 8x8.",
    ),
    SystemSpec(
        "c128",
        "Commodore 128",
        "computer",
        1985,
        ((320, 200), (640, 200), (160, 200)),
        16,
        1,
        ((8, 8),),
        notes="VIC-IIe comme le C64, plus un VDC 640x200 en 16 couleurs.",
    ),
    SystemSpec(
        "msx2",
        "MSX2",
        "computer",
        1985,
        ((256, 212), (512, 212), (256, 192)),
        256,
        4,
        ((8, 8),),
        notes="VDP V9938 : 256x212, jusqu'à 256 couleurs (écran 8), tuiles 8x8.",
    ),
    SystemSpec(
        "enterprise-128",
        "Enterprise 128",
        "computer",
        1985,
        ((320, 256), (160, 256), (640, 256), (640, 512)),
        256,
        4,
        ((8, 8),),
        notes="Nick : 320x256 en 4 couleurs, 160x256 en 16, palette de 256.",
    ),
    SystemSpec(
        "coco-3",
        "TRS-80 CoCo 3",
        "computer",
        1986,
        ((320, 200), (640, 200), (320, 225), (256, 225)),
        16,
        4,
        ((8, 8),),
        notes="GIME : 320x200 en 16 couleurs, 640x200 en 4, tuiles 8x8.",
    ),
    SystemSpec(
        "ibm-vga",
        "IBM PC VGA (mode 13h)",
        "computer",
        1987,
        ((320, 200), (640, 480), (320, 240)),
        256,
        8,
        ((8, 8),),
        notes="Mode 13h : 320x200 en 8 bits, 256 couleurs sur une palette 18 bits.",
    ),
    SystemSpec(
        "acorn-archimedes",
        "Acorn Archimedes",
        "computer",
        1987,
        ((640, 256), (320, 256), (640, 480), (800, 600)),
        256,
        8,
        ((8, 8),),
        notes="VIDC : modes 256 couleurs (8 bits), 640x256 courant.",
    ),
    SystemSpec(
        "sharp-x68000",
        "Sharp X68000",
        "computer",
        1987,
        ((768, 512), (512, 512), (256, 256)),
        65536,
        4,
        ((8, 8), (16, 16)),
        notes="Vidéos 768x512, palette 65536, tuiles 8x8 ou 16x16.",
    ),
    SystemSpec(
        "sam-coupe",
        "Sam Coupé",
        "computer",
        1989,
        ((256, 192), (512, 192)),
        16,
        4,
        ((8, 8),),
        notes="Modes 256x192 en 16 couleurs et 512x192 en 4, tuiles 8x8.",
    ),
    SystemSpec(
        "atari-falcon",
        "Atari Falcon",
        "computer",
        1992,
        ((320, 240), (640, 480), (320, 200), (640, 400)),
        65536,
        8,
        ((8, 8),),
        notes="Videl : modes chunky jusqu'à 640x480 en 16 bits (65536 couleurs).",
    ),

    # -----------------------------------------------------------------------
    # Arcade
    # -----------------------------------------------------------------------

    SystemSpec(
        "pac-man",
        "Pac-Man (Namco)",
        "arcade",
        1980,
        ((224, 288),),
        32,
        2,
        ((8, 8),),
        notes="Écran vertical 224x288, tuiles 8x8 en 2 bits, palette fixe de 32 couleurs.",
        pixel_aspect=0.857,
    ),
    SystemSpec(
        "williams",
        "Williams (Defender/Robotron)",
        "arcade",
        1980,
        ((292, 240),),
        16,
        1,
        ((8, 8),),
        notes="Bitmap 292x240 en 1 bit, palette de 16 couleurs, pas de tuiles.",
    ),
    SystemSpec(
        "galaga",
        "Galaga",
        "arcade",
        1981,
        ((288, 224),),
        32,
        2,
        ((8, 8), (16, 16)),
        notes="288x224, tuiles 8x8 et sprites 16x16 en 2 bits.",
        pixel_aspect=0.857,
    ),
    SystemSpec(
        "donkey-kong",
        "Donkey Kong (Nintendo)",
        "arcade",
        1981,
        ((224, 256),),
        16,
        2,
        ((8, 8),),
        notes="Écran vertical 224x256, tuiles 8x8 en 2 bits, 16 couleurs.",
        pixel_aspect=0.857,
    ),
    SystemSpec(
        "nintendo-vs-system",
        "Nintendo Vs. System",
        "arcade",
        1984,
        ((256, 240),),
        25,
        2,
        ((8, 8),),
        notes="Matériel NES en arcade, écran 256x240, tuiles 8x8 en 2 plans.",
    ),
    SystemSpec(
        "sega-system-16",
        "Sega System 16",
        "arcade",
        1985,
        ((320, 224),),
        4096,
        4,
        ((8, 8), (16, 16)),
        notes="320x224, tuiles 8x8 et sprites 16x16 en 4 bits.",
        pixel_aspect=0.933,
    ),
    SystemSpec(
        "konami-gx400",
        "Konami GX400",
        "arcade",
        1985,
        ((256, 224),),
        512,
        4,
        ((8, 8), (16, 16)),
        notes="256x224, tuiles 8x8 et sprites 16x16 en 4 bits, palette de 512.",
    ),
    SystemSpec(
        "atari-gauntlet",
        "Atari Gauntlet",
        "arcade",
        1985,
        ((336, 240),),
        16,
        2,
        ((8, 8),),
        notes="336x240, tuiles 8x8 en 2 bits, 16 couleurs, jusqu'à quatre joueurs.",
    ),
    SystemSpec(
        "namco-system-1",
        "Namco System 1",
        "arcade",
        1987,
        ((288, 224),),
        4096,
        4,
        ((8, 8), (16, 16)),
        notes="288x224, tuiles 8x8 et sprites 16x16 en 4 bits, 4096 couleurs.",
        pixel_aspect=0.857,
    ),
    SystemSpec(
        "irem-m72",
        "Irem M72",
        "arcade",
        1987,
        ((384, 256),),
        512,
        4,
        ((8, 8),),
        notes="384x256, tuiles 8x8 en 4 bits, palette de 512 couleurs.",
        pixel_aspect=0.889,
    ),
    SystemSpec(
        "data-east",
        "Data East (Karnov)",
        "arcade",
        1987,
        ((256, 240),),
        1024,
        4,
        ((8, 8), (16, 16)),
        notes="256x240, tuiles 8x8 et sprites 16x16 en 4 bits, palette de 1024.",
    ),
    SystemSpec(
        "cps1",
        "Capcom CPS-1",
        "arcade",
        1988,
        ((384, 224),),
        4096,
        4,
        ((16, 16),),
        notes="Tuiles 16x16 en 4 bits, palette de 4096 couleurs, écran 384x224.",
        pixel_aspect=0.857,
    ),
    SystemSpec(
        "sega-system-24",
        "Sega System 24",
        "arcade",
        1988,
        ((496, 384),),
        4352,
        8,
        ((8, 8),),
        notes="Carte à framebuffer : 496x384, tuiles 8x8, 4352 couleurs à l'écran.",
    ),
    SystemSpec(
        "namco-system-2",
        "Namco System 2",
        "arcade",
        1988,
        ((288, 224),),
        4096,
        4,
        ((8, 8), (16, 16)),
        notes="288x224, trois plans de tuiles 8x8 et sprites 16x16 en 4 bits.",
        pixel_aspect=0.857,
    ),
    SystemSpec(
        "taito-f2",
        "Taito F2",
        "arcade",
        1988,
        ((320, 224),),
        4096,
        4,
        ((8, 8), (16, 16)),
        notes="320x224, tuiles 8x8 et sprites 16x16 en 4 bits, 4096 couleurs.",
        pixel_aspect=0.933,
    ),
    SystemSpec(
        "toaplan",
        "Toaplan (Truxton)",
        "arcade",
        1988,
        ((320, 240),),
        256,
        4,
        ((8, 8), (16, 16)),
        notes="Shoot'em ups verticaux 320x240, tuiles 8x8 et sprites 16x16 en 4 bits.",
    ),
    SystemSpec(
        "neo-geo-mvs",
        "Neo Geo MVS",
        "arcade",
        1990,
        ((320, 224),),
        4096,
        4,
        ((16, 16),),
        notes="Tuiles 16x16 en 4 bits, sprites jusqu'à 16x512, 4096 couleurs.",
        pixel_aspect=0.933,
    ),
    SystemSpec(
        "irem-m92",
        "Irem M92",
        "arcade",
        1991,
        ((320, 240),),
        4096,
        4,
        ((8, 8), (16, 16)),
        notes="320x240, tuiles 8x8 et sprites 16x16 en 4 bits, 4096 couleurs.",
    ),
    SystemSpec(
        "sega-model-1",
        "Sega Model 1",
        "arcade",
        1992,
        ((496, 384),),
        65536,
        8,
        ((8, 8),),
        notes="3D polygonale 496x384, framebuffer 16 bits, décors en tuiles 8x8.",
    ),
    SystemSpec(
        "cps2",
        "Capcom CPS-2",
        "arcade",
        1993,
        ((384, 224),),
        4096,
        4,
        ((16, 16),),
        notes="Évolution du CPS-1 : 384x224, tuiles 16x16 en 4 bits, 4096 couleurs.",
        pixel_aspect=0.857,
    ),
    SystemSpec(
        "sega-model-2",
        "Sega Model 2",
        "arcade",
        1993,
        ((496, 384),),
        65536,
        8,
        ((8, 8),),
        notes="3D texturée 496x384, framebuffer 16 bits, décors en tuiles 8x8.",
    ),
    SystemSpec(
        "psikyo",
        "Psikyo",
        "arcade",
        1993,
        ((320, 224),),
        4096,
        4,
        ((8, 8), (16, 16)),
        notes="Shoot'em ups 320x224, tuiles 8x8 et sprites 16x16 en 4 bits.",
        pixel_aspect=0.933,
    ),
    SystemSpec(
        "cave-cv1000",
        "Cave CV-1000",
        "arcade",
        1995,
        ((320, 240),),
        4096,
        4,
        ((8, 8), (16, 16)),
        notes="Shoot'em ups verticaux 320x240, tuiles 8x8 et sprites 16x16 en 4 bits.",
    ),
    SystemSpec(
        "cps3",
        "Capcom CPS-3",
        "arcade",
        1996,
        ((384, 224),),
        32768,
        8,
        ((16, 16),),
        notes="384x224, graphismes 6 ou 8 bits, 32768 couleurs à l'écran.",
        pixel_aspect=0.857,
    ),
    SystemSpec(
        "sega-naomi",
        "Sega NAOMI",
        "arcade",
        1998,
        ((640, 480),),
        16777216,
        8,
        ((8, 8),),
        notes="Dérivée Dreamcast : 640x480, textures 8 ou 16 bits, 16,7 M couleurs.",
    ),
)


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

SYSTEMS_BY_KEY: dict[str, SystemSpec] = {system.key: system for system in SYSTEMS}


def _build_resolutions() -> dict[tuple[int, int], list[SystemSpec]]:
    """Regroupe les systèmes par résolution native, dans l'ordre du catalogue."""
    index: dict[tuple[int, int], list[SystemSpec]] = {}
    for system in SYSTEMS:
        for resolution in system.resolutions:
            index.setdefault(resolution, []).append(system)
    return index


RESOLUTIONS: dict[tuple[int, int], list[SystemSpec]] = _build_resolutions()


# ---------------------------------------------------------------------------
# Auto-vérification
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # auto-vérification : clés uniques, familles valides, résolutions cohérentes
    counts = dict.fromkeys(FAMILIES, 0)
    for spec in SYSTEMS:
        counts[spec.family] += 1

    print("Systèmes par famille :")
    for family in FAMILIES:
        print(f"  {family:9s} : {counts[family]}")
    print(f"  {'total':9s} : {len(SYSTEMS)}")

    assert len({spec.key for spec in SYSTEMS}) == len(SYSTEMS), "clé dupliquée"
    assert all(spec.family in FAMILIES for spec in SYSTEMS), "famille inconnue"
    assert all(
        0 < width <= 1024 and 0 < height <= 1024
        for spec in SYSTEMS
        for width, height in spec.resolutions
    ), "résolution hors bornes"
    assert all(
        width > 0 and height > 0
        for spec in SYSTEMS
        for width, height in spec.tile_sizes
    ), "taille de tuile invalide"
    assert all(spec.colors > 0 for spec in SYSTEMS), "palette invalide"
    assert all(spec.bpp in (1, 2, 3, 4, 8) for spec in SYSTEMS), "bpp invalide"

    assert list(SYSTEMS_BY_KEY) == [spec.key for spec in SYSTEMS], "index par clé incohérent"
    assert list(SYSTEMS_BY_KEY.values()) == list(SYSTEMS), "index par clé altéré"
    assert all(resolution in RESOLUTIONS for spec in SYSTEMS for resolution in spec.resolutions)
    for resolution, specs in RESOLUTIONS.items():
        expected = [spec for spec in SYSTEMS if resolution in spec.resolutions]
        assert specs == expected, f"index de résolution incohérent pour {resolution}"

    family_rank = {family: rank for rank, family in enumerate(FAMILIES)}
    ordering = [(family_rank[spec.family], spec.year) for spec in SYSTEMS]
    assert ordering == sorted(ordering), "catalogue non trié par famille puis année"

    print("Auto-vérification OK.")
