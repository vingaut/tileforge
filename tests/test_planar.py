"""Tests du rendu planaire Amiga et des palettes 0x0RGB."""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import planar as P
from tileforge.core.palettes import Palette


def encode(index: np.ndarray, planes: int, layout: str,
           stride: int | None = None) -> bytes:
    height, width = index.shape
    stride = stride or (width + 7) // 8
    out = bytearray()
    if layout == "row":
        for y in range(height):
            for plane in range(planes):
                for bx in range((width + 7) // 8):
                    byte = 0
                    for k in range(8):
                        x = bx * 8 + k
                        bit = (index[y, x] >> plane) & 1 if x < width else 0
                        byte = (byte << 1) | int(bit)
                    out.append(byte)
                out += b"\x00" * (stride - (width + 7) // 8)
    else:
        for plane in range(planes):
            for y in range(height):
                for bx in range((width + 7) // 8):
                    byte = 0
                    for k in range(8):
                        x = bx * 8 + k
                        bit = (index[y, x] >> plane) & 1 if x < width else 0
                        byte = (byte << 1) | int(bit)
                    out.append(byte)
                out += b"\x00" * (stride - (width + 7) // 8)
    return bytes(out)


def _grid(height: int = 8, width: int = 16) -> np.ndarray:
    index = np.zeros((height, width), dtype=np.int32)
    index[:, :width // 2] = 1
    index[:, width // 2:] = 2
    return index


def test_decode_row_major():
    index = _grid()
    data = encode(index, 2, "row")
    decoded = P.decode_indices(data, 0, 16, 8, 2, "row", 2)
    assert np.array_equal(decoded, index)


def test_decode_plane_major():
    index = _grid()
    data = encode(index, 2, "plane")
    decoded = P.decode_indices(data, 0, 16, 8, 2, "plane", 2)
    assert np.array_equal(decoded, index)


def test_stride_et_bourrage():
    # Image de 8 colonnes utiles dans un bitmap de 16 : le pas vaut 2.
    index = np.zeros((4, 8), dtype=np.int32)
    index[:, :4] = 1
    data = encode(index, 1, "plane", stride=2)
    decoded = P.decode_indices(data, 0, 8, 4, 1, "plane", 2)
    assert np.array_equal(decoded, index)


def test_densite_des_plans():
    index = _grid()
    data = encode(index, 2, "plane")
    density = P.plane_density(data, 0, 16, 8, 2, "plane", 2)
    assert abs(density[0] - 0.5) < 0.01
    assert abs(density[1] - 0.5) < 0.01


def test_rendu_indexe():
    index = _grid()
    data = encode(index, 2, "plane")
    palette = Palette([(0, 0, 0), (255, 0, 0), (0, 255, 0)])
    image = P.render_screen(data, 0, 16, 8, 2, "plane", 2, palette,
                            transparent=None)
    assert image.size == (16, 8)
    assert tuple(image.px[0, 0][:3]) == (255, 0, 0)
    assert tuple(image.px[0, 15][:3]) == (0, 255, 0)


def test_detection_bourrage():
    index = np.zeros((16, 320), dtype=np.int32)
    index[:, :256] = np.arange(256) % 16
    width, strength = P.detect_padding(index)
    assert width == 256
    assert strength > 3.0


def test_palette_scan():
    words = [0, 0x0F00, 0x00F0, 0x000F, 0x0FFF, 0x0444, 0x0888, 0x0CCC]
    data = bytearray(b"\x00" * 64)
    for i in range(32):
        data += words[i % len(words)].to_bytes(2, "big")
    found = P.scan_palettes(bytes(data), count=32)
    assert any(c.offset == 64 for c in found), [c.offset for c in found]
    exact = next(c for c in found if c.offset == 64)
    assert exact.words[1] == 0x0F00


def test_palette_fondu_ecartee():
    # Une table de fondu est majoritairement très sombre, mais contient
    # assez de valeurs distinctes pour ne pas être rejetée par ce seul critère.
    data = bytearray()
    for i in range(32):
        data += (i % 16).to_bytes(2, "big")
    found = P.scan_palettes(bytes(data), count=32)
    assert not found
    found = P.scan_palettes(bytes(data), count=32, include_fades=True)
    assert found and found[0].fade


def test_meilleure_palette():
    index = _grid()
    data = bytearray()
    good = [0, 0x0F00, 0x00F0, 0x000F, 0x0FFF, 0x0444, 0x0888, 0x0CCC]
    bad = [0, 0x0FFF, 0x000F, 0x00F0, 0x0F0F, 0x0FF0, 0x0F00, 0x00FF]
    for words in (good, bad):
        palette = bytearray()
        for i in range(32):
            palette += words[i % len(words)].to_bytes(2, "big")
        data += palette
    candidates = P.scan_palettes(bytes(data), count=32, limit=4)
    best, score = P.best_palette(index, candidates)
    assert best is not None
    assert score < 255 * 3


def test_detecte_geometrie():
    rng = np.random.default_rng(7)
    blocks = rng.integers(0, 4, size=(4, 8))
    index = np.kron(blocks, np.ones((8, 8), dtype=np.int32))
    data = b"JUNK" * 4 + encode(index, 3, "plane", stride=8)
    candidates = P.detect_geometry(data, start=0, width=64, height=32,
                                   planes=3, layout="plane", step=1,
                                   limit=1)
    assert candidates
    assert candidates[0].offset == 16
    assert candidates[0].score > 0.5
