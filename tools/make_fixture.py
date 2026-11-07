#!/usr/bin/env python3
"""Fabrique des données de test : encodeur Kosinski et ROM synthétique.

Le décodeur Kosinski est validé par les vecteurs officiels de Sega Retro.
Pour vérifier la **chaîne complète** — balayage, décompression, découpage — il
manquait l'autre moitié : un encodeur. Ce script en fournit un, volontairement
simple (recherche gloutonne des répétitions), suffisant pour fabriquer des
fixtures et prouver que l'outil retrouve une banque réellement compressée.

    python tools/make_fixture.py --tiles 128 --output /tmp/rom.bin
"""

from __future__ import annotations

import argparse
import random
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Encodeur Kosinski
# ---------------------------------------------------------------------------


class _Writer:
    """Accumule les bits de description et les octets de données."""

    def __init__(self) -> None:
        self.commands: list[tuple[list[int], bytes]] = []

    def add(self, bits: list[int], data: bytes) -> None:
        self.commands.append((bits, data))


def kosinski_encode(data: bytes, window: int = 8192) -> bytes:
    """Encode ``data`` en Kosinski (recherche gloutonne).

    Format : un mot de description de 16 bits (lu bit 0 d'abord) précède les
    données qu'il décrit. ``1`` = octet littéral, ``01`` = copie longue
    (distance sur 13 bits, longueur), ``00xx`` = copie courte (distance sur
    8 bits, longueur 2 à 5).
    """
    index: dict[bytes, list[int]] = {}
    for position in range(len(data) - 1):
        index.setdefault(data[position:position + 2], []).append(position)

    commands: list[tuple[list[int], bytes]] = []
    position = 0
    size = len(data)
    while position < size:
        best_length = 0
        best_distance = 0
        if position + 2 <= size:
            for candidate in reversed(index.get(data[position:position + 2], [])[-64:]):
                distance = position - candidate
                if distance <= 0 or distance > window:
                    continue
                length = 0
                while (position + length < size and length < 256
                       and data[candidate + length] == data[position + length]):
                    length += 1
                if length > best_length:
                    best_length, best_distance = length, distance
                    if length >= 256:
                        break
        # une copie de longueur 2 n'existe que sous la forme courte, donc
        # seulement à moins de 256 octets ; au-delà, on écrit un littéral
        usable = best_length >= 3 or (best_length == 2 and best_distance <= 256)
        if usable:
            commands.append(_match(best_distance, best_length))
            position += best_length
        else:
            commands.append(([1], data[position:position + 1]))
            position += 1

    # terminaison : copie longue de longueur nulle (troisième octet à 0)
    commands.append(([0, 1], bytes([0x00, 0x00, 0x00])))

    # Émission bit à bit : le décodeur lit les bits sans discontinuité, donc
    # un mot de description doit être écrit **dès** que le seizième bit est
    # atteint, même au milieu d'une commande. Les octets de données d'une
    # commande viennent après le mot de description qui contient ses bits.
    out = bytearray()
    group_bits: list[int] = []
    group_data = bytearray()

    def flush() -> None:
        word = 0
        for bit_index, bit in enumerate(group_bits):
            word |= (bit & 1) << bit_index
        out.extend(struct.pack("<H", word))
        out.extend(group_data)
        group_bits.clear()
        group_data.clear()

    for bits, payload in commands:
        placed = False
        for index, bit in enumerate(bits):
            group_bits.append(bit)
            if len(group_bits) == 16:
                if index == len(bits) - 1:
                    # la commande se termine sur ce mot : ses données lui
                    # appartiennent, il faut les écrire avant de vider
                    group_data.extend(payload)
                    placed = True
                flush()
        if not placed:
            group_data.extend(payload)
    if group_bits or group_data:
        flush()
    return bytes(out)


def _match(distance: int, length: int) -> tuple[list[int], bytes]:
    """Commande de copie : longue si possible, courte pour les cas courts."""
    if 2 <= length <= 5 and distance <= 256:
        # copie courte : 00 + 2 bits de longueur, distance sur 8 bits
        count_bits = length - 2
        return ([0, 0, (count_bits >> 1) & 1, count_bits & 1],
                bytes([256 - distance]))
    # le décodeur fait « valeur - 8192 » : on lui donne donc 8192 - distance
    value = (8192 - distance) & 0x1FFF
    first = value & 0xFF
    second = ((value >> 8) & 0x1F) << 3
    if length <= 9:
        second |= length - 2
        return ([0, 1], bytes([first, second]))
    return ([0, 1], bytes([first, second, (length - 1) & 0xFF]))


# ---------------------------------------------------------------------------
# Données de test
# ---------------------------------------------------------------------------


def sprite_tiles(count: int, seed: int = 1, size: int = 8) -> bytes:
    """Banque de tuiles « sprite » : aplats, marges, formes pleines."""
    rng = random.Random(seed)
    out = bytearray()
    for _ in range(count):
        tile = [[0] * size for _ in range(size)]
        for _ in range(rng.randint(1, 3)):
            x0, y0 = rng.randint(0, size - 2), rng.randint(0, size - 2)
            w = rng.randint(1, size - x0)
            h = rng.randint(1, size - y0)
            color = rng.randint(1, 7)
            for y in range(y0, y0 + h):
                for x in range(x0, x0 + w):
                    tile[y][x] = color
        if rng.random() < 0.7:
            tile[0] = [0] * size
            for row in tile:
                row[0] = 0
        for y in range(size):
            for plane in range(4):
                byte = 0
                for x in range(size):
                    if (tile[y][x] >> plane) & 1:
                        byte |= 0x80 >> x
                out.append(byte)
    return bytes(out)


def synthetic_rom(tiles: bytes, offset: int = 0x10000,
                  seed: int = 7) -> tuple[bytes, int]:
    """ROM de bruit contenant une banque compressée à ``offset``."""
    rng = random.Random(seed)
    payload = kosinski_encode(tiles)
    rom = bytearray(rng.randrange(256) for _ in range(offset))
    rom.extend(payload)
    rom.extend(rng.randrange(256) for _ in range(0x8000))
    return bytes(rom), len(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiles", type=int, default=128)
    parser.add_argument("--offset", type=lambda value: int(value, 0), default=0x10000)
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)

    tiles = sprite_tiles(args.tiles)
    rom, compressed = synthetic_rom(tiles, args.offset)
    print(f"tuiles : {len(tiles)} octets ({args.tiles} tuiles)")
    print(f"compressé : {compressed} octets "
          f"({len(tiles) / max(1, compressed):.1f}:1)")
    if args.output:
        Path(args.output).write_bytes(rom)
        print(f"ROM écrite : {args.output} ({len(rom)} octets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
