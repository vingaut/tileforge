"""Tests du décodage des tuiles (formats SNES, Mega Drive, Atari ST)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from tileforge.core.formats import FORMATS_BY_KEY


def _pixels(w=8, h=8):
    return np.array([[(x * 3 + y * 5) % 16 for x in range(w)] for y in range(h)])


def _encode_snes(pixels: np.ndarray, bpp: int) -> bytes:
    """Encode une tuile au format SNES (paires de plans entrelacées par ligne)."""
    h, w = pixels.shape
    out = bytearray()
    for pair in range(bpp // 2):
        for y in range(h):
            for plane in (2 * pair, 2 * pair + 1):
                byte = 0
                for x in range(8):
                    if (int(pixels[y, x]) >> plane) & 1:
                        byte |= 0x80 >> x
                out.append(byte)
    return bytes(out)


def test_snes_2bpp():
    fmt = FORMATS_BY_KEY["snes_2bpp"]
    pixels = _pixels() % 4
    data = _encode_snes(pixels, 2)
    assert len(data) == 16, len(data)
    decoded = fmt.decode(data)
    assert np.array_equal(decoded, pixels), decoded


def test_snes_4bpp():
    fmt = FORMATS_BY_KEY["snes_4bpp"]
    pixels = _pixels()
    data = _encode_snes(pixels, 4)
    assert len(data) == 32, len(data)
    decoded = fmt.decode(data)
    assert np.array_equal(decoded, pixels), decoded


def test_snes_8bpp():
    fmt = FORMATS_BY_KEY["snes_8bpp"]
    pixels = np.array([[(x * 7 + y * 11) % 256 for x in range(8)] for y in range(8)])
    data = _encode_snes(pixels, 8)
    assert len(data) == 64, len(data)
    decoded = fmt.decode(data)
    assert np.array_equal(decoded, pixels), decoded


def test_snes_3bpp():
    fmt = FORMATS_BY_KEY["snes_3bpp"]
    pixels = _pixels() % 8
    out = bytearray()
    for y in range(8):
        for plane in (0, 1):
            byte = 0
            for x in range(8):
                if (int(pixels[y, x]) >> plane) & 1:
                    byte |= 0x80 >> x
            out.append(byte)
    for y in range(8):
        byte = 0
        for x in range(8):
            if (int(pixels[y, x]) >> 2) & 1:
                byte |= 0x80 >> x
        out.append(byte)
    decoded = fmt.decode(bytes(out))
    assert np.array_equal(decoded, pixels), decoded


def _encode_planar(pixels: np.ndarray, planes: int = 4) -> bytes:
    """Encode une tuile 8x8 en plans entrelacés par ligne (Mega Drive, SMS)."""
    out = bytearray()
    for y in range(8):
        for plane in range(planes):
            byte = 0
            for x in range(8):
                if (int(pixels[y, x]) >> plane) & 1:
                    byte |= 0x80 >> x
            out.append(byte)
    return bytes(out)


def test_megadrive_planar():
    """La Mega Drive est planaire (4 octets/ligne), pas en quartets."""
    fmt = FORMATS_BY_KEY["megadrive"]
    pixels = _pixels()
    data = _encode_planar(pixels)
    assert len(data) == 32, len(data)
    decoded = fmt.decode(data)
    assert np.array_equal(decoded, pixels), decoded


def test_megadrive_et_master_system_meme_disposition():
    """MD et Master System partagent le même encodage de tuiles."""
    md = FORMATS_BY_KEY["megadrive"]
    sms = FORMATS_BY_KEY["master_system"]
    assert md.layout == sms.layout == "row_planes_bytes"
    data = _encode_planar(_pixels())
    assert np.array_equal(md.decode(data), sms.decode(data))


def test_atari_st_barbarian():
    """La banque Barbarian doit correspondre au rendu de référence."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dat = os.path.join(root, "extract", "BARB.DAT")
    ref = os.path.join(root, "graphisme", "sprites_banque1.png")
    if not (os.path.exists(dat) and os.path.exists(ref)):
        return          # données de test absentes : on saute
    from tileforge.core.formats import load_raw_bank
    from tileforge.core.image import load_image

    fmt = FORMATS_BY_KEY["barbarian_st"]
    bank = load_raw_bank(dat, 0x33A52, 252, fmt, per_row=16, gap=2)
    reference = load_image(ref)
    wrong = 0
    for k, rect in enumerate(bank.tile_rects()):
        tile = bank.image.cropped(*rect)
        gx, gy = k % 16, k // 16
        expected = reference.cropped(gx * 26, gy * 23, 24, 21)
        mask = tile.px[..., 3] > 0
        if not np.array_equal(tile.px[..., :3][mask], expected.px[..., :3][mask]):
            wrong += 1
    assert wrong == 0, f"{wrong} tuiles différentes du rendu de référence"


def test_amiga_5bpp():
    """Les tuiles Amiga 5 plans sont planaires, un octet par plan et par ligne."""
    fmt = FORMATS_BY_KEY["amiga_5bpp"]
    pixels = _pixels() % 32
    data = _encode_planar(pixels, planes=5)
    assert len(data) == 40
    assert np.array_equal(fmt.decode(data), pixels)


def test_amiga_sprite_5pl():
    """Le sprite 16x16 en 5 plans utilise deux mots par plan et par ligne."""
    fmt = FORMATS_BY_KEY["amiga_sprite_5pl"]
    assert fmt.real_bytes == 160
    assert fmt.stride_bytes == 10
