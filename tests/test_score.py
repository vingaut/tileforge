"""Tests de la notation de vraisemblance graphique.

Le corpus est entièrement synthétique : aucun contenu de jeu commercial n'est
nécessaire pour vérifier que le modèle sépare du graphisme de du bruit.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from tileforge.core import score as S
from tileforge.core.formats import FORMATS_BY_KEY

# ---------------------------------------------------------------------------
# Encodage de tuiles synthétiques
# ---------------------------------------------------------------------------


def _encode_snes(pixels: np.ndarray, bpp: int) -> bytes:
    """Encode une tuile 8×8 au format SNES (paires de plans entrelacées)."""
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


def _sprite_tile(rng: random.Random, size: int = 8, colors: int = 8) -> np.ndarray:
    """Une tuile « sprite » : aplats, marges vides, formes pleines."""
    tile = np.zeros((size, size), dtype=np.int32)
    for _ in range(rng.randint(1, 3)):
        x0, y0 = rng.randint(0, size - 2), rng.randint(0, size - 2)
        w, h = rng.randint(1, size - x0), rng.randint(1, size - y0)
        tile[y0:y0 + h, x0:x0 + w] = rng.randint(1, colors - 1)
    if rng.random() < 0.7:
        tile[0, :] = tile[:, 0] = 0
    if rng.random() < 0.7:
        tile[-1, :] = tile[:, -1] = 0
    return tile


def _sprite_sheet(seed: int, count: int = 64, colors: int = 8) -> bytes:
    rng = random.Random(seed)
    return b"".join(_encode_snes(_sprite_tile(rng, colors=colors), 4)
                    for _ in range(count))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_bloc_constant_note_nulle():
    """Un bloc rempli d'une seule valeur n'est jamais un graphisme."""
    fmt = FORMATS_BY_KEY["snes_4bpp"]
    for filler in (b"\x00", b"\xff", b"\x55"):
        assert S.score(filler * 4096, fmt) == 0.0


def test_bloc_aleatoire_rejete():
    """Du bruit uniforme doit rester sous le seuil de travail."""
    fmt = FORMATS_BY_KEY["snes_4bpp"]
    rng = random.Random(7)
    for _ in range(5):
        blob = bytes(rng.randrange(256) for _ in range(4096))
        assert S.score(blob, fmt) < S.DEFAULT_THRESHOLD, S.score(blob, fmt)


def test_sprites_synthetiques_acceptes():
    """Une planche de sprites synthétique doit dépasser le seuil."""
    fmt = FORMATS_BY_KEY["snes_4bpp"]
    for seed in range(5):
        value = S.score(_sprite_sheet(seed), fmt)
        assert value > 0.60, (seed, value)


def test_veto_des_tuiles_identiques():
    """Un bloc fait de tuiles toutes identiques est rejeté par le veto."""
    fmt = FORMATS_BY_KEY["snes_4bpp"]
    rng = random.Random(3)
    tile = _encode_snes(_sprite_tile(rng, colors=8), 4)
    blob = tile * 64
    assert S.score(blob, fmt) < 0.05, S.score(blob, fmt)


def test_indices_dans_les_bornes():
    """Chaque indice est normalisé entre 0 et 1."""
    fmt = FORMATS_BY_KEY["snes_4bpp"]
    for blob in (_sprite_sheet(1), bytes(range(256)) * 16):
        features = S.tile_features(blob, fmt)
        assert features is not None
        for name, value in features.items():
            assert 0.0 <= value <= 1.0, (name, value)


def test_bloc_trop_court_rejete():
    """Moins de quatre tuiles : la note n'a pas de sens et vaut zéro."""
    fmt = FORMATS_BY_KEY["snes_4bpp"]
    assert S.score(b"\x01\x02\x03" * 8, fmt) == 0.0


def test_explain_coherent_avec_score():
    """Le détail renvoyé par ``explain`` correspond à la note."""
    fmt = FORMATS_BY_KEY["snes_4bpp"]
    blob = _sprite_sheet(11)
    detail = S.explain(blob, fmt)
    assert abs(detail["score"] - S.score(blob, fmt)) < 1e-9
    assert set(detail["contributions"]) == set(S.FEATURE_NAMES)
    assert 0.0 <= detail["gate"] <= 1.0


def test_score_formats_renvoie_le_maximum():
    """``score_formats`` renvoie bien le meilleur format et sa note."""
    blob = _sprite_sheet(5)
    formats = [FORMATS_BY_KEY[key] for key in
               ("snes_4bpp", "snes_2bpp", "megadrive", "zx_spectrum")]
    value, chosen = S.score_formats(blob, formats)
    expected = max(S.score(blob, fmt) for fmt in formats)
    assert abs(value - expected) < 1e-9
    assert chosen is not None
    assert value > 0.6


def test_bruit_rejete_dans_tous_les_formats():
    """Du bruit reste du bruit, quelle que soit la profondeur de lecture."""
    rng = random.Random(9)
    blob = bytes(rng.randrange(256) for _ in range(4096))
    for key in ("zx_spectrum", "c64", "snes_2bpp", "snes_4bpp", "megadrive",
                "cpc_mode0", "chunky8"):
        fmt = FORMATS_BY_KEY[key]
        value = S.score(blob, fmt)
        assert value < S.DEFAULT_THRESHOLD, (key, value)
