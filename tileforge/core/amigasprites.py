"""Découpe automatique de planches de sprites Amiga.

Une planche Amiga est un bitmap planaire où les sprites sont posés en vrac :
sur Project-X, 640×256 en 5 plans, 1 043 composantes connexes, beaucoup de
fragments (un vaisseau et ses flammes séparées).  Ce module fournit les
outils qui manquaient :

* **composantes connexes** 8-connexité sur le masque « index ≠ 0 », avec
  fermeture morphologique optionnelle pour ne pas couper un vaisseau en
  morceaux ;
* **détection de grille** par autocorrélation des marges vides ;
* **détection de pré-décalage** : sur Amiga, un sprite peut être stocké en
  16 copies décalées horizontalement pour le défilement ; on repère les
  copies quasi identiques à un décalage près ;
* **groupement d'animations** par distance de Hamming sur le masque ;
* export RGBA avec transparence sur l'index 0.

Le module travaille sur des grilles d'indices (``numpy``), pas sur des
fichiers : il s'utilise après :func:`tileforge.core.planar.decode_indices`.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .image import Image, save_image
from .palettes import Palette


@dataclass
class Sprite:
    """Composante connexe extraite d'une planche."""

    x: int
    y: int
    w: int
    h: int
    area: int
    index: np.ndarray = field(repr=False)

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)

    @property
    def mask(self) -> np.ndarray:
        return self.index != 0

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h,
                "area": self.area}

    def image(self, palette: Palette, transparent: int = 0) -> Image:
        colors = [palette.rgba(i) for i in range(len(palette))]
        if transparent < len(colors):
            r, g, b, _ = colors[transparent]
            colors[transparent] = (r, g, b, 0)
        return Image.from_indexed(self.index, colors)


@dataclass
class GridSpec:
    """Grille régulière détectée sur une planche."""

    cell_w: int
    cell_h: int
    offset_x: int = 0
    offset_y: int = 0
    score: float = 0.0

    def cells(self, width: int, height: int) -> list[tuple[int, int, int, int]]:
        out = []
        y = self.offset_y
        while y + self.cell_h <= height:
            x = self.offset_x
            while x + self.cell_w <= width:
                out.append((x, y, self.cell_w, self.cell_h))
                x += self.cell_w
            y += self.cell_h
        return out

    def as_dict(self) -> dict:
        return {"cell_w": self.cell_w, "cell_h": self.cell_h,
                "offset_x": self.offset_x, "offset_y": self.offset_y,
                "score": round(self.score, 4)}


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
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


def _erode(mask: np.ndarray, radius: int) -> np.ndarray:
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
            out &= shifted
    return out


def close_mask(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    """Fermeture morphologique : bouche les trous de ``radius`` pixels."""
    if radius <= 0:
        return mask
    return _erode(_dilate(mask, radius), radius)


def components(index: np.ndarray, min_area: int = 4,
               close_radius: int = 0) -> list[Sprite]:
    """Extrait les composantes 8-connexes du masque « index ≠ 0 »."""
    mask = close_mask(index != 0, close_radius)
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    sprites: list[Sprite] = []
    neighbours = ((-1, -1), (-1, 0), (-1, 1), (0, -1),
                  (0, 1), (1, -1), (1, 0), (1, 1))

    for y in range(height):
        for x in range(width):
            if not mask[y, x] or visited[y, x]:
                continue
            queue = deque([(y, x)])
            visited[y, x] = True
            min_x = max_x = x
            min_y = max_y = y
            area = 0
            pixels: list[tuple[int, int]] = []
            while queue:
                cy, cx = queue.popleft()
                area += 1
                pixels.append((cy, cx))
                if cx < min_x:
                    min_x = cx
                elif cx > max_x:
                    max_x = cx
                if cy < min_y:
                    min_y = cy
                elif cy > max_y:
                    max_y = cy
                for dy, dx in neighbours:
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < height and 0 <= nx < width \
                            and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        queue.append((ny, nx))
            if area < min_area:
                continue
            crop = index[min_y:max_y + 1, min_x:max_x + 1].copy()
            # Les pixels hors de la composante (autres objets du rectangle)
            # sont ramenés au fond pour ne pas les inclure dans le sprite.
            component_mask = np.zeros(crop.shape, dtype=bool)
            for cy, cx in pixels:
                component_mask[cy - min_y, cx - min_x] = True
            crop[~component_mask] = 0
            sprites.append(Sprite(min_x, min_y, max_x - min_x + 1,
                                  max_y - min_y + 1, area, crop))
    sprites.sort(key=lambda s: (s.y, s.x))
    return sprites


def detect_grid(index: np.ndarray, min_cell: int = 8,
                max_cell: int = 64) -> GridSpec:
    """Détecte une grille régulière par les marges vides.

    On cherche la période qui maximise la proportion de colonnes (et de
    lignes) entièrement vides : sur une planche en cellules, les séparateurs
    tombent à chaque multiple de la cellule.
    """
    mask = index != 0
    height, width = mask.shape
    col_empty = ~mask.any(axis=0)
    row_empty = ~mask.any(axis=1)

    def runs(empty: np.ndarray) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        start = None
        for i, value in enumerate(empty):
            if not value and start is None:
                start = i
            elif value and start is not None:
                out.append((start, i - start))
                start = None
        if start is not None:
            out.append((start, len(empty) - start))
        return out

    def period_from_runs(empty: np.ndarray, limit: int) -> tuple[int, int, float]:
        """Période déduite des débuts de blocs d'encre."""
        blocks = runs(empty)
        if len(blocks) >= 2:
            starts = [start for start, _ in blocks]
            diffs = [b - a for a, b in zip(starts, starts[1:], strict=False)
                     if min_cell <= b - a <= limit]
            if diffs:
                diffs.sort()
                period = diffs[len(diffs) // 2]
                score = sum(1 for d in diffs if d == period) / len(diffs)
                return period, starts[0], score
        # Repli : période des marges vides, en préférant la plus petite.
        scores: list[tuple[int, float]] = []
        for period in range(min_cell, min(limit, len(empty)) + 1):
            positions = range(0, len(empty), period)
            score = float(np.mean([empty[p] for p in positions]))
            scores.append((period, score))
        if not scores:
            return 0, 0, 0.0
        best_score = max(score for _, score in scores)
        for period, score in scores:
            if score >= best_score - 0.01:
                return period, 0, score
        return scores[-1][0], 0, scores[-1][1]

    cell_w, offset_x, score_w = period_from_runs(col_empty, max_cell)
    cell_h, offset_y, score_h = period_from_runs(row_empty, max_cell)
    if not cell_w:
        cell_w = width
    if not cell_h:
        cell_h = height
    return GridSpec(cell_w, cell_h, offset_x, offset_y,
                    (score_w + score_h) / 2.0)


def _mask_similarity(a: np.ndarray, b: np.ndarray, shift: int = 0) -> float:
    """Similarité de deux masques, avec décalage horizontal de ``b``."""
    height = min(a.shape[0], b.shape[0])
    width = min(a.shape[1], b.shape[1] - shift)
    if width <= 0 or height <= 0:
        return 0.0
    aa = a[:height, :width]
    bb = b[:height, shift:shift + width]
    union = np.logical_or(aa, bb).sum()
    if union == 0:
        return 1.0
    return float(np.logical_and(aa, bb).sum() / union)


def detect_preshift(sprites: list[Sprite], max_shift: int = 16,
                    threshold: float = 0.92,
                    max_pairs: int = 50000) -> list[dict]:
    """Repère les copies d'un sprite à un décalage horizontal près.

    Renvoie les paires ``{a, b, shift, similarity}`` ; ``a`` et ``b`` sont des
    indices dans ``sprites``.  Sur les planches Amiga, 16 copies décalées sont
    courantes pour le défilement.

    Les sprites sont d'abord regroupés par hauteur et par surface : sur une
    planche de 1 043 sprites, comparer toutes les paires coûterait des
    millions d'opérations. ``max_pairs`` borne le travail.
    """
    found: list[dict] = []
    buckets: dict[tuple[int, int], list[int]] = {}
    for index, sprite in enumerate(sprites):
        buckets.setdefault((sprite.h // 2, sprite.area // 32), []).append(index)
    pairs = 0
    for indices in buckets.values():
        for position, i in enumerate(indices):
            first = sprites[i]
            for j in indices[position + 1:]:
                if pairs >= max_pairs:
                    return found
                pairs += 1
                second = sprites[j]
                if abs(first.h - second.h) > 2:
                    continue
                if abs(first.area - second.area) > max(4, first.area * 0.4):
                    continue
                best_shift, best_score, best_rank = 0, 0.0, -1.0
                for shift in range(0, min(max_shift, second.w) + 1):
                    score = _mask_similarity(first.mask, second.mask, shift)
                    # Un recouvrement étroit ne doit pas gagner : on pondère
                    # par la largeur réellement comparée.
                    width = min(first.w, second.w - shift)
                    coverage = width / max(first.w, second.w, 1)
                    rank = score * coverage
                    if rank >= best_rank:
                        best_shift, best_score, best_rank = shift, score, rank
                # Un décalage nul signifie « sprite identique » (doublon), pas
                # une copie pré-décalée : on ne le signale pas ici.
                if best_shift > 0 and best_score >= threshold:
                    found.append({"a": i, "b": j, "shift": best_shift,
                                  "similarity": round(best_score, 4)})
    return found


def group_animations(sprites: list[Sprite], threshold: float = 0.80,
                     max_shift: int = 4,
                     max_comparisons: int = 200000) -> list[list[int]]:
    """Regroupe les sprites similaires en séquences d'animation.

    Distance de Hamming sur le masque, tolérance de quelques pixels de
    décalage.  Groupement glouton : chaque sprite rejoint le premier groupe
    dont un membre lui ressemble.
    """
    groups: list[list[int]] = []
    comparisons = 0
    for index, sprite in enumerate(sprites):
        placed = False
        for group in groups:
            comparisons += 1
            if comparisons > max_comparisons:
                groups.append([index])
                placed = True
                break
            reference = sprites[group[0]]
            best = max(_mask_similarity(sprite.mask, reference.mask, shift)
                       for shift in range(0, min(max_shift, reference.w) + 1))
            if best >= threshold:
                group.append(index)
                placed = True
                break
        if not placed:
            groups.append([index])
    return [g for g in groups if len(g) > 1] + [[g[0]] for g in groups if len(g) == 1]


def export_sheet(sprites: list[Sprite], palette: Palette, path: str,
                 columns: int = 8, padding: int = 2) -> int:
    """Écrit une planche RGBA des sprites extraits ; renvoie le nombre écrit."""
    if not sprites:
        raise ValueError("aucun sprite à exporter")
    cell_w = max(s.w for s in sprites) + padding * 2
    cell_h = max(s.h for s in sprites) + padding * 2
    rows = (len(sprites) + columns - 1) // columns
    width = columns * cell_w
    height = rows * cell_h
    sheet = Image.blank(width, height, (0, 0, 0, 0))
    for i, sprite in enumerate(sprites):
        image = sprite.image(palette)
        x = (i % columns) * cell_w + padding
        y = (i // columns) * cell_h + padding
        sheet.paste(image, x, y)
    save_image(path, sheet)
    return len(sprites)
