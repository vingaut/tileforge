"""Tests de l'identification du format de tuiles.

Les banques sont fabriquées : on encode une planche de sprites dans un format
connu, puis on vérifie que l'outil le retrouve — et qu'il refuse de trancher
sur du bruit.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from tileforge.core.formats import FORMATS_BY_KEY
from tileforge.core.identify import best, explain, identify, null_baseline

# ---------------------------------------------------------------------------
# Fabrique
# ---------------------------------------------------------------------------


def _encode_snes(pixels: np.ndarray, bpp: int) -> bytes:
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


def _encode_megadrive(pixels: np.ndarray) -> bytes:
    out = bytearray()
    for y in range(8):
        for i in range(4):
            out.append((int(pixels[y, 2 * i]) << 4) | int(pixels[y, 2 * i + 1]))
    return bytes(out)


def _sprite_tile(rng: random.Random, colors: int = 8) -> np.ndarray:
    tile = np.zeros((8, 8), dtype=np.int32)
    for _ in range(rng.randint(1, 3)):
        x0, y0 = rng.randint(0, 6), rng.randint(0, 6)
        w, h = rng.randint(1, 8 - x0), rng.randint(1, 8 - y0)
        tile[y0:y0 + h, x0:x0 + w] = rng.randint(1, colors - 1)
    if rng.random() < 0.7:
        tile[0, :] = tile[:, 0] = 0
    if rng.random() < 0.7:
        tile[-1, :] = tile[:, -1] = 0
    return tile


def _sheet(seed: int, count: int = 96, colors: int = 8) -> list[np.ndarray]:
    rng = random.Random(seed)
    return [_sprite_tile(rng, colors) for _ in range(count)]


def _encode(tiles: list[np.ndarray], key: str) -> bytes:
    if key == "snes_4bpp":
        return b"".join(_encode_snes(tile, 4) for tile in tiles)
    if key == "snes_2bpp":
        return b"".join(_encode_snes(tile % 4, 2) for tile in tiles)
    if key == "megadrive":
        return b"".join(_encode_megadrive(tile) for tile in tiles)
    raise ValueError(key)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_identifie_snes_4bpp():
    for seed in range(3):
        blob = _encode(_sheet(seed), "snes_4bpp")
        chosen = best(blob)
        assert chosen is not None and chosen.key == "snes_4bpp", \
            [guess.key for guess in identify(blob)[:3]]


def test_identifie_megadrive():
    for seed in range(3):
        blob = _encode(_sheet(seed + 10), "megadrive")
        chosen = best(blob)
        assert chosen is not None and chosen.key == "megadrive", \
            [guess.key for guess in identify(blob)[:3]]


def test_identifie_snes_2bpp():
    for seed in range(3):
        blob = _encode(_sheet(seed + 20, colors=4), "snes_2bpp")
        chosen = best(blob)
        assert chosen is not None and chosen.key == "snes_2bpp", \
            [guess.key for guess in identify(blob)[:3]]


def test_refuse_de_trancher_sur_du_bruit():
    rng = random.Random(5)
    noise = bytes(rng.randrange(256) for _ in range(8192))
    assert best(noise) is None
    assert explain(noise)["confident"] is False


def test_plancher_de_bruit_positif_et_reproductible():
    fmt = FORMATS_BY_KEY["snes_4bpp"]
    first = null_baseline(fmt)
    second = null_baseline(fmt)
    assert first == second          # graine fixe
    assert 0.0 <= first < 0.6


def test_marge_superieure_a_la_note_brute():
    """La marge corrige le biais des formats à faible profondeur."""
    blob = _encode(_sheet(3), "snes_4bpp")
    guesses = identify(blob)
    assert guesses
    for guess in guesses:
        assert abs(guess.margin - (guess.score - guess.baseline)) < 1e-9


def test_explain_structure():
    blob = _encode(_sheet(7), "megadrive")
    result = explain(blob)
    assert result["confident"] is True
    assert result["best"]["key"] == "megadrive"
    assert result["ranking"][0]["margin"] >= result["ranking"][-1]["margin"]


def test_bloc_trop_court():
    assert identify(b"\x00\x01" * 8) == []
