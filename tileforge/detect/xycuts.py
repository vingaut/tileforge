"""D4 — découpe récursive (XY-cut).

On coupe la boîte englobante à l'endroit du plus grand espace vide, en
alternant colonnes et lignes, jusqu'à obtenir des cellules de taille
raisonnable.  C'est la méthode classique pour séparer des sprites collés.
"""

from __future__ import annotations

import numpy as np

from ..core.image import Image
from .base import Detector, ParamSpec, Rect, content_mask, runs_of


class XYCutDetector(Detector):
    key = "xycut"
    name = "Découpe récursive (XY-cut)"
    description = ("Coupe récursivement au plus grand espace vide, en "
                   "alternant horizontal et vertical, jusqu'à des cellules "
                   "de taille acceptable.")
    params = [
        ParamSpec("tolerance", "Tolérance de fond", "int", 8, 0, 255),
        ParamSpec("min_size", "Taille minimale", "int", 4, 1, 512),
        ParamSpec("max_size", "Taille maximale", "int", 32, 1, 2048),
        ParamSpec("gap_min", "Gouttière minimale", "int", 1, 1, 64),
        ParamSpec("max_depth", "Profondeur maximale", "int", 12, 1, 40),
        ParamSpec("max_cells", "Nombre maximal de cellules", "int", 4000, 1, 100000),
    ]

    def detect(self, image: Image, p: dict) -> list[Rect]:
        mask = content_mask(image, int(p["tolerance"]))
        if not mask.any():
            return []
        ys = np.flatnonzero(mask.any(axis=1))
        xs = np.flatnonzero(mask.any(axis=0))
        root = (int(xs[0]), int(ys[0]), int(xs[-1] - xs[0] + 1), int(ys[-1] - ys[0] + 1))

        min_size = int(p["min_size"])
        max_size = int(p["max_size"])
        gap_min = int(p["gap_min"])
        max_depth = int(p["max_depth"])
        max_cells = int(p["max_cells"])

        out: list[Rect] = []
        stack = [(root, 0)]
        while stack:
            rect, depth = stack.pop()
            if len(out) >= max_cells:
                break
            if rect[2] <= max_size and rect[3] <= max_size:
                out.append(rect)
                continue
            if depth >= max_depth or (rect[2] <= min_size and rect[3] <= min_size):
                out.append(rect)
                continue
            split = self._best_split(mask, rect, gap_min)
            if split is None:
                out.append(rect)
                continue
            a, b = split
            stack.append((b, depth + 1))
            stack.append((a, depth + 1))
        return out

    @staticmethod
    def _best_split(mask: np.ndarray, rect: Rect, gap_min: int):
        x, y, w, h = rect
        sub = mask[y:y + h, x:x + w]

        def largest_gap(profile):
            empty = profile == 0
            best = None
            for a, b in runs_of(empty):
                if a == 0 or b == len(empty):
                    continue          # pas de coupe sur le bord
                if b - a < gap_min:
                    continue
                if best is None or (b - a) > (best[1] - best[0]):
                    best = (a, b)
            return best

        gx = largest_gap(sub.sum(axis=0))
        gy = largest_gap(sub.sum(axis=1))
        if gx is None and gy is None:
            return None
        # on privilégie la coupe qui équilibre le mieux les deux morceaux
        def balance(gap, length):
            mid = (gap[0] + gap[1]) / 2
            return abs(mid - length / 2)
        cand = []
        if gx is not None:
            cand.append((balance(gx, w), (x, y, gx[0], h), (x + gx[1], y, w - gx[1], h)))
        if gy is not None:
            cand.append((balance(gy, h), (x, y, w, gy[0]), (x, y + gy[1], w, h - gy[1])))
        cand.sort(key=lambda c: c[0])
        _score, a, b = cand[0]
        if a[2] <= 0 or a[3] <= 0 or b[2] <= 0 or b[3] <= 0:
            return None
        return a, b
