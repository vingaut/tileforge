"""Palettes des machines 8/16 bits et conversions de couleur.

Les banques brutes ne contiennent que des indices : c'est la palette qui donne
l'image.  Ce module fournit les tables usuelles (Atari ST, Amiga, NES, Game Boy,
Master System, Mega Drive, PC Engine, CPC, C64, ZX, EGA/CGA) et les conversions
entre formats historiques.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


def st_to_rgb(word: int) -> tuple[int, int, int]:
    """Mot 0x0RGB Atari ST (3 bits par composante) vers RGB 8 bits."""
    return (((word >> 8) & 7) * 255 // 7,
            ((word >> 4) & 7) * 255 // 7,
            (word & 7) * 255 // 7)


def rgb_to_st(rgb) -> int:
    r, g, b = (min(255, max(0, int(v))) for v in rgb[:3])
    return ((r * 7 // 255) << 8) | ((g * 7 // 255) << 4) | (b * 7 // 255)


def amiga_to_rgb(word: int) -> tuple[int, int, int]:
    """Mot 0x0RGB Amiga (4 bits par composante) vers RGB 8 bits."""
    return (((word >> 8) & 0xF) * 17, ((word >> 4) & 0xF) * 17, (word & 0xF) * 17)


def rgb_to_amiga(rgb) -> int:
    r, g, b = (min(255, max(0, int(v))) for v in rgb[:3])
    return ((r * 15 // 255) << 8) | ((g * 15 // 255) << 4) | (b * 15 // 255)


def rgb_to_hex(rgb) -> str:
    return f"#{int(rgb[0]):02x}{int(rgb[1]):02x}{int(rgb[2]):02x}"


def hex_to_rgb(text: str) -> tuple[int, int, int]:
    text = text.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


# ---------------------------------------------------------------------------
# Classe Palette
# ---------------------------------------------------------------------------


class Palette:
    """Liste ordonnée de couleurs RGB (index 0 en premier)."""

    def __init__(self, colors, name: str = "palette", transparent: int | None = 0):
        self.colors = [tuple(int(v) for v in c[:3]) for c in colors]
        self.name = name
        self.transparent = transparent

    def __len__(self) -> int:
        return len(self.colors)

    def __getitem__(self, i: int):
        return self.colors[i % len(self.colors)]

    def __iter__(self):
        return iter(self.colors)

    def rgba(self, i: int) -> tuple[int, int, int, int]:
        c = self.colors[i % len(self.colors)]
        a = 0 if (self.transparent is not None and i == self.transparent) else 255
        return (c[0], c[1], c[2], a)

    def with_transparent(self, index: int | None) -> Palette:
        p = Palette(self.colors, self.name, index)
        return p

    def extended(self, n: int) -> list[tuple[int, int, int]]:
        """Complète la palette jusqu'à n couleurs (répétition de la dernière)."""
        out = list(self.colors)
        while len(out) < n:
            out.append(out[-1] if out else (0, 0, 0))
        return out[:n]

    def to_st_words(self) -> list[int]:
        return [rgb_to_st(c) for c in self.colors]

    def copy(self) -> Palette:
        return Palette(self.colors, self.name, self.transparent)

    # -- fichiers -----------------------------------------------------------

    @classmethod
    def from_jasc_pal(cls, path: str) -> Palette:
        with open(path, encoding="latin-1") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        colors = []
        i = 0
        while i + 2 < len(lines):
            try:
                r, g, b = (int(v) for v in lines[i:i + 3])
                colors.append((r, g, b))
                i += 3
            except ValueError:
                i += 1
        return cls(colors or [(0, 0, 0)], os.path.basename(path))

    @classmethod
    def from_gpl(cls, path: str) -> Palette:
        colors = []
        with open(path, encoding="latin-1") as f:
            for line in f:
                parts = line.split()
                if len(parts) == 3 and all(p.isdigit() for p in parts):
                    colors.append(tuple(int(p) for p in parts))
        return cls(colors or [(0, 0, 0)], os.path.basename(path))

    @classmethod
    def load(cls, path: str) -> Palette:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".gpl":
            return cls.from_gpl(path)
        return cls.from_jasc_pal(path)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="ascii") as f:
            f.write(f"JASC-PAL\n0100\n{len(self.colors)}\n")
            for c in self.colors:
                f.write(f"{c[0]} {c[1]} {c[2]}\n")


# ---------------------------------------------------------------------------
# Palettes intégrées
# ---------------------------------------------------------------------------

#: Palette Atari ST du jeu Barbarian (écran 1) — couleurs 12 à 15 pour les sprites.
ST_BARBARIAN = Palette([st_to_rgb(w) for w in
                        (0x000, 0x430, 0x320, 0x542, 0x230, 0x777, 0x047, 0x370,
                         0x051, 0x500, 0x700, 0x740, 0x760, 0x444, 0x006, 0x777)],
                       "Atari ST — Barbarian")

#: Palette 16 couleurs Atari ST « standard » (celle du TOS, utile pour les écrans).
ST_DEFAULT = Palette([st_to_rgb(w) for w in
                      (0x000, 0x700, 0x070, 0x770, 0x007, 0x707, 0x077, 0x777,
                       0x333, 0x733, 0x373, 0x773, 0x337, 0x737, 0x377, 0xFFF)],
                     "Atari ST — 16 couleurs")

#: Palette 32 couleurs Amiga (OCS) par défaut.
AMIGA_OCS = Palette([amiga_to_rgb(w) for w in
                     (0x000, 0x333, 0x555, 0x777, 0x999, 0xBBB, 0xDDD, 0xFFF,
                      0x800, 0xA00, 0xC00, 0xE00, 0x080, 0x0A0, 0x0C0, 0x0E0,
                      0x008, 0x00A, 0x00C, 0x00E, 0x880, 0xA80, 0xC80, 0xE80,
                      0x808, 0xA0A, 0xC0C, 0xE0E, 0x088, 0x0AA, 0x0CC, 0x0EE)],
                    "Amiga OCS — 32 couleurs")

#: Palette NES (2C02), 64 entrées.
NES_PALETTE = Palette([
    (0x7C, 0x7C, 0x7C), (0x00, 0x00, 0xFC), (0x00, 0x00, 0xBC), (0x44, 0x28, 0xBC),
    (0x94, 0x00, 0x84), (0xA8, 0x00, 0x20), (0xA8, 0x10, 0x00), (0x88, 0x14, 0x00),
    (0x50, 0x30, 0x00), (0x00, 0x78, 0x00), (0x00, 0x68, 0x00), (0x00, 0x58, 0x00),
    (0x00, 0x40, 0x58), (0x00, 0x00, 0x00), (0x00, 0x00, 0x00), (0x00, 0x00, 0x00),
    (0xBC, 0xBC, 0xBC), (0x00, 0x78, 0xF8), (0x00, 0x58, 0xF8), (0x68, 0x44, 0xFC),
    (0xD8, 0x00, 0xCC), (0xE4, 0x00, 0x58), (0xF8, 0x38, 0x00), (0xE4, 0x5C, 0x10),
    (0xAC, 0x7C, 0x00), (0x00, 0xB8, 0x00), (0x00, 0xA8, 0x00), (0x00, 0x90, 0x38),
    (0x00, 0x70, 0xA8), (0x00, 0x00, 0x00), (0x00, 0x00, 0x00), (0x00, 0x00, 0x00),
    (0xFC, 0xFC, 0xFC), (0x3C, 0xBC, 0xFC), (0x68, 0x88, 0xFC), (0x98, 0x78, 0xF8),
    (0xF8, 0x78, 0xF8), (0xF8, 0x58, 0x98), (0xF8, 0x78, 0x58), (0xFC, 0xA0, 0x44),
    (0xF8, 0xB8, 0x00), (0xB8, 0xF8, 0x18), (0x58, 0xD8, 0x54), (0x58, 0xF8, 0x98),
    (0x00, 0xE8, 0xD8), (0x78, 0x78, 0x78), (0x00, 0x00, 0x00), (0x00, 0x00, 0x00),
    (0xFC, 0xFC, 0xFC), (0xA4, 0xE4, 0xFC), (0xB8, 0xB8, 0xF8), (0xD8, 0xB8, 0xF8),
    (0xF8, 0xB8, 0xF8), (0xF8, 0xA4, 0xC0), (0xF0, 0xD0, 0xB0), (0xFC, 0xE0, 0xA8),
    (0xF8, 0xD8, 0x78), (0xD8, 0xF8, 0x78), (0xB8, 0xF8, 0xB8), (0xB8, 0xF8, 0xD8),
    (0x00, 0xFC, 0xFC), (0xF8, 0xD8, 0xF8), (0x00, 0x00, 0x00), (0x00, 0x00, 0x00),
], "NES — 2C02", transparent=0)

#: Palette Game Boy (DMG) — 4 nuances de vert.
GAMEBOY_PALETTE = Palette([(0x0F, 0x38, 0x0F), (0x30, 0x62, 0x30),
                           (0x8B, 0xAC, 0x0F), (0x9B, 0xBC, 0x0F)],
                          "Game Boy (DMG)", transparent=None)

#: Palette Game Boy Pocket (gris).
GAMEBOY_POCKET = Palette([(0x00, 0x00, 0x00), (0x55, 0x55, 0x55),
                          (0xAA, 0xAA, 0xAA), (0xFF, 0xFF, 0xFF)],
                         "Game Boy Pocket", transparent=None)

#: Palette Master System / Game Gear (16 couleurs).
SMS_PALETTE = Palette([(0, 0, 0), (85, 85, 85), (170, 170, 170), (255, 255, 255),
                       (85, 0, 0), (170, 0, 0), (255, 0, 0), (0, 85, 0),
                       (85, 85, 0), (170, 85, 0), (255, 85, 0), (0, 170, 0),
                       (85, 170, 0), (170, 170, 0), (255, 170, 0), (0, 255, 0)],
                      "Master System — 16 couleurs", transparent=0)

#: Palette Mega Drive (16 couleurs de base, la vraie est par CRAM).
MEGADRIVE_PALETTE = Palette([(0, 0, 0), (34, 34, 34), (68, 68, 68), (102, 102, 102),
                             (136, 136, 136), (170, 170, 170), (204, 204, 204), (238, 238, 238),
                             (0, 0, 102), (0, 0, 170), (0, 0, 238), (0, 102, 0),
                             (0, 170, 0), (0, 238, 0), (102, 0, 0), (238, 0, 0)],
                            "Mega Drive — 16 couleurs", transparent=0)

#: Palette Amstrad CPC (27 couleurs matérielles).
CPC_PALETTE = Palette([
    (0x00, 0x00, 0x00), (0x00, 0x00, 0x80), (0x00, 0x80, 0x00), (0x00, 0x80, 0x80),
    (0x80, 0x00, 0x00), (0x80, 0x00, 0x80), (0x80, 0x80, 0x00), (0x80, 0x80, 0x80),
    (0xFF, 0x00, 0x00), (0xFF, 0x00, 0x80), (0xFF, 0x80, 0x00), (0xFF, 0x80, 0x80),
    (0x00, 0xFF, 0x00), (0x00, 0xFF, 0x80), (0x00, 0x80, 0xFF), (0x00, 0xFF, 0xFF),
    (0x80, 0xFF, 0x00), (0x80, 0xFF, 0x80), (0x80, 0x00, 0xFF), (0x80, 0x80, 0xFF),
    (0xFF, 0xFF, 0x00), (0xFF, 0xFF, 0x80), (0xFF, 0x00, 0xFF), (0xFF, 0x80, 0xFF),
    (0x00, 0x00, 0xFF), (0xFF, 0x00, 0xFF), (0xFF, 0xFF, 0xFF),
], "Amstrad CPC — 27 couleurs")

#: Palette Commodore 64 (Pepto).
C64_PALETTE = Palette([
    (0x00, 0x00, 0x00), (0xFF, 0xFF, 0xFF), (0x88, 0x39, 0x32), (0x67, 0xB6, 0xBD),
    (0x8B, 0x3F, 0x96), (0x55, 0xA0, 0x49), (0x40, 0x31, 0x8D), (0xD5, 0xDA, 0x66),
    (0x8B, 0x4F, 0x29), (0x57, 0x42, 0x00), (0xB8, 0x69, 0x62), (0x50, 0x50, 0x50),
    (0x78, 0x78, 0x78), (0x94, 0xE0, 0x89), (0x78, 0x69, 0xC4), (0x9F, 0x9F, 0x9F),
], "Commodore 64 — Pepto", transparent=0)

#: Palette ZX Spectrum (8 couleurs × 2 luminosités).
ZX_PALETTE = Palette([
    (0x00, 0x00, 0x00), (0x00, 0x00, 0xD7), (0xD7, 0x00, 0x00), (0xD7, 0x00, 0xD7),
    (0x00, 0xD7, 0x00), (0x00, 0xD7, 0xD7), (0xD7, 0xD7, 0x00), (0xD7, 0xD7, 0xD7),
    (0x00, 0x00, 0x00), (0x00, 0x00, 0xFF), (0xFF, 0x00, 0x00), (0xFF, 0x00, 0xFF),
    (0x00, 0xFF, 0x00), (0x00, 0xFF, 0xFF), (0xFF, 0xFF, 0x00), (0xFF, 0xFF, 0xFF),
], "ZX Spectrum", transparent=None)

#: Palette EGA / CGA 16 couleurs (table IBM).
EGA_PALETTE = Palette([
    (0x00, 0x00, 0x00), (0x00, 0x00, 0xAA), (0x00, 0xAA, 0x00), (0x00, 0xAA, 0xAA),
    (0xAA, 0x00, 0x00), (0xAA, 0x00, 0xAA), (0xAA, 0x55, 0x00), (0xAA, 0xAA, 0xAA),
    (0x55, 0x55, 0x55), (0x55, 0x55, 0xFF), (0x55, 0xFF, 0x55), (0x55, 0xFF, 0xFF),
    (0xFF, 0x55, 0x55), (0xFF, 0x55, 0xFF), (0xFF, 0xFF, 0x55), (0xFF, 0xFF, 0xFF),
], "EGA / CGA — 16 couleurs", transparent=0)

#: Palette 16 couleurs « arcade CPS-1/2 » de démonstration.
CPS_PALETTE = Palette([(0, 0, 0), (0x22, 0x22, 0x22), (0x44, 0x44, 0x44), (0x66, 0x66, 0x66),
                       (0x88, 0x88, 0x88), (0xAA, 0xAA, 0xAA), (0xCC, 0xCC, 0xCC), (0xFF, 0xFF, 0xFF),
                       (0x88, 0x00, 0x00), (0xCC, 0x00, 0x00), (0x00, 0x88, 0x00), (0x00, 0xCC, 0x00),
                       (0x00, 0x00, 0x88), (0x00, 0x00, 0xCC), (0x88, 0x66, 0x00), (0xCC, 0xAA, 0x00)],
                      "Arcade CPS — 16 couleurs", transparent=0)

#: Palette 16 couleurs générique (arc-en-ciel lisible), pour les formats inconnus.
GENERIC_16 = Palette([
    (0, 0, 0), (255, 255, 255), (255, 0, 0), (0, 255, 0),
    (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255),
    (128, 128, 128), (255, 128, 0), (128, 0, 255), (0, 128, 0),
    (128, 64, 0), (0, 128, 255), (255, 0, 128), (192, 192, 192),
], "Générique — 16 couleurs", transparent=0)

#: Palette 4 couleurs générique.
GENERIC_4 = Palette([(0, 0, 0), (85, 85, 85), (170, 170, 170), (255, 255, 255)],
                    "Générique — 4 couleurs", transparent=0)

#: Palette 8 couleurs générique.
GENERIC_8 = Palette([(0, 0, 0), (255, 255, 255), (255, 0, 0), (0, 255, 0),
                     (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255)],
                    "Générique — 8 couleurs", transparent=0)


BUILTIN_PALETTES: dict[str, Palette] = {
    "st_barbarian": ST_BARBARIAN,
    "st": ST_DEFAULT,
    "amiga": AMIGA_OCS,
    "nes": NES_PALETTE,
    "gameboy": GAMEBOY_PALETTE,
    "gameboy_pocket": GAMEBOY_POCKET,
    "sms": SMS_PALETTE,
    "megadrive": MEGADRIVE_PALETTE,
    "cpc": CPC_PALETTE,
    "c64": C64_PALETTE,
    "zx": ZX_PALETTE,
    "ega": EGA_PALETTE,
    "cps": CPS_PALETTE,
    "generic16": GENERIC_16,
    "generic8": GENERIC_8,
    "generic4": GENERIC_4,
}


def palette_for_system(key: str) -> Palette:
    """Palette par défaut associée à une clé de système (systems.py)."""
    aliases = {
        "atari-st": "st", "atari-falcon": "st",
        "nes": "nes", "famicom": "nes",
        "game-boy": "gameboy", "game-boy-color": "gameboy", "game-boy-advance": "generic16",
        "master-system": "sms", "game-gear": "sms", "sg-1000": "sms",
        "mega-drive": "megadrive", "sega-32x": "megadrive",
        "pc-engine": "generic16",
        "amstrad-cpc": "cpc", "amstrad-pcw": "cpc",
        "c64": "c64", "vic-20": "c64", "c128": "c64",
        "zx-spectrum": "zx", "zx81": "zx",
        "amiga": "amiga",
        "cps1": "cps", "cps2": "cps", "cps3": "cps", "neo-geo-mvs": "cps",
        "neo-geo-aes": "cps", "snes": "generic16",
    }
    key = (key or "").lower()
    if key in BUILTIN_PALETTES:
        return BUILTIN_PALETTES[key]
    return BUILTIN_PALETTES.get(aliases.get(key, "generic16"))


def default_palette_for_bpp(bpp: int) -> Palette:
    return {1: Palette([(0, 0, 0), (255, 255, 255)], "1 bit", transparent=0),
            2: GENERIC_4,
            3: GENERIC_8,
            4: GENERIC_16,
            8: GENERIC_16}.get(bpp, GENERIC_16)


# ---------------------------------------------------------------------------
# Palettes lues directement dans une ROM
# ---------------------------------------------------------------------------


def from_snes_bgr555(data: bytes, offset: int = 0, count: int = 16) -> Palette:
    """Palette SNES : 2 octets little-endian, BGR555 (bit 15 ignoré)."""
    colors = []
    for i in range(count):
        pos = offset + i * 2
        if pos + 1 >= len(data):
            break
        word = data[pos] | (data[pos + 1] << 8)
        b = (word & 0x1F) * 255 // 31
        g = ((word >> 5) & 0x1F) * 255 // 31
        r = ((word >> 10) & 0x1F) * 255 // 31
        colors.append((r, g, b))
    return Palette(colors or [(0, 0, 0)], "SNES (ROM)", transparent=0)


def from_megadrive_cram(data: bytes, offset: int = 0, count: int = 16) -> Palette:
    """Palette Mega Drive : 2 octets big-endian, 0BGR (3 bits par composante)."""
    colors = []
    for i in range(count):
        pos = offset + i * 2
        if pos + 1 >= len(data):
            break
        word = (data[pos] << 8) | data[pos + 1]
        b = ((word >> 9) & 0x07) * 255 // 7
        g = ((word >> 5) & 0x07) * 255 // 7
        r = ((word >> 1) & 0x07) * 255 // 7
        colors.append((r, g, b))
    return Palette(colors or [(0, 0, 0)], "Mega Drive (ROM)", transparent=0)


def from_atari_st_rom(data: bytes, offset: int = 0, count: int = 16) -> Palette:
    """Palette Atari ST : 2 octets big-endian, 0RGB (3 bits par composante)."""
    colors = []
    for i in range(count):
        pos = offset + i * 2
        if pos + 1 >= len(data):
            break
        word = (data[pos] << 8) | data[pos + 1]
        colors.append(st_to_rgb(word))
    return Palette(colors or [(0, 0, 0)], "Atari ST (ROM)", transparent=0)


#: Formats de palette rencontrés dans les ROM, pour les dialogues.
ROM_PALETTES = (
    ("snes", "SNES — BGR555 (2 octets, petit-boutiste)"),
    ("megadrive", "Mega Drive — 0BGR (2 octets, gros-boutiste)"),
    ("atari_st", "Atari ST — 0RGB (2 octets, gros-boutiste)"),
    ("raw8", "Octets bruts (R, V, B, 8 bits)"),
)


def read_rom_palette(data: bytes, offset: int, count: int, kind: str) -> Palette:
    """Lit une palette dans une ROM selon le format demandé."""
    if kind == "snes":
        return from_snes_bgr555(data, offset, count)
    if kind == "megadrive":
        return from_megadrive_cram(data, offset, count)
    if kind == "atari_st":
        return from_atari_st_rom(data, offset, count)
    colors = []
    for i in range(count):
        pos = offset + i * 3
        if pos + 2 >= len(data):
            break
        colors.append((data[pos], data[pos + 1], data[pos + 2]))
    return Palette(colors or [(0, 0, 0)], "ROM (RVB 8 bits)", transparent=0)
