#!/usr/bin/env python3
"""Banc d'essai des solveurs d'assemblage.

Le but est de répondre à une question mesurable : *quelle méthode retrouve
l'assemblage d'origine, et à quel prix ?*

Deux jeux de données sont utilisés :

* **Barbarian (réel)** — les tuiles sont prises dans l'ordre où le jeu les
  range. Attention : cet ordre **n'est pas** l'assemblage d'origine ; on a
  vérifié à l'œil qu'aucune grille simple (2×4, 3×4, 4×3, 4×4, en lignes ou en
  colonnes) ne reconstitue un sprite cohérent. Le jeu compose donc ses sprites
  à partir d'une table. Cette partie du banc ne mesure donc **pas** la
  justesse : seulement la distance au classement de stockage, et la capacité
  des méthodes à ne pas s'en écarter follement.
* **Sprites synthétiques** — on dessine une image, on la découpe en tuiles, on
  mélange les tuiles, puis on demande aux solveurs de retrouver l'ordre. On
  connaît ici la réponse exacte.

    python tools/bench_solvers.py                    # Barbarian + synthétique
    python tools/bench_solvers.py --groups 20        # plus de groupes
    python tools/bench_solvers.py --json             # sortie machine
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tileforge.assemble import solvers  # noqa: E402
from tileforge.assemble.cost import build_cost_model  # noqa: E402

METHODS = ["M1", "M2", "M3", "M4", "M5", "M6"]


# ---------------------------------------------------------------------------
# Jeu de données : Barbarian
# ---------------------------------------------------------------------------


def barbarian_groups(limit: int) -> list[tuple[object, list[int]]]:
    """Groupes de tuiles consécutives de la banque Barbarian."""
    from tileforge.games.atari_st import load_barbarian

    sheet = load_barbarian(str(ROOT / "Barbarian (1987)(Palace).stx"), 1)
    ids = [tile.id for tile in sheet.tiles_sorted()]
    groups = []
    for start in range(0, min(len(ids), limit * 8), 8):
        group = ids[start:start + 8]
        if len(group) == 8:
            groups.append((sheet, group))
    return groups


# ---------------------------------------------------------------------------
# Jeu de données : sprites synthétiques
# ---------------------------------------------------------------------------


def synthetic_sheet(seed: int, sprites: int = 6, cols: int = 2, rows: int = 4,
                    tile: int = 8):
    """Construit une planche dont on connaît l'assemblage d'origine.

    Chaque sprite est dessiné en grille (``cols`` × ``rows``), puis ses blocs
    sont **mélangés** sur la planche : la vérité est la permutation qui
    rétablit l'image. C'est exactement le problème que l'outil doit résoudre.
    """
    from tileforge.core.image import Image
    from tileforge.core.model import Sheet, Tile

    rng = random.Random(seed)
    per_sprite = cols * rows
    # les tuiles sont rangées sur une seule ligne : la planche n'est qu'un
    # support de stockage, seule la permutation compte
    width = sprites * per_sprite * tile
    height = tile
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    palette = [(0, 0, 0, 0), (220, 40, 60, 255), (40, 180, 90, 255),
               (60, 90, 220, 255), (240, 220, 80, 255)]
    truth: list[list[int]] = []
    for sprite in range(sprites):
        canvas = np.zeros((rows * tile, cols * tile), dtype=np.int32)
        for _ in range(rng.randint(2, 5)):
            x0 = rng.randint(1, cols * tile - 4)
            y0 = rng.randint(1, rows * tile - 4)
            w = rng.randint(2, min(10, cols * tile - x0))
            h = rng.randint(2, min(10, rows * tile - y0))
            canvas[y0:y0 + h, x0:x0 + w] = rng.randint(1, len(palette) - 2)
        # contour plus sombre : c'est lui qui porte l'information aux
        # frontières de tuiles. Sans lui, un sprite en aplats est ambigu et
        # aucune méthode ne peut retrouver l'ordre — ce serait mesurer le
        # hasard, pas l'algorithme.
        shape = canvas > 0
        outline = np.zeros_like(shape)
        outline[1:, :] |= shape[:-1, :] & ~shape[1:, :]
        outline[:-1, :] |= shape[1:, :] & ~shape[:-1, :]
        outline[:, 1:] |= shape[:, :-1] & ~shape[:, 1:]
        outline[:, :-1] |= shape[:, 1:] & ~shape[:, :-1]
        canvas[shape & outline] = len(palette) - 1

        # blocs du sprite, dans l'ordre de la grille
        blocks = []
        for slot in range(per_sprite):
            gx, gy = slot % cols, slot // cols
            blocks.append(canvas[gy * tile:(gy + 1) * tile, gx * tile:(gx + 1) * tile])

        # mélange : la position p de la planche contient le bloc permutation[p]
        permutation = list(range(per_sprite))
        rng.shuffle(permutation)
        for position, block_index in enumerate(permutation):
            x0 = sprite * per_sprite * tile + position * tile
            block = blocks[block_index]
            for y in range(tile):
                for x in range(tile):
                    pixels[y, x0 + x] = palette[block[y, x]]

        # ordre correct, en indices **relatifs au groupe** (le modèle de coût
        # numérote les tuiles de 0 à n-1 pour le groupe étudié)
        truth.append([permutation.index(slot) for slot in range(per_sprite)])

    image = Image(pixels, None, [list(c) for c in palette])
    sheet = Sheet(image=image)
    for index in range(sprites * per_sprite):
        sprite, position = divmod(index, per_sprite)
        x0 = sprite * per_sprite * tile + position * tile
        sheet.tiles.append(Tile(id=index, rect=(x0, 0, tile, tile)))
    return sheet, truth


# ---------------------------------------------------------------------------
# Mesure
# ---------------------------------------------------------------------------


def reference_percentile(model, cols: int, rows: int, reference: list[int],
                         samples: int = 400, seed: int = 0) -> float:
    """Part des arrangements aléatoires qui font *mieux* que l'ordre de référence.

    C'est la mesure honnête du pouvoir discriminant du coût : si l'ordre vrai
    bat 99 % des arrangements tirés au hasard, le modèle porte de l'information
    même quand le solveur ne retrouve pas l'ordre exact.
    """
    rng = random.Random(seed)
    reference_cost = model.arrangement_cost(list(reference), cols, rows)
    better = 0
    for _ in range(samples):
        permutation = list(range(model.n))
        rng.shuffle(permutation)
        if model.arrangement_cost(permutation, cols, rows) < reference_cost:
            better += 1
    return better / samples


def measure(model, cols: int, rows: int, reference: list[int]) -> dict:
    """Lance chaque méthode et compare son coût à celui de l'ordre de référence."""
    reference_cost = model.arrangement_cost(list(reference), cols, rows)
    result = {"reference_cost": reference_cost,
              "percentile": reference_percentile(model, cols, rows, reference),
              "methods": {}}
    for method in METHODS:
        if method == "M5" and model.n > 10:
            continue
        if method == "M6" and (min(cols, rows) != 1 or model.n > 14):
            continue
        began = time.perf_counter()
        try:
            solutions = solvers.solve(method, model, cols, rows, {"width": 400})
        except Exception as exc:  # une méthode qui échoue ne doit pas arrêter le banc
            result["methods"][method] = {"error": str(exc)}
            continue
        elapsed = time.perf_counter() - began
        if not solutions:
            result["methods"][method] = {"error": "aucune solution"}
            continue
        best = solutions[0]
        found_reference = best.order == list(reference)
        result["methods"][method] = {
            "cost": best.cost,
            "ratio": best.cost / reference_cost if reference_cost else 1.0,
            "time": elapsed,
            "exact": found_reference,
            "solutions": len(solutions),
        }
    return result


def summarise(rows: list[dict]) -> dict:
    """Agrège les mesures par méthode."""
    percentiles = [row["percentile"] for row in rows if "percentile" in row]
    summary: dict[str, dict] = {
        "_reference": {
            "mean_percentile": statistics.mean(percentiles) if percentiles else 0.0,
        }
    }
    for row in rows:
        for method, data in row["methods"].items():
            entry = summary.setdefault(method, {"costs": [], "ratios": [],
                                                "times": [], "exact": 0, "runs": 0})
            if "error" in data:
                continue
            entry["runs"] += 1
            entry["costs"].append(data["cost"])
            entry["ratios"].append(data["ratio"])
            entry["times"].append(data["time"])
            entry["exact"] += 1 if data["exact"] else 0
    for name, entry in summary.items():
        if name == "_reference" or not entry["runs"]:
            continue
        entry["mean_ratio"] = statistics.mean(entry["ratios"])
        entry["mean_time"] = statistics.mean(entry["times"])
        entry["exact_rate"] = entry["exact"] / entry["runs"]
        entry["mean_cost"] = statistics.mean(entry["costs"])
    return summary


def print_summary(title: str, summary: dict, runs: int) -> None:
    reference = summary.get("_reference", {})
    if reference:
        print(f"\n{title} — {runs} groupe(s)")
        print(f"  Ordre vrai battu par {reference['mean_percentile']:.1%} des "
              "arrangements aléatoires (plus bas = coût plus discriminant)")
    print(f"  {'méthode':8s} {'coût moyen':>11s} {'ratio':>7s} {'exact':>7s} {'temps':>9s}")
    for method in METHODS:
        entry = summary.get(method)
        if not entry or not entry["runs"]:
            continue
        print(f"  {method:8s} {entry['mean_cost']:11.3f} {entry['mean_ratio']:7.3f} "
              f"{entry['exact_rate']:6.0%} {entry['mean_time']:8.3f}s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", type=int, default=12,
                        help="nombre de groupes Barbarian à essayer")
    parser.add_argument("--synthetic", type=int, default=6,
                        help="nombre de sprites synthétiques")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    args = parser.parse_args(argv)

    results: dict = {}

    # -- Barbarian
    stx = ROOT / "Barbarian (1987)(Palace).stx"
    if stx.exists():
        rows = []
        for sheet, group in barbarian_groups(args.groups):
            model = build_cost_model(sheet, group)
            rows.append(measure(model, 2, 4, group))
        results["barbarian"] = {"runs": len(rows), "summary": summarise(rows)}
        if not args.json:
            print_summary("Barbarian (ordre de stockage = référence)",
                          results["barbarian"]["summary"], len(rows))
    else:
        if not args.json:
            print("Barbarian absent : banc limité au synthétique.")

    # -- synthétique
    rows = []
    for seed in range(args.synthetic):
        sheet, truth = synthetic_sheet(seed)
        for index, order in enumerate(truth):
            group = list(range(index * 8, index * 8 + 8))
            model = build_cost_model(sheet, group)
            rows.append(measure(model, 2, 4, order))
    results["synthetic"] = {"runs": len(rows), "summary": summarise(rows)}
    if not args.json:
        print_summary("Sprites synthétiques (ordre connu)", results["synthetic"]["summary"],
                      len(rows))
        print("\nRappel : ratio 1,000 = aussi bien que la référence ; "
              "« exact » = la référence a été retrouvée.")
        print("Barbarian : la référence est l'ordre de stockage, qui n'est PAS "
              "l'assemblage d'origine.")
        print("Synthétique : la référence est la vraie permutation, mais les "
              "sprites en aplats restent ambigus.")

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
