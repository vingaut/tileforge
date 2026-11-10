"""Écrans Amiga : rendu planaire libre et détection de géométrie.

TileForge ne savait rendre que des tuiles de 8×8, 16×16 ou 24×21.  Or l'Amiga
stocke des **bitmaps pleine page** en plans de bits, dans deux dispositions :

``row``
    pour chaque ligne, les uns après les autres les octets du plan 0, du
    plan 1, etc. (disposition des écrans Atari ST et de nombreux jeux Amiga) ;
``plane``
    tous les octets du plan 0, puis tous ceux du plan 1, etc. (disposition
    des écrans de chargement de Project-X, 10 240 octets par plan).

La largeur utile, la hauteur, le nombre de plans et le **pas de ligne**
(stride) sont indépendants : le cas « image de 256 pixels dans un bitmap de
320 » est la norme, pas l'exception.  Le module fournit donc un rendu libre,
un détecteur de géométrie par cohérence de voisinage, un détecteur de
bourrage et un lecteur de palettes ``0x0RGB``.

Références : le RKM Amiga (« Graphics Library ») pour la disposition des
plans, et les mesures faites sur les six écrans de chargement de Project-X
(256×256 utiles dans un bitmap de 320, plan 6 vide sur quatre images).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .image import Image
from .palettes import Palette, amiga_to_rgb

#: Largeurs de bitmap les plus courantes sur Amiga.
COMMON_WIDTHS: tuple[int, ...] = (256, 288, 320, 352, 384, 640)

#: Dispositions gérées.
LAYOUTS: tuple[str, ...] = ("row", "plane")

#: Palette par défaut si l'appelant n'en fournit pas.
DEFAULT_PALETTE = Palette([amiga_to_rgb(i * 0x111) for i in range(16)],
                          "amiga 4 bits")

#: Nombre maximal de couleurs d'un écran Amiga (8 plans).
MAX_COLORS = 256


@dataclass
class ScreenCandidate:
    """Géométrie candidate pour un bitmap planaire."""

    offset: int
    width: int
    height: int
    planes: int
    layout: str
    stride: int
    score: float
    plane_density: list[float] = field(default_factory=list)
    content_width: int = 0

    def as_dict(self) -> dict:
        return {
            "offset": self.offset,
            "width": self.width,
            "height": self.height,
            "planes": self.planes,
            "layout": self.layout,
            "stride": self.stride,
            "score": round(self.score, 4),
            "plane_density": [round(v, 4) for v in self.plane_density],
            "content_width": self.content_width,
        }


def _plane_rows(data: bytes, offset: int, width: int, height: int,
                planes: int, layout: str, stride: int) -> np.ndarray:
    """Extrait les bits de chaque plan : tableau (planes, height, width)."""
    needed = ((height * stride * planes) if layout == "row"
              else (planes * height * stride))
    if offset < 0 or offset + needed > len(data):
        raise ValueError(
            f"bitmap tronqué : {needed} octets nécessaires à {offset}, "
            f"{len(data) - offset} disponibles")
    row_bytes = (width + 7) // 8
    if stride < row_bytes:
        raise ValueError("pas de ligne plus petit que la largeur")

    bits = np.zeros((planes, height, width), dtype=np.uint8)
    if layout == "row":
        row_size = stride * planes
        raw = np.frombuffer(data, dtype=np.uint8, count=height * row_size,
                            offset=offset).reshape(height, row_size)
        for p in range(planes):
            plane = raw[:, p * stride:(p + 1) * stride]
            unpacked = np.unpackbits(plane, axis=1, bitorder="big")
            bits[p] = unpacked[:, :width]
    elif layout == "plane":
        plane_size = stride * height
        for p in range(planes):
            raw = np.frombuffer(data, dtype=np.uint8, count=plane_size,
                                offset=offset + p * plane_size).reshape(
                                    height, stride)
            unpacked = np.unpackbits(raw, axis=1, bitorder="big")
            bits[p] = unpacked[:, :width]
    else:
        raise ValueError(f"disposition inconnue : {layout}")
    return bits


def decode_indices(data: bytes, offset: int, width: int, height: int,
                   planes: int, layout: str = "row",
                   stride: int | None = None) -> np.ndarray:
    """Décode un bitmap planaire en grille d'indices ``(height, width)``."""
    if width < 1 or height < 1:
        raise ValueError("largeur et hauteur doivent être positives")
    if not 1 <= planes <= 8:
        raise ValueError("le nombre de plans doit être compris entre 1 et 8")
    stride = stride or (width + 7) // 8
    bits = _plane_rows(data, offset, width, height, planes, layout, stride)
    index = np.zeros((height, width), dtype=np.int32)
    for p in range(planes):
        index |= bits[p].astype(np.int32) << p
    return index


def plane_density(data: bytes, offset: int, width: int, height: int,
                  planes: int, layout: str = "row",
                  stride: int | None = None) -> list[float]:
    """Fraction de bits à 1 dans chaque plan (0 = plan vide)."""
    stride = stride or (width + 7) // 8
    bits = _plane_rows(data, offset, width, height, planes, layout, stride)
    return [float(bits[p].mean()) for p in range(planes)]


def render_screen(data: bytes, offset: int, width: int, height: int,
                  planes: int, layout: str = "row",
                  stride: int | None = None,
                  palette: Palette | None = None,
                  transparent: int | None = 0) -> Image:
    """Rend un bitmap planaire en image indexée RGBA."""
    index = decode_indices(data, offset, width, height, planes, layout, stride)
    pal = palette or DEFAULT_PALETTE
    needed = 1 << planes
    if len(pal) < needed:
        pal = Palette(pal.extended(needed), pal.name, pal.transparent)
    colors = [pal.rgba(i) for i in range(max(len(pal), 1))]
    if transparent is not None and transparent < len(colors):
        r, g, b, _ = colors[transparent]
        colors[transparent] = (r, g, b, 0)
    return Image.from_indexed(index, colors)


def detect_padding(index: np.ndarray, min_width: int = 32) -> tuple[int, float]:
    """Détecte la largeur utile d'une image dans un bitmap plus large.

    Renvoie ``(largeur_utile, force_du_pic)``.  La force est le rapport entre
    la discontinuité à la frontière et la discontinuité médiane : au-delà de
    3, le bourrage est net.
    """
    if index.shape[1] < min_width + 2:
        return index.shape[1], 0.0
    diff = np.abs(np.diff(index.astype(np.int16), axis=1)).mean(axis=0)
    if diff.size == 0:
        return index.shape[1], 0.0
    median = float(np.median(diff)) or 1e-6
    # Le bourrage de fin de ligne est une zone vide : la dernière colonne
    # qui contient de l'encre donne directement la largeur utile.
    used = np.flatnonzero(index.any(axis=0))
    if used.size:
        content = int(used[-1]) + 1
        if min_width <= content < index.shape[1]:
            return content, float(diff[content - 1]) / median
    # Repli : plus forte discontinuité, à condition qu'elle soit dans la
    # moitié droite de l'image (un bourrage est en fin de ligne).
    search = diff[:max(1, diff.size - 1)]
    position = int(np.argmax(search)) + 1
    peak = float(search[position - 1])
    if position < max(min_width, index.shape[1] // 2):
        return index.shape[1], 0.0
    return position, peak / median


def _coherence(index: np.ndarray) -> float:
    """Fraction de pixels identiques à leur voisin (horizontal et vertical)."""
    if index.size == 0:
        return 0.0
    horizontal = (index[:, 1:] == index[:, :-1]).mean() if index.shape[1] > 1 else 0.0
    vertical = (index[1:, :] == index[:-1, :]).mean() if index.shape[0] > 1 else 0.0
    return float((horizontal + vertical) / 2.0)


def detect_geometry(data: bytes, start: int = 0, end: int | None = None,
                    width: int = 0, height: int = 256,
                    planes: int = 0, layout: str = "",
                    step: int = 32, limit: int = 8,
                    min_score: float = 0.55,
                    budget: float = 20.0) -> list[ScreenCandidate]:
    """Cherche des bitmaps planaires cohérents dans un binaire.

    Sans largeur ni nombre de plans imposés, essaie les combinaisons usuelles
    (256/288/320/352/384 colonnes, 3 à 6 plans, les deux dispositions) et
    classe les candidats par cohérence de voisinage.  Un vrai bitmap obtient
    0,8 à 0,95 ; du code ou du bruit reste autour de 0,03.
    """
    end = len(data) if end is None else min(end, len(data))
    deadline = time.monotonic() + budget if budget > 0 else None
    widths = (width,) if width else COMMON_WIDTHS
    planes_list = (planes,) if planes else (3, 4, 5, 6)
    layouts = (layout,) if layout else LAYOUTS
    results: list[ScreenCandidate] = []

    # On note d'abord sur quelques lignes : c'est le coût qui domine un
    # balayage complet, et un vrai bitmap est déjà cohérent sur 24 lignes.
    sample_height = min(height, 24)
    for offset in range(max(0, start), max(0, end - 16), max(1, step)):
        if deadline is not None and time.monotonic() > deadline:
            break
        for w in widths:
            row_bytes = (w + 7) // 8
            for p in planes_list:
                for lay in layouts:
                    stride = row_bytes
                    needed = (height * stride * p if lay == "row"
                              else p * height * stride)
                    if offset + needed > len(data):
                        continue
                    try:
                        sample = decode_indices(data, offset, w, sample_height,
                                                p, lay, stride)
                    except ValueError:
                        continue
                    density = [float((sample >> b & 1).mean())
                               for b in range(p)]
                    if min(density) < 1e-4:
                        continue
                    score = _coherence(sample)
                    # Un vrai bitmap n'est pas presque vide : les zones de
                    # bourrage et de palette produisent des « images » très
                    # cohérentes mais à 1 % de pixels allumés.
                    nonzero = float((sample != 0).mean())
                    content = 0.7 + 0.3 * min(1.0, nonzero / 0.05)
                    density_factor = sum(
                        1.0 - min(1.0, abs(value - 0.5) * 1.8)
                        for value in density) / p
                    score *= content * (0.7 + 0.3 * density_factor)
                    if score < min_score:
                        continue
                    index = decode_indices(data, offset, w, height, p,
                                           lay, stride)
                    density = [float((index >> b & 1).mean())
                               for b in range(p)]
                    content, strength = detect_padding(index)
                    if strength < 2.0:
                        content = w
                    results.append(ScreenCandidate(
                        offset, w, height, p, lay, stride, score,
                        density, content))
    results.sort(key=lambda c: c.score, reverse=True)
    # Un même offset ne doit pas apparaître dix fois avec des variantes.
    unique: list[ScreenCandidate] = []
    seen: set[tuple[int, int]] = set()
    for candidate in results:
        key = (candidate.offset // 32, candidate.width)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
        if len(unique) >= limit:
            break
    return unique


# ---------------------------------------------------------------------------
# Palettes 0x0RGB
# ---------------------------------------------------------------------------


@dataclass
class PaletteCandidate:
    """Palette candidate trouvée dans un binaire."""

    offset: int
    count: int
    words: list[int]
    score: float
    fade: bool = False

    @property
    def palette(self) -> Palette:
        return Palette([amiga_to_rgb(w) for w in self.words],
                       f"0x0RGB@{self.offset:#x}")

    def as_dict(self) -> dict:
        return {
            "offset": self.offset,
            "count": self.count,
            "score": round(self.score, 4),
            "fade": self.fade,
            "colors": [[*amiga_to_rgb(w)] for w in self.words],
        }


def read_palette(data: bytes, offset: int, count: int = 32) -> Palette:
    """Lit ``count`` mots ``0x0RGB`` à ``offset``."""
    if offset < 0 or offset + count * 2 > len(data):
        raise ValueError("palette hors du fichier")
    words = [int.from_bytes(data[offset + 2 * i:offset + 2 * i + 2], "big")
             for i in range(count)]
    return Palette([amiga_to_rgb(w) for w in words], f"0x0RGB@{offset:#x}")


def _palette_score(words: list[int]) -> tuple[float, bool]:
    if not words or words[0] != 0:
        return 0.0, False
    distinct = len(set(words))
    # Les palettes réelles répètent parfois une couleur (transparence, noir
    # de fond) : on exige un quart de valeurs distinctes, pas la moitié.
    if distinct < max(4, len(words) // 4):
        return 0.0, False
    # Une palette de fondu est majoritairement très sombre : on mesure la
    # luminosité moyenne plutôt qu'un seuil par composante.
    brightness = sum(((w >> 8) & 0xF) + ((w >> 4) & 0xF) + (w & 0xF)
                     for w in words) / (len(words) * 45.0)
    fade = brightness < 0.20
    # Les motifs de registres copper (0x00E0..0x01BE) ne sont pas des couleurs.
    registers = sum(1 for w in words if 0x00E0 <= w <= 0x01BE)
    score = distinct / len(words)
    if fade:
        score *= 0.35
    if registers > len(words) // 4:
        score *= 0.2
    return score, fade


def scan_palettes(data: bytes, count: int = 32, limit: int = 16,
                  start: int = 0, end: int | None = None,
                  include_fades: bool = False) -> list[PaletteCandidate]:
    """Cherche des palettes ``0x0RGB`` dans un binaire.

    Critères : premier mot noir, valeurs distinctes, absence de motifs de
    registres copper.  Les tables de fondu sont reconnues et écartées par
    défaut (elles produisent des images « à moitié noires » qui semblent
    valides).
    """
    end = len(data) if end is None else min(end, len(data))
    start = max(0, start)
    start -= start % 2
    found: list[PaletteCandidate] = []
    # Lecture vectorisée des mots 0x0RGB : le balayage octet par octet coûtait
    # plusieurs secondes sur un mégaoctet.
    usable = (end - start) // 2 * 2
    if usable < count * 2:
        return []
    words_all = np.frombuffer(data, dtype=">u2", count=usable // 2,
                              offset=start)
    if words_all.size < count:
        return []
    windows = np.lib.stride_tricks.sliding_window_view(words_all, count)
    valid = ((windows <= 0x0FFF).all(axis=1)
             & (windows[:, 0] == 0)
             & (np.count_nonzero(windows, axis=1) >= max(4, count // 4)))
    for index in np.flatnonzero(valid):
        words = windows[index].tolist()
        score, fade = _palette_score(words)
        if score <= 0:
            continue
        if fade and not include_fades:
            continue
        found.append(PaletteCandidate(start + int(index) * 2,
                                      count, words, score, fade))
    found.sort(key=lambda c: c.score, reverse=True)
    unique: list[PaletteCandidate] = []
    seen: set[int] = set()
    for candidate in found:
        bucket = candidate.offset // 32
        if bucket in seen:
            continue
        seen.add(bucket)
        unique.append(candidate)
        if len(unique) >= limit:
            break
    return unique


def palette_continuity(index: np.ndarray, palette: Palette) -> float:
    """Note une palette par continuité des couleurs entre pixels voisins.

    Plus la note est basse, plus l'image est cohérente : un dégradé correct
    donne des voisins proches, une mauvaise palette fait sauter les couleurs.
    """
    colors = np.asarray([palette[i] for i in range(len(palette))],
                        dtype=np.float32)
    safe = np.clip(index, 0, len(colors) - 1)
    rgb = colors[safe]
    horizontal = np.abs(np.diff(rgb, axis=1)).mean() if rgb.shape[1] > 1 else 0.0
    vertical = np.abs(np.diff(rgb, axis=0)).mean() if rgb.shape[0] > 1 else 0.0
    return float((horizontal + vertical) / 2.0)


def best_palette(index: np.ndarray,
                 candidates: list[PaletteCandidate]) -> tuple[PaletteCandidate | None, float]:
    """Choisit la palette qui rend l'image la plus continue."""
    best: PaletteCandidate | None = None
    best_score = float("inf")
    for candidate in candidates:
        if len(candidate.words) <= int(index.max(initial=0)):
            continue
        score = palette_continuity(index, candidate.palette)
        if score < best_score:
            best, best_score = candidate, score
    return best, best_score
