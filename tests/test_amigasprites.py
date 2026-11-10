"""Tests de la découpe de sprites Amiga."""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import amigasprites as A
from tileforge.core.palettes import Palette


def _sheet() -> np.ndarray:
    index = np.zeros((64, 64), dtype=np.int32)
    for y in (4, 20, 36, 52):
        for x in (4, 20, 36, 52):
            index[y:y + 8, x:x + 8] = 1 + ((x + y) // 16) % 3
    return index


def test_composantes_connexes():
    index = _sheet()
    sprites = A.components(index, min_area=4)
    assert len(sprites) == 16
    assert sprites[0].rect == (4, 4, 8, 8)
    assert sprites[0].area == 64


def test_fermeture_morphologique():
    index = np.zeros((32, 32), dtype=np.int32)
    index[4:12, 4:12] = 1
    index[13:21, 4:12] = 1          # deux blocs séparés d'une ligne
    assert len(A.components(index, min_area=4)) == 2
    assert len(A.components(index, min_area=4, close_radius=1)) == 1


def test_grille_reguliere():
    grid = A.detect_grid(_sheet())
    assert grid.cell_w == 16
    assert grid.cell_h == 16
    assert grid.offset_x == 4
    assert grid.offset_y == 4


def test_predécalage():
    index = np.zeros((16, 32), dtype=np.int32)
    index[0:8, 0:8] = 1             # boîte 10×8, encre à gauche
    index[0:8, 12:22] = 1           # boîte 10×8, encre à droite (décalage 2)
    sprites = A.components(index, min_area=4)
    assert len(sprites) == 2
    shifts = A.detect_preshift(sprites)
    assert shifts
    assert shifts[0]["shift"] == 2


def test_groupement_animations():
    index = np.zeros((32, 64), dtype=np.int32)
    index[0:8, 0:8] = 1
    index[0:8, 16:24] = 1           # même forme
    index[16:24, 0:8] = 2           # forme différente (plus petite)
    index[16:24, 0:4] = 0
    sprites = A.components(index, min_area=2)
    groups = A.group_animations(sprites)
    assert any(len(group) >= 2 for group in groups)


def test_export_planche():
    index = _sheet()
    sprites = A.components(index, min_area=4)
    palette = Palette([(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)])
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "sheet.png")
        count = A.export_sheet(sprites, palette, path)
        assert count == len(sprites)
        assert os.path.getsize(path) > 0


def test_masque_ne_melange_pas_les_objets():
    """Un objet entouré par un autre ne doit pas être aspiré dans sa boîte."""
    index = np.zeros((20, 20), dtype=np.int32)
    index[2:18, 2:18] = 1          # anneau
    index[3:17, 3:17] = 0
    index[9:11, 9:11] = 2          # petit objet au centre
    sprites = A.components(index, min_area=2, close_radius=0)
    assert len(sprites) == 2
    ring = next(s for s in sprites if s.area > 10)
    # Le petit objet central ne doit pas apparaître dans le rectangle de l'anneau.
    assert not np.any(ring.index == 2)
