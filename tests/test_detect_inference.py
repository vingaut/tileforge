"""Tests des détecteurs de tuiles et de l'inférence de règle.

Les deux briques qui font la valeur de l'outil : découper une planche, puis
retrouver la logique d'ordonnancement des développeurs.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from tileforge.assemble.inference import Observation, infer, make_recipe
from tileforge.core.image import Image
from tileforge.detect.base import all_detectors

# ---------------------------------------------------------------------------
# Fabrique
# ---------------------------------------------------------------------------


def _sheet(cols: int = 4, rows: int = 3, tile: int = 8, gap: int = 2) -> Image:
    """Planche de tuiles colorées, séparées par une gouttière transparente."""
    width = cols * tile + (cols + 1) * gap
    height = rows * tile + (rows + 1) * gap
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    for gy in range(rows):
        for gx in range(cols):
            x0 = gap + gx * (tile + gap)
            y0 = gap + gy * (tile + gap)
            pixels[y0:y0 + tile, x0:x0 + tile, 0] = (gx * 40 + gy * 15) % 256
            pixels[y0:y0 + tile, x0:x0 + tile, 1] = 128
            pixels[y0:y0 + tile, x0:x0 + tile, 3] = 255
    return Image(pixels, None, [[0, 0, 0, 0], [255, 255, 255, 255]])


# ---------------------------------------------------------------------------
# Détecteurs
# ---------------------------------------------------------------------------


def test_detecteurs_disponibles():
    detectors = all_detectors()
    assert len(detectors) >= 6
    keys = {detector.key for detector in detectors}
    assert {"grid", "manual"} <= keys


def test_grille_fixe_retrouve_les_tuiles():
    image = _sheet(cols=4, rows=3, tile=8, gap=2)
    detector = next(d for d in all_detectors() if d.key == "grid")
    rects = detector.detect(image, {"tile_w": 8, "tile_h": 8, "gap_x": 2,
                                    "gap_y": 2, "offset_x": 2, "offset_y": 2,
                                    "cols": 4, "rows": 3, "count": 0})
    assert len(rects) == 12
    assert rects[0] == (2, 2, 8, 8)
    assert rects[1] == (12, 2, 8, 8)
    assert rects[4] == (2, 12, 8, 8)


def test_grille_fixe_respecte_le_nombre_demande():
    image = _sheet()
    detector = next(d for d in all_detectors() if d.key == "grid")
    rects = detector.detect(image, {"tile_w": 8, "tile_h": 8, "gap_x": 2,
                                    "gap_y": 2, "offset_x": 2, "offset_y": 2,
                                    "cols": 4, "rows": 3, "count": 5})
    assert len(rects) == 5


# ---------------------------------------------------------------------------
# Inférence
# ---------------------------------------------------------------------------


def _observations(mapping: list[int], count: int = 6) -> list[Observation]:
    """Sprites dont la case ``slot`` contient la tuile ``mapping[slot]``."""
    observations = []
    for index in range(count):
        obs = Observation(sprite_id=index, name=f"pose_{index:02d}",
                          cols=len(mapping), rows=1, base=index * 16)
        for slot, offset in enumerate(mapping):
            obs.offsets[slot] = offset
        observations.append(obs)
    return observations


def test_inference_identite():
    observations = _observations([0, 1, 2, 3, 4, 5])
    results = infer(observations)
    assert results
    best = results[0]
    assert best.key == "identity"
    assert best.exact_ratio == 1.0
    assert make_recipe(best, observations).mapping == [0, 1, 2, 3, 4, 5]


def test_inference_permutation():
    mapping = [3, 1, 5, 0, 2, 4]
    observations = _observations(mapping)
    results = infer(observations)
    assert results
    assert make_recipe(results[0], observations).mapping == mapping


def test_inference_serpentin():
    """Le serpentin est un modèle connu : il doit être retrouvé tel quel."""
    mapping = [0, 1, 2, 3, 5, 4, 7, 6]
    observations = _observations(mapping, count=4)
    results = infer(observations)
    assert results
    assert make_recipe(results[0], observations).mapping == mapping


def test_recette_depuis_inference():
    mapping = [2, 0, 3, 1]
    observations = _observations(mapping, count=4)
    result = infer(observations)[0]
    recipe = make_recipe(result, observations, name="test")
    assert recipe.mapping == mapping
    assert recipe.cols == 4 and recipe.rows == 1
    applied = recipe.apply([10, 11, 12, 13])
    assert applied == {0: 12, 1: 10, 2: 13, 3: 11}


def test_inference_sans_observation():
    assert infer([]) == []
