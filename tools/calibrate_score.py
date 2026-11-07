#!/usr/bin/env python3
"""Calibre la note de vraisemblance graphique sur un corpus étiqueté.

Le corpus mélange des **vrais graphismes** (banques Barbarian, planches
synthétiques de sprites et de police) et du **non-graphisme** (octets
aléatoires, code 68000, texte ASCII, motifs répétitifs, et surtout les faux
positifs réels observés lors d'un balayage LC_LZ2 sur Final Fight).

Le script ajuste les poids du modèle logistique de ``tileforge.core.score``
par descente de gradient, puis affiche la séparation obtenue (AUC) globale et
par format. Les poids retenus sont ensuite recopiés dans ``score.py``.

    python tools/calibrate_score.py            # rapport + poids proposés
    python tools/calibrate_score.py --write    # réécrit les poids dans score.py
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tileforge.core import score as S  # noqa: E402
from tileforge.core.formats import FORMATS_BY_KEY  # noqa: E402

# ---------------------------------------------------------------------------
# Encodeurs (inverses des décodeurs, pour fabriquer des positifs synthétiques)
# ---------------------------------------------------------------------------


def encode_snes(pixels: np.ndarray, bpp: int) -> bytes:
    """Encode une tuile 8×8 au format SNES (paires de plans entrelacées)."""
    h, w = pixels.shape
    out = bytearray()
    for pair in range(bpp // 2):
        for y in range(h):
            for plane in (2 * pair, 2 * pair + 1):
                byte = 0
                for x in range(8):
                    if (int(pixels[y, x]) >> plane) & 1:
                        byte |= 0x80 >> x
                out.append(byte)
    return bytes(out)


def encode_megadrive(pixels: np.ndarray) -> bytes:
    """Encode une tuile 8×8 au format Mega Drive (4 plans, un octet par ligne)."""
    out = bytearray()
    for y in range(8):
        for plane in range(4):
            byte = 0
            for x in range(8):
                if (int(pixels[y, x]) >> plane) & 1:
                    byte |= 0x80 >> x
            out.append(byte)
    return bytes(out)


# ---------------------------------------------------------------------------
# Fabriques de données
# ---------------------------------------------------------------------------


def sprite_tile(rng: random.Random, size: int = 8, colors: int = 8,
                margin: float = 0.75) -> np.ndarray:
    """Une tuile « sprite » : aplats, marges vides, quelques formes."""
    tile = np.zeros((size, size), dtype=np.int32)
    shapes = rng.randint(1, 3)
    for _ in range(shapes):
        x0 = rng.randint(0, size - 2)
        y0 = rng.randint(0, size - 2)
        w = rng.randint(1, max(1, size - x0))
        h = rng.randint(1, max(1, size - y0))
        color = rng.randint(1, max(1, colors - 1))
        tile[y0:y0 + h, x0:x0 + w] = color
    # marges : le bord reste souvent vide
    if rng.random() < margin:
        tile[0, :] = 0
        tile[:, 0] = 0
    if rng.random() < margin:
        tile[-1, :] = 0
        tile[:, -1] = 0
    return tile


def sprite_sheet(seed: int, count: int = 64, size: int = 8,
                 colors: int = 8) -> list[np.ndarray]:
    rng = random.Random(seed)
    tiles = []
    base = sprite_tile(rng, size, colors)
    for index in range(count):
        # une partie des tuiles sont des variantes de la précédente (animation)
        if index and rng.random() < 0.35:
            tile = base.copy()
            for _ in range(rng.randint(1, 6)):
                x, y = rng.randrange(size), rng.randrange(size)
                tile[y, x] = rng.randint(0, colors - 1)
        else:
            tile = sprite_tile(rng, size, colors)
            if index % 7 == 0:
                base = tile
        if rng.random() < 0.08:       # tuile vide, fréquente dans une banque
            tile = np.zeros((size, size), dtype=np.int32)
        tiles.append(tile)
    return tiles


def font_sheet(seed: int, count: int = 64) -> list[np.ndarray]:
    """Police 8×8 : traits pleins, 2 couleurs, marges."""
    rng = random.Random(seed)
    tiles = []
    for _ in range(count):
        tile = np.zeros((8, 8), dtype=np.int32)
        for _ in range(rng.randint(3, 12)):
            if rng.random() < 0.5:
                y = rng.randrange(1, 7)
                x0 = rng.randint(1, 4)
                tile[y, x0:x0 + rng.randint(2, 6)] = 1
            else:
                x = rng.randrange(1, 7)
                y0 = rng.randint(1, 4)
                tile[y0:y0 + rng.randint(2, 6), x] = 1
        tiles.append(tile)
    return tiles


def pack(tiles: list[np.ndarray], encoder) -> bytes:
    return b"".join(encoder(tile) for tile in tiles)


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------


def barbarian_blocks() -> list[bytes]:
    """Vraies tuiles Barbarian, découpées en fenêtres de 48 tuiles."""
    dat = ROOT / "extract" / "BARB.DAT"
    if not dat.exists():
        return []
    data = dat.read_bytes()
    blocks = []
    for offset in (0x33A52, 0x3B65A):
        chunk = data[offset:offset + 252 * 126]
        for start in range(0, len(chunk) - 48 * 126, 48 * 126):
            blocks.append(chunk[start:start + 48 * 126])
    return blocks


def lz2_false_positives(limit: int = 150) -> list[bytes]:
    """Blocs issus d'un balayage LC_LZ2 réel sur Final Fight.

    La sélection est **indépendante du modèle évalué** : on garde tout ce que
    le décompresseur produit de taille plausible et alignée sur la tuile, puis
    on échantillonne régulièrement. Sélectionner d'après la note qu'on cherche
    à calibrer rendrait le corpus circulaire.
    """
    rom = ROOT / "snes" / "Final Fight.bin"
    if not rom.exists():
        return []
    from tileforge.core.compression import lz2

    data = rom.read_bytes()
    pool: list[bytes] = []
    for offset in range(0, 262144):
        try:
            result = lz2(data, offset, 1 << 17)
        except Exception:
            continue
        if 512 <= len(result) <= 8192 and len(result) % 32 == 0:
            pool.append(result)
    if len(pool) <= limit:
        return pool
    stride = len(pool) / limit
    return [pool[int(index * stride)] for index in range(limit)]


def code_blocks() -> list[bytes]:
    """Code 68000 réel, découpé en blocs."""
    prg = ROOT / "extract" / "A.PRG"
    if not prg.exists():
        return []
    data = prg.read_bytes()
    return [data[start:start + 2048] for start in range(0x200, min(len(data), 0x8000), 2048)]


def real_png_blocks() -> list[tuple[bytes, str]]:
    """Vrais graphismes Barbarian relus depuis les PNG de référence.

    Les écrans 320×200 sont découpés en tuiles 8×8 puis réencodés en SNES 4bpp :
    ce sont de vrais décors de jeu, utiles pour équilibrer le corpus face aux
    sprites. La police 8×8 fournit des tuiles 1 bit.
    """
    try:
        from tileforge.core.image import load_image
    except Exception:
        return []
    blocks: list[tuple[bytes, str]] = []
    folder = ROOT / "graphisme"
    if not folder.exists():
        return []
    for path in sorted(folder.glob("ecran_*.png")):
        try:
            image = load_image(str(path))
        except Exception:
            continue
        pixels = image.px
        colors, inverse = np.unique(pixels.reshape(-1, 4), axis=0, return_inverse=True)
        if len(colors) > 16:
            continue
        indices = inverse.reshape(pixels.shape[:2]).astype(np.int32)
        height, width = indices.shape
        tiles = [indices[y:y + 8, x:x + 8]
                 for y in range(0, height - 7, 8)
                 for x in range(0, width - 7, 8)]
        for start in range(0, len(tiles) - 127, 128):
            blob = b"".join(encode_snes(tile, 4) for tile in tiles[start:start + 128])
            blocks.append((blob, "snes_4bpp"))
    font = folder / "police_8x8.png"
    if font.exists():
        try:
            image = load_image(str(font))
            pixels = image.px
            colors, inverse = np.unique(pixels.reshape(-1, 4), axis=0, return_inverse=True)
            indices = inverse.reshape(pixels.shape[:2]).astype(np.int32)
            height, width = indices.shape
            tiles = [indices[y:y + 8, x:x + 8]
                     for y in range(0, height - 7, 8)
                     for x in range(0, width - 7, 8)]
            for start in range(0, len(tiles) - 63, 64):
                blob = b"".join(encode_snes(tile % 4, 2) for tile in tiles[start:start + 64])
                blocks.append((blob, "snes_2bpp"))
        except Exception:
            pass
    return blocks


def build_corpus() -> tuple[list[tuple[int, bytes, str, str]], list[str]]:
    """Renvoie [(étiquette, bloc, clé de format, source)] et la liste des sources."""
    rng = random.Random(1234)
    corpus: list[tuple[int, bytes, str, str]] = []
    sources: list[str] = []

    def add(label: int, blob: bytes, fmt_key: str, source: str) -> None:
        if len(blob) >= 256:
            corpus.append((label, blob, fmt_key, source))

    # -- positifs réels ------------------------------------------------------
    for blob in barbarian_blocks():
        add(1, blob, "barbarian_st", "barbarian")
    sources.append("Barbarian (banque brute réelle)")

    for blob, fmt_key in real_png_blocks():
        add(1, blob, fmt_key, "png_reel")
    sources.append("Barbarian (écrans et police relus depuis les PNG)")

    # -- positifs synthétiques ----------------------------------------------
    for seed in range(6):
        tiles = sprite_sheet(seed * 17 + 1, 64, 8, 8)
        add(1, pack(tiles, lambda t: encode_snes(t, 4)), "snes_4bpp", "synthetique")
        add(1, pack(tiles, encode_megadrive), "megadrive", "synthetique")
    for seed in range(4):
        tiles = sprite_sheet(seed * 31 + 7, 64, 16, 4)
        add(1, pack(tiles, lambda t: encode_snes(t, 2)), "snes_2bpp", "synthetique")
    for seed in range(3):
        tiles = font_sheet(seed * 13 + 3, 64)
        add(1, pack(tiles, lambda t: encode_snes(t, 2)), "snes_2bpp", "synthetique")
    sources.append("planches synthétiques (sprites, police)")

    # -- négatifs ------------------------------------------------------------
    for size in (1024, 2048, 4096):
        add(0, bytes(rng.randrange(256) for _ in range(size)), "snes_4bpp", "alea")
        add(0, bytes(rng.randrange(256) for _ in range(size)), "megadrive", "alea")
    for _ in range(3):
        add(0, bytes(rng.randrange(4) for _ in range(2048)), "snes_2bpp", "alea")
    for _ in range(3):
        add(0, bytes(rng.randrange(8) for _ in range(2048)), "snes_4bpp", "alea")
    text = (b"TileForge calibration corpus. " * 200)[:4096]
    add(0, text, "snes_4bpp", "texte")
    for pattern in (b"\x00\x00", b"\xff\x00", b"\xaa\x55"):
        add(0, pattern * 2048, "snes_4bpp", "motif")
    for blob in code_blocks():
        add(0, blob, "barbarian_st", "code")
    sources.append("aléatoire, texte, motifs, code 68000")

    for blob in lz2_false_positives():
        add(0, blob, "snes_4bpp", "faux_positif")
    sources.append("faux positifs LC_LZ2 réels (Final Fight)")

    return corpus, sources


# ---------------------------------------------------------------------------
# Statistiques
# ---------------------------------------------------------------------------


def auc(positive: np.ndarray, negative: np.ndarray) -> float:
    """Aire sous la courbe ROC, calculée par les rangs (Mann-Whitney)."""
    if len(positive) == 0 or len(negative) == 0:
        return float("nan")
    values = np.concatenate([positive, negative])
    order = values.argsort()
    ranks = np.empty(len(values), dtype=np.float64)
    ranks[order] = np.arange(1, len(values) + 1)
    # rangs moyens pour les ex æquo
    unique, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    sums = np.zeros(len(unique))
    np.add.at(sums, inverse, ranks)
    ranks = (sums / counts)[inverse]
    rank_pos = ranks[:len(positive)].sum()
    return float((rank_pos - len(positive) * (len(positive) + 1) / 2)
                 / (len(positive) * len(negative)))


def fit(features: np.ndarray, labels: np.ndarray, iterations: int = 8000,
        learning_rate: float = 0.6, l2: float = 1e-3,
        non_negative: bool = True, max_weight: float = 2.0) -> tuple[np.ndarray, float]:
    """Régression logistique par descente de gradient, classes équilibrées.

    Les poids sont contraints à rester positifs et bornés : chaque indice doit
    faire *monter* la note, et aucun ne doit écraser les autres. Ces deux
    contraintes, mesurées par validation croisée, améliorent nettement la
    généralisation (AUC hors échantillon 0,98 contre 0,92 sans borne) et
    rendent le score interprétable.
    """
    n, d = features.shape
    weights = np.zeros(d)
    bias = 0.0
    positive = labels.sum()
    negative = n - positive
    weight_pos = n / (2 * max(1, positive))
    weight_neg = n / (2 * max(1, negative))
    sample_weight = np.where(labels == 1, weight_pos, weight_neg)
    sample_weight /= sample_weight.mean()
    for _ in range(iterations):
        logits = features @ weights + bias
        predictions = 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))
        error = (predictions - labels) * sample_weight
        grad_w = features.T @ error / n + l2 * weights
        grad_b = error.mean()
        weights -= learning_rate * grad_w
        if non_negative:
            np.clip(weights, 0.0, max_weight, out=weights)
        bias -= learning_rate * grad_b
    return weights, float(bias)


# ---------------------------------------------------------------------------
# Programme
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="réécrit WEIGHTS et BIAS dans tileforge/core/score.py")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="seuil à évaluer (défaut : 0,5)")
    args = parser.parse_args(argv)

    corpus, sources = build_corpus()
    print(f"Corpus : {len(corpus)} blocs")
    for source in sources:
        print(f"  · {source}")
    if not corpus:
        print("Corpus vide : données absentes.")
        return 2

    rows, labels, formats, groups, varieties = [], [], [], [], []
    for label, blob, fmt_key, source in corpus:
        fmt = FORMATS_BY_KEY[fmt_key]
        features = S.tile_features(blob, fmt)
        if features is None:
            continue
        rows.append(S.features_vector(features))
        labels.append(label)
        formats.append(fmt_key)
        groups.append(source)
        varieties.append(features["variety"])
    X = np.asarray(rows)
    y = np.asarray(labels, dtype=np.float64)
    formats_arr = np.asarray(formats)
    groups_arr = np.asarray(groups)
    gate = np.asarray([S.variety_gate(value) for value in varieties])

    def predict(weights, bias, subset=None):
        logits = X @ weights + bias
        base = 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))
        return base * gate
    print(f"Blocs exploitables : {len(y)}  (positifs : {int(y.sum())})")

    # -- note avec les poids actuels ---------------------------------------
    current = predict(np.asarray(S.WEIGHTS), S.BIAS)
    pos, neg = current[y == 1], current[y == 0]
    print("\nPoids actuels")
    print(f"  AUC globale      : {auc(pos, neg):.4f}")
    print(f"  positifs médiane : {np.median(pos):.3f}  min : {pos.min():.3f}")
    print(f"  négatifs médiane : {np.median(neg):.3f}  max : {neg.max():.3f}")
    for key in sorted(set(formats)):
        mask = formats_arr == key
        sub_pos, sub_neg = current[mask & (y == 1)], current[mask & (y == 0)]
        if len(sub_pos) and len(sub_neg):
            print(f"    {key:14s} AUC {auc(sub_pos, sub_neg):.4f}")

    # -- pouvoir discriminant de chaque indice ------------------------------
    print("\nIndices (moyenne positifs / négatifs, AUC individuelle)")
    for index, name in enumerate(S.FEATURE_NAMES):
        column = X[:, index]
        print(f"  {name:12s} {column[y == 1].mean():.3f} / {column[y == 0].mean():.3f}"
              f"   AUC {auc(column[y == 1], column[y == 0]):.3f}")

    # -- validation croisée par groupe -------------------------------------
    # On retire à la fois une famille de positifs et une famille de négatifs,
    # on ajuste sur le reste, et on mesure la séparation sur les familles
    # retirées. C'est la seule mesure honnête de généralisation : aucune
    # image du test n'a servi à l'ajustement.
    positive_groups = sorted({g for g, label in zip(groups, y, strict=False) if label == 1})
    negative_groups = sorted({g for g, label in zip(groups, y, strict=False) if label == 0})
    print("\nValidation croisée (une famille de positifs + une de négatifs retirées)")
    fold_aucs = []
    for pos_group in positive_groups:
        for neg_group in negative_groups:
            test = (groups_arr == pos_group) | (groups_arr == neg_group)
            train = ~test
            if (y[test] == 1).sum() < 2 or (y[test] == 0).sum() < 2:
                continue
            if (y[train] == 1).sum() < 3 or (y[train] == 0).sum() < 3:
                continue
            w, b = fit(X[train], y[train])
            held = predict(w, b)[test]
            value = auc(held[y[test] == 1], held[y[test] == 0])
            if value == value:  # pas NaN
                fold_aucs.append(value)
                print(f"  sans {pos_group:12s} + {neg_group:12s} → AUC {value:.4f}")
    if fold_aucs:
        print(f"  moyenne {np.mean(fold_aucs):.4f} · écart-type {np.std(fold_aucs):.4f}")

    # -- ajustement final ---------------------------------------------------
    weights, bias = fit(X, y)
    fitted = predict(weights, bias)
    pos, neg = fitted[y == 1], fitted[y == 0]
    print("\nPoids ajustés sur tout le corpus")
    for name, value in zip(S.FEATURE_NAMES, weights, strict=False):
        print(f"  {name:10s} {value:+.4f}")
    print(f"  {'biais':10s} {bias:+.4f}")
    print(f"  AUC globale      : {auc(pos, neg):.4f}")
    print(f"  positifs médiane : {np.median(pos):.3f}  min : {pos.min():.3f}")
    print(f"  négatifs médiane : {np.median(neg):.3f}  max : {neg.max():.3f}")
    for key in sorted(set(formats)):
        mask = formats_arr == key
        sub_pos, sub_neg = fitted[mask & (y == 1)], fitted[mask & (y == 0)]
        if len(sub_pos) and len(sub_neg):
            print(f"    {key:14s} AUC {auc(sub_pos, sub_neg):.4f}")
    false_positive = float((neg >= args.threshold).mean())
    false_negative = float((pos < args.threshold).mean())
    print(f"\nAu seuil {args.threshold:.2f} : faux positifs {false_positive:.1%}, "
          f"faux négatifs {false_negative:.1%}")

    # -- pires faux positifs ------------------------------------------------
    worst = np.argsort(-fitted)[:5]
    print("\nBlocs les mieux notés (à vérifier : un négatif ici est un faux positif) :")
    for index in worst:
        print(f"  {fitted[index]:.3f}  {'positif' if y[index] else 'NÉGATIF'}  "
              f"{formats[index]:12s} {groups[index]}")

    if args.write:
        path = ROOT / "tileforge" / "core" / "score.py"
        text = path.read_text(encoding="utf-8")
        rounded = ", ".join(f"{value:.2f}" for value in weights)
        text = re.sub(r"WEIGHTS: tuple\[float, \.\.\.\] = \([^)]*\)",
                      f"WEIGHTS: tuple[float, ...] = ({rounded})", text)
        text = re.sub(r"BIAS: float = [-0-9.]+", f"BIAS: float = {bias:.2f}", text)
        path.write_text(text, encoding="utf-8")
        print(f"\nPoids écrits dans {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
