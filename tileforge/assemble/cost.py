"""Fonction de coût d'un assemblage.

Le problème : trouver la permutation des tuiles qui rend le sprite « cohérent ».
Le coût est une somme pondérée de six indices :

C1 continuité de silhouette   — le masque opaque doit se poursuivre de part et
                                d'autre de la jointure ;
C2 continuité de couleur      — les pixels opaques voisins doivent se ressembler ;
C3 continuité de contour      — la dérivée au bord doit se poursuivre ;
C4 pénalité de trou           — un sprite ne doit pas avoir de trou intérieur ;
C5 similarité de palette      — deux tuiles voisines d'un même sprite partagent
                                souvent la même dominante ;
C6 pénalité de doublon        — deux tuiles quasi identiques ne doivent pas
                                être collées (piège des poses successives).

C1, C2, C3, C5 et C6 sont des coûts de *paire* : ils se précalculent une fois
pour toutes dans des matrices ``H`` (jointure horizontale) et ``V`` (jointure
verticale).  C4 est global et n'est évalué que sur un assemblage complet.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# Pondérations
# ---------------------------------------------------------------------------


@dataclass
class CostWeights:
    silhouette: float = 1.0
    color: float = 0.55
    gradient: float = 0.25
    hole: float = 0.45
    palette: float = 0.20
    duplicate: float = 0.35

    def as_dict(self) -> dict:
        return {"silhouette": self.silhouette, "color": self.color,
                "gradient": self.gradient, "hole": self.hole,
                "palette": self.palette, "duplicate": self.duplicate}

    @classmethod
    def from_dict(cls, d: dict) -> CostWeights:
        w = cls()
        for k, v in (d or {}).items():
            if hasattr(w, k):
                setattr(w, k, float(v))
        return w

    def normalized(self) -> CostWeights:
        total = (self.silhouette + self.color + self.gradient
                 + self.hole + self.palette + self.duplicate)
        if total <= 0:
            return CostWeights()
        return CostWeights(self.silhouette / total, self.color / total,
                           self.gradient / total, self.hole / total,
                           self.palette / total, self.duplicate / total)


# ---------------------------------------------------------------------------
# Vues de tuile
# ---------------------------------------------------------------------------


def _luminance(px: np.ndarray) -> np.ndarray:
    return (0.299 * px[..., 0] + 0.587 * px[..., 1] + 0.114 * px[..., 2])


def _histogram(px: np.ndarray, mask: np.ndarray, bins: int = 4) -> np.ndarray:
    """Histogramme normalisé de couleurs quantifiées (bins³ cases)."""
    n = bins ** 3
    if not mask.any():
        return np.zeros(n, dtype=np.float64)
    vals = (px[..., :3][mask].astype(np.int32) * bins) // 256
    vals = np.clip(vals, 0, bins - 1)
    codes = vals[:, 0] * bins * bins + vals[:, 1] * bins + vals[:, 2]
    hist = np.bincount(codes, minlength=n).astype(np.float64)
    s = hist.sum()
    return hist / s if s else hist


@dataclass
class TileView:
    """Données précalculées d'une tuile pour le calcul des coûts."""

    alpha: np.ndarray            # (h, w) bool
    lum: np.ndarray              # (h, w) float
    rgb: np.ndarray              # (h, w, 3) float
    hist: np.ndarray             # (64,)
    w: int
    h: int

    @classmethod
    def from_image(cls, img) -> TileView:
        px = img.px
        alpha = px[..., 3] > 0
        rgb = px[..., :3].astype(np.float64)
        return cls(alpha=alpha, lum=_luminance(rgb), rgb=rgb,
                   hist=_histogram(px, alpha), w=img.w, h=img.h)


# ---------------------------------------------------------------------------
# Modèle de coût
# ---------------------------------------------------------------------------


class CostModel:
    """Coûts de paire précalculés pour un ensemble de tuiles."""

    def __init__(self, views: list[TileView], weights: CostWeights | None = None):
        if not views:
            raise ValueError("aucune tuile")
        self.views = views
        self.weights = (weights or CostWeights()).normalized()
        self.n = len(views)
        self.w = max(v.w for v in views)
        self.h = max(v.h for v in views)
        self._build_edges()
        self._build_matrices()

    # -- bords --------------------------------------------------------------

    def _build_edges(self) -> None:
        n, w, h = self.n, self.w, self.h
        self.left_a = np.zeros((n, h), dtype=bool)
        self.right_a = np.zeros((n, h), dtype=bool)
        self.left_rgb = np.zeros((n, h, 3))
        self.right_rgb = np.zeros((n, h, 3))
        self.left_lum = np.zeros((n, h))
        self.right_lum = np.zeros((n, h))
        self.left_d = np.zeros((n, h))
        self.right_d = np.zeros((n, h))

        self.top_a = np.zeros((n, w), dtype=bool)
        self.bottom_a = np.zeros((n, w), dtype=bool)
        self.top_rgb = np.zeros((n, w, 3))
        self.bottom_rgb = np.zeros((n, w, 3))
        self.top_lum = np.zeros((n, w))
        self.bottom_lum = np.zeros((n, w))
        self.top_d = np.zeros((n, w))
        self.bottom_d = np.zeros((n, w))

        for i, v in enumerate(self.views):
            hh, ww = v.alpha.shape
            self.left_a[i, :hh] = v.alpha[:, 0]
            self.right_a[i, :hh] = v.alpha[:, -1]
            self.left_rgb[i, :hh] = v.rgb[:, 0]
            self.right_rgb[i, :hh] = v.rgb[:, -1]
            self.left_lum[i, :hh] = v.lum[:, 0]
            self.right_lum[i, :hh] = v.lum[:, -1]
            self.left_d[i, :hh] = v.lum[:, 0] - v.lum[:, min(1, ww - 1)]
            self.right_d[i, :hh] = v.lum[:, -1] - v.lum[:, max(0, ww - 2)]

            self.top_a[i, :ww] = v.alpha[0, :]
            self.bottom_a[i, :ww] = v.alpha[-1, :]
            self.top_rgb[i, :ww] = v.rgb[0, :]
            self.bottom_rgb[i, :ww] = v.rgb[-1, :]
            self.top_lum[i, :ww] = v.lum[0, :]
            self.bottom_lum[i, :ww] = v.lum[-1, :]
            self.top_d[i, :ww] = v.lum[0, :] - v.lum[min(1, hh - 1), :]
            self.bottom_d[i, :ww] = v.lum[-1, :] - v.lum[max(0, hh - 2), :]

    # -- matrices -----------------------------------------------------------

    #: Coût attribué à une jointure sans information (deux bords vides).
    #: Sans cette valeur neutre, les solveurs adorent les arrangements
    #: « fragmentés » où toutes les jointures tombent dans le vide.
    NEUTRAL = 0.5

    def _build_matrices(self) -> None:
        w = self.weights
        neutral = self.NEUTRAL

        # C1 : silhouette. On ne compare que les lignes où au moins un des deux
        # bords a du contenu : une jointure « vide des deux côtés » n'apporte
        # aucune information et reçoit le coût neutre.
        ra = self.right_a[:, None, :]
        la = self.left_a[None, :, :]
        content_h = ra | la
        cnt_h = content_h.sum(axis=2)
        mism_h = (ra != la).sum(axis=2)
        c1h = np.where(cnt_h > 0, mism_h / np.maximum(cnt_h, 1), neutral)

        ba = self.bottom_a[:, None, :]
        ta = self.top_a[None, :, :]
        content_v = ba | ta
        cnt_v = content_v.sum(axis=2)
        mism_v = (ba != ta).sum(axis=2)
        c1v = np.where(cnt_v > 0, mism_v / np.maximum(cnt_v, 1), neutral)

        # C2 : couleur (distance RGB moyenne sur les pixels opaques communs)
        both_h = ra & la
        d_h = np.abs(self.right_rgb[:, None, :, :] - self.left_rgb[None, :, :, :]).mean(axis=3)
        cnt_bh = both_h.sum(axis=2)
        c2h = np.where(cnt_bh > 0, (d_h * both_h).sum(axis=2) / np.maximum(cnt_bh, 1) / 255.0,
                       neutral)

        both_v = ba & ta
        d_v = np.abs(self.bottom_rgb[:, None, :, :] - self.top_rgb[None, :, :, :]).mean(axis=3)
        cnt_bv = both_v.sum(axis=2)
        c2v = np.where(cnt_bv > 0, (d_v * both_v).sum(axis=2) / np.maximum(cnt_bv, 1) / 255.0,
                       neutral)

        # C3 : contour
        dd_h = np.abs(self.right_d[:, None, :] - self.left_d[None, :, :])
        c3h = np.where(cnt_bh > 0, (dd_h * both_h).sum(axis=2) / np.maximum(cnt_bh, 1) / 255.0,
                       neutral)
        dd_v = np.abs(self.bottom_d[:, None, :] - self.top_d[None, :, :])
        c3v = np.where(cnt_bv > 0, (dd_v * both_v).sum(axis=2) / np.maximum(cnt_bv, 1) / 255.0,
                       neutral)

        # C5 : histogrammes (distance du chi²)
        hists = np.stack([v.hist for v in self.views])
        inter = hists[:, None, :] * hists[None, :, :]
        denom = hists[:, None, :] + hists[None, :, :] + 1e-9
        chi2 = (inter / denom).sum(axis=2)          # 0 = identique, 1 = disjoint
        c5 = 1.0 - chi2

        # C6 : doublons
        same = (self._similarity_matrix() > 0.92).astype(np.float64)
        np.fill_diagonal(same, 0.0)

        self.C1H, self.C1V = c1h, c1v
        self.C2H, self.C2V = c2h, c2v
        self.C3H, self.C3V = c3h, c3v
        self.C5 = c5
        self.C6 = same

        self.H = (w.silhouette * c1h + w.color * c2h + w.gradient * c3h
                  + w.palette * c5 + w.duplicate * same)
        self.V = (w.silhouette * c1v + w.color * c2v + w.gradient * c3v
                  + w.palette * c5 + w.duplicate * same)

    def _similarity_matrix(self) -> np.ndarray:
        """Similarité moyenne entre tuiles (pour détecter les doublons)."""
        n = self.n
        out = np.eye(n)
        flat = [v.rgb.reshape(-1, 3) for v in self.views]
        masks = [v.alpha.reshape(-1) for v in self.views]
        for i in range(n):
            for j in range(i + 1, n):
                m = masks[i] & masks[j]
                if not m.any():
                    continue
                d = np.abs(flat[i][m] - flat[j][m]).mean() / 255.0
                s = 1.0 - d
                out[i, j] = out[j, i] = s
        return out

    # -- évaluation ---------------------------------------------------------

    def pair_cost(self, a: int, b: int, horizontal: bool) -> float:
        return float(self.H[a, b] if horizontal else self.V[a, b])

    def arrangement_cost(self, order: list[int], cols: int, rows: int,
                         include_global: bool = True) -> float:
        """Coût d'un arrangement ``order`` (indices de tuiles, -1 = vide)."""
        total, count = self._pair_sum(order, cols, rows)
        per_join = total / max(1, count)
        if include_global and self.weights.hole > 0:
            per_join += self.weights.hole * self.hole_ratio(order, cols, rows)
        return per_join

    def _pair_sum(self, order: list[int], cols: int, rows: int):
        total = 0.0
        count = 0
        n = self.n
        for gy in range(rows):
            base = gy * cols
            for gx in range(cols):
                a = order[base + gx]
                if a < 0 or a >= n:
                    continue
                if gx + 1 < cols:
                    b = order[base + gx + 1]
                    if 0 <= b < n:
                        total += float(self.H[a, b])
                        count += 1
                if gy + 1 < rows:
                    b = order[base + cols + gx]
                    if 0 <= b < n:
                        total += float(self.V[a, b])
                        count += 1
        return total, count

    def breakdown(self, order: list[int], cols: int, rows: int) -> dict:
        """Détail des six indices pour un arrangement."""
        n = self.n
        s1 = s2 = s3 = s5 = s6 = 0.0
        count = 0
        for gy in range(rows):
            base = gy * cols
            for gx in range(cols):
                a = order[base + gx]
                if not (0 <= a < n):
                    continue
                if gx + 1 < cols:
                    b = order[base + gx + 1]
                    if 0 <= b < n:
                        s1 += self.C1H[a, b]
                        s2 += self.C2H[a, b]
                        s3 += self.C3H[a, b]
                        s5 += self.C5[a, b]
                        s6 += self.C6[a, b]
                        count += 1
                if gy + 1 < rows:
                    b = order[base + cols + gx]
                    if 0 <= b < n:
                        s1 += self.C1V[a, b]
                        s2 += self.C2V[a, b]
                        s3 += self.C3V[a, b]
                        s5 += self.C5[a, b]
                        s6 += self.C6[a, b]
                        count += 1
        k = max(1, count)
        w = self.weights
        hole = self.hole_ratio(order, cols, rows)
        return {
            "C1_silhouette": s1 / k,
            "C2_couleur": s2 / k,
            "C3_contour": s3 / k,
            "C4_trou": hole,
            "C5_palette": s5 / k,
            "C6_doublon": s6 / k,
            "total": (w.silhouette * s1 / k + w.color * s2 / k + w.gradient * s3 / k
                      + w.hole * hole + w.palette * s5 / k + w.duplicate * s6 / k),
            "jointures": count,
        }

    # -- C4 : trous ---------------------------------------------------------

    def assembled_alpha(self, order: list[int], cols: int, rows: int) -> np.ndarray:
        alpha = np.zeros((rows * self.h, cols * self.w), dtype=bool)
        for gy in range(rows):
            for gx in range(cols):
                a = order[gy * cols + gx]
                if not (0 <= a < self.n):
                    continue
                v = self.views[a]
                alpha[gy * self.h:gy * self.h + v.h, gx * self.w:gx * self.w + v.w] |= v.alpha
        return alpha

    def hole_ratio(self, order: list[int], cols: int, rows: int) -> float:
        """Proportion de pixels transparents enfermés dans la silhouette.

        Approximation vectorisée : un pixel vide est considéré comme un trou
        s'il a de la matière des quatre côtés.  C'est très proche du résultat
        d'un vrai remplissage depuis le bord, pour un coût négligeable — ce qui
        compte quand la fonction est appelée des milliers de fois par les
        solveurs.
        """
        if self.n == 0:
            return 0.0
        alpha = self.assembled_alpha(order, cols, rows)
        total = alpha.size
        if total == 0:
            return 0.0
        empty = ~alpha
        if not empty.any():
            return 0.0
        left = np.maximum.accumulate(alpha, axis=1)
        right = np.maximum.accumulate(alpha[:, ::-1], axis=1)[:, ::-1]
        up = np.maximum.accumulate(alpha, axis=0)
        down = np.maximum.accumulate(alpha[::-1], axis=0)[::-1]
        holes = empty & left & right & up & down
        return float(holes.sum()) / total


# ---------------------------------------------------------------------------
# Fabrication du modèle depuis une planche
# ---------------------------------------------------------------------------


def build_cost_model(sheet, tile_ids: list[int], weights: CostWeights | None = None,
                     transforms: dict[int, tuple] | None = None) -> CostModel:
    """Construit un :class:`CostModel` à partir des tuiles d'une planche."""
    views = []
    for tid in tile_ids:
        fh, fv, rot = (transforms or {}).get(tid, (False, False, 0))
        views.append(TileView.from_image(sheet.tile_image(tid, fh, fv, rot)))
    return CostModel(views, weights)
