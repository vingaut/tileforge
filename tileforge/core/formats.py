"""Décodage des banques de tuiles brutes (formats « ROM »).

Une banque brute est une suite d'octets : ``count`` tuiles de
``bytes_per_tile`` octets.  Le décodage dépend de la machine ; ce module
fournit un décodeur générique piloté par quelques paramètres (largeur, hauteur,
bits par pixel, disposition des plans, ordre des bits) et des préréglages pour
les formats les plus courants des consoles, ordinateurs et bornes d'arcade.

Dispositions gérées
-------------------
``row_planes_bytes``
    Pour chaque ligne, pour chaque groupe de 8 pixels, un octet par plan
    (Atari ST sprites, SNES, Master System, Neo Geo, CPS…).
``row_planes_words``
    Pour chaque ligne, pour chaque groupe de 16 pixels, un mot de 16 bits par
    plan (écrans Atari ST et Amiga).
``row_plane_pairs_bytes``
    Les plans sont groupés par paires ; dans chaque paire, les deux octets de
    la ligne se suivent (SNES 4bpp et 8bpp).
``snes_3bpp``
    Paires (plan 1, plan 2) ligne par ligne, puis le plan 3 en bloc (SNES 3bpp).
``seq_planes_bytes``
    Les plans sont stockés les uns après les autres pour la tuile entière
    (NES, Game Boy, ZX Spectrum).
``seq_plane_pairs``
    Variante « paires de plans » avec 2 pixels par octet (PC Engine).
``nibble``
    Un octet = 2 pixels, quartet haut = pixel de gauche (GBA, PC Engine).
``chunky``
    Un octet = 1 pixel indexé (8 bits) ou 2 pixels (4 bits).
``cpc``
    Entrelacement Amstrad CPC (mode 0, 1 ou 2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .image import Image
from .palettes import Palette, default_palette_for_bpp, palette_for_system

# ---------------------------------------------------------------------------
# Description d'un format
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TileFormat:
    key: str
    name: str
    tile_w: int
    tile_h: int
    bpp: int
    layout: str
    bytes_per_tile: int = 0          # 0 = calculé
    bit_order: str = "msb"           # "msb" | "lsb"
    row_padding: int = 0             # octets ajoutés en fin de ligne
    notes: str = ""
    palette_key: str = "generic16"
    system_key: str = ""
    transparent_index: int = 0
    index_base: int = 0              # décalage ajouté aux indices décodés

    # -- propriétés ---------------------------------------------------------

    @property
    def planes(self) -> int:
        return self.bpp

    @property
    def stride_bytes(self) -> int:
        """Taille d'une ligne de tuile dans le fichier."""
        w, h, p = self.tile_w, self.tile_h, self.planes
        if self.layout == "row_planes_bytes":
            return (w // 8) * p + self.row_padding
        if self.layout == "row_planes_words":
            return (w // 16) * p * 2 + self.row_padding
        if self.layout == "seq_planes_bytes":
            return h * (w // 8) + self.row_padding
        if self.layout == "row_plane_pairs_bytes":
            return (h * 2 * (w // 8)) + self.row_padding
        if self.layout == "snes_3bpp":
            return (h * 2 + h * (w // 8)) + self.row_padding
        if self.layout == "seq_plane_pairs":
            return h * (w // 2) + self.row_padding
        if self.layout in ("nibble", "chunky"):
            return (w * self.bpp) // 8 + self.row_padding
        if self.layout == "cpc":
            return (w * self.bpp) // 8 + self.row_padding
        return self.computed_bytes

    @property
    def computed_bytes(self) -> int:
        return max(1, (self.tile_w * self.tile_h * self.bpp + 7) // 8)

    @property
    def real_bytes(self) -> int:
        return self.bytes_per_tile or self.computed_bytes

    @property
    def palette(self) -> Palette:
        from .palettes import BUILTIN_PALETTES
        pal = BUILTIN_PALETTES.get(self.palette_key)
        if pal is None and self.system_key:
            pal = palette_for_system(self.system_key)
        if pal is None:
            pal = default_palette_for_bpp(self.bpp)
        return pal.with_transparent(self.transparent_index)

    # -- décodage -----------------------------------------------------------

    def decode(self, block) -> np.ndarray:
        """Décode un bloc d'octets en grille (h, w) d'indices de palette."""
        out = decode_block(block, self)
        if self.index_base:
            out = out + self.index_base
        return out

    def with_changes(self, **kw) -> TileFormat:
        d = dict(self.__dict__)
        d.update(kw)
        return TileFormat(**d)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, d: dict) -> TileFormat:
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


# ---------------------------------------------------------------------------
# Décodeur générique
# ---------------------------------------------------------------------------


def decode_block(block, fmt: TileFormat) -> np.ndarray:
    """Décode une tuile et renvoie une grille d'indices (h, w)."""
    w, h, p = fmt.tile_w, fmt.tile_h, fmt.planes
    buf = bytes(block)
    out = np.zeros((h, w), dtype=np.int32)
    msb = fmt.bit_order != "lsb"

    def put_bit(y, x, plane, value):
        out[y, x] |= (1 << plane) if value else 0

    layout = fmt.layout

    if layout == "row_planes_bytes":
        stride = fmt.stride_bytes
        gcount = w // 8
        for y in range(h):
            base = y * stride
            for g in range(gcount):
                for pl in range(p):
                    pos = base + g * p + pl
                    if pos >= len(buf):
                        continue
                    byte = buf[pos]
                    for bit in range(8):
                        v = (byte >> ((7 - bit) if msb else bit)) & 1
                        if v:
                            out[y, g * 8 + bit] |= 1 << pl

    elif layout == "row_planes_words":
        stride = fmt.stride_bytes
        gcount = w // 16
        for y in range(h):
            base = y * stride
            for g in range(gcount):
                for pl in range(p):
                    pos = base + (g * p + pl) * 2
                    if pos + 1 >= len(buf):
                        continue
                    word = (buf[pos] << 8) | buf[pos + 1]
                    for bit in range(16):
                        v = (word >> ((15 - bit) if msb else bit)) & 1
                        if v:
                            out[y, g * 16 + bit] |= 1 << pl

    elif layout == "row_plane_pairs_bytes":
        # SNES 4bpp / 8bpp : les plans vont par paires, et dans une paire les
        # octets des deux plans se suivent ligne par ligne.
        groups = max(1, w // 8)
        block = h * 2 * groups
        for pr in range(max(1, p // 2)):
            base = pr * block
            for y in range(h):
                for g in range(groups):
                    pos = base + y * 2 * groups + g * 2
                    if pos + 1 >= len(buf):
                        continue
                    byte_a, byte_b = buf[pos], buf[pos + 1]
                    for bit in range(8):
                        if (byte_a >> ((7 - bit) if msb else bit)) & 1:
                            out[y, g * 8 + bit] |= 1 << (2 * pr)
                        if (byte_b >> ((7 - bit) if msb else bit)) & 1:
                            out[y, g * 8 + bit] |= 1 << (2 * pr + 1)

    elif layout == "snes_3bpp":
        # 16 octets pour les plans 1 et 2 entrelacés par ligne, puis le plan 3.
        groups = max(1, w // 8)
        first_block = h * 2 * groups
        for y in range(h):
            for g in range(groups):
                pos = y * 2 * groups + g * 2
                if pos + 1 >= len(buf):
                    continue
                byte_a, byte_b = buf[pos], buf[pos + 1]
                for bit in range(8):
                    if (byte_a >> ((7 - bit) if msb else bit)) & 1:
                        out[y, g * 8 + bit] |= 1
                    if (byte_b >> ((7 - bit) if msb else bit)) & 1:
                        out[y, g * 8 + bit] |= 2
        for y in range(h):
            for g in range(groups):
                pos = first_block + y * groups + g
                if pos >= len(buf):
                    continue
                byte = buf[pos]
                for bit in range(8):
                    if (byte >> ((7 - bit) if msb else bit)) & 1:
                        out[y, g * 8 + bit] |= 4

    elif layout == "seq_planes_bytes":
        plane_stride = h * (w // 8)
        for pl in range(p):
            for y in range(h):
                base = pl * plane_stride + y * (w // 8)
                for g in range(w // 8):
                    pos = base + g
                    if pos >= len(buf):
                        continue
                    byte = buf[pos]
                    for bit in range(8):
                        v = (byte >> ((7 - bit) if msb else bit)) & 1
                        if v:
                            out[y, g * 8 + bit] |= 1 << pl

    elif layout == "seq_plane_pairs":
        pairs = max(1, p // 2)
        pair_stride = h * (w // 2)
        for pr in range(pairs):
            for y in range(h):
                base = pr * pair_stride + y * (w // 2)
                for i in range(w // 2):
                    pos = base + i
                    if pos >= len(buf):
                        continue
                    byte = buf[pos]
                    hi, lo = (byte >> 4) & 0xF, byte & 0xF
                    out[y, 2 * i] |= (hi & 3) << (2 * pr)
                    out[y, 2 * i + 1] |= (lo & 3) << (2 * pr)

    elif layout == "nibble":
        bpr = (w * fmt.bpp) // 8
        mask = (1 << fmt.bpp) - 1
        for y in range(h):
            base = y * fmt.stride_bytes
            for i in range(bpr):
                pos = base + i
                if pos >= len(buf):
                    continue
                byte = buf[pos]
                if msb:
                    out[y, 2 * i] = (byte >> 4) & mask
                    out[y, 2 * i + 1] = byte & mask
                else:
                    out[y, 2 * i] = byte & mask
                    out[y, 2 * i + 1] = (byte >> 4) & mask

    elif layout == "chunky":
        per_byte = 8 // fmt.bpp
        mask = (1 << fmt.bpp) - 1
        for y in range(h):
            base = y * fmt.stride_bytes
            for i in range(w // per_byte):
                pos = base + i
                if pos >= len(buf):
                    continue
                byte = buf[pos]
                for k in range(per_byte):
                    shift = (8 - fmt.bpp * (k + 1)) if msb else (fmt.bpp * k)
                    out[y, i * per_byte + k] = (byte >> shift) & mask

    elif layout == "cpc":
        ppb = 8 // fmt.bpp
        for y in range(h):
            base = y * fmt.stride_bytes
            for i in range(w // ppb):
                pos = base + i
                if pos >= len(buf):
                    continue
                byte = buf[pos]
                for k in range(ppb):
                    val = 0
                    for pl in range(fmt.bpp):
                        bitpos = 7 - k - pl * ppb
                        if 0 <= bitpos < 8:
                            val |= ((byte >> bitpos) & 1) << pl
                    out[y, i * ppb + k] = val

    else:
        raise ValueError(f"disposition inconnue : {layout}")

    return out


# ---------------------------------------------------------------------------
# Préréglages
# ---------------------------------------------------------------------------

FORMATS: tuple[TileFormat, ...] = (
    TileFormat("barbarian_st", "Barbarian ST — 24x21, 2 plans", 24, 21, 2,
               "row_planes_bytes", 126, notes="Atari ST, 6 octets/ligne (3 groupes de 8 px), "
               "couleurs 12 à 15.", system_key="atari-st", palette_key="st_barbarian",
               transparent_index=12, index_base=12),
    TileFormat("st_sprite_2pl", "Atari ST — sprite 2 plans (16x16)", 16, 16, 2,
               "row_planes_bytes", 64, notes="4 octets/ligne, mot par plan.",
               system_key="atari-st", palette_key="st"),
    TileFormat("st_sprite_4pl", "Atari ST — sprite 4 plans (16x16)", 16, 16, 4,
               "row_planes_bytes", 128, notes="8 octets/ligne, mot par plan.",
               system_key="atari-st", palette_key="st"),
    TileFormat("amiga_sprite", "Amiga — sprite 4 plans (16x16)", 16, 16, 4,
               "row_planes_bytes", 128, notes="Proche du ST, mots big-endian.",
               system_key="amiga", palette_key="amiga"),
    TileFormat("amiga_sprite_5pl", "Amiga — sprite 5 plans (16x16)", 16, 16, 5,
               "row_planes_words", 160,
               notes="Deux mots par plan et par ligne (Project-X).",
               system_key="amiga", palette_key="amiga"),
    TileFormat("amiga_3bpp", "Amiga — tuile 8x8, 3 plans", 8, 8, 3,
               "row_planes_bytes", 24,
               notes="Un octet par plan et par ligne, bit 7 = pixel de gauche.",
               system_key="amiga", palette_key="amiga"),
    TileFormat("amiga_4bpp", "Amiga — tuile 8x8, 4 plans", 8, 8, 4,
               "row_planes_bytes", 32,
               notes="Un octet par plan et par ligne.",
               system_key="amiga", palette_key="amiga"),
    TileFormat("amiga_5bpp", "Amiga — tuile 8x8, 5 plans", 8, 8, 5,
               "row_planes_bytes", 40,
               notes="Un octet par plan et par ligne (32 couleurs).",
               system_key="amiga", palette_key="amiga"),
    TileFormat("amiga_6bpp", "Amiga — tuile 8x8, 6 plans", 8, 8, 6,
               "row_planes_bytes", 48,
               notes="Un octet par plan et par ligne (64 couleurs).",
               system_key="amiga", palette_key="amiga"),
    TileFormat("nes", "NES / Famicom — 8x8, 2 plans", 8, 8, 2,
               "seq_planes_bytes", 16, notes="8 octets plan 0 puis 8 octets plan 1.",
               system_key="nes", palette_key="nes", transparent_index=0),
    TileFormat("gameboy", "Game Boy — 8x8, 2 plans", 8, 8, 2,
               "seq_planes_bytes", 16, notes="Identique au NES, 4 nuances.",
               system_key="game-boy", palette_key="gameboy", transparent_index=None),
    TileFormat("snes_2bpp", "SNES — 8x8, 2 plans", 8, 8, 2,
               "row_planes_bytes", 16, notes="Plans entrelacés par ligne.",
               system_key="snes", palette_key="generic4", transparent_index=0),
    TileFormat("snes_3bpp", "SNES — 8x8, 3 plans (3bpp)", 8, 8, 3,
               "snes_3bpp", 24, notes="Plans 1-2 entrelacés, plan 3 à part.",
               system_key="snes", palette_key="generic8", transparent_index=0),
    TileFormat("snes_4bpp", "SNES — 8x8, 4 plans", 8, 8, 4,
               "row_plane_pairs_bytes", 32,
               notes="Plans 1-2 puis 3-4, entrelacés ligne par ligne.",
               system_key="snes", palette_key="generic16", transparent_index=0),
    TileFormat("snes_8bpp", "SNES — 8x8, 8 plans", 8, 8, 8,
               "row_plane_pairs_bytes", 64,
               notes="Quatre paires de plans entrelacées (256 couleurs).",
               system_key="snes", palette_key="generic16", transparent_index=0),
    TileFormat("master_system", "Master System / Game Gear — 8x8, 4 plans", 8, 8, 4,
               "row_planes_bytes", 32,
               notes="4 octets par ligne, un par plan (comme la Mega Drive).",
               system_key="master-system", palette_key="sms", transparent_index=0),
    TileFormat("megadrive", "Mega Drive / Genesis — 8x8, 4 plans", 8, 8, 4,
               "row_planes_bytes", 32,
               notes="4 octets par ligne, un par plan, bit 7 = pixel de gauche.",
               system_key="mega-drive", palette_key="megadrive", transparent_index=0),
    TileFormat("gba_4bpp", "Game Boy Advance — 8x8, 4 bits", 8, 8, 4,
               "nibble", 32,
               notes="Deux pixels par octet, quartet bas à gauche. "
               "16 couleurs par palette.",
               system_key="game-boy-advance", palette_key="generic16",
               transparent_index=0, bit_order="lsb"),
    TileFormat("gba_8bpp", "Game Boy Advance — 8x8, 8 bits", 8, 8, 8,
               "chunky", 64, notes="Un octet par pixel, 256 couleurs.",
               system_key="game-boy-advance", palette_key="generic16",
               transparent_index=0),
    TileFormat("pc_engine", "PC Engine — 8x8, 4 plans", 8, 8, 4,
               "seq_plane_pairs", 32, notes="16 octets plans 0/1 puis 16 octets plans 2/3.",
               system_key="pc-engine", palette_key="generic16", transparent_index=0),
    TileFormat("neo_geo", "Neo Geo — 16x16, 4 plans", 16, 16, 4,
               "row_planes_bytes", 128, notes="8 octets par ligne (2 par plan).",
               system_key="neo-geo-mvs", palette_key="cps", transparent_index=0),
    TileFormat("cps1", "CPS-1 / CPS-2 — 16x16, 4 plans", 16, 16, 4,
               "row_planes_bytes", 128, notes="Disposition identique au Neo Geo.",
               system_key="cps1", palette_key="cps", transparent_index=0),
    TileFormat("zx_spectrum", "ZX Spectrum — 8x8, 1 plan", 8, 8, 1,
               "seq_planes_bytes", 8, notes="8 octets par caractère, 1 bit/pixel.",
               system_key="zx-spectrum", palette_key="zx", transparent_index=None),
    TileFormat("cpc_mode0", "Amstrad CPC mode 0 — 8x8, 4 plans", 8, 8, 4,
               "cpc", 16, notes="2 pixels par octet, plans entrelacés.",
               system_key="amstrad-cpc", palette_key="cpc", transparent_index=0),
    TileFormat("cpc_mode1", "Amstrad CPC mode 1 — 8x8, 2 plans", 8, 8, 2,
               "cpc", 16, notes="4 pixels par octet, plans entrelacés.",
               system_key="amstrad-cpc", palette_key="cpc", transparent_index=0),
    TileFormat("cpc_mode2", "Amstrad CPC mode 2 — 8x8, 1 plan", 8, 8, 1,
               "cpc", 8, notes="8 pixels par octet.",
               system_key="amstrad-cpc", palette_key="zx", transparent_index=None),
    TileFormat("c64", "Commodore 64 — 8x8, 1 plan", 8, 8, 1,
               "seq_planes_bytes", 8, notes="8 octets par caractère.",
               system_key="c64", palette_key="c64", transparent_index=None),
    TileFormat("chunky8", "Chunky 8 bits — 8x8 indexé", 8, 8, 8,
               "chunky", 64, notes="Un octet par pixel (VGA, PC-98, X68000).",
               palette_key="generic16", transparent_index=0),
    TileFormat("chunky4", "Chunky 4 bits — 8x8 indexé", 8, 8, 4,
               "chunky", 32, notes="Deux pixels par octet.",
               palette_key="generic16", transparent_index=0),
    TileFormat("raw8", "Octets bruts — 8x8, 8 plans", 8, 8, 8,
               "seq_planes_bytes", 64, notes="Plan par plan, 8 octets chacun.",
               palette_key="generic16", transparent_index=0),
)


FORMATS_BY_KEY: dict[str, TileFormat] = {f.key: f for f in FORMATS}


def format_by_key(key: str) -> TileFormat:
    return FORMATS_BY_KEY.get(key, FORMATS_BY_KEY["chunky8"])


#: Dispositions proposées dans l'interface.
LAYOUTS = (
    ("row_planes_bytes", "Plans entrelacés par ligne (octets)"),
    ("row_planes_words", "Plans entrelacés par ligne (mots 16 bits)"),
    ("seq_planes_bytes", "Plans séquentiels (NES, GB)"),
    ("seq_plane_pairs", "Paires de plans, 2 px/octet (PC Engine)"),
    ("nibble", "Quartets, 2 px/octet (GBA)"),
    ("chunky", "Indexé, pixels entiers (chunky)"),
    ("cpc", "Entrelacement Amstrad CPC"),
)


# ---------------------------------------------------------------------------
# Chargement d'une banque brute
# ---------------------------------------------------------------------------


@dataclass
class RawBank:
    """Banque décodée : image planche + indices de stockage."""

    image: Image
    count: int
    per_row: int
    gap: int
    tile_w: int
    tile_h: int
    format: TileFormat
    offset: int = 0
    source: str = ""

    def tile_rects(self) -> list[tuple[int, int, int, int]]:
        rects = []
        step_x = self.tile_w + self.gap
        step_y = self.tile_h + self.gap
        for k in range(self.count):
            gx, gy = k % self.per_row, k // self.per_row
            rects.append((self.gap + gx * step_x, self.gap + gy * step_y,
                          self.tile_w, self.tile_h))
        return rects


def load_raw_bank(path: str | None, offset: int, count: int, fmt: TileFormat,
                  per_row: int | None = None, gap: int = 1,
                  palette: Palette | None = None,
                  max_count: int | None = None,
                  data: bytes | None = None) -> RawBank:
    """Décode ``count`` tuiles à partir de ``offset``.

    Les octets peuvent venir d'un fichier (``path``) ou être fournis
    directement (``data``), par exemple après décompression.
    """
    if data is None:
        if path is None:
            raise ValueError("ni fichier ni données fournies")
        with open(path, "rb") as f:
            f.seek(max(0, offset))
            data = f.read()
    else:
        data = bytes(data[offset:]) if offset else bytes(data)
        offset = 0

    bpt = fmt.real_bytes
    available = len(data) // bpt
    if max_count is not None:
        count = min(count, max_count)
    count = max(0, min(count, available))

    if per_row is None:
        per_row = max(1, min(32, int(math.ceil(math.sqrt(max(1, count))))))
        # préférer une largeur « ronde » en tuiles
        for cand in (16, 12, 10, 8, 6, 4, 3, 2):
            if cand <= count and count % cand == 0 and cand <= 24:
                per_row = cand
                break
    per_row = max(1, per_row)

    rows = max(1, (count + per_row - 1) // per_row)
    W = gap + per_row * (fmt.tile_w + gap)
    H = gap + rows * (fmt.tile_h + gap)
    # la palette fournie doit respecter l'index transparent du format
    pal = (palette or fmt.palette).with_transparent(fmt.transparent_index)
    ncolors = max(len(pal), 1 << min(fmt.bpp, 8))
    palette_list = [pal.rgba(i) for i in range(ncolors)]

    px = np.zeros((H, W, 4), dtype=np.uint8)
    index_map = np.full((H, W), -1, dtype=np.int32)
    pal_rgba = np.asarray(palette_list, dtype=np.uint8)

    for k in range(count):
        block = data[k * bpt:(k + 1) * bpt]
        idx = fmt.decode(block)
        gx, gy = k % per_row, k // per_row
        x0 = gap + gx * (fmt.tile_w + gap)
        y0 = gap + gy * (fmt.tile_h + gap)
        hh = min(fmt.tile_h, idx.shape[0])
        ww = min(fmt.tile_w, idx.shape[1])
        sub = idx[:hh, :ww]
        safe = np.clip(sub, 0, len(pal_rgba) - 1)
        px[y0:y0 + hh, x0:x0 + ww] = pal_rgba[safe]
        index_map[y0:y0 + hh, x0:x0 + ww] = safe

    # les marges restent transparentes
    px[index_map < 0] = 0
    image = Image(px, index_map, palette_list)
    return RawBank(image=image, count=count, per_row=per_row, gap=gap,
                   tile_w=fmt.tile_w, tile_h=fmt.tile_h, format=fmt,
                   offset=offset, source=path)


def read_bytes(path: str, offset: int, length: int) -> bytes:
    with open(path, "rb") as f:
        f.seek(max(0, offset))
        return f.read(length)


def scan_tile_sizes(path: str, offset: int = 0, limit: int = 1 << 20,
                    candidates=((8, 8), (16, 16), (24, 21), (32, 32), (8, 16), (16, 8))) -> list[dict]:
    """Liste les tailles de tuile qui « tombent juste » sur la taille du fichier.

    Indice utile quand on ne connaît pas le format d'une banque : si la taille
    du fichier est un multiple exact de la taille d'une tuile, c'est un bon
    candidat.
    """
    import os
    size = os.path.getsize(path) - offset
    out = []
    for (w, h) in candidates:
        for bpp in (1, 2, 3, 4, 8):
            bpt = w * h * bpp // 8
            if bpt <= 0 or size % bpt:
                continue
            out.append({"tile_w": w, "tile_h": h, "bpp": bpp,
                        "bytes_per_tile": bpt, "count": size // bpt})
    out.sort(key=lambda d: (abs(d["tile_w"] * d["tile_h"] - 256), d["bpp"]))
    return out
