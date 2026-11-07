"""Découverte de la logique d'ordonnancement.

Une fois quelques sprites validés, on connaît pour chaque case de la grille
l'indice de stockage de la tuile.  On cherche une fonction simple
``slot = f(indice de stockage)`` qui explique ces observations, puis on
l'exporte sous forme de *recette* réapplicable aux groupes suivants.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from ..core.model import Recipe, Sprite

# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


@dataclass
class Observation:
    sprite_id: int
    name: str
    cols: int
    rows: int
    base: int
    offsets: dict[int, int] = field(default_factory=dict)   # slot -> offset

    @property
    def count(self) -> int:
        return self.cols * self.rows


def observations(project) -> list[Observation]:
    """Extrait les observations des sprites validés (et du sprite courant)."""
    sheet = project.sheet
    if sheet is None:
        return []
    out: list[Observation] = []
    sprites = list(project.validated_sprites())
    if project.current.placements:
        sprites.append(project.current)
    for sp in sprites:
        idx = []
        for slot, tid in sp.placements.items():
            t = sheet.tile(tid)
            if t is not None and t.storage_index is not None:
                idx.append((slot, t.storage_index))
        if not idx:
            continue
        base = min(v for _, v in idx)
        obs = Observation(sp.id, sp.name, sp.cols, sp.rows, base)
        for slot, si in idx:
            obs.offsets[slot] = si - base
        out.append(obs)
    return out


# ---------------------------------------------------------------------------
# Modèles
# ---------------------------------------------------------------------------


@dataclass
class ModelResult:
    key: str
    label: str
    exact: int = 0
    total: int = 0
    tiles_ok: int = 0
    tiles_total: int = 0
    params: dict = field(default_factory=dict)
    description: str = ""

    @property
    def exact_ratio(self) -> float:
        return self.exact / self.total if self.total else 0.0

    @property
    def tile_ratio(self) -> float:
        return self.tiles_ok / self.tiles_total if self.tiles_total else 0.0

    def score(self) -> float:
        return 0.65 * self.exact_ratio + 0.35 * self.tile_ratio

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "exact": self.exact,
                "total": self.total, "tiles_ok": self.tiles_ok,
                "tiles_total": self.tiles_total, "params": self.params,
                "description": self.description}


def _evaluate(key: str, label: str, fn, obs_list: list[Observation],
              params: dict | None = None, description: str = "") -> ModelResult:
    res = ModelResult(key, label, params=params or {}, description=description)
    res.total = len(obs_list)
    for obs in obs_list:
        ok = 0
        n = obs.count
        for slot, off in obs.offsets.items():
            res.tiles_total += 1
            if fn(off, slot, n, obs.cols, obs.rows):
                ok += 1
                res.tiles_ok += 1
        if ok == n and len(obs.offsets) == n:
            res.exact += 1
    return res


def _coprimes(n: int) -> list[int]:
    return [a for a in range(1, n) if math.gcd(a, n) == 1]


def infer(obs_list: list[Observation], exhaustive: bool = False) -> list[ModelResult]:
    """Teste les modèles connus et renvoie le classement."""
    results: list[ModelResult] = []
    if not obs_list:
        return results
    ns = [o.count for o in obs_list]
    n = max(ns)

    results.append(_evaluate("identity", "Identité (slot = indice)",
                             lambda off, slot, n, c, r: off == slot, obs_list,
                             description="Les tuiles sont stockées dans l'ordre de la grille."))
    results.append(_evaluate("transpose", "Transposition (colonne par colonne)",
                             lambda off, slot, n, c, r: slot == (off % r) * c + off // r,
                             obs_list,
                             description="Le stockage parcourt la grille colonne par colonne."))
    results.append(_evaluate("serpentine", "Serpentin",
                             lambda off, slot, n, c, r: slot == _serp(off, c, r), obs_list,
                             description="Lignes alternées (boustrophédon)."))
    results.append(_evaluate("reverse", "Inversé",
                             lambda off, slot, n, c, r: slot == n - 1 - off, obs_list,
                             description="Ordre de stockage inverse de la lecture."))

    # affine mod N
    best_affine = None
    for a in _coprimes(n):
        for b in range(n if exhaustive else min(n, 24)):
            res = _evaluate(f"affine_{a}_{b}", f"Affine {a}·i+{b} mod {n}",
                            lambda off, slot, n, c, r, a=a, b=b: slot == (a * off + b) % n,
                            obs_list, {"a": a, "b": b},
                            description="slot = (a × indice + b) modulo N")
            if best_affine is None or res.score() > best_affine.score():
                best_affine = res
    if best_affine:
        results.append(best_affine)

    # pas multiplicatif
    best_step = None
    for k in range(2, n):
        if math.gcd(k, n) != 1:
            continue
        res = _evaluate(f"step_{k}", f"Pas ×{k} mod {n}",
                        lambda off, slot, n, c, r, k=k: slot == (k * off) % n,
                        obs_list, {"k": k}, description="slot = (k × indice) mod N")
        if best_step is None or res.score() > best_step.score():
            best_step = res
    if best_step:
        results.append(best_step)

    # bits
    if n & (n - 1) == 0 and n >= 4:
        bits = int(math.log2(n))
        res = _evaluate("bitrev", "Inversion des bits",
                        lambda off, slot, n, c, r, bits=bits: slot == _bitrev(off, bits),
                        obs_list, {"bits": bits},
                        description="Les bits de l'indice sont inversés.")
        results.append(res)

    # blocs
    for blk in range(2, min(9, n)):
        if n % blk:
            continue
        size = n // blk
        best = None
        for perm in _block_perms(blk):
            res = _evaluate(f"blocks_{blk}_{perm}", f"Blocs {blk} → {perm}",
                            lambda off, slot, n, c, r, size=size, perm=perm:
                                slot == perm[off // size] * size + off % size,
                            obs_list, {"blocks": blk, "perm": list(perm)},
                            description="La banque est découpée en blocs réordonnés.")
            if best is None or res.score() > best.score():
                best = res
        if best:
            results.append(best)

    # par plans
    for planes in range(2, min(9, n)):
        if n % planes:
            continue
        res = _evaluate(f"planes_{planes}", f"Par plans ({planes})",
                        lambda off, slot, n, c, r, planes=planes:
                            slot == (off % planes) * (n // planes) + off // planes,
                        obs_list, {"planes": planes},
                        description="Les tuiles sont rangées plan par plan.")
        results.append(res)

    # majorité par case (modèle libre)
    mapping = _majority_mapping(obs_list, n)
    if mapping:
        res = ModelResult("mapping", "Correspondance majoritaire par case",
                          params={"mapping": mapping},
                          description="Table case → décalage observée le plus souvent.")
        res.total = len(obs_list)
        for obs in obs_list:
            ok = 0
            for slot, off in obs.offsets.items():
                res.tiles_total += 1
                if 0 <= slot < len(mapping) and mapping[slot] == off:
                    ok += 1
                    res.tiles_ok += 1
            if ok == obs.count and len(obs.offsets) == obs.count:
                res.exact += 1
        results.append(res)

    results.sort(key=lambda r: (-r.score(), -r.exact, -r.tiles_ok))
    return results


def _serp(off: int, cols: int, rows: int) -> int:
    gy, gx = off // cols, off % cols
    if gy % 2:
        gx = cols - 1 - gx
    return gy * cols + gx


def _bitrev(v: int, bits: int) -> int:
    out = 0
    for _ in range(bits):
        out = (out << 1) | (v & 1)
        v >>= 1
    return out


def _block_perms(blk: int):
    """Permutations de blocs (toutes si blk ≤ 4, sinon rotations)."""
    import itertools
    if blk <= 4:
        return list(itertools.permutations(range(blk)))
    return [tuple((i + k) % blk for i in range(blk)) for k in range(blk)]


def _majority_mapping(obs_list: list[Observation], n: int) -> list[int]:
    votes: dict[int, Counter] = {slot: Counter() for slot in range(n)}
    for obs in obs_list:
        for slot, off in obs.offsets.items():
            if 0 <= slot < n:
                votes[slot][off] += 1
    mapping = []
    for slot in range(n):
        if not votes[slot]:
            mapping.append(-1)
        else:
            mapping.append(votes[slot].most_common(1)[0][0])
    return mapping


def confidence(obs_list: list[Observation], mapping: list[int]) -> list[float]:
    """Confiance par case : part des sprites qui votent pour la valeur retenue."""
    votes: dict[int, Counter] = {}
    totals: Counter = Counter()
    for obs in obs_list:
        for slot, off in obs.offsets.items():
            votes.setdefault(slot, Counter())[off] += 1
            totals[slot] += 1
    out = []
    for slot, value in enumerate(mapping):
        if value < 0 or not totals[slot]:
            out.append(0.0)
        else:
            out.append(votes[slot][value] / totals[slot])
    return out


# ---------------------------------------------------------------------------
# Recette
# ---------------------------------------------------------------------------


def make_recipe(result: ModelResult, obs_list: list[Observation], name: str = "recette") -> Recipe:
    """Transforme un modèle gagnant en recette réapplicable."""
    if obs_list:
        cols, rows = obs_list[0].cols, obs_list[0].rows
    else:
        cols = rows = 0
    n = cols * rows
    mapping = [-1] * n

    if result.key == "identity":
        mapping = list(range(n))
    elif result.key == "transpose":
        mapping = [(i % rows) * cols + i // rows for i in range(n)]
    elif result.key == "serpentine":
        mapping = [_serp(i, cols, rows) for i in range(n)]
    elif result.key == "reverse":
        mapping = [n - 1 - i for i in range(n)]
    elif result.key.startswith("affine_"):
        a, b = result.params["a"], result.params["b"]
        mapping = [(a * i + b) % n for i in range(n)]
    elif result.key.startswith("step_"):
        k = result.params["k"]
        mapping = [(k * i) % n for i in range(n)]
    elif result.key == "bitrev":
        bits = result.params["bits"]
        mapping = [_bitrev(i, bits) for i in range(n)]
    elif result.key.startswith("blocks_"):
        blk, perm = result.params["blocks"], result.params["perm"]
        size = n // blk
        mapping = [perm[i // size] * size + i % size for i in range(n)]
    elif result.key.startswith("planes_"):
        planes = result.params["planes"]
        mapping = [(i % planes) * (n // planes) + i // planes for i in range(n)]
    elif result.key == "mapping":
        mapping = list(result.params["mapping"])

    return Recipe(name=name, cols=cols, rows=rows, mapping=mapping,
                  fit={"type": result.key, "score": result.score(),
                       "exact": result.exact, "total": result.total,
                       "params": result.params})


def apply_to_sprite(recipe: Recipe, storage_indices: list[int], base: int,
                    sheet, sprite: Sprite) -> int:
    """Remplit un sprite d'après une recette ; renvoie le nombre de cases posées."""
    by_index = sheet.by_storage_index()
    placed = 0
    for slot, off in enumerate(recipe.mapping):
        if off < 0 or slot >= sprite.cols * sprite.rows:
            continue
        si = base + off
        tile = by_index.get(si)
        if tile is None:
            continue
        sprite.placements[slot] = tile.id
        placed += 1
    return placed


def next_group(project, recipe: Recipe) -> tuple[int, int]:
    """Indice de stockage de début du prochain groupe non encore traité."""
    sheet = project.sheet
    if sheet is None:
        return (0, 0)
    used: set[int] = set()
    for sp in project.validated_sprites():
        for tid in sp.placements.values():
            t = sheet.tile(tid)
            if t and t.storage_index is not None:
                used.add(t.storage_index)
    available = sorted(t.storage_index for t in sheet.tiles
                       if t.storage_index is not None)
    if not available:
        return (0, 0)
    n = recipe.count
    for start in range(0, len(available), n):
        group = available[start:start + n]
        if group and not any(g in used for g in group):
            return (group[0], group[-1])
    return (available[0], available[min(n, len(available)) - 1])
