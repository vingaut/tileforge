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


def test_megadrive_nibbles():
    fmt = FORMATS_BY_KEY["megadrive"]
    pixels = _pixels()
    out = bytearray()
    for y in range(8):
        for i in range(4):
            out.append((int(pixels[y, 2 * i]) << 4) | int(pixels[y, 2 * i + 1]))
    decoded = fmt.decode(bytes(out))
    assert np.array_equal(decoded, pixels), decoded


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
