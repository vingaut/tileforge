"""D2 — profils de projection.

On projette le masque de contenu sur les axes : les colonnes (resp. lignes)
entièrement vides séparent les tuiles.  Les petites gouttières internes sont
fusionnées, puis on peut « régulariser » la grille si les bandes ont toutes la
même largeur (cas des planches de ROM).
"""

from __future__ import annotations

import numpy as np

from ..core.image import Image
from .base import Detector, ParamSpec, Rect, content_mask, mask_profiles, runs_of


class ProjectionDetector(Detector):
    key = "projection"
    name = "Profils de projection"
    description = ("Découpe aux colonnes et lignes vides. Robuste sur les "
                   "planches avec gouttières ; la régularisation reconstruit "
                   "une grille quand une tuile est vide.")
    params = [
        ParamSpec("tolerance", "Tolérance de fond", "int", 8, 0, 255,
                  help="écart de couleur admis pour le fond"),
        ParamSpec("min_pixels", "Seuil de vide", "int", 1, 1, 255,
                  help="nombre de pixels pleins pour qu'une ligne/colonne compte"),
        ParamSpec("min_band", "Taille minimale", "int", 2, 1, 512),
        ParamSpec("fuse_gap", "Fusion des petits vides", "int", 1, 0, 64,
                  help="fusionne les bandes séparées par moins de N pixels"),
        ParamSpec("regularize", "Régulariser la grille", "bool", True),
        ParamSpec("keep_empty", "Conserver les cellules vides", "bool", True),
    ]

    def detect(self, image: Image, p: dict) -> list[Rect]:
        mask = content_mask(image, int(p["tolerance"]))
        colp, rowp = mask_profiles(mask)
        thr = max(1, int(p["min_pixels"]))
        fuse = max(0, int(p["fuse_gap"]))
        min_band = max(1, int(p["min_band"]))

        bands_x = self._bands(colp > thr, fuse, min_band)
        bands_y = self._bands(rowp > thr, fuse, min_band)

        if p.get("regularize", True):
            bands_x = self._regularize(bands_x)
            bands_y = self._regularize(bands_y)

        rects: list[Rect] = []
        for (y0, y1) in bands_y:
            for (x0, x1) in bands_x:
                if (not p.get("keep_empty", True)
                        and not mask[y0:y1, x0:x1].any()):
                    continue
                rects.append((x0, y0, x1 - x0, y1 - y0))
        return rects

    # -- étapes -------------------------------------------------------------

    @staticmethod
    def _bands(flags, fuse: int, min_band: int) -> list[tuple[int, int]]:
        runs = runs_of(flags)
        merged: list[list[int]] = []
        for a, b in runs:
            if merged and a - merged[-1][1] <= fuse:
                merged[-1][1] = b
            else:
                merged.append([a, b])
        return [(a, b) for a, b in merged if b - a >= min_band]

    @staticmethod
    def _regularize(bands: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Reconstruit une grille régulière si les bandes sont homogènes."""
        if len(bands) < 3:
            return bands
        widths = np.array([b - a for a, b in bands])
        starts = np.array([a for a, _ in bands])
        steps = np.diff(starts)
        if len(steps) == 0:
            return bands
        w_med = int(np.median(widths))
        step_med = int(np.median(steps))
        if w_med <= 0 or step_med <= 0:
            return bands
        # homogénéité : au moins 80 % des bandes à la largeur médiane
        if np.mean(np.abs(widths - w_med) <= 1) < 0.8:
            return bands
        if np.mean(np.abs(steps - step_med) <= 1) < 0.8:
            return bands
        out = []
        pos = bands[0][0]
        last = bands[-1][1]
        while pos + w_med <= last:
            out.append((pos, pos + w_med))
            pos += step_med
        return out
