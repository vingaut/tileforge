"""Moteur de recherche de graphismes dans un fichier binaire.

Le moteur répond à une question simple : *où y a-t-il des tuiles dans ce
fichier ?* Il balaye les données brutes et les blocs compressés, note chaque
candidat avec :mod:`tileforge.core.score`, délimite les zones trouvées et
respecte un budget de temps.

Trois principes ont guidé la conception.

**Le temps est borné.** Un balayage de ROM ne doit jamais bloquer une interface
ni dépasser le budget demandé. Le moteur s'arrête proprement, signale la
troncature et renvoie ce qu'il a trouvé.

**Le coût est étagé.** Décompresser est bon marché, noter est cher. Les données
brutes sont d'abord balayées à grands pas, puis chaque zone retenue est affinée
au voisinage de son début ; les blocs compressés sont notés sur peu de tuiles
d'abord, en entier ensuite.

**Un candidat est cohérent.** L'offset, la taille et la note affichés
proviennent toujours de la même évaluation : une zone n'hérite jamais de la
note d'une fenêtre voisine.

Le module ne dépend ni de Qt ni de l'interface : il s'utilise en script, en
ligne de commande et via MCP.
"""

from __future__ import annotations

import multiprocessing
import os
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from . import score as scoring
from .compression import DECOMPRESSORS_BY_KEY
from .formats import FORMATS_BY_KEY, TileFormat

#: Nombre de tuiles notées lors du criblage rapide.
QUICK_TILES: int = 16

#: Note minimale pour qu'une fenêtre soit retenue au criblage.
QUICK_KEEP: float = 0.30

#: Nombre de tuiles d'une fenêtre de balayage brut.
WINDOW_TILES: int = 64

#: Pas du balayage brut, en octets (affiné ensuite autour des zones trouvées).
RAW_STEP: int = 256

#: Pas d'affinage fin, en octets.
REFINE_STEP: int = 8

#: Étendue maximale d'une zone fusionnée, en octets.
MAX_REGION: int = 1 << 16

#: Taille maximale d'un bloc décompressé, en octets.
DEFAULT_MAX_SIZE: int = 1 << 16

#: Taille de la sonde de décompression, en octets.
#:
#: Un essai à chaque offset ne peut pas décompresser des dizaines de kilo-octets :
#: sur un million d'offsets, cela représente des gigaoctets. On sonde d'abord
#: sur 4 Ko (128 tuiles, largement de quoi noter), et on ne décompresse
#: entièrement que les candidats qui ont passé le criblage. Un flux plus long
#: que la sonde échoue : c'est volontaire, un décodeur ne doit pas produire un
#: résultat partiel qui serait noté comme un vrai bloc.
PROBE_SIZE: int = 1 << 12

#: Taille minimale d'un bloc candidat, en octets.
DEFAULT_MIN_SIZE: int = 512

#: Budget de temps par défaut, en secondes.
DEFAULT_BUDGET: float = 30.0

#: Décompresseurs essayés par un balayage automatique.
#:
#: Seuls les formats qui savent dire « stop » y figurent : soit ils butent sur
#: un marqueur de fin, soit ils échouent vite. Les formats sans terminateur
#: (RLE génériques, PackBits, Saxman sans longueur) décompressent depuis
#: n'importe quel offset et ne peuvent jamais échouer : un balayage complet
#: coûterait des heures. Enigma, pour sa part, ne compresse pas des graphismes
#: mais des plans de tuiles, et coûte cher à sonder. Tous restent disponibles
#: quand on connaît l'offset.
DEFAULT_COMPRESSIONS: tuple[str, ...] = (
    "kosinski", "kosinski_moduled", "nemesis", "lz2")

#: Formats dont le décompresseur est propre à une famille de machines.
#: On ne les ajoute pas au balayage par défaut : sur des données qui ne sont
#: pas du LZ, ils peuvent décoder longtemps avant de rencontrer leur fin, ce
#: qui ralentit un balayage complet. Ils restent disponibles en choisissant le
#: décompresseur dans la liste, ou avec ``extended=True``.
FAMILY_COMPRESSIONS: dict[str, tuple[str, ...]] = {
    "snes": ("lz3",),
    "gba": ("gba_lz77",),
    "gameboy": ("gba_lz77",),
}


def compressions_for(tile_format: str, extended: bool = False) -> list[str]:
    """Décompresseurs à essayer pour un format de tuiles donné.

    Par défaut, seulement les formats rapides à écarter. ``extended=True``
    ajoute les décompresseurs de la famille (LC_LZ3 sur SNES, LZ77/LZ11 sur
    Game Boy) : ils sont corrects, mais un faux départ peut décoder longtemps
    avant de rencontrer sa fin, ce qui ralentit un balayage complet.
    """
    keys = list(DEFAULT_COMPRESSIONS)
    if extended:
        for prefix, extra in FAMILY_COMPRESSIONS.items():
            if tile_format.startswith(prefix):
                keys.extend(key for key in extra if key not in keys)
    return keys


#: Nombre maximal de candidats renvoyés.
DEFAULT_MAX_CANDIDATES: int = 200

#: Nombre maximal de blocs notés par décompresseur.
#:
#: Les formats sans marqueur de fin (RLE, PackBits) « réussissent » à tous les
#: offsets : sans plafond, le balayage noterait des centaines de milliers de
#: blocs et durerait des heures. Les vrais flux se trouvent dans les premiers
#: milliers de positions utiles ; au-delà, on arrête ce décompresseur.
DEFAULT_MAX_SCORES: int = 2500


# ---------------------------------------------------------------------------
# Résultats
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    """Un bloc de données qui ressemble à des tuiles.

    ``offset`` et ``size`` délimitent la zone trouvée ; ``score`` est la
    meilleure note observée à l'intérieur, avec ``best_offset`` pour la
    localiser précisément.
    """

    offset: int
    size: int
    score: float
    tile_format: str
    compression: str = ""
    tiles: int = 0
    best_offset: int = -1
    features: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.best_offset < 0:
            self.best_offset = self.offset

    @property
    def end(self) -> int:
        return self.offset + self.size

    def as_dict(self) -> dict:
        return {
            "offset": self.offset,
            "offset_hex": f"0x{self.offset:X}",
            "size": self.size,
            "score": round(self.score, 4),
            "tile_format": self.tile_format,
            "compression": self.compression,
            "tiles": self.tiles,
            "best_offset": self.best_offset,
        }

    def __str__(self) -> str:
        origin = self.compression or "brut"
        return (f"0x{self.offset:06X} {origin:9s} {self.size:6d} o "
                f"{self.tile_format:14s} note {self.score:.3f}")


@dataclass
class ScanReport:
    """Résultat complet d'un balayage."""

    candidates: list[Candidate] = field(default_factory=list)
    tested: int = 0
    scored: int = 0
    elapsed: float = 0.0
    budget: float = DEFAULT_BUDGET
    truncated: bool = False
    errors: int = 0
    source: str = ""

    @property
    def best(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None

    def as_dict(self, limit: int | None = None) -> dict:
        items = self.candidates if limit is None else self.candidates[:limit]
        return {
            "source": self.source,
            "tested": self.tested,
            "scored": self.scored,
            "elapsed": round(self.elapsed, 3),
            "budget": self.budget,
            "truncated": self.truncated,
            "errors": self.errors,
            "candidates": [candidate.as_dict() for candidate in items],
        }


# ---------------------------------------------------------------------------
# Crible bon marché
# ---------------------------------------------------------------------------


def quick_gate(blob: bytes) -> bool:
    """Écarte en quelques microsecondes les blocs qui ne peuvent pas être des tuiles.

    Des octets aléatoires ou du code machine utilisent presque toutes les
    valeurs possibles et contiennent peu de zéros ; une planche de tuiles a un
    fond répétitif, donc beaucoup de zéros et un alphabet réduit.
    """
    size = len(blob)
    if size < 64:
        return False
    sample = blob[:4096]
    zeros = sample.count(0) / len(sample)
    distinct = len(set(sample))
    if distinct > 200 and zeros < 0.02:
        return False
    return not (zeros < 0.005 and distinct > 120)


# ---------------------------------------------------------------------------
# Fusion des candidats voisins
# ---------------------------------------------------------------------------


def merge_candidates(candidates: list[Candidate], tolerance: int) -> list[Candidate]:
    """Fusionne les candidats qui décrivent la même zone.

    Deux fenêtres qui se chevauchent, ou séparées de moins de ``tolerance``
    octets, sont le même graphisme : on garde le mieux noté et on retient
    l'étendue totale.
    """
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda item: item.offset)
    merged: list[Candidate] = []
    for candidate in ordered:
        if merged:
            current = merged[-1]
            if (current.compression == candidate.compression
                    and candidate.offset <= current.end + tolerance):
                start = min(current.offset, candidate.offset)
                end = max(current.end, candidate.end)
                better = candidate if candidate.score > current.score else current
                merged[-1] = Candidate(
                    offset=start, size=end - start, score=better.score,
                    tile_format=better.tile_format, compression=better.compression,
                    tiles=better.tiles, best_offset=better.best_offset,
                    features=better.features)
                continue
        merged.append(candidate)
    return merged


# ---------------------------------------------------------------------------
# Balayage parallèle
# ---------------------------------------------------------------------------


def _scan_key_job(payload: dict) -> dict:
    """Balaye un décompresseur dans un processus séparé.

    Chaque processus traite une clé de compression : les décompresseurs sont
    indépendants, la répartition est donc naturelle et sans communication.
    """
    data = payload["data"]
    formats = [FORMATS_BY_KEY[key] for key in payload["formats"]
               if key in FORMATS_BY_KEY]
    if not formats:
        return {"key": payload["key"], "candidates": [], "tested": 0,
                "scored": 0, "errors": 0}
    scanner = Scanner(data, formats, [payload["key"]])
    found: list[Candidate] = []
    counters = {"tested": 0, "scored": 0, "errors": 0}
    deadline = payload.get("deadline") or (time.monotonic() + 3600.0)
    scanner.scan_compressed(
        payload["key"], start=payload["start"], end=payload["end"],
        step=payload["step"], threshold=payload["threshold"],
        max_size=payload["max_size"], min_size=payload["min_size"],
        out=found, counters=counters,
        should_stop=lambda: time.monotonic() > deadline)
    return {
        "key": payload["key"],
        "candidates": [(c.offset, c.size, c.score, c.tile_format,
                        c.compression, c.tiles, c.best_offset) for c in found],
        "tested": counters["tested"],
        "scored": counters["scored"],
        "errors": counters["errors"],
    }


def _scan_range_job(payload: dict) -> dict:
    """Balaye une tranche de données brutes dans un processus séparé."""
    data = payload["data"]
    formats = [FORMATS_BY_KEY[key] for key in payload["formats"]
               if key in FORMATS_BY_KEY]
    if not formats:
        return {"candidates": [], "tested": 0, "scored": 0}
    scanner = Scanner(data, formats, ())
    found: list[Candidate] = []
    counters = {"tested": 0, "scored": 0}
    deadline = payload.get("deadline") or (time.monotonic() + 3600.0)
    scanner.scan_raw(payload["start"], payload["end"], step=payload["step"],
                     threshold=payload["threshold"], out=found,
                     counters=counters,
                     should_stop=lambda: time.monotonic() > deadline)
    return {
        "candidates": [(c.offset, c.size, c.score, c.tile_format,
                        c.compression, c.tiles, c.best_offset) for c in found],
        "tested": counters["tested"],
        "scored": counters["scored"],
    }


def _worker_count(requested: int, tasks: int) -> int:
    """Nombre de processus à lancer : au moins 1, jamais plus que de tâches."""
    if requested <= 0:
        try:
            available = os.cpu_count() or 1
        except Exception:
            available = 1
        requested = max(1, available - 1)
    return max(1, min(int(requested), tasks))


# ---------------------------------------------------------------------------
# Moteur
# ---------------------------------------------------------------------------


class Scanner:
    """Balayage d'un tampon de données à la recherche de tuiles.

    :param data: contenu du fichier.
    :param formats: un ou plusieurs formats de tuiles ; le premier sert au
        criblage, les suivants ne sont essayés que sur les candidats retenus.
    :param compressions: clés de décompresseurs à essayer, ou ``()`` pour ne
        balayer que les données brutes.
    """

    def __init__(self, data: bytes, formats: Sequence[TileFormat],
                 compressions: Iterable[str] = DEFAULT_COMPRESSIONS,
                 source: str = ""):
        if not formats:
            raise ValueError("au moins un format de tuiles est nécessaire")
        self.data = data
        self.formats = list(formats)
        self.format = self.formats[0]
        self.compressions = [key for key in compressions
                             if key in DECOMPRESSORS_BY_KEY]
        self.source = source
        self._budget_hit = False

    # -- utilitaires -------------------------------------------------------

    @property
    def tile_bytes(self) -> int:
        return max(1, int(self.format.real_bytes))

    def _tiles(self, size: int) -> int:
        return size // self.tile_bytes

    def _window(self, offset: int, tiles: int) -> bytes:
        span = tiles * self.tile_bytes
        return self.data[offset:offset + span]

    def _score_blob(self, blob: bytes, quick: bool) -> tuple[float, dict, str]:
        """Note un bloc et renvoie (note, indices, clé du format retenu)."""
        best = 0.0
        best_features: dict = {}
        best_key = self.format.key
        formats = self.formats[:1] if quick else self.formats
        max_tiles = QUICK_TILES if quick else scoring.MAX_TILES
        for fmt in formats:
            try:
                features = scoring.tile_features(blob, fmt, max_tiles=max_tiles)
            except Exception:
                continue
            if features is None:
                continue
            value = scoring.combine(scoring.features_vector(features),
                                    features["variety"])
            if value > best:
                best, best_features, best_key = value, features, fmt.key
        return best, best_features, best_key

    def _quick(self, offset: int, tiles: int = QUICK_TILES,
               max_tiles: int | None = None) -> float:
        """Note rapide d'une fenêtre ; ``max_tiles`` règle le nombre de tuiles notées.

        Par défaut on ne note que :data:`QUICK_TILES` tuiles, pour le criblage.
        La note finale d'un candidat doit, elle, être calculée sur toute la
        fenêtre : sinon un bloc dont seule une petite partie est graphique
        obtient une note que l'utilisateur ne retrouve pas à l'ouverture.
        """
        blob = self._window(offset, tiles)
        if len(blob) < max(4, tiles // 2) * self.tile_bytes:
            return 0.0
        if max_tiles is None:
            value, _, _ = self._score_blob(blob, quick=True)
            return value
        value, _, _ = self._score_blob(blob, quick=False) if max_tiles >= 32 else self._score_blob(blob, quick=True)
        return value

    # -- affinage d'une zone brute -----------------------------------------

    def _refine(self, offset: int, radius: int, threshold: float,
                stop: Callable[[], bool] | None = None) -> int:
        """Cherche l'offset le mieux noté au voisinage d'une position grossière.

        La recherche descend par paliers (16, 4 puis 1 octet) : on obtient la
        précision d'un balayage octet par octet pour une fraction du coût.
        """
        best_offset, best_score = offset, self._quick(offset)
        low = max(0, offset - radius)
        high = min(len(self.data), offset + radius)
        step = 16
        while step >= 1:
            base = best_offset
            for position in range(max(low, base - radius), min(high, base + radius) + 1,
                                  step):
                if stop and stop():
                    return best_offset
                if position + QUICK_TILES * self.tile_bytes > len(self.data):
                    break
                value = self._quick(position)
                if value > best_score:
                    best_offset, best_score = position, value
            step //= 4
        return best_offset

    def _extend(self, offset: int, direction: int, threshold: float,
                limit: int, stop: Callable[[], bool] | None = None) -> int:
        """Recule ou avance tant que la fenêtre reste au-dessus du seuil.

        Deux passes : un pas grossier pour traverser vite une grande zone, puis
        un pas fin pour coller à la frontière exacte.
        """
        span = QUICK_TILES * self.tile_bytes
        position = offset
        for step in (2048, 256, 32):
            origin = position
            while abs(position - origin) <= limit:
                nxt = position + direction * step
                if nxt < 0 or nxt + span > len(self.data):
                    break
                if stop and stop():
                    return position
                if self._quick(nxt) < threshold:
                    break
                position = nxt
        return position

    # -- balayages ---------------------------------------------------------

    def scan_raw(self, start: int = 0, end: int | None = None,
                 step: int = RAW_STEP,
                 threshold: float = scoring.DEFAULT_THRESHOLD,
                 out: list[Candidate] | None = None,
                 counters: dict | None = None,
                 should_stop: Callable[[], bool] | None = None) -> list[Candidate]:
        """Balaye les données brutes à grands pas, puis affine chaque zone."""
        out = [] if out is None else out
        counters = {"tested": 0, "scored": 0} if counters is None else counters
        end = len(self.data) if end is None else min(end, len(self.data))
        span = WINDOW_TILES * self.tile_bytes
        min_size = max(4 * self.tile_bytes, DEFAULT_MIN_SIZE)
        if span < min_size:
            return out

        hits: list[int] = []
        for offset in range(max(0, start), max(0, end - min_size), max(self.tile_bytes, step)):
            if should_stop and should_stop():
                break
            counters["tested"] += 1
            value = self._quick(offset)
            if value < threshold:
                continue
            counters["scored"] += 1
            hits.append(offset)
        if not hits:
            return out

        # une zone = une suite de positions grossières consécutives
        regions: list[list[int]] = []
        for offset in hits:
            if regions and offset - regions[-1][-1] <= max(self.tile_bytes, step) * 2:
                regions[-1].append(offset)
            else:
                regions.append([offset])

        for region in regions:
            if should_stop and should_stop():
                break
            seed = region[0]
            refined = self._refine(seed, max(self.tile_bytes, step), threshold,
                                   stop=should_stop)
            value = self._quick(refined, WINDOW_TILES, max_tiles=scoring.MAX_TILES)
            if value < threshold:
                refined = seed
                value = self._quick(seed, WINDOW_TILES, max_tiles=scoring.MAX_TILES)
            begin = self._extend(refined, -1, threshold * 1.15,
                                 min(MAX_REGION, refined), stop=should_stop)
            finish = self._extend(refined, +1, threshold * 1.15,
                                  min(MAX_REGION, end - refined), stop=should_stop)
            finish = min(end, max(finish, refined) + span)
            size = max(min_size, finish - begin)
            size -= size % self.tile_bytes
            out.append(Candidate(
                offset=begin, size=size, score=value,
                tile_format=self.format.key, compression="",
                tiles=self._tiles(size), best_offset=refined))
        return out

    def scan_compressed(self, key: str, start: int = 0, end: int | None = None,
                        step: int = 1,
                        threshold: float = scoring.DEFAULT_THRESHOLD,
                        max_size: int = DEFAULT_MAX_SIZE,
                        min_size: int = DEFAULT_MIN_SIZE,
                        out: list[Candidate] | None = None,
                        counters: dict | None = None,
                        should_stop: Callable[[], bool] | None = None,
                        progress: Callable[[float], None] | None = None,
                        max_scores: int = DEFAULT_MAX_SCORES,
                        ) -> list[Candidate]:
        """Balaye un décompresseur, offset par offset."""
        out = [] if out is None else out
        counters = {"tested": 0, "scored": 0, "errors": 0} if counters is None else counters
        entry = DECOMPRESSORS_BY_KEY.get(key)
        if entry is None:
            return out
        end = len(self.data) if end is None else min(end, len(self.data))
        total = max(1, (end - start) // max(1, step))
        report_every = max(1, total // 100)
        for index, offset in enumerate(range(max(0, start), end, max(1, step))):
            if should_stop and should_stop():
                break
            if progress and index % report_every == 0:
                progress(index / total)
            limit = min(max_size, entry.max_size) if entry.max_size else max_size
            probe = min(limit, PROBE_SIZE)
            try:
                blob = entry.function(self.data, offset, probe)
            except Exception:
                counters["errors"] += 1
                continue
            if not blob:
                continue
            if len(blob) < min_size or len(blob) % self.tile_bytes:
                continue
            counters["tested"] += 1
            if not quick_gate(blob):
                continue
            if counters["scored"] >= max_scores:
                break
            counters["scored"] += 1
            value, features, fmt_key = self._score_blob(blob, quick=True)
            if value < min(QUICK_KEEP, threshold):
                continue
            # Le criblage est passé : on décompresse pour de bon, pour
            # connaître la taille réelle et noter le bloc entier.
            if probe < limit:
                try:
                    full = entry.function(self.data, offset, limit)
                except Exception:
                    full = b""
                if full and len(full) > len(blob):
                    blob = full
            size = len(blob)
            # Un flux qui atteint le plafond n'a pas rencontré de fin : l'offset
            # est presque sûrement faux.
            if size > max_size or (entry.max_size and size >= entry.max_size):
                continue
            if size < min_size or size % self.tile_bytes:
                continue
            refined, detailed, fmt_key = self._score_blob(blob, quick=False)
            if refined > value:
                value, features = refined, detailed
            if value < threshold:
                continue
            out.append(Candidate(
                offset=offset, size=size, score=value, tile_format=fmt_key,
                compression=key, tiles=self._tiles(size), features=features))
        return out

    # -- orchestration -----------------------------------------------------

    def _scan_raw_parallel(self, start: int, end: int, step: int,
                           threshold: float, deadline: float, workers: int,
                           progress: Callable[[float, str], None] | None,
                           ) -> tuple[list[Candidate], dict, bool]:
        """Répartit le balayage brut en tranches sur plusieurs processus."""
        span = max(RAW_STEP * 8, (end - start) // workers)
        chunks = []
        position = start
        while position < end:
            chunks.append((position, min(end, position + span)))
            position += span
        payloads = [{
            "data": self.data,
            "formats": [fmt.key for fmt in self.formats],
            "start": chunk_start,
            "end": chunk_end,
            "step": max(self.tile_bytes, RAW_STEP),
            "threshold": threshold,
            "deadline": deadline,
        } for chunk_start, chunk_end in chunks]

        candidates: list[Candidate] = []
        stats = {"tested": 0, "scored": 0}
        timed_out = False
        done = 0
        try:
            from concurrent.futures import ProcessPoolExecutor, as_completed

            context = multiprocessing.get_context("spawn")
            with ProcessPoolExecutor(max_workers=min(workers, len(payloads)),
                                     mp_context=context) as pool:
                futures = [pool.submit(_scan_range_job, payload)
                           for payload in payloads]
                for future in as_completed(
                        futures, timeout=max(0.1, deadline - time.monotonic())):
                    result = future.result()
                    for item in result["candidates"]:
                        offset, size, value, fmt_key, compression, tiles, best = item
                        candidates.append(Candidate(
                            offset=offset, size=size, score=value,
                            tile_format=fmt_key, compression=compression,
                            tiles=tiles, best_offset=best))
                    stats["tested"] += result["tested"]
                    stats["scored"] += result["scored"]
                    done += 1
                    if progress:
                        progress(done / len(payloads), "données brutes")
        except TimeoutError:
            timed_out = True
        except Exception:
            candidates = []
            stats = {"tested": 0, "scored": 0}
            self.scan_raw(start, end, step=step, threshold=threshold,
                          out=candidates, counters=stats,
                          should_stop=lambda: time.monotonic() > deadline)
        return candidates, stats, timed_out

    def _scan_compressed_parallel(self, keys: list[str], start: int, end: int,
                                  step: int, threshold: float, max_size: int,
                                  min_size: int, deadline: float, workers: int,
                                  progress: Callable[[float, str], None] | None,
                                  ) -> tuple[list[Candidate], dict, bool]:
        """Répartit les décompresseurs sur plusieurs processus.

        Renvoie (candidats, compteurs, délai dépassé). En cas d'indisponibilité
        du parallélisme, retombe silencieusement sur un balayage séquentiel :
        le résultat doit rester identique, seule la durée change.
        """
        payloads = [{
            "data": self.data,
            "formats": [fmt.key for fmt in self.formats],
            "key": key,
            "start": start,
            "end": end,
            "step": step,
            "threshold": threshold,
            "max_size": max_size,
            "min_size": min_size,
            "deadline": deadline,
        } for key in keys]

        candidates: list[Candidate] = []
        stats = {"tested": 0, "scored": 0, "errors": 0}
        timed_out = False
        done = 0
        try:
            from concurrent.futures import ProcessPoolExecutor, as_completed

            context = multiprocessing.get_context("spawn")
            with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
                futures = {pool.submit(_scan_key_job, payload): payload["key"]
                           for payload in payloads}
                for future in as_completed(futures, timeout=max(0.1, deadline - time.monotonic())):
                    key = futures[future]
                    result = future.result()
                    for item in result["candidates"]:
                        offset, size, value, fmt_key, compression, tiles, best = item
                        candidates.append(Candidate(
                            offset=offset, size=size, score=value,
                            tile_format=fmt_key, compression=compression,
                            tiles=tiles, best_offset=best))
                    stats["tested"] += result["tested"]
                    stats["scored"] += result["scored"]
                    stats["errors"] += result["errors"]
                    done += 1
                    if progress:
                        progress(done / len(payloads), DECOMPRESSORS_BY_KEY[key].name)
        except TimeoutError:
            timed_out = True
        except Exception:
            # Parallélisme indisponible (bac à sable, plateforme…) : on
            # refait le travail ici plutôt que d'échouer.
            candidates = []
            stats = {"tested": 0, "scored": 0, "errors": 0}
            timed_out = False
            for key in keys:
                if time.monotonic() > deadline:
                    timed_out = True
                    break
                self.scan_compressed(key, start, end, step=step,
                                     threshold=threshold, max_size=max_size,
                                     min_size=min_size, out=candidates,
                                     counters=stats,
                                     should_stop=lambda: time.monotonic() > deadline)
        return candidates, stats, timed_out

    def run(self, start: int = 0, end: int | None = None,
            step: int = 1, raw: bool = True, compressed: bool = True,
            threshold: float = scoring.DEFAULT_THRESHOLD,
            budget: float = DEFAULT_BUDGET,
            max_size: int = DEFAULT_MAX_SIZE,
            min_size: int = DEFAULT_MIN_SIZE,
            max_candidates: int = DEFAULT_MAX_CANDIDATES,
            workers: int = 1,
            progress: Callable[[float, str], None] | None = None,
            should_stop: Callable[[], bool] | None = None) -> ScanReport:
        """Lance le balayage complet et renvoie le rapport."""
        began = time.perf_counter()
        deadline = time.monotonic() + max(0.1, budget)
        end = len(self.data) if end is None else min(end, len(self.data))
        start = max(0, min(start, end))
        found: list[Candidate] = []
        counters = {"tested": 0, "scored": 0, "errors": 0}
        truncated = False

        def out_of_time() -> bool:
            return time.monotonic() > deadline

        def stop() -> bool:
            nonlocal truncated
            if truncated:
                return True
            if should_stop and should_stop():
                truncated = True
                return True
            if out_of_time():
                truncated = True
                return True
            return False

        # -- données brutes
        if raw and not stop():
            wanted = _worker_count(workers, 4)
            if wanted > 1 and (end - start) > 262144:
                if progress:
                    progress(0.0, "données brutes")
                candidates, stats, timed_out = self._scan_raw_parallel(
                    start, end, step=max(self.tile_bytes, RAW_STEP),
                    threshold=threshold, deadline=deadline, workers=wanted,
                    progress=progress)
                found.extend(candidates)
                counters["tested"] += stats["tested"]
                counters["scored"] += stats["scored"]
                if timed_out:
                    truncated = True
            else:
                if progress:
                    progress(0.0, "données brutes")
                self.scan_raw(start, end, step=max(self.tile_bytes, RAW_STEP),
                              threshold=threshold, out=found, counters=counters,
                              should_stop=stop)

        # -- blocs compressés
        keys = [key for key in self.compressions if key in DECOMPRESSORS_BY_KEY]
        if compressed and keys and not stop():
            wanted = _worker_count(workers, len(keys))
            if wanted > 1 and len(keys) > 1:
                candidates, stats, timed_out = self._scan_compressed_parallel(
                    keys, start, end, step, threshold, max_size, min_size,
                    deadline, wanted, progress)
                found.extend(candidates)
                counters["tested"] += stats["tested"]
                counters["scored"] += stats["scored"]
                counters["errors"] += stats["errors"]
                if timed_out:
                    truncated = True
            else:
                for index, key in enumerate(keys):
                    if stop():
                        break
                    entry = DECOMPRESSORS_BY_KEY[key]
                    base, span = index / len(keys), 1.0 / len(keys)
                    if progress:
                        progress(base, entry.name)

                    def sub_progress(fraction: float, _base=base, _span=span,
                                     _name=entry.name) -> None:
                        if progress:
                            progress(_base + _span * fraction, _name)

                    self.scan_compressed(key, start, end, step=step,
                                         threshold=threshold, max_size=max_size,
                                         min_size=min_size, out=found,
                                         counters=counters, should_stop=stop,
                                         progress=sub_progress)
        if progress:
            progress(1.0, "")

        merged = merge_candidates(found, max(self.tile_bytes, REFINE_STEP))
        merged.sort(key=lambda item: (-item.score, -item.size))
        if len(merged) > max_candidates:
            merged = merged[:max_candidates]
        return ScanReport(candidates=merged, tested=counters["tested"],
                          scored=counters["scored"],
                          elapsed=time.perf_counter() - began, budget=budget,
                          truncated=truncated, errors=counters["errors"],
                          source=self.source)


# ---------------------------------------------------------------------------
# Raccourcis
# ---------------------------------------------------------------------------


def scan_bytes(data: bytes, tile_format: str | TileFormat = "snes_4bpp",
               compressions: Iterable[str] = DEFAULT_COMPRESSIONS,
               extra_formats: Iterable[str] = (), source: str = "",
               **options) -> ScanReport:
    """Balaye un tampon ; ``tile_format`` est une clé ou un :class:`TileFormat`."""
    primary = (FORMATS_BY_KEY[tile_format] if isinstance(tile_format, str)
               else tile_format)
    formats = [primary] + [FORMATS_BY_KEY[key] for key in extra_formats
                           if key in FORMATS_BY_KEY]
    return Scanner(data, formats, compressions, source=source).run(**options)


def scan_ranges(data: bytes, tile_format: str | TileFormat,
                ranges: list[tuple[int, int]], **options) -> ScanReport:
    """Balaye plusieurs plages et fusionne les rapports.

    Sert à concentrer la recherche sur les zones repérées par la cartographie
    plutôt que sur toute la ROM.
    """
    reports = []
    for start, end in ranges:
        sub = dict(options)
        sub["start"] = start
        sub["end"] = end
        reports.append(scan_bytes(data, tile_format, source=sub.pop("source", ""),
                                  **sub))
    candidates: list[Candidate] = []
    for report in reports:
        candidates.extend(report.candidates)
    candidates.sort(key=lambda item: (-item.score, -item.size))
    return ScanReport(
        candidates=candidates,
        tested=sum(report.tested for report in reports),
        scored=sum(report.scored for report in reports),
        elapsed=sum(report.elapsed for report in reports),
        budget=options.get("budget", DEFAULT_BUDGET),
        truncated=any(report.truncated for report in reports),
        errors=sum(report.errors for report in reports),
        source=options.get("source", ""))


def scan_file(path: str, tile_format: str | TileFormat = "snes_4bpp",
              compressions: Iterable[str] = DEFAULT_COMPRESSIONS,
              extra_formats: Iterable[str] = (), **options) -> ScanReport:
    """Balaye un fichier."""
    with open(path, "rb") as handle:
        data = handle.read()
    return scan_bytes(data, tile_format, compressions, extra_formats,
                      source=path, **options)
