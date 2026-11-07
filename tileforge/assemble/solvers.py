"""Solveurs d'assemblage automatique.

M1  hypothèses d'ordre            (catalogue de permutations « plausibles »)
M2  glouton + amélioration 2-opt
M3  beam search (faisceau)
M4  recuit simulé
M5  recherche exhaustive avec élagage (N ≤ 9)
M6  chemin optimal par programmation dynamique (grille 1 × N)
M7  affectation hongroise à une référence (facultatif)

Tous renvoient une liste de :class:`Solution` triées par coût croissant.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from .cost import CostModel
from .hypotheses import rank as rank_hypotheses


@dataclass
class Solution:
    order: list[int]
    cost: float
    method: str
    label: str = ""
    breakdown: dict = field(default_factory=dict)
    elapsed: float = 0.0

    def as_dict(self) -> dict:
        return {"order": list(self.order), "cost": self.cost,
                "method": self.method, "label": self.label}


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------


def _join_cost(model: CostModel, order: list[int], slot: int, tile: int,
               cols: int, rows: int) -> float:
    """Coût des jointures qu'ajouterait ``tile`` à la case ``slot``."""
    total = 0.0
    gx, gy = slot % cols, slot // cols
    if gx > 0:
        left = order[slot - 1]
        if left >= 0:
            total += float(model.H[left, tile])
    if gy > 0:
        top = order[slot - cols]
        if top >= 0:
            total += float(model.V[top, tile])
    return total


def _finish(model: CostModel, order: list[int], cols: int, rows: int,
            method: str, label: str, elapsed: float = 0.0) -> Solution:
    cost = model.arrangement_cost(order, cols, rows, include_global=True)
    return Solution(list(order), cost, method, label,
                    model.breakdown(order, cols, rows), elapsed)


# ---------------------------------------------------------------------------
# M1 — hypothèses
# ---------------------------------------------------------------------------


def solve_hypotheses(model: CostModel, cols: int, rows: int, limit: int = 15,
                     exhaustive: bool = False, progress=None) -> list[Solution]:
    t0 = time.time()
    results = rank_hypotheses(model, cols, rows, limit=limit, exhaustive=exhaustive)
    out = []
    for hyp, _cost, breakdown in results:
        out.append(Solution(hyp.order, _cost, "M1", hyp.name, breakdown,
                            time.time() - t0))
    if progress:
        progress(1.0, f"{len(out)} hypothèses évaluées")
    return out


# ---------------------------------------------------------------------------
# M2 — glouton + 2-opt
# ---------------------------------------------------------------------------


def solve_greedy(model: CostModel, cols: int, rows: int, restarts: int = 4,
                 progress=None) -> list[Solution]:
    t0 = time.time()
    n = model.n
    if n == 0:
        return []
    richness = [float(v.alpha.sum()) for v in model.views]
    seeds = sorted(range(n), key=lambda i: richness[i], reverse=True)[:max(1, restarts)]
    solutions: list[Solution] = []

    for seed in seeds:
        order = [-1] * n
        remaining = set(range(n))
        first_slot = 0
        order[first_slot] = seed
        remaining.discard(seed)
        for slot in range(1, n):
            best_t, best_c = -1, float("inf")
            for t in remaining:
                c = _join_cost(model, order, slot, t, cols, rows)
                if c < best_c:
                    best_c, best_t = c, t
            order[slot] = best_t
            remaining.discard(best_t)
        order = _two_opt(model, order, cols, rows)
        solutions.append(_finish(model, order, cols, rows, "M2",
                                 f"glouton (départ tuile {seed})", time.time() - t0))
        if progress:
            progress(0.5, "glouton + 2-opt")

    solutions.sort(key=lambda s: s.cost)
    # dédoublonne
    seen, out = set(), []
    for s in solutions:
        k = tuple(s.order)
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _two_opt(model: CostModel, order: list[int], cols: int, rows: int,
             max_passes: int = 30) -> list[int]:
    n = len(order)
    best, best_cost = list(order), model._pair_sum(order, cols, rows)[0]
    for _ in range(max_passes):
        improved = False
        for i in range(n):
            for j in range(i + 1, n):
                cand = list(best)
                cand[i], cand[j] = cand[j], cand[i]
                c = model._pair_sum(cand, cols, rows)[0]
                if c < best_cost - 1e-12:
                    best, best_cost = cand, c
                    improved = True
        if not improved:
            break
    return best


# ---------------------------------------------------------------------------
# M3 — beam search
# ---------------------------------------------------------------------------


def solve_beam(model: CostModel, cols: int, rows: int, width: int = 250,
               keep: int = 5, progress=None) -> list[Solution]:
    t0 = time.time()
    n = model.n
    if n == 0:
        return []
    width = max(1, min(width, 5000))
    states: list[tuple[float, tuple, int]] = [(0.0, (), 0)]
    full_mask = (1 << n) - 1

    for slot in range(n):
        expanded: list[tuple[float, tuple, int]] = []
        gx, gy = slot % cols, slot // cols
        for cost, prefix, mask in states:
            for t in range(n):
                bit = 1 << t
                if mask & bit:
                    continue
                c = cost
                if gx > 0:
                    c += float(model.H[prefix[-1], t])
                if gy > 0:
                    c += float(model.V[prefix[slot - cols], t])
                expanded.append((c, prefix + (t,), mask | bit))
        if not expanded:
            break
        expanded.sort(key=lambda s: s[0])
        # diversité : on garde les `width` meilleurs, en évitant les doublons
        seen = set()
        pruned = []
        for st in expanded:
            key = st[1]
            if key in seen:
                continue
            seen.add(key)
            pruned.append(st)
            if len(pruned) >= width:
                break
        states = pruned
        if progress:
            progress((slot + 1) / n, f"faisceau {slot + 1}/{n}")

    out = []
    for _cost, prefix, mask in states[:keep]:
        if mask == full_mask:
            out.append(_finish(model, list(prefix), cols, rows, "M3",
                               f"faisceau largeur {width}", time.time() - t0))
    out.sort(key=lambda s: s.cost)
    return out


# ---------------------------------------------------------------------------
# M4 — recuit simulé
# ---------------------------------------------------------------------------


def solve_annealing(model: CostModel, cols: int, rows: int, iterations: int = 6000,
                    t0: float | None = None, t1: float = 0.001, seed: int = 0,
                    start: list[int] | None = None, progress=None) -> list[Solution]:
    begin = time.time()
    n = model.n
    if n == 0:
        return []
    rng = random.Random(seed)
    if start is None:
        hyp = solve_hypotheses(model, cols, rows, limit=1)
        order = list(hyp[0].order) if hyp else list(range(n))
    else:
        order = list(start)

    cur_cost = model._pair_sum(order, cols, rows)[0]
    best_order, best_cost = list(order), cur_cost
    if t0 is None:
        t0 = max(0.01, cur_cost / max(1, n) * 0.8)

    for it in range(iterations):
        frac = it / max(1, iterations - 1)
        temp = t0 * ((t1 / t0) ** frac) if t0 > 0 else 0.0
        i, j = rng.randrange(n), rng.randrange(n)
        if i == j:
            continue
        order[i], order[j] = order[j], order[i]
        new_cost = model._pair_sum(order, cols, rows)[0]
        delta = new_cost - cur_cost
        if delta <= 0 or (temp > 0 and rng.random() < math.exp(-delta / temp)):
            cur_cost = new_cost
            if new_cost < best_cost:
                best_order, best_cost = list(order), new_cost
        else:
            order[i], order[j] = order[j], order[i]
        if progress and it % 200 == 0:
            progress(frac, f"recuit {it}/{iterations}")

    return [_finish(model, best_order, cols, rows, "M4",
                    f"recuit simulé ({iterations} itérations)", time.time() - begin)]


# ---------------------------------------------------------------------------
# M5 — exhaustif avec élagage
# ---------------------------------------------------------------------------


def solve_exhaustive(model: CostModel, cols: int, rows: int, progress=None) -> list[Solution]:
    """Parcourt toutes les permutations et renvoie la meilleure.

    L'élagage porte sur le **coût réel** affiché, terme de trous compris :
    le coût d'un arrangement est la moyenne des coûts de paires plus une
    pénalité de trous. Comme cette pénalité est positive, la moyenne des
    paires déjà placées minore le coût final, ce qui autorise un élagage
    sûr. Sans cela, le solveur minimisait la somme des paires puis affichait
    un coût calculé autrement — l'utilisateur ne retrouvait pas le chiffre
    annoncé.
    """
    begin = time.time()
    n = model.n
    if n == 0:
        return []
    if n > 10:
        raise ValueError("recherche exhaustive limitée à 10 tuiles")

    total_pairs = max(1, (cols - 1) * rows + cols * (rows - 1))
    best_cost = [float("inf")]
    best_order: list[list[int]] = []
    order = [-1] * n
    counter = [0]

    def search(slot: int, used: int, partial: float) -> None:
        counter[0] += 1
        # borne inférieure : moyenne des paires déjà fixées (les trous
        # ajoutent toujours un terme positif)
        if slot > 0 and partial / total_pairs >= best_cost[0]:
            return
        if slot == n:
            full = model.arrangement_cost(order, cols, rows, include_global=True)
            if full < best_cost[0]:
                best_cost[0] = full
                best_order.clear()
                best_order.append(list(order))
            return
        gx, gy = slot % cols, slot // cols
        cands = []
        for t in range(n):
            if used & (1 << t):
                continue
            c = partial
            if gx > 0:
                c += float(model.H[order[slot - 1], t])
            if gy > 0:
                c += float(model.V[order[slot - cols], t])
            cands.append((c, t))
        cands.sort()
        for c, t in cands:
            order[slot] = t
            search(slot + 1, used | (1 << t), c)
            order[slot] = -1
            if progress and counter[0] % 50000 == 0:
                progress(0.5, f"exhaustif : {counter[0]} nœuds")

    search(0, 0, 0.0)
    if not best_order:
        return []
    return [_finish(model, best_order[0], cols, rows, "M5",
                    f"exhaustif ({counter[0]} nœuds)", time.time() - begin)]


# ---------------------------------------------------------------------------
# M6 — chemin optimal (programmation dynamique)
# ---------------------------------------------------------------------------


def solve_chain_dp(model: CostModel, cols: int, rows: int, progress=None) -> list[Solution]:
    """Chemin hamiltonien optimal pour une grille 1 × N (N ≤ 14)."""
    begin = time.time()
    n = model.n
    if n == 0:
        return []
    if n > 14:
        raise ValueError("programmation dynamique limitée à 14 tuiles")
    if min(cols, rows) != 1:
        raise ValueError("cette méthode suppose une grille 1 × N ou N × 1")

    horizontal = rows == 1
    mat = model.H if horizontal else model.V
    full = (1 << n) - 1
    dp = [[float("inf")] * n for _ in range(1 << n)]
    parent = [[-1] * n for _ in range(1 << n)]
    for i in range(n):
        dp[1 << i][i] = 0.0
    for mask in range(1 << n):
        row = dp[mask]
        for last in range(n):
            c = row[last]
            if c == float("inf"):
                continue
            for nxt in range(n):
                if mask & (1 << nxt):
                    continue
                nm = mask | (1 << nxt)
                nc = c + float(mat[last, nxt])
                if nc < dp[nm][nxt]:
                    dp[nm][nxt] = nc
                    parent[nm][nxt] = last
        if progress and mask % 512 == 0:
            progress(mask / (1 << n), "programmation dynamique")

    best_last = min(range(n), key=lambda i: dp[full][i])
    order = []
    mask, last = full, best_last
    while last >= 0:
        order.append(last)
        prev = parent[mask][last]
        mask ^= 1 << last
        last = prev
    order.reverse()
    if cols == 1:
        order = order  # colonne : l'ordre est déjà linéaire
    return [_finish(model, order, cols, rows, "M6",
                    "chemin optimal (DP)", time.time() - begin)]


# ---------------------------------------------------------------------------
# M7 — affectation hongroise (référence)
# ---------------------------------------------------------------------------


def hungarian(cost: list[list[float]]) -> list[int]:
    """Affectation de coût minimal (algorithme hongrois, O(n³)).

    Renvoie ``assign`` où ``assign[i]`` est la colonne attribuée à la ligne ``i``.
    """
    n = len(cost)
    if n == 0:
        return []
    m = len(cost[0])
    size = max(n, m)
    INF = float("inf")
    a = [[cost[i][j] if i < n and j < m else 0.0 for j in range(size)] for i in range(size)]
    u = [0.0] * (size + 1)
    v = [0.0] * (size + 1)
    p = [0] * (size + 1)
    way = [0] * (size + 1)
    for i in range(1, size + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = 0
            for j in range(1, size + 1):
                if used[j]:
                    continue
                cur = a[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(size + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assign = [-1] * n
    for j in range(1, size + 1):
        if p[j] and p[j] - 1 < n and j - 1 < m:
            assign[p[j] - 1] = j - 1
    return assign


def solve_reference(model: CostModel, cols: int, rows: int,
                    reference: list, progress=None) -> list[Solution]:
    """M7 : affecte les tuiles aux cases d'une référence (image ou indices).

    ``reference[i]`` est l'image attendue dans la case ``i`` (ou ``None``).
    """
    begin = time.time()
    n = model.n
    cells = len(reference)
    if n == 0 or cells == 0:
        return []
    from .cost import TileView

    cost = []
    for i in range(n):
        row = []
        for j in range(cells):
            ref = reference[j]
            if ref is None:
                row.append(0.0)
                continue
            rv = TileView.from_image(ref) if hasattr(ref, "px") else ref
            row.append(_view_distance(model.views[i], rv))
        cost.append(row)
    assign = hungarian(cost)
    order = [-1] * cells
    for i, j in enumerate(assign):
        if 0 <= j < cells:
            order[j] = i
    # les cases non attribuées prennent les tuiles restantes
    used = {v for v in order if v >= 0}
    rest = [i for i in range(n) if i not in used]
    for k in range(cells):
        if order[k] < 0 and rest:
            order[k] = rest.pop(0)
    return [_finish(model, order, cols, rows, "M7",
                    "affectation à la référence", time.time() - begin)]


def _view_distance(a, b) -> float:
    import numpy as np
    h = min(a.alpha.shape[0], b.alpha.shape[0])
    w = min(a.alpha.shape[1], b.alpha.shape[1])
    m = a.alpha[:h, :w] & b.alpha[:h, :w]
    if not m.any():
        return 1.0
    d = np.abs(a.rgb[:h, :w][m] - b.rgb[:h, :w][m]).mean() / 255.0
    sil = (a.alpha[:h, :w] != b.alpha[:h, :w]).mean()
    return float(0.5 * d + 0.5 * sil)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

METHODS = (
    ("M1", "Hypothèses d'ordre"),
    ("M2", "Glouton + 2-opt"),
    ("M3", "Beam search"),
    ("M4", "Recuit simulé"),
    ("M5", "Exhaustif (≤ 10 tuiles)"),
    ("M6", "Chemin optimal (1 × N)"),
)


def solve(method: str, model: CostModel, cols: int, rows: int,
          options: dict | None = None, progress=None) -> list[Solution]:
    """Lance une méthode et renvoie les meilleures solutions."""
    opt = options or {}
    if method == "M1":
        return solve_hypotheses(model, cols, rows, limit=int(opt.get("limit", 15)),
                                exhaustive=bool(opt.get("exhaustive", False)),
                                progress=progress)
    if method == "M2":
        return solve_greedy(model, cols, rows, restarts=int(opt.get("restarts", 4)),
                            progress=progress)
    if method == "M3":
        return solve_beam(model, cols, rows, width=int(opt.get("width", 250)),
                          progress=progress)
    if method == "M4":
        return solve_annealing(model, cols, rows,
                               iterations=int(opt.get("iterations", 6000)),
                               seed=int(opt.get("seed", 0)), progress=progress)
    if method == "M5":
        return solve_exhaustive(model, cols, rows, progress=progress)
    if method == "M6":
        return solve_chain_dp(model, cols, rows, progress=progress)
    raise ValueError(f"méthode inconnue : {method}")


def solve_all(model: CostModel, cols: int, rows: int, options: dict | None = None,
              progress=None) -> list[Solution]:
    """Enchaîne plusieurs méthodes et renvoie un classement fusionné."""
    opt = options or {}
    out: list[Solution] = []
    methods = opt.get("methods", ["M1", "M2", "M3", "M4"])
    total = max(1, len(methods))
    for k, m in enumerate(methods):
        try:
            if m == "M5" and model.n > 10:
                continue
            if m == "M6" and (min(cols, rows) != 1 or model.n > 14):
                continue
            sub_progress = None
            if progress:
                def sub_progress(frac, msg, k=k, total=total, m=m):
                    progress((k + frac) / total, f"{m} — {msg}")
            out.extend(solve(m, model, cols, rows, opt, sub_progress))
        except Exception as exc:  # une méthode qui échoue ne doit pas bloquer
            if progress:
                progress((k + 1) / total, f"{m} : échec ({exc})")
    out.sort(key=lambda s: s.cost)
    return out
