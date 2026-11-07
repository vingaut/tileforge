"""Chargements génériques : PNG déjà découpé, banque brute, atlas.

Ce sont les points d'entrée utilisés par l'interface pour ouvrir n'importe
quel jeu, indépendamment des plugins spécifiques.
"""

from __future__ import annotations

import os

from ..core.formats import RawBank, TileFormat, load_raw_bank
from ..core.image import Image, load_image
from ..core.model import Sheet


def sheet_from_bank(bank: RawBank, source: str, game: str = "") -> Sheet:
    """Transforme une banque décodée en planche éditable."""
    info = {
        "offset": bank.offset,
        "format": bank.format.key,
        "count": bank.count,
        "per_row": bank.per_row,
        "gap": bank.gap,
        "game": game,
        "palette": bank.format.palette_key,
        "tile_w": bank.tile_w,
        "tile_h": bank.tile_h,
    }
    sheet = Sheet(image=bank.image, source=source, kind="raw", info=info)
    for k, rect in enumerate(bank.tile_rects()):
        sheet.add_tile(rect, storage_index=k, label=str(k))
    return sheet


def load_raw_sheet(path: str, offset: int, count: int, fmt: TileFormat,
                   per_row: int | None = None, gap: int = 1,
                   palette=None, transparent: bool = True) -> Sheet:
    bank = load_raw_bank(path, offset, count, fmt, per_row=per_row, gap=gap,
                         palette=palette)
    if transparent:
        bank.image = _apply_transparency(bank.image, fmt.transparent_index)
    return sheet_from_bank(bank, path)


def load_png_sheet(path: str, auto_transparent: bool = True) -> Sheet:
    """Ouvre un PNG ; rend transparente la couleur de fond si demandé."""
    img = load_image(path)
    info = {"source_size": [img.w, img.h]}
    if auto_transparent and img.px[..., 3].min() == 255:
        img = img.auto_transparent(0)
        info["auto_transparent"] = True
    sheet = Sheet(image=img, source=path, kind="png", info=info)
    return sheet


def load_atlas_png(path: str) -> Sheet:
    return load_png_sheet(path, auto_transparent=False)


def _apply_transparency(image: Image, index) -> Image:
    if index is None:
        return image
    if image.index is None:
        return image
    px = image.px.copy()
    px[image.index == index, 3] = 0
    return Image(px, image.index, image.palette)


def palette_from_sheet(sheet: Sheet):
    """Palette déduite de la planche (si elle est indexée)."""
    from ..core.palettes import Palette
    if sheet.image.palette:
        return Palette([c[:3] for c in sheet.image.palette],
                       "palette de la banque",
                       transparent=0 if sheet.image.palette[0][3] == 0 else None)
    return None


def describe_source(sheet: Sheet) -> str:
    if sheet is None:
        return "aucune planche"
    name = os.path.basename(sheet.source) if sheet.source else "planche"
    return f"{name} — {sheet.image.w}×{sheet.image.h} px, {len(sheet.tiles)} tuiles"
