"""Socle commun des détecteurs de tuiles.

Un détecteur prend une :class:`~tileforge.core.image.Image` et un dictionnaire
de paramètres, et renvoie une liste de rectangles ``(x, y, largeur, hauteur)``.
Chaque détecteur déclare ses paramètres (:class:`ParamSpec`) pour que
l'interface puisse générer le formulaire automatiquement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..core.image import Image, detect_background

# ---------------------------------------------------------------------------
# Paramètres
# ---------------------------------------------------------------------------


@dataclass
class ParamSpec:
    """Description d'un paramètre de détecteur."""

    key: str
    label: str
    kind: str = "int"            # "int" | "float" | "bool" | "choice"
    default: object = 0
    minimum: int = 0
    maximum: int = 4096
    step: int = 1
    choices: list = field(default_factory=list)   # [(valeur, libellé), ...]
    help: str = ""

    def coerce(self, value):
        if self.kind == "int":
            return int(value)
        if self.kind == "float":
            return float(value)
        if self.kind == "bool":
            return bool(value)
        return value


Rect = tuple[int, int, int, int]


# ---------------------------------------------------------------------------
# Masque de contenu
# ---------------------------------------------------------------------------


def content_mask(image: Image, tolerance: int = 8, alpha_threshold: int = 1) -> np.ndarray:
    """Masque booléen des pixels « pleins ».

    Si l'image possède de la transparence, c'est l'alpha qui décide ; sinon on
    compare à la couleur de fond détectée sur le bord.
    """
    alpha = image.px[..., 3]
    if int(alpha.min()) < 255:
        return alpha >= alpha_threshold
    bg = np.asarray(detect_background(image), dtype=np.int16)
    d = np.abs(image.px[..., :3].astype(np.int16) - bg).max(axis=2)
    return d > tolerance


def mask_profiles(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return mask.sum(axis=0), mask.sum(axis=1)


def runs_of(flags: np.ndarray) -> list[tuple[int, int]]:
    """Plages [début, fin) où ``flags`` est vrai."""
    runs: list[tuple[int, int]] = []
    start = None
    for i, v in enumerate(flags):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(flags)))
    return runs


# ---------------------------------------------------------------------------
# Utilitaires de rectangles
# ---------------------------------------------------------------------------


def clamp_rect(rect: Rect, width: int, height: int) -> Rect | None:
    x, y, w, h = rect
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(width, x + w), min(height, y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def dedupe_rects(rects: list[Rect], tolerance: int = 0) -> list[Rect]:
    """Supprime les rectangles identiques (à ``tolerance`` près)."""
    out: list[Rect] = []
    seen = set()
    for r in rects:
        key = tuple(round(v / max(1, tolerance)) for v in r) if tolerance else r
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def sort_reading_order(rects: list[Rect], row_tolerance: int | None = None) -> list[Rect]:
    """Tri ligne par ligne (ordre de lecture)."""
    if not rects:
        return []
    if row_tolerance is None:
        heights = [r[3] for r in rects]
        row_tolerance = max(2, int(np.median(heights)) // 2) if heights else 2
    ordered = sorted(rects, key=lambda r: (r[1], r[0]))
    rows: list[list[Rect]] = []
    for r in ordered:
        if rows and abs(r[1] - rows[-1][0][1]) <= row_tolerance:
            rows[-1].append(r)
        else:
            rows.append([r])
    out = []
    for row in rows:
        out.extend(sorted(row, key=lambda r: r[0]))
    return out


def union_rects(a: Rect, b: Rect) -> Rect:
    x0 = min(a[0], b[0])
    y0 = min(a[1], b[1])
    x1 = max(a[0] + a[2], b[0] + b[2])
    y1 = max(a[1] + a[3], b[1] + b[3])
    return (x0, y0, x1 - x0, y1 - y0)


def overlap_ratio(a: Rect, b: Rect) -> float:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[0] + a[2], b[0] + b[2])
    y1 = min(a[1] + a[3], b[1] + b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    return inter / max(1, min(a[2] * a[3], b[2] * b[3]))


# ---------------------------------------------------------------------------
# Détecteur
# ---------------------------------------------------------------------------


class Detector:
    """Classe de base des détecteurs."""

    key: str = ""
    name: str = ""
    description: str = ""
    params: list[ParamSpec] = []

    def defaults(self) -> dict:
        return {p.key: p.default for p in self.params}

    def detect(self, image: Image, params: dict) -> list[Rect]:  # pragma: no cover
        raise NotImplementedError

    def run(self, image: Image, params: dict | None = None) -> list[Rect]:
        p = self.defaults()
        p.update(params or {})
        rects = self.detect(image, p)
        out = []
        for r in rects:
            c = clamp_rect(r, image.w, image.h)
            if c:
                out.append(c)
        return dedupe_rects(out)


# ---------------------------------------------------------------------------
# Contrôle qualité
# ---------------------------------------------------------------------------


@dataclass
class QualityIssue:
    kind: str          # "overlap" | "empty" | "bounds" | "size" | "duplicate"
    message: str
    tile_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "message": self.message, "tiles": self.tile_ids}


def quality_report(sheet, empty_ratio: float = 0.98) -> list[QualityIssue]:
    """Liste les anomalies d'un découpage."""
    issues: list[QualityIssue] = []
    tiles = sheet.tiles
    if not tiles:
        return issues

    sizes: dict[tuple[int, int], int] = {}
    for t in tiles:
        sizes[(t.w, t.h)] = sizes.get((t.w, t.h), 0) + 1
    if len(sizes) > 1:
        main = max(sizes.items(), key=lambda kv: kv[1])[0]
        odd = [t for t in tiles if (t.w, t.h) != main]
        issues.append(QualityIssue(
            "size",
            f"{len(odd)} tuile(s) hors de la taille dominante {main[0]}×{main[1]}",
            [t.id for t in odd[:50]]))

    for t in tiles:
        if t.x < 0 or t.y < 0 or t.x + t.w > sheet.image.w or t.y + t.h > sheet.image.h:
            issues.append(QualityIssue("bounds", f"Tuile {t.id} dépasse la planche", [t.id]))

    # chevauchements (grille spatiale grossière)
    if len(tiles) <= 4000:
        order = sorted(tiles, key=lambda t: t.x)
        for i, a in enumerate(order):
            for b in order[i + 1:]:
                if b.x >= a.x + a.w:
                    break
                if overlap_ratio(a.rect, b.rect) > 0.0:
                    issues.append(QualityIssue(
                        "overlap", f"Tuiles {a.id} et {b.id} se chevauchent", [a.id, b.id]))

    # tuiles vides
    empty_ids = []
    for t in tiles:
        sub = sheet.image.cropped(*t.rect)
        if sub.alpha_mask().mean() < (1.0 - empty_ratio):
            empty_ids.append(t.id)
    if empty_ids:
        issues.append(QualityIssue("empty", f"{len(empty_ids)} tuile(s) vide(s)",
                                   empty_ids[:50]))
    return issues


# ---------------------------------------------------------------------------
# Registre
# ---------------------------------------------------------------------------


def all_detectors() -> list[Detector]:
    """Tous les détecteurs disponibles, dans l'ordre de l'interface."""
    from .components import ComponentsDetector
    from .grid import GridDetector
    from .manual import ManualDetector
    from .period import PeriodDetector
    from .projection import ProjectionDetector
    from .xycuts import XYCutDetector

    return [GridDetector(), PeriodDetector(), ProjectionDetector(),
            XYCutDetector(), ComponentsDetector(), ManualDetector()]


def detector_by_key(key: str) -> Detector | None:
    for d in all_detectors():
        if d.key == key:
            return d
    return None
