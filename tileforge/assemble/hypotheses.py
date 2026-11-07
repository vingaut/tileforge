"""M1 — hypothèses d'ordonnancement.

Plutôt que de chercher une permutation au hasard, on teste un catalogue de
règles simples que les développeurs utilisaient réellement : lecture ligne par
ligne, colonne par colonne, serpentin, blocs, entrelacement, pas arithmétique,
permutation de bits…

Chaque hypothèse produit un arrangement ``order`` où ``order[slot]`` donne la
position (dans l'ordre de stockage) de la tuile à placer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import permutations


@dataclass
class Hypothesis:
    name: str
    order: list[int]
    family: str = ""


def _invert(slot_for_storage: list[int]) -> list[int]:
    order = [0] * len(slot_for_storage)
    for i, s in enumerate(slot_for_storage):
        if 0 <= s < len(order):
            order[s] = i
    return order


def _coprimes(n: int) -> list[int]:
    return [a for a in range(1, n) if math.gcd(a, n) == 1]


def generate(n: int, cols: int, rows: int, exhaustive: bool = False) -> list[Hypothesis]:
    """Catalogue d'hypothèses pour une grille ``cols`` × ``rows``."""
    out: list[Hypothesis] = []
    if n <= 0:
        return out
    seen: set[tuple] = set()

    def add(name: str, slot_for_storage: list[int], family: str = "") -> None:
        if len(slot_for_storage) != n:
            return
        if sorted(slot_for_storage) != list(range(n)):
            return
        order = _invert(slot_for_storage)
        key = tuple(order)
        if key in seen:
            return
        seen.add(key)
        out.append(Hypothesis(name, order, family))

    rng = list(range(n))
    add("Identité (ligne par ligne)", list(rng), "lecture")
    add("Inversé", list(reversed(rng)), "lecture")
    add("Colonne par colonne", [(i % rows) * cols + i // rows for i in rng], "lecture")
    add("Lignes inversées", [((n // cols - 1) - i // cols) * cols + i % cols for i in rng], "lecture")
    add("Colonnes inversées", [(i // cols) * cols + (cols - 1 - i % cols) for i in rng], "lecture")
    add("Lignes et colonnes inversées",
        [((n // cols - 1) - i // cols) * cols + (cols - 1 - i % cols) for i in rng], "lecture")

    # serpentin
    serp = []
    for i in rng:
        gy, gx = i // cols, i % cols
        if gy % 2:
            gx = cols - 1 - gx
        serp.append(gy * cols + gx)
    add("Serpentin (ligne)", serp, "serpentin")
    serp2 = []
    for i in rng:
        gy, gx = i // cols, i % cols
        if gx % 2:
            gy = (n // cols) - 1 - gy
        serp2.append(gy * cols + gx)
    add("Serpentin (colonne)", serp2, "serpentin")

    # blocs
    for b in range(2, min(5, n)):
        if n % b:
            continue
        size = n // b
        for perm in permutations(range(b)):
            if perm == tuple(range(b)):
                continue
            slots = []
            for i in rng:
                blk = i // size
                off = i % size
                slots.append(perm[blk] * size + off)
            add(f"Blocs {b} → {''.join(map(str, perm))}", slots, "blocs")

    # entrelacement
    for k in range(2, min(6, n)):
        if n % k:
            continue
        slots = []
        for i in rng:
            slots.append((i % k) * (n // k) + i // k)
        add(f"Entrelacement modulo {k}", slots, "entrelacement")

    # pas et affine
    for a in _coprimes(n):
        slots = [(i * a) % n for i in rng]
        add(f"Pas multiplicatif ×{a}", slots, "arithmétique")
    limit = n if exhaustive else min(n, 32)
    for a in _coprimes(n)[:limit]:
        for b in range(min(n, 16 if not exhaustive else n)):
            slots = [(a * i + b) % n for i in rng]
            add(f"Affine {a}·i+{b} mod {n}", slots, "arithmétique")
            if not exhaustive and len(out) > 400:
                break

    # décalage circulaire
    for k in range(1, n):
        add(f"Décalage circulaire +{k}", [(i + k) % n for i in rng], "rotation")

    # bits
    if n & (n - 1) == 0 and n >= 4:
        bits = int(math.log2(n))
        for _ in rng:
            add("Inversion des bits", [int(f"{j:0{bits}b}"[::-1], 2) for j in rng], "bits")
            break
        add("Échange des moitiés de bits",
            [((i & ((1 << (bits // 2)) - 1)) << (bits - bits // 2)) |
             (i >> (bits // 2)) for i in rng], "bits")
        # permutation de bits par échange de deux positions
        for p in range(bits):
            for q in range(p + 1, bits):
                def swap(v, p=p, q=q):
                    bp, bq = (v >> p) & 1, (v >> q) & 1
                    if bp == bq:
                        return v
                    return v ^ (1 << p) ^ (1 << q)
                add(f"Échange bits {p}/{q}", [swap(i) for i in rng], "bits")

    # par plans
    for planes in range(2, min(9, n)):
        if n % planes:
            continue
        add(f"Par plans ({planes})",
            [(i % planes) * (n // planes) + i // planes for i in rng], "plans")

    return out


def rank(model, cols: int, rows: int, limit: int | None = None,
         exhaustive: bool = False) -> list[tuple[Hypothesis, float, dict]]:
    """Classe les hypothèses par coût croissant."""
    results = []
    for hyp in generate(model.n, cols, rows, exhaustive=exhaustive):
        cost = model.arrangement_cost(hyp.order, cols, rows, include_global=True)
        results.append((hyp, cost, model.breakdown(hyp.order, cols, rows)))
    results.sort(key=lambda r: r[1])
    return results[:limit] if limit else results
