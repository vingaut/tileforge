"""D1 — grille fixe : la tuile est un rectangle régulier répété."""

from __future__ import annotations

import math

from ..core.image import Image
from .base import Detector, ParamSpec, Rect


class GridDetector(Detector):
    key = "grid"
    name = "Grille fixe"
    description = ("Découpe régulière : toutes les tuiles ont la même taille, "
                   "posées sur une grille avec un espacement constant. "
                   "C'est le détecteur exact d'une banque de ROM.")
    params = [
        ParamSpec("tile_w", "Largeur de tuile", "int", 24, 1, 512, help="en pixels"),
        ParamSpec("tile_h", "Hauteur de tuile", "int", 21, 1, 512, help="en pixels"),
        ParamSpec("offset_x", "Décalage X", "int", 0, 0, 4096),
        ParamSpec("offset_y", "Décalage Y", "int", 0, 0, 4096),
        ParamSpec("gap_x", "Espacement X", "int", 0, 0, 64,
                  help="pixels vides entre deux tuiles"),
        ParamSpec("gap_y", "Espacement Y", "int", 0, 0, 64),
        ParamSpec("cols", "Colonnes", "int", 0, 0, 4096,
                  help="0 = calculé d'après l'image"),
        ParamSpec("rows", "Lignes", "int", 0, 0, 4096,
                  help="0 = calculé d'après l'image"),
        ParamSpec("count", "Nombre de tuiles", "int", 0, 0, 100000,
                  help="0 = toutes ; sinon s'arrête après N tuiles"),
    ]

    def detect(self, image: Image, p: dict) -> list[Rect]:
        tw = max(1, int(p["tile_w"]))
        th = max(1, int(p["tile_h"]))
        ox = max(0, int(p["offset_x"]))
        oy = max(0, int(p["offset_y"]))
        gx = max(0, int(p["gap_x"]))
        gy = max(0, int(p["gap_y"]))
        cols = max(0, int(p["cols"]))
        rows = max(0, int(p["rows"]))
        count = max(0, int(p["count"]))

        step_x, step_y = tw + gx, th + gy
        if count and cols:
            rows = math.ceil(count / cols)
        elif count and rows:
            cols = math.ceil(count / rows)
        if not cols:
            cols = max(0, (image.w - ox + gx) // step_x)
        if not rows:
            rows = max(0, (image.h - oy + gy) // step_y)

        rects: list[Rect] = []
        for r in range(rows):
            y = oy + r * step_y
            if y + th > image.h:
                break
            for c in range(cols):
                x = ox + c * step_x
                if x + tw > image.w:
                    break
                rects.append((x, y, tw, th))
                if count and len(rects) >= count:
                    return rects
        return rects
