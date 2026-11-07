"""D3 — composantes connexes du masque de contenu.

Utile quand les sprites ont des tailles variables et sont séparés par du vide :
on étiquette les paquets de pixels pleins, on dilate un peu pour recoller les
morceaux d'un même sprite, puis on fusionne les boîtes proches.
"""

from __future__ import annotations

import numpy as np

from ..core.image import Image
from .base import Detector, ParamSpec, Rect, content_mask, union_rects


def dilate_mask(mask: np.ndarray, radius: int) -> np.ndarray:
    """Dilatation carrée (rayon en pixels) par décalages successifs."""
    if radius <= 0:
        return mask
    out = mask.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue
            shifted = np.zeros_like(mask)
            ys = slice(max(0, dy), mask.shape[0] + min(0, dy))
            xs = slice(max(0, dx), mask.shape[1] + min(0, dx))
            yd = slice(max(0, -dy), mask.shape[0] + min(0, -dy))
            xd = slice(max(0, -dx), mask.shape[1] + min(0, -dx))
            shifted[ys, xs] = mask[yd, xd]
            out |= shifted
    return out


def label_mask(mask: np.ndarray, connectivity: int = 8):
    """Étiquetage des composantes connexes (union-find sur les plages).

    Renvoie ``(labels, n, boxes)`` où ``boxes[i]`` est la boîte de l'étiquette i+1.
    """
    h, w = mask.shape
    parent: list[int] = []
    info: list[tuple[int, int, int]] = []   # (y, x0, x1)

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    prev: list[int] = []
    for y in range(h):
        row = mask[y].astype(np.int8)
        edges = np.flatnonzero(np.diff(np.concatenate(([0], row, [0]))))
        cur: list[int] = []
        for k in range(0, len(edges), 2):
            x0, x1 = int(edges[k]), int(edges[k + 1])
            rid = len(parent)
            parent.append(rid)
            info.append((y, x0, x1))
            for pr in prev:
                py, px0, px1 = info[pr]
                if connectivity == 8:
                    if px1 >= x0 and px0 <= x1:
                        union(rid, pr)
                else:
                    if px1 > x0 and px0 < x1:
                        union(rid, pr)
            cur.append(rid)
        prev = cur

    labels = np.zeros((h, w), dtype=np.int32)
    roots: dict[int, int] = {}
    boxes: list[list[int]] = []
    for rid, (y, x0, x1) in enumerate(info):
        r = find(rid)
        lab = roots.get(r)
        if lab is None:
            lab = len(boxes) + 1
            roots[r] = lab
            boxes.append([x0, y, x1, y + 1])
        else:
            b = boxes[lab - 1]
            b[0] = min(b[0], x0)
            b[2] = max(b[2], x1)
            b[3] = max(b[3], y + 1)
        labels[y, x0:x1] = lab
    return labels, len(boxes), [tuple(b) for b in boxes]


class ComponentsDetector(Detector):
    key = "components"
    name = "Composantes connexes"
    description = ("Étiquette les paquets de pixels puis fusionne les boîtes "
                   "proches. Adapté aux sprites de tailles variables.")
    params = [
        ParamSpec("tolerance", "Tolérance de fond", "int", 8, 0, 255),
        ParamSpec("dilatation", "Dilatation", "int", 0, 0, 8,
                  help="pixels ajoutés autour du masque avant étiquetage"),
        ParamSpec("min_area", "Aire minimale", "int", 2, 0, 100000),
        ParamSpec("distance_fusion", "Distance de fusion", "int", 2, 0, 64,
                  help="fusionne les boîtes distantes de moins de N pixels"),
        ParamSpec("max_size", "Taille maximale", "int", 256, 1, 4096,
                  help="ignore les boîtes plus grandes (fond parasite)"),
        ParamSpec("connectivity", "Connexité", "choice", 8,
                  choices=[(4, "4-connexe"), (8, "8-connexe")]),
    ]

    def detect(self, image: Image, p: dict) -> list[Rect]:
        mask = content_mask(image, int(p["tolerance"]))
        if not mask.any():
            return []
        work = dilate_mask(mask, int(p["dilatation"]))
        _labels, n, boxes = label_mask(work, int(p["connectivity"]))
        if not n:
            return []

        min_area = int(p["min_area"])
        max_size = int(p["max_size"])
        rects: list[Rect] = []
        for (x0, y0, x1, y1) in boxes:
            bw, bh = x1 - x0, y1 - y0
            if bw * bh < min_area:
                continue
            if bw > max_size or bh > max_size:
                continue
            rects.append((x0, y0, bw, bh))

        dist = int(p["distance_fusion"])
        return self._merge(rects, dist)

    @staticmethod
    def _merge(rects: list[Rect], distance: int) -> list[Rect]:
        if distance <= 0 or len(rects) < 2:
            return rects
        changed = True
        while changed:
            changed = False
            out: list[Rect] = []
            used = [False] * len(rects)
            for i, a in enumerate(rects):
                if used[i]:
                    continue
                cur = a
                for j in range(i + 1, len(rects)):
                    if used[j]:
                        continue
                    if _near(cur, rects[j], distance):
                        cur = union_rects(cur, rects[j])
                        used[j] = True
                        changed = True
                used[i] = True
                out.append(cur)
            rects = out
        return rects


def _near(a: Rect, b: Rect, distance: int) -> bool:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    dx = max(bx0 - (ax0 + aw), ax0 - (bx0 + bw), 0)
    dy = max(by0 - (ay0 + ah), ay0 - (by0 + bh), 0)
    return dx <= distance and dy <= distance
