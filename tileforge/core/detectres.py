"""Détection de la résolution native et identification de la machine.

Trois questions auxquelles ce module répond :

1. **Quelle est la résolution native ?**  Une capture d'émulateur est souvent
   agrandie ×2 ou ×3 (voire ×4) : on cherche le facteur d'agrandissement, puis
   la taille d'origine.
2. **Quel est le pas de la grille de tuiles ?**  Par autocorrélation des
   profils de projection et par analyse des colonnes vides.
3. **De quelle machine vient l'image ?**  On confronte résolution, nombre de
   couleurs, profondeur et taille de tuile à la base ``systems.py``.

Le résultat est un :class:`ResolutionReport` que l'interface affiche et que
l'utilisateur peut corriger.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .image import Image, detect_background
from .systems import SYSTEMS, SystemSpec

# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------


@dataclass
class SystemGuess:
    spec: SystemSpec
    score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.spec.name} ({self.spec.family}, {self.spec.year})"


@dataclass
class ResolutionReport:
    """Synthèse de l'analyse d'une image."""

    width: int = 0
    height: int = 0
    content_box: tuple[int, int, int, int] = (0, 0, 0, 0)
    background: tuple[int, int, int] = (0, 0, 0)
    has_alpha: bool = False
    color_count: int = 0
    estimated_bpp: int = 4
    scale: int = 1
    native_size: tuple[int, int] = (0, 0)
    pitch: tuple[int, int] = (8, 8)
    pitch_scores: list[tuple[int, int, float]] = field(default_factory=list)
    tile_size: tuple[int, int] = (8, 8)
    tile_scores: list[tuple[tuple[int, int], float]] = field(default_factory=list)
    guesses: list[SystemGuess] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [f"Image : {self.width} × {self.height} px"]
        if self.scale > 1:
            lines.append(f"Agrandissement ×{self.scale} → natif {self.native_size[0]} × {self.native_size[1]}")
        else:
            lines.append("Résolution native (pas d'agrandissement détecté)")
        lines.append(f"Couleurs distinctes : {self.color_count} → environ {self.estimated_bpp} bits/pixel")
        lines.append(f"Pas de grille estimé : {self.pitch[0]} × {self.pitch[1]} px")
        lines.append(f"Taille de tuile proposée : {self.tile_size[0]} × {self.tile_size[1]}")
        bx, by, bw, bh = self.content_box
        if (bx, by, bw, bh) != (0, 0, self.width, self.height) and bw and bh:
            lines.append(f"Zone utile : {bw} × {bh} px en ({bx}, {by})")
        if self.guesses:
            lines.append("Machines compatibles :")
            for g in self.guesses[:5]:
                lines.append(f"  • {g.label} — {g.score:.0f} pts")
        else:
            lines.append("Aucune machine connue ne correspond exactement.")
        return lines

    def best(self) -> SystemSpec | None:
        return self.guesses[0].spec if self.guesses else None

    def as_dict(self) -> dict:
        return {
            "width": self.width, "height": self.height,
            "content_box": list(self.content_box),
            "background": list(self.background),
            "color_count": self.color_count,
            "estimated_bpp": self.estimated_bpp,
            "scale": self.scale,
            "native_size": list(self.native_size),
            "pitch": list(self.pitch),
            "tile_size": list(self.tile_size),
            "systems": [g.spec.key for g in self.guesses[:6]],
        }


# ---------------------------------------------------------------------------
# Statistiques de base
# ---------------------------------------------------------------------------


def color_count(img: Image) -> int:
    return img.color_count()


def estimate_bpp(colors: int) -> int:
    """Profondeur minimale nécessaire pour coder ``colors`` couleurs."""
    for bpp in (1, 2, 3, 4, 5, 6, 7, 8):
        if colors <= (1 << bpp):
            return bpp
    return 8


def content_box(img: Image, tolerance: int = 8) -> tuple[int, int, int, int]:
    """Boîte englobante du contenu, en ignorant le fond détecté."""
    bg = np.asarray(detect_background(img), dtype=np.int16)
    d = np.abs(img.px[..., :3].astype(np.int16) - bg).max(axis=2)
    mask = d > tolerance
    if img.px[..., 3].min() < 255:
        mask |= img.px[..., 3] > 0
    if not mask.any():
        return (0, 0, img.w, img.h)
    ys = mask.any(axis=1)
    xs = mask.any(axis=0)
    y0, y1 = int(ys.argmax()), int(len(ys) - 1 - ys[::-1].argmax())
    x0, x1 = int(xs.argmax()), int(len(xs) - 1 - xs[::-1].argmax())
    return (x0, y0, x1 - x0 + 1, y1 - y0 + 1)


def detect_scale(img: Image, max_scale: int = 8) -> int:
    """Facteur d'agrandissement au plus proche voisin (1 si aucun)."""
    px = img.px
    h, w = px.shape[:2]
    for k in range(2, max_scale + 1):
        if w % k or h % k:
            continue
        small = px[::k, ::k]
        if small.shape[0] * k != h or small.shape[1] * k != w:
            continue
        big = np.repeat(np.repeat(small, k, axis=0), k, axis=1)
        if np.array_equal(big, px):
            return k
    return 1


# ---------------------------------------------------------------------------
# Pas de la grille
# ---------------------------------------------------------------------------


def _autocorr(profile: np.ndarray, min_p: int, max_p: int) -> list[tuple[int, float]]:
    """Autocorrélation normalisée d'un profil 1D, pics pour les périodes utiles."""
    x = profile.astype(np.float64)
    x = x - x.mean()
    if not np.any(x):
        return []
    n = len(x)
    ac = np.correlate(x, x, mode="full")[n - 1:]
    if ac[0] <= 0:
        return []
    ac = ac / ac[0]
    out = []
    for p in range(max(2, min_p), min(max_p, n - 1) + 1):
        if ac[p] >= ac[p - 1] and ac[p] >= (ac[p + 1] if p + 1 < n else -1):
            out.append((p, float(ac[p])))
    return out


def _projection_profiles(img: Image):
    """Profils de projection : nombre de pixels non-fond par colonne / ligne."""
    bg = np.asarray(detect_background(img), dtype=np.int16)
    d = np.abs(img.px[..., :3].astype(np.int16) - bg).max(axis=2)
    mask = d > 8
    if img.px[..., 3].min() < 255:
        mask |= img.px[..., 3] > 0
    return mask.sum(axis=0), mask.sum(axis=1)


def detect_pitch(img: Image, min_p: int = 4, max_p: int = 96,
                 preferred=(8, 16, 24, 32, 12, 6, 4)) -> tuple[tuple[int, int], list[tuple[int, int, float]]]:
    """Période dominante en X et en Y, et liste des candidats classés.

    Renvoie ``((px, py), [(px, py, score), ...])``.
    """
    colp, rowp = _projection_profiles(img)
    scores: dict[tuple[int, int], float] = {}

    for axis, prof in ((0, colp), (1, rowp)):
        peaks = dict(_autocorr(prof, min_p, max_p))
        for p, s in peaks.items():
            scores[(p, 0) if axis == 0 else (0, p)] = s

    # combine les deux axes
    xs = {p: s for (p, _), s in scores.items() if p}
    ys = {p: s for (_, p), s in scores.items() if p}
    if not xs:
        xs = {8: 0.0}
    if not ys:
        ys = {8: 0.0}

    combos = []
    for px, sx in xs.items():
        for py, sy in ys.items():
            score = (sx + sy) / 2.0
            # faveur aux tailles « rondes » et carrées
            if px in preferred:
                score += 0.06
            if py in preferred:
                score += 0.06
            if px == py:
                score += 0.04
            combos.append(((int(px), int(py)), float(score)))
    combos.sort(key=lambda kv: kv[1], reverse=True)

    best = combos[0][0] if combos else (8, 8)
    return best, [(w, h, s) for (w, h), s in combos[:12]]


def _empty_runs(profile: np.ndarray) -> list[tuple[int, int]]:
    """Plages d'indices consécutifs où le profil est nul."""
    runs = []
    start = None
    for i, v in enumerate(profile):
        if v == 0 and start is None:
            start = i
        elif v != 0 and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(profile)))
    return runs


def detect_gap_and_tiles(img: Image, tile_w: int, tile_h: int) -> tuple[int, int]:
    """Déduit l'espacement entre tuiles d'une planche déjà découpée."""
    colp, rowp = _projection_profiles(img)
    def gap_for(profile, t):
        runs = _empty_runs(profile)
        if not runs:
            return 0
        widths = [b - a for a, b in runs]
        # les gouttières sont les plages vides les plus fréquentes, plus courtes que t
        cands = [w for w in widths if 0 < w <= max(1, t // 2)]
        if not cands:
            return 0
        vals, counts = np.unique(cands, return_counts=True)
        return int(vals[int(np.argmax(counts))])
    return gap_for(colp, tile_w), gap_for(rowp, tile_h)


# ---------------------------------------------------------------------------
# Identification de la machine
# ---------------------------------------------------------------------------


def _res_distance(a, b) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def guess_systems(width: int, height: int, colors: int = 0, bpp: int = 0,
                  tile_size: tuple[int, int] | None = None,
                  max_results: int = 8) -> list[SystemGuess]:
    """Classe les machines compatibles avec une résolution et un profil couleur."""
    guesses: list[SystemGuess] = []
    for spec in SYSTEMS:
        score = 0.0
        reasons: list[str] = []
        best_res = min((_res_distance((width, height), r) for r in spec.resolutions),
                       default=9999)
        exact = (width, height) in spec.resolutions
        if exact:
            score += 60
            reasons.append("résolution exacte")
        elif best_res <= 8:
            score += 30
            reasons.append(f"résolution proche (±{best_res} px)")
        elif best_res <= 32:
            score += 12
            reasons.append(f"résolution voisine (±{best_res} px)")
        elif best_res <= 96:
            score += 3
        else:
            continue

        if colors:
            if colors <= spec.colors:
                score += 12
                reasons.append(f"{colors} couleurs ≤ {spec.colors}")
            else:
                score -= 25
                reasons.append(f"trop de couleurs pour {spec.colors}")
        if bpp and spec.bpp == bpp:
            score += 8
            reasons.append(f"{bpp} bits/pixel")
        if tile_size and tile_size in spec.tile_sizes:
            score += 10
            reasons.append(f"tuiles {tile_size[0]}×{tile_size[1]}")

        if score > 0:
            guesses.append(SystemGuess(spec, score, reasons))

    guesses.sort(key=lambda g: (-g.score, g.spec.year))
    return guesses[:max_results]


def guess_systems_by_profile(bpp: int, tile_size: tuple[int, int] | None = None,
                             colors: int = 0, max_results: int = 8) -> list[SystemGuess]:
    """Classe les machines d'après le profil des tuiles (sans résolution).

    Utile pour une banque brute : la taille d'image n'y veut rien dire, mais la
    profondeur, la taille de tuile et le nombre de couleurs parlent.
    """
    guesses: list[SystemGuess] = []
    for spec in SYSTEMS:
        score = 0.0
        reasons: list[str] = []
        if bpp and spec.bpp == bpp:
            score += 20
            reasons.append(f"{bpp} bits/pixel")
        if tile_size and tile_size in spec.tile_sizes:
            score += 25
            reasons.append(f"tuiles {tile_size[0]}×{tile_size[1]}")
        if colors and colors <= spec.colors:
            score += 5
            reasons.append(f"{colors} couleurs possibles")
        if score > 0:
            guesses.append(SystemGuess(spec, score, reasons))
    guesses.sort(key=lambda g: (-g.score, g.spec.year))
    return guesses[:max_results]


# ---------------------------------------------------------------------------
# Analyse complète
# ---------------------------------------------------------------------------


def analyse(img: Image, tile_size: tuple[int, int] | None = None) -> ResolutionReport:
    """Analyse une image et renvoie un rapport complet."""
    rep = ResolutionReport(width=img.w, height=img.h)
    rep.background = detect_background(img)
    rep.has_alpha = bool(img.px[..., 3].min() < 255)
    rep.color_count = img.color_count()
    rep.estimated_bpp = estimate_bpp(max(1, rep.color_count))
    rep.content_box = content_box(img)

    rep.scale = detect_scale(img)
    rep.native_size = (img.w // rep.scale, img.h // rep.scale)

    rep.pitch, rep.pitch_scores = detect_pitch(img)

    # tailles de tuile candidates : multiples du pas, tailles usuelles
    cands: dict[tuple[int, int], float] = {}
    px, py = rep.pitch
    for t in (4, 6, 8, 12, 16, 24, 32, 48, 64):
        if t % px == 0 or px % t == 0:
            cands[(t, t)] = 0.25
    for t in (8, 16, 32):
        cands[(t, t)] = cands.get((t, t), 0) + 0.35
    if tile_size:
        cands[tile_size] = 1.0
    for w, h, s in rep.pitch_scores[:6]:
        cands[(w, h)] = cands.get((w, h), 0) + s * 0.5
    ordered = sorted(cands.items(), key=lambda kv: kv[1], reverse=True)
    rep.tile_scores = ordered[:8]
    rep.tile_size = ordered[0][0] if ordered else (8, 8)

    rep.guesses = guess_systems(rep.native_size[0], rep.native_size[1],
                                rep.color_count, rep.estimated_bpp, rep.tile_size)
    return rep


def analyse_file(path: str) -> ResolutionReport:
    from .image import load_image
    return analyse(load_image(path))


# ---------------------------------------------------------------------------
# Aide au choix de résolution
# ---------------------------------------------------------------------------


def resolutions_by_family() -> dict[str, list[tuple[SystemSpec, tuple[int, int]]]]:
    """Toutes les résolutions connues, groupées par famille de machine."""
    out: dict[str, list[tuple[SystemSpec, tuple[int, int]]]] = {}
    for spec in SYSTEMS:
        for res in spec.resolutions:
            out.setdefault(spec.family, []).append((spec, res))
    for fam in out:
        out[fam].sort(key=lambda sr: (sr[0].year, sr[0].name, sr[1]))
    return out


def systems_for_resolution(width: int, height: int) -> list[SystemSpec]:
    return [s for s in SYSTEMS if (width, height) in s.resolutions]
