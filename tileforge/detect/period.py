"""D5 — détection de période par autocorrélation.

La planche est supposée être une grille régulière.  On cherche la période
dominante des profils de projection (colonnes / lignes), on en déduit le pas,
puis la taille de tuile en retirant la gouttière détectée.
"""

from __future__ import annotations

from ..core.detectres import detect_gap_and_tiles, detect_pitch
from ..core.image import Image
from .base import Detector, ParamSpec, Rect


class PeriodDetector(Detector):
    key = "period"
    name = "Période (autocorrélation)"
    description = ("Cherche la période dominante du motif en X et en Y, puis "
                   "applique une grille régulière. Utile quand on ne connaît "
                   "pas la taille de tuile.")
    params = [
        ParamSpec("min_period", "Période minimale", "int", 4, 2, 256),
        ParamSpec("max_period", "Période maximale", "int", 96, 4, 1024),
        ParamSpec("tile_w", "Largeur imposée", "int", 0, 0, 512,
                  help="0 = déduite de la période"),
        ParamSpec("tile_h", "Hauteur imposée", "int", 0, 0, 512),
        ParamSpec("detect_gap", "Détecter la gouttière", "bool", True),
        ParamSpec("offset_x", "Décalage X", "int", 0, 0, 4096),
        ParamSpec("offset_y", "Décalage Y", "int", 0, 0, 4096),
        ParamSpec("count", "Nombre de tuiles", "int", 0, 0, 100000),
    ]

    def detect(self, image: Image, p: dict) -> list[Rect]:
        (px, py), _scores = detect_pitch(image, int(p["min_period"]), int(p["max_period"]))
        tw = int(p["tile_w"]) or px
        th = int(p["tile_h"]) or py
        gx = gy = 0
        if p.get("detect_gap", True):
            dgx, dgy = detect_gap_and_tiles(image, tw, th)
            # la période inclut la gouttière
            if tw == px:
                tw = max(1, px - dgx)
                gx = dgx
            if th == py:
                th = max(1, py - dgy)
                gy = dgy
        ox = max(0, int(p["offset_x"]))
        oy = max(0, int(p["offset_y"]))
        count = max(0, int(p["count"]))
        step_x, step_y = tw + gx, th + gy
        if step_x <= 0 or step_y <= 0:
            return []
        cols = max(0, (image.w - ox + gx) // step_x)
        rows = max(0, (image.h - oy + gy) // step_y)
        rects: list[Rect] = []
        for r in range(rows):
            y = oy + r * step_y
            for c in range(cols):
                x = ox + c * step_x
                rects.append((x, y, tw, th))
                if count and len(rects) >= count:
                    return rects
        return rects
