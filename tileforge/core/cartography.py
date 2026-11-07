"""Cartographie d'une ROM : plateforme, zones et tables de pointeurs.

Avant de chercher des graphismes, il faut savoir où l'on met les pieds. Ce
module répond à trois questions :

* **Quelle machine ?** L'en-tête d'une ROM contient presque toujours une
  signature (``SEGA`` à l'offset 0x100 sur Mega Drive, ``NES\\x1A`` au début
  d'une cartouche NES, somme de contrôle valide sur SNES…).
* **Où sont les zones homogènes ?** L'entropie locale sépare le vide, les
  données structurées, le code et les blocs compressés.
* **Où sont les tables ?** Une suite de pointeurs croissants vers la ROM trahit
  une table de données — souvent le point d'entrée vers les graphismes.

Le module ne dépend ni de Qt ni de l'interface.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

#: Signatures d'en-tête connues, testées dans cet ordre.
PLATFORM_NAMES: dict[str, str] = {
    "nes": "NES / Famicom",
    "snes": "Super Nintendo",
    "megadrive": "Mega Drive / Genesis",
    "gameboy": "Game Boy",
    "mastersystem": "Master System / Game Gear",
    "lynx": "Atari Lynx",
    "unknown": "inconnue",
}

#: Seuils d'entropie (bits par octet) utilisés pour classer une zone.
EMPTY_ENTROPY = 1.0
STRUCTURED_ENTROPY = 5.0
COMPRESSED_ENTROPY = 7.2


@dataclass
class Platform:
    """Machine reconnue à partir de l'en-tête."""

    key: str
    title: str = ""
    confidence: float = 0.0
    details: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return PLATFORM_NAMES.get(self.key, self.key)

    def as_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "title": self.title,
                "confidence": round(self.confidence, 2), "details": self.details}


@dataclass
class Zone:
    """Une plage contiguë de la ROM, classée par son entropie."""

    offset: int
    size: int
    entropy: float
    kind: str

    @property
    def end(self) -> int:
        return self.offset + self.size

    def as_dict(self) -> dict:
        return {"offset": self.offset, "offset_hex": f"0x{self.offset:06X}",
                "size": self.size, "entropy": round(self.entropy, 2),
                "kind": self.kind}


@dataclass
class PointerTable:
    """Une suite de pointeurs vraisemblablement lue par le jeu."""

    offset: int
    count: int
    width: int
    big_endian: bool
    monotonic: float

    def as_dict(self) -> dict:
        return {"offset": self.offset, "offset_hex": f"0x{self.offset:06X}",
                "count": self.count, "width": self.width,
                "big_endian": self.big_endian,
                "monotonic": round(self.monotonic, 2)}


# ---------------------------------------------------------------------------
# Plateforme
# ---------------------------------------------------------------------------


def _ascii(raw: bytes) -> str:
    return raw.decode("ascii", "replace").replace("\x00", " ").strip()


def _detect_nes(data: bytes) -> Platform | None:
    if data[:4] != b"NES\x1a":
        return None
    details = {"prg_banks": data[4] if len(data) > 4 else 0,
               "chr_banks": data[5] if len(data) > 5 else 0}
    mapper = ((data[6] >> 4) & 0x0F) | (data[7] & 0xF0) if len(data) > 7 else 0
    details["mapper"] = mapper
    return Platform("nes", f"iNES, mapper {mapper}", 0.99, details)


def _detect_megadrive(data: bytes) -> Platform | None:
    if len(data) < 0x120:
        return None
    if data[0x100:0x104] != b"SEGA":
        return None
    console = _ascii(data[0x110:0x120])
    title = _ascii(data[0x120:0x150]) if len(data) > 0x150 else ""
    return Platform("megadrive", title, 0.99,
                    {"console": console, "region": _ascii(data[0x1F0:0x200])})


def _detect_gameboy(data: bytes) -> Platform | None:
    if len(data) < 0x150:
        return None
    logo = data[0x104:0x134]
    # La première moitié du logo Nintendo suffit à écarter les faux positifs.
    if logo[:8] != bytes([0xCE, 0xED, 0x66, 0x66, 0xCC, 0x0D, 0x00, 0x0B]):
        return None
    title = _ascii(data[0x134:0x144])
    cartridge = data[0x147] if len(data) > 0x147 else 0
    return Platform("gameboy", title, 0.99, {"cartridge_type": cartridge})


def _detect_mastersystem(data: bytes) -> Platform | None:
    if len(data) < 0x8000:
        return None
    if data[0x7FF0:0x7FF8] != b"TMR SEGA":
        return None
    return Platform("mastersystem", "", 0.95, {})


def _detect_snes(data: bytes) -> Platform | None:
    """L'en-tête SNES est reconnu par sa somme de contrôle complémentaire."""
    best: Platform | None = None
    for base, name in ((0x7FC0, "LoROM"), (0xFFC0, "HiROM"), (0x40FFC0, "ExHiROM")):
        if len(data) < base + 0x20:
            continue
        header = data[base:base + 0x20]
        title = _ascii(header[:21])
        if not title or sum(1 for ch in title if ch.isprintable()) < 10:
            continue
        checksum = header[0x1E] | (header[0x1F] << 8)
        complement = header[0x1C] | (header[0x1D] << 8)
        valid = (checksum ^ complement) == 0xFFFF and checksum != 0
        confidence = 0.95 if valid else 0.45
        details = {"map_mode": header[0x15], "checksum_ok": valid}
        candidate = Platform("snes", title, confidence, details)
        if best is None or candidate.confidence > best.confidence:
            best = candidate
        best.details.setdefault("layout", name)
    return best


def detect_platform(data: bytes) -> Platform:
    """Devine la machine à partir de l'en-tête ; ``unknown`` si rien ne colle."""
    for detector in (_detect_nes, _detect_megadrive, _detect_gameboy,
                     _detect_mastersystem, _detect_snes):
        found = detector(data)
        if found is not None:
            return found
    return Platform("unknown", "", 0.0)


# ---------------------------------------------------------------------------
# Entropie
# ---------------------------------------------------------------------------


def shannon_entropy(block: bytes) -> float:
    """Entropie de Shannon du bloc, en bits par octet (0 à 8)."""
    if not block:
        return 0.0
    counts = [0] * 256
    for value in block:
        counts[value] += 1
    total = len(block)
    entropy = 0.0
    for count in counts:
        if count:
            probability = count / total
            entropy -= probability * math.log2(probability)
    return entropy


def _classify(entropy: float) -> str:
    if entropy < EMPTY_ENTROPY:
        return "vide"
    if entropy < STRUCTURED_ENTROPY:
        return "données structurées"
    if entropy < COMPRESSED_ENTROPY:
        return "code probable"
    return "compressé ou aléatoire"


def entropy_profile(data: bytes, window: int = 4096, step: int | None = None) -> list[Zone]:
    """Découpe la ROM en fenêtres et calcule l'entropie de chacune."""
    step = step or window
    zones: list[Zone] = []
    for offset in range(0, max(1, len(data)), step):
        block = data[offset:offset + window]
        if not block:
            break
        zones.append(Zone(offset, len(block), shannon_entropy(block),
                          _classify(shannon_entropy(block))))
    return zones


def merge_zones(zones: list[Zone]) -> list[Zone]:
    """Regroupe les fenêtres voisines de même nature."""
    merged: list[Zone] = []
    for zone in zones:
        if merged and merged[-1].kind == zone.kind:
            merged[-1].size += zone.size
            merged[-1].entropy = (
                merged[-1].entropy * (merged[-1].size - zone.size)
                + zone.entropy * zone.size) / max(1, merged[-1].size)
        else:
            merged.append(Zone(zone.offset, zone.size, zone.entropy, zone.kind))
    return merged


# ---------------------------------------------------------------------------
# Tables de pointeurs
# ---------------------------------------------------------------------------


def _read_pointer(data: bytes, offset: int, width: int, big_endian: bool) -> int:
    raw = data[offset:offset + width]
    if len(raw) < width:
        return -1
    return int.from_bytes(raw, "big" if big_endian else "little")


def find_pointer_tables(data: bytes, min_count: int = 8,
                        max_tables: int = 24) -> list[PointerTable]:
    """Cherche des suites de pointeurs qui pointent dans la ROM.

    Un tableau de pointeurs est une suite de valeurs de 2 ou 3 octets qui
    restent dans la ROM et progressent globalement. On exige ``min_count``
    valeurs consécutives : en dessous, le hasard produit trop de faux
    positifs sur des octets quelconques.
    """
    size = len(data)
    found: list[PointerTable] = []
    for width in (2, 3):
        for big_endian in (True, False):
            for offset in range(0, max(1, size - width * min_count), width):
                values = [_read_pointer(data, offset + index * width, width, big_endian)
                          for index in range(min_count)]
                if any(value <= 0 or value >= size for value in values):
                    continue
                increasing = sum(1 for a, b in zip(values, values[1:], strict=False)
                                 if b > a)
                ratio = increasing / (min_count - 1)
                # On exige une progression stricte sur la fenêtre de départ :
                # tolérer des valeurs plates décalerait le début de la table de
                # quelques octets et ferait entrer des zéros de remplissage.
                if ratio < 1.0:
                    continue
                # on prolonge la table tant que les pointeurs restent plausibles
                count = min_count
                previous = values[-1]
                while True:
                    position = offset + count * width
                    value = _read_pointer(data, position, width, big_endian)
                    if value <= previous or value >= size:
                        break
                    previous = value
                    count += 1
                found.append(PointerTable(offset, count, width, big_endian, ratio))
    # on ne garde que les tables les plus longues, sans recouvrement
    found.sort(key=lambda table: -table.count)
    kept: list[PointerTable] = []
    for table in found:
        end = table.offset + table.count * table.width
        if any(table.offset < other.offset + other.count * other.width
               and end > other.offset for other in kept):
            continue
        kept.append(table)
        if len(kept) >= max_tables:
            break
    kept.sort(key=lambda table: table.offset)
    return kept


def structured_ranges(data: bytes, window: int = 4096,
                      min_size: int = 512) -> list[tuple[int, int]]:
    """Plages de la ROM classées « données structurées ».

    C'est là que se trouvent les banques de tuiles non compressées : le code
    et les blocs compressés sont plus entropiques, le vide l'est moins. Balayer
    ces plages plutôt que la ROM entière va plusieurs fois plus vite et produit
    beaucoup moins de faux positifs.
    """
    zones = merge_zones(entropy_profile(data, window))
    ranges = []
    for zone in zones:
        if zone.kind != "données structurées":
            continue
        start = zone.offset
        end = min(len(data), zone.end)
        if end - start >= min_size:
            ranges.append((start, end))
    return ranges


def table_blocks(data: bytes, tables: list[PointerTable],
                 min_size: int = 256, max_size: int = 1 << 16) -> list[dict]:
    """Blocs délimités par les pointeurs consécutifs d'une table.

    Chaque pointeur ouvre un bloc qui va jusqu'au suivant : c'est ainsi qu'un
    jeu découpe souvent ses données (une banque de sprites, une table de
    niveaux…). Les tailles aberrantes sont écartées.
    """
    seen: set[tuple[int, int]] = set()
    for table in tables:
        values = []
        for index in range(table.count):
            position = table.offset + index * table.width
            raw = data[position:position + table.width]
            if len(raw) < table.width:
                break
            values.append(int.from_bytes(raw, "big" if table.big_endian else "little"))
        for index, start in enumerate(values):
            if start <= 0 or start >= len(data):
                continue
            end = values[index + 1] if index + 1 < len(values) else min(len(data), start + max_size)
            size = end - start
            if min_size <= size <= max_size and start + size <= len(data):
                seen.add((start, size))
    return [{"offset": offset, "size": size} for offset, size in sorted(seen)]


# ---------------------------------------------------------------------------
# Rapport complet
# ---------------------------------------------------------------------------


def cartography(data: bytes, window: int = 4096) -> dict:
    """Résumé structuré d'une ROM : plateforme, zones, tables de pointeurs."""
    platform = detect_platform(data)
    zones = merge_zones(entropy_profile(data, window))
    tables = find_pointer_tables(data)
    blocks = table_blocks(data, tables)
    compressed = sum(zone.size for zone in zones if zone.kind.startswith("compressé"))
    structured = sum(zone.size for zone in zones if zone.kind == "données structurées")
    return {
        "size": len(data),
        "platform": platform.as_dict(),
        "zones": [zone.as_dict() for zone in zones],
        "pointer_tables": [table.as_dict() for table in tables],
        "blocks": blocks[:64],
        "summary": {
            "zones": len(zones),
            "structured_bytes": structured,
            "compressed_bytes": compressed,
            "pointer_tables": len(tables),
            "blocks": len(blocks),
        },
    }


def describe(report: dict) -> str:
    """Version texte du rapport, pour la console et les journaux."""
    platform = report["platform"]
    lines = [
        f"Taille : {report['size']} octets",
        f"Plateforme : {platform['name']}"
        + (f" — « {platform['title']} »" if platform["title"] else "")
        + (f" (confiance {platform['confidence']:.0%})" if platform["confidence"] else ""),
        f"Zones : {report['summary']['zones']} · "
        f"{report['summary']['structured_bytes']} octets structurés · "
        f"{report['summary']['compressed_bytes']} octets compressés",
        f"Tables de pointeurs : {report['summary']['pointer_tables']}",
    ]
    for table in report["pointer_tables"][:5]:
        lines.append(f"  0x{table['offset']:06X} — {table['count']} pointeurs "
                     f"de {table['width']} octets")
    return "\n".join(lines)


def unpack_header(data: bytes, offset: int, width: int, big_endian: bool) -> int:
    """Lit un entier de ``width`` octets ; utilitaire public pour les tests."""
    raw = data[offset:offset + width]
    if len(raw) < width:
        raise ValueError("lecture hors des données")
    return struct.unpack(">H" if big_endian else "<H", raw)[0] if width == 2 else \
        int.from_bytes(raw, "big" if big_endian else "little")
