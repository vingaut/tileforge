"""Notation de vraisemblance graphique d'un bloc de données.

Un balayage de ROM produit des millions de blocs candidats. Il faut pouvoir
répondre vite et de façon fiable à une seule question : *ces octets
ressemblent-ils à des tuiles de jeu ?*

Le modèle combine quatre indices de structure, puis applique un **veto de
variété** : un bloc fait de tuiles toutes identiques n'est pas un graphisme,
quelles que soient ses qualités par ailleurs.

Indices
-------
``coherence``   deux pixels voisins ont-ils souvent la même couleur ?
``runs``        longueur moyenne des plages de couleur (un sprite a des aplats)
``palette``     le bloc utilise-t-il peu de couleurs par rapport à sa profondeur ?
``singletons``  les plages d'un seul pixel sont-elles rares (le bruit en est plein) ?
``variety``     (veto) les tuiles sont-elles différentes les unes des autres ?

Les poids et le veto ne sont pas choisis à l'œil : ils sont ajustés sur un
corpus étiqueté par ``tools/calibrate_score.py`` (vrais graphismes contre
bruit, code, texte, motifs et faux positifs réels de balayage), et la
séparation obtenue est vérifiée par les tests.

Mesures obtenues sur ce corpus (235 blocs, 66 positifs) : AUC 0,978,
validation croisée par famille 0,978 ± 0,033, précision 87 % au seuil 0,45.

Le module ne dépend ni de Qt ni de l'interface : il s'utilise en script.
"""

from __future__ import annotations

import math

import numpy as np

#: Indices utilisés par le modèle, dans l'ordre du vecteur.
FEATURE_NAMES: tuple[str, ...] = (
    "coherence",
    "runs",
    "palette",
    "singletons",
)

#: Poids ajustés par ``tools/calibrate_score.py``.
WEIGHTS: tuple[float, ...] = (2.00, 2.00, 1.04, 2.00)

#: Biais du modèle.
BIAS: float = -4.16

#: En dessous de ce taux de tuiles distinctes, la note est annulée.
GATE_LOW: float = 0.05

#: Au-delà de ``GATE_LOW + GATE_SPAN``, le veto ne mord plus.
GATE_SPAN: float = 0.20

#: Part de tuiles non vides en dessous de laquelle la note est annulée.
CONTENT_LOW: float = 0.15

#: Écart de part de tuiles non vides au-delà duquel le veto ne mord plus.
CONTENT_SPAN: float = 0.25

#: Une tuile dont une couleur couvre plus que cette part est du remplissage.
RICH_DOMINANCE: float = 0.90

#: Nombre de tuiles examinées au maximum pour noter un bloc.
MAX_TILES: int = 96

#: Nombre minimal de tuiles pour qu'une note ait un sens.
MIN_TILES: int = 4

#: Seuil de travail conseillé : compromis rappel / précision mesuré.
DEFAULT_THRESHOLD: float = 0.45


# ---------------------------------------------------------------------------
# Extraction des indices
# ---------------------------------------------------------------------------


def _clip01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _decode_tiles(data: bytes, fmt, max_tiles: int):
    """Décode au plus ``max_tiles`` tuiles ; renvoie un tableau (n, h, w)."""
    try:
        tile_bytes = int(fmt.real_bytes)
    except Exception:
        return None
    if tile_bytes <= 0:
        return None
    count = min(len(data) // tile_bytes, max_tiles)
    if count < MIN_TILES:
        return None
    tiles = []
    shape = None
    for index in range(count):
        block = data[index * tile_bytes:(index + 1) * tile_bytes]
        try:
            tile = np.asarray(fmt.decode(block))
        except Exception:
            return None
        if tile.ndim != 2 or tile.size == 0:
            return None
        if shape is None:
            shape = tile.shape
        elif tile.shape != shape:
            return None
        tiles.append(tile.astype(np.int32, copy=False))
    if not tiles:
        return None
    return np.stack(tiles)


def tile_features(data: bytes, fmt, max_tiles: int = MAX_TILES) -> dict[str, float] | None:
    """Calcule les indices de vraisemblance, ou ``None`` si le bloc est inutilisable."""
    stack = _decode_tiles(data, fmt, max_tiles)
    if stack is None:
        return None
    count, height, width = stack.shape
    if height < 2 or width < 2:
        return None

    bpp = max(1, min(8, int(getattr(fmt, "bpp", 4) or 4)))
    levels = 1 << bpp
    baseline = 1.0 / levels  # probabilité que deux pixels voisins soient égaux par hasard

    # Un bloc constant n'est jamais un graphisme : c'est du remplissage, une
    # zone vide ou une donnée répétitive. On l'écarte sans calcul.
    flat = stack.reshape(-1)
    if int(flat.min()) == int(flat.max()):
        return dict.fromkeys((*FEATURE_NAMES, "variety"), 0.0)

    # -- cohérence spatiale -------------------------------------------------
    eq_h = float((stack[:, :, :-1] == stack[:, :, 1:]).mean())
    eq_v = float((stack[:, :-1, :] == stack[:, 1:, :]).mean())
    raw_coherence = 0.5 * (eq_h + eq_v)
    coherence = _clip01((raw_coherence - baseline) / max(1e-6, 1.0 - baseline))

    # -- longueur et isolement des plages -----------------------------------
    # Tout est vectorisé : un balayage de ROM note des milliers de blocs, une
    # boucle Python par ligne de tuile coûterait des minutes.
    transitions = int((stack[:, :, 1:] != stack[:, :, :-1]).sum())
    total_runs = transitions + count * height
    mean_run = (count * height * width) / max(1, total_runs)
    runs = _clip01(mean_run / max(2.0, width * 0.55))
    if width > 2:
        middle = stack[:, :, 1:-1]
        isolated = ((middle != stack[:, :, :-2]) & (middle != stack[:, :, 2:])).sum()
        singleton_ratio = float(isolated) / float(count * height * max(1, width - 2))
    else:
        singleton_ratio = 0.0
    singletons = _clip01(1.0 - singleton_ratio / 0.55)

    # -- économie de palette -------------------------------------------------
    colors = int(np.bincount(flat, minlength=levels).astype(bool).sum())
    palette = _clip01(1.0 - (colors - 2) / max(1.0, levels - 2))

    # -- variété des tuiles (veto) ------------------------------------------
    # Les tuiles d'une seule couleur ne portent aucune information : ce sont
    # les marges d'un sprite ou le remplissage d'une ROM. On les écarte avant
    # de mesurer la variété, sinon un bloc de remplissage multicolore passerait
    # pour une planche de sprites.
    # Une tuile « riche » n'est pas dominée par une seule couleur : une tuile
    # de remplissage à un pixel près ne compte pas comme du dessin.
    bins = max(levels, int(flat.max()) + 1)
    shifted = stack.reshape(count, -1) + (np.arange(count, dtype=np.int64) * bins)[:, None]
    hist = np.bincount(shifted.reshape(-1), minlength=count * bins).reshape(count, bins)
    dominant = hist.max(axis=1) / float(height * width)
    rich = [tile for tile, value in zip(stack, dominant, strict=False)
            if value < RICH_DOMINANCE]
    if len(rich) < 3:
        variety = 0.0
    else:
        distinct = len({tile.tobytes() for tile in rich})
        richness = _clip01((len(rich) / count - CONTENT_LOW) / CONTENT_SPAN)
        variety = _clip01((distinct / len(rich) - GATE_LOW) / GATE_SPAN) * richness

    return {
        "coherence": coherence,
        "runs": runs,
        "palette": palette,
        "singletons": singletons,
        "variety": variety,
    }


# ---------------------------------------------------------------------------
# Modèle
# ---------------------------------------------------------------------------


def features_vector(features: dict[str, float]) -> np.ndarray:
    """Vecteur de caractéristiques dans l'ordre de :data:`FEATURE_NAMES`."""
    return np.asarray([features[name] for name in FEATURE_NAMES], dtype=np.float64)


def variety_gate(variety: float) -> float:
    """Facteur de veto : 0 pour un bloc de tuiles toutes identiques, 1 sinon."""
    return _clip01((variety - GATE_LOW) / GATE_SPAN)


def combine(vector: np.ndarray, variety: float = 1.0,
            weights: tuple[float, ...] | np.ndarray = WEIGHTS,
            bias: float = BIAS) -> float:
    """Applique le modèle à un vecteur de caractéristiques et au veto de variété."""
    logit = float(np.dot(np.asarray(weights, dtype=np.float64), vector) + bias)
    logit = max(-30.0, min(30.0, logit))
    return float(1.0 / (1.0 + math.exp(-logit))) * variety_gate(variety)


def score(data: bytes, fmt, max_tiles: int = MAX_TILES) -> float:
    """Note de 0 à 1 : ces octets ressemblent-ils à des graphismes ?

    ``fmt`` est un :class:`tileforge.core.formats.TileFormat`.
    """
    features = tile_features(data, fmt, max_tiles)
    if features is None:
        return 0.0
    return combine(features_vector(features), features["variety"])


def explain(data: bytes, fmt, max_tiles: int = MAX_TILES) -> dict:
    """Note, détail des indices et contributions, pour l'interface et le diagnostic."""
    features = tile_features(data, fmt, max_tiles)
    if features is None:
        return {"score": 0.0, "features": {}, "contributions": {},
                "gate": 0.0, "reason": "bloc trop petit ou indécodable"}
    vector = features_vector(features)
    return {
        "score": combine(vector, features["variety"]),
        "features": features,
        "contributions": {
            name: float(w * x)
            for name, w, x in zip(FEATURE_NAMES, WEIGHTS, vector, strict=True)
        },
        "gate": variety_gate(features["variety"]),
        "reason": "",
    }


def score_formats(data: bytes, formats, max_tiles: int = MAX_TILES):
    """Note un bloc sur plusieurs formats et renvoie le meilleur couple (note, format).

    Attention : ce n'est **pas** un identificateur de format. Une lecture en
    1 bit « explique » presque n'importe quelle donnée structurée, et obtient
    souvent une meilleure note que le format réel. La fonction sert à classer
    des candidats quand le format est déjà restreint à une famille plausible ;
    l'identification du format reste à faire (phase A.5 de la feuille de route).
    """
    best_score = 0.0
    best_format = None
    for fmt in formats:
        value = score(data, fmt, max_tiles)
        if value > best_score:
            best_score, best_format = value, fmt
    return best_score, best_format
