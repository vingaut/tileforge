"""Identification du format de tuiles d'une banque inconnue.

On dispose d'un bloc d'octets et l'on veut savoir comment le lire : taille de
tuile, profondeur, disposition des plans. C'est le premier obstacle quand on
attaque un jeu sans documentation.

La méthode est simple mais doit être menée avec soin : on note le bloc avec
chaque format candidat, **puis on compare cette note à ce que ce même format
donnerait sur du bruit**. Sans cette référence, un format à 1 bit « explique »
n'importe quoi et gagne toujours : deux pixels voisins tirés au hasard sont
identiques une fois sur deux, ce qui suffit à faire croire à un dessin.

On classe donc les formats par **marge** au-dessus de leur propre plancher de
bruit, pas par note brute.

Le module ne dépend ni de Qt ni de l'interface.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import score as scoring
from .formats import FORMATS, FORMATS_BY_KEY, TileFormat

#: Formats proposés par défaut à l'identification.
#:
#: Les variantes exotiques (chunky 8 bits, CPS-1…) restent disponibles en
#: passant une liste explicite, mais elles fausseraient le classement sur une
#: banque 8 bits classique.
DEFAULT_CANDIDATES: tuple[str, ...] = (
    "snes_4bpp", "snes_2bpp", "snes_3bpp", "snes_8bpp",
    "megadrive", "gba_4bpp", "gba_8bpp", "master_system", "pc_engine",
    "nes", "gameboy", "zx_spectrum", "c64",
    "cpc_mode0", "cpc_mode1", "cpc_mode2",
    "st_sprite_2pl", "st_sprite_4pl", "amiga_sprite",
    "neo_geo", "barbarian_st", "chunky4", "chunky8",
)

#: Nombre d'échantillons de bruit par format pour établir le plancher.
NULL_SAMPLES: int = 6

#: Taille des échantillons de bruit, en octets.
NULL_SIZE: int = 4096

#: Graine fixe : le plancher doit être reproductible d'une exécution à l'autre.
NULL_SEED: int = 20261107


#: Libellés des dispositions de plans, pour l'affichage.
_LAYOUT_LABELS: dict[str, str] = {
    "row_planes_bytes": "plans par ligne, octets",
    "row_planes_words": "plans par ligne, mots",
    "row_plane_pairs_bytes": "paires de plans par ligne (SNES)",
    "seq_planes_bytes": "plans séquentiels (NES, Game Boy)",
    "seq_plane_pairs": "paires de plans séquentielles (PC Engine)",
    "snes_3bpp": "3 plans façon SNES",
    "nibble": "quartets, 2 pixels par octet (Mega Drive)",
    "chunky": "pixels indexés",
    "cpc": "entrelacement CPC",
}


def family_label(fmt: TileFormat) -> str:
    """Décrit la profondeur et la disposition, ce qui est le plus fiable."""
    layout = _LAYOUT_LABELS.get(fmt.layout, fmt.layout)
    return f"{fmt.bpp} plans, {layout}"


@dataclass
class FormatGuess:
    """Un format candidat et les mesures qui l'ont classé."""

    key: str
    name: str
    score: float
    baseline: float
    margin: float
    tiles: int = 0
    family: str = ""
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "score": round(self.score, 4),
            "baseline": round(self.baseline, 4),
            "margin": round(self.margin, 4),
            "tiles": self.tiles,
            "family": self.family,
        }


def null_baseline(fmt: TileFormat, size: int = NULL_SIZE,
                  samples: int = NULL_SAMPLES) -> float:
    """Note moyenne obtenue par ce format sur du bruit de même taille.

    C'est le « plancher » du format : en dessous, un bloc n'apprend rien.
    """
    rng = random.Random(NULL_SEED)
    total = 0.0
    usable = 0
    for _ in range(samples):
        blob = bytes(rng.randrange(256) for _ in range(size))
        value = scoring.score(blob, fmt)
        if value > 0.0:
            total += value
            usable += 1
    return total / usable if usable else 0.0


_BASELINES: dict[tuple[str, int], float] = {}


def baseline_for(fmt: TileFormat, size: int = NULL_SIZE) -> float:
    """Plancher de bruit du format, calculé une fois et mémorisé."""
    key = (fmt.key, size)
    if key not in _BASELINES:
        _BASELINES[key] = null_baseline(fmt, size)
    return _BASELINES[key]


def candidates(formats: list[str] | None = None) -> list[TileFormat]:
    """Formats candidats, dans l'ordre demandé ou par défaut."""
    keys = formats or DEFAULT_CANDIDATES
    out = []
    for key in keys:
        fmt = FORMATS_BY_KEY.get(key)
        if fmt is not None:
            out.append(fmt)
    return out or list(FORMATS)


def identify(data: bytes, formats: list[str] | None = None,
             limit: int = 5, min_tiles: int = 8) -> list[FormatGuess]:
    """Classe les formats qui expliquent le mieux ce bloc.

    Renvoie les ``limit`` meilleurs, triés par marge décroissante. Une marge
    faible (moins de 0,05) signifie que le bloc ne ressemble à rien de connu :
    mieux vaut alors le dire que proposer un format au hasard.
    """
    if not data:
        return []
    sample = data[: NULL_SIZE * 2]
    guesses: list[FormatGuess] = []
    for fmt in candidates(formats):
        tile_bytes = max(1, int(fmt.real_bytes))
        tiles = len(sample) // tile_bytes
        if tiles < min_tiles:
            continue
        value = scoring.score(sample, fmt)
        if value <= 0.0:
            continue
        base = baseline_for(fmt, min(len(sample), NULL_SIZE))
        guesses.append(FormatGuess(
            key=fmt.key, name=fmt.name, score=value, baseline=base,
            margin=value - base, tiles=tiles, family=family_label(fmt)))
    guesses.sort(key=lambda guess: -guess.margin)
    return guesses[:limit]


def best(data: bytes, formats: list[str] | None = None,
         min_margin: float = 0.05) -> FormatGuess | None:
    """Meilleur format, ou ``None`` si aucun ne se détache du bruit."""
    guesses = identify(data, formats, limit=1)
    if not guesses:
        return None
    return guesses[0] if guesses[0].margin >= min_margin else None


def explain(data: bytes, formats: list[str] | None = None) -> dict:
    """Résumé lisible : classement, meilleur format, verdict."""
    guesses = identify(data, formats, limit=5)
    chosen = best(data, formats)
    return {
        "best": chosen.as_dict() if chosen else None,
        "ranking": [guess.as_dict() for guess in guesses],
        "confident": chosen is not None,
        "message": (
            f"Format probable : {chosen.name} ({chosen.family}). "
            "La profondeur et la disposition sont fiables ; vérifiez la taille "
            "de tuile, elle ne se déduit pas de l'analyse." if chosen
            else "Aucun format ne se détache : le bloc ne ressemble pas à des tuiles"),
    }
