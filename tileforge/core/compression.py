"""Décompression des formats graphiques des consoles 8/16 bits.

Les jeux SNES et Mega Drive stockent rarement leurs tuiles en clair : elles
sont compressées dans la ROM. Ce module décompresse les formats les plus
courants pour que TileForge puisse ensuite les découper normalement.

Formats fournis
---------------
``kosinski``
    LZSS de Sega (Sonic 2/3, QuackShot…). Spécification et exemples de test
    d'après `Sega Retro <https://segaretro.org/Kosinski_compression>`_.
``nemesis``
    Codage entropique de Sega pour les graphismes Mega Drive (Sonic, Golden
    Axe, Streets of Rage…). D'après
    `Sega Retro <https://segaretro.org/Nemesis_compression>`_.
``snes_lzss``
    LZSS « 0x100 » de Super Nintendo, drapeaux par huit et longueur étendue.
``lz3``
    LC_LZ3, format Nintendo des hacks Super Mario World et, selon SnesLab,
    de Pokémon Or/Argent ; d'après `SnesLab <https://sneslab.net/wiki/LZ3>`_.
``gba_lz77``
    LZ77/LZ11 de Game Boy Advance et Nintendo DS (en-tête ``0x10``/``0x11``),
    d'après GBATEK.
``lz2``
    LC_LZ2, format Nintendo (Super Mario World, Yoshi's Island…). D'après
    `SnesLab <https://sneslab.net/wiki/LC_LZ2>`_.
``zlib`` / ``gzip``
    Quelques homebrews et romhacks stockent les graphismes en DEFLATE.

Ajouter un format
-----------------
Écrire une fonction ``(data, offset) -> bytes`` puis l'enregistrer ::

    register("mon_format", mon_format, "Mon format")

Le dialogue « Banque brute » la proposera automatiquement.
"""

from __future__ import annotations

import gzip
import zlib
from dataclasses import dataclass


class DecompressionError(Exception):
    """Données invalides ou format inattendu."""


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def _byte(data, index: int) -> int:
    if index < 0 or index >= len(data):
        raise DecompressionError("fin de flux inattendue")
    return data[index]


class _BitReader:
    """Lecteur de bits MSB-first avec fenêtre extensible."""

    def __init__(self, data: bytes, offset: int = 0):
        self.data = data
        self.pos = offset
        self.buffer = 0
        self.count = 0

    def _fill(self, needed: int) -> None:
        while self.count < needed:
            if self.pos >= len(self.data):
                # fin de flux : on complète par des zéros, les décodeurs
                # s'arrêtent sur un critère de taille
                self.buffer = (self.buffer << 8) & 0xFFFFFFFFFFFF
                self.count += 8
                self.pos += 1
                if self.count > 64:
                    raise DecompressionError("flux trop court")
                continue
            self.buffer = (self.buffer << 8) | self.data[self.pos]
            self.pos += 1
            self.count += 8

    def peek(self, n: int) -> int:
        self._fill(n)
        return (self.buffer >> (self.count - n)) & ((1 << n) - 1)

    def read(self, n: int) -> int:
        value = self.peek(n)
        self.count -= n
        self.buffer &= (1 << self.count) - 1
        return value

    @property
    def consumed(self) -> int:
        """Position en octets correspondant aux bits consommés."""
        return self.pos - self.count // 8


# ---------------------------------------------------------------------------
# Kosinski (Mega Drive)
# ---------------------------------------------------------------------------


def _kosinski_at(data: bytes, offset: int = 0,
                 max_size: int = 1 << 24) -> tuple[bytes, int]:
    """Décompresse un flux Kosinski et renvoie aussi la position de fin.

    Le champ de description fait 16 bits lus bit 0 d'abord ; un 1 annonce un
    octet littéral, ``01`` une copie par dictionnaire, ``00xx`` une copie
    courte de ``xx + 2`` octets.  Le pointeur de lecture est partagé : quand
    les 16 bits de description sont épuisés, les deux octets suivants du flux
    forment la description suivante, et les données reprennent après.

    La position de fin est nécessaire au format « modulé », où plusieurs
    modules compressés se suivent sans séparateur.
    """
    if offset + 2 > len(data):
        raise DecompressionError("flux Kosinski tronqué")
    pos = offset
    state = {"desc": 0, "bits": 0}

    def next_description() -> None:
        nonlocal pos
        if pos + 2 > len(data):
            raise DecompressionError("description Kosinski tronquée")
        state["desc"] = data[pos] | (data[pos + 1] << 8)
        state["bits"] = 16
        pos += 2

    def bit() -> int:
        if state["bits"] == 0:
            next_description()
        value = state["desc"] & 1
        state["desc"] >>= 1
        state["bits"] -= 1
        return value

    out = bytearray()

    def copy_from(distance: int, length: int) -> None:
        start = len(out) + distance
        if start < 0 or start >= len(out):
            raise DecompressionError("référence arrière invalide")
        for k in range(length):
            out.append(out[start + k])

    next_description()
    while True:
        if len(out) > max_size:
            raise DecompressionError("taille décompressée excessive")
        if bit():
            if pos >= len(data):
                raise DecompressionError("octet littéral hors flux")
            out.append(data[pos])
            pos += 1
            continue
        if bit():
            if pos + 2 > len(data):
                raise DecompressionError("copie Kosinski tronquée")
            first, second = data[pos], data[pos + 1]
            pos += 2
            distance = (((second & 0xF8) << 5) | first) - 8192
            count_bits = second & 0x07
            if count_bits:
                copy_from(distance, count_bits + 2)
            else:
                if pos >= len(data):
                    raise DecompressionError("copie longue tronquée")
                third = data[pos]
                pos += 1
                if third == 0:
                    break
                if third == 1:
                    state["bits"] = 0      # nouvelle description
                    continue
                copy_from(distance, third + 1)
        else:
            count = (bit() << 1) | bit() + 0
            count = count + 2
            if pos >= len(data):
                raise DecompressionError("copie courte tronquée")
            distance = data[pos] - 256
            pos += 1
            copy_from(distance, count)
    return bytes(out), pos


def kosinski(data: bytes, offset: int = 0, max_size: int = 1 << 24) -> bytes:
    """Décompresse un flux Kosinski (Mega Drive)."""
    return _kosinski_at(data, offset, max_size)[0]


def kosinski_moduled(data: bytes, offset: int = 0, max_size: int = 1 << 24,
                     decoder=None) -> bytes:
    """Décompresse des données Kosinski « modulées » (KosM).

    L'en-tête de 16 bits donne le nombre de modules moins un (4 bits de poids
    fort) et la taille décompressée du dernier module (12 bits). Tous les
    modules sauf le dernier font 0x1000 octets une fois décompressés ; ils se
    suivent dans le flux sans séparateur, leur taille compressée se déduisant
    de la position de fin du module précédent.

    Spécification : https://segaretro.org/Moduled_compression
    """
    if offset + 2 > len(data):
        raise DecompressionError("en-tête Moduled tronqué")
    header = (data[offset] << 8) | data[offset + 1]
    modules = (header >> 12) + 1
    last_size = header & 0x0FFF
    if last_size == 0:
        raise DecompressionError("taille de dernier module nulle")
    decode = decoder or _kosinski_at
    position = offset + 2
    out = bytearray()
    for index in range(modules):
        wanted = 0x1000 if index < modules - 1 else last_size
        if len(out) + wanted > max_size:
            raise DecompressionError("taille décompressée excessive")
        chunk, position = decode(data, position, wanted)
        if len(chunk) != wanted:
            raise DecompressionError(f"module {index} incomplet")
        out.extend(chunk)
    return bytes(out)


# ---------------------------------------------------------------------------
# Nemesis (Mega Drive)
# ---------------------------------------------------------------------------


def nemesis(data: bytes, offset: int = 0, max_patterns: int = 8192) -> bytes:
    """Décompresse un flux Nemesis (tuiles 8×8 en 4 bits par pixel).

    Le premier mot donne le nombre de motifs ; son bit de poids fort indique le
    mode XOR (chaque ligne est le OU exclusif de la précédente).
    """
    if offset + 2 > len(data):
        raise DecompressionError("en-tête Nemesis tronqué")
    header = (data[offset] << 8) | data[offset + 1]
    xor_mode = bool(header & 0x8000)
    patterns = header & 0x7FFF
    if patterns > max_patterns:
        raise DecompressionError("nombre de motifs absurde")
    pos = offset + 2

    # -- table des codes ----------------------------------------------------
    table: list[tuple[int, int, int] | None] = [None] * 256
    try:
        current = data[pos]
    except IndexError:
        raise DecompressionError("table de codes tronquée") from None
    pos += 1
    while True:
        if current == 0xFF:
            break
        palette = current & 0x0F
        while True:
            current = _byte(data, pos)
            pos += 1
            if current >= 0x80:
                break
            repeat = (current >> 4) & 0x07
            length = current & 0x0F
            if length == 0:
                raise DecompressionError("longueur de code nulle")
            code = _byte(data, pos)
            pos += 1
            if length == 8:
                table[code] = (8, palette, repeat)
            else:
                shift = 8 - length
                base = code << shift
                for k in range(1 << shift):
                    if base + k < 256:
                        table[base + k] = (length, palette, repeat)
        if current == 0xFF:
            break

    # -- flux de données ----------------------------------------------------
    reader = _BitReader(data, pos)
    out = bytearray()
    previous = 0
    rows = patterns * 4
    for _ in range(rows):
        value = 0
        written = 0
        while written < 8:
            if reader.peek(6) == 0b111111:
                reader.read(6)
                payload = reader.read(7)
                pixel = payload & 0x0F
                repeat = (payload >> 4) & 0x07
            else:
                index = reader.peek(8)
                entry = table[index]
                if entry is None:
                    raise DecompressionError(
                        f"code inconnu dans le flux (index 0x{index:02X})")
                length, pixel, repeat = entry
                reader.read(length)
            count = repeat + 1
            if written + count > 8:
                count = 8 - written
            for _k in range(count):
                value = ((value << 4) | pixel) & 0xFFFFFFFF
                written += 1
            if count <= 0:
                raise DecompressionError("flux Nemesis incohérent")
        if xor_mode:
            value ^= previous
            previous = value
        out += value.to_bytes(4, "big")
        if len(out) > max_patterns * 32:
            raise DecompressionError("taille décompressée excessive")
    return bytes(out)


# ---------------------------------------------------------------------------
# LC_LZ2 (Super Nintendo)
# ---------------------------------------------------------------------------


def lz2(data: bytes, offset: int = 0, max_size: int = 1 << 24) -> bytes:
    """Décompresse un flux LC_LZ2 (format Nintendo).

    Chaque bloc commence par un octet ``CCCLLLLL`` : trois bits de commande et
    une longueur moins un. ``0xFF`` termine le flux.
    """
    pos = offset
    out = bytearray()
    while True:
        if pos >= len(data):
            raise DecompressionError("flux LZ2 tronqué")
        header = data[pos]
        pos += 1
        if header == 0xFF:
            break
        command = header >> 5
        length = (header & 0x1F) + 1
        if command == 7:
            command = (header >> 2) & 0x07
            length = (((header & 0x03) << 8) | _byte(data, pos)) + 1
            pos += 1

        if command == 0:            # copie directe
            if pos + length > len(data):
                raise DecompressionError("copie directe hors flux")
            out += data[pos:pos + length]
            pos += length
        elif command == 1:          # remplissage d'octet
            out += bytes([_byte(data, pos)]) * length
            pos += 1
        elif command == 2:          # remplissage de mot
            first, second = _byte(data, pos), _byte(data, pos + 1)
            pos += 2
            for k in range(length):
                out.append(first if k % 2 == 0 else second)
        elif command == 3:          # remplissage croissant
            value = _byte(data, pos)
            pos += 1
            for k in range(length):
                out.append((value + k) & 0xFF)
        elif command == 4:          # répétition depuis une adresse absolue
            address = (_byte(data, pos) << 8) | _byte(data, pos + 1)
            pos += 2
            if address >= len(out):
                raise DecompressionError("répétition LZ2 hors tampon")
            for k in range(length):
                out.append(out[address + k])
        else:
            raise DecompressionError(f"commande LZ2 inutilisée ({command})")
        if len(out) > max_size:
            raise DecompressionError("taille décompressée excessive")
    return bytes(out)


# ---------------------------------------------------------------------------
# LZ77 / LZ11 (Game Boy Advance, Nintendo DS)
# ---------------------------------------------------------------------------


def gba_lz77(data: bytes, offset: int = 0, max_size: int = 1 << 24) -> bytes:
    """Décompresse un flux LZ77 de GBA/NDS (types ``0x10`` et ``0x11``).

    L'en-tête fait quatre octets : le type (``0x10`` = LZ10, ``0x11`` = LZ11),
    puis la taille décompressée sur 24 bits, petit-boutiste. Un octet de
    drapeaux précède chaque groupe de huit jetons, **bit 7 en premier** :
    ``1`` = référence arrière de deux à quatre octets, ``0`` = octet littéral.
    (C'est la convention du BIOS GBA, vérifiée sur l'implémentation de mGBA ;
    plusieurs documents l'inversent.)

    LZ10 code une longueur de 3 à 18 (quatre bits) et une distance de 1 à
    4096 (douze bits). LZ11 ajoute deux formes longues, la première jusqu'à
    272 octets, la seconde jusqu'à 65 552. Les préfixes ``LZ77`` et ``CMPR``
    de certains fichiers Nintendo DS sont acceptés.

    Référence : GBATEK, « LZSS Decompression », et les SWI ``0x11``/``0x12``
    du BIOS GBA. Contrairement à une idée répandue, ``0x11`` n'est pas une
    variante de l'en-tête GBA : c'est le type LZ11 des fichiers NDS.
    """
    if offset + 1 > len(data):
        raise DecompressionError("flux LZ77 vide")
    if data[offset:offset + 4] in (b"LZ77", b"CMPR"):
        offset += 4
    if offset + 4 > len(data):
        raise DecompressionError("en-tête LZ77 tronqué")
    kind = data[offset]
    if kind not in (0x10, 0x11):
        raise DecompressionError(f"en-tête LZ77 inconnu (0x{kind:02X})")
    size = data[offset + 1] | (data[offset + 2] << 8) | (data[offset + 3] << 16)
    if size == 0:
        return b""
    if size > max_size:
        raise DecompressionError("taille LZ77 annoncée excessive")

    pos = offset + 4
    out = bytearray()
    flags = 0
    remaining = 0
    while len(out) < size:
        if remaining == 0:
            flags = _byte(data, pos)
            pos += 1
            remaining = 8
        remaining -= 1
        if not flags & 0x80:
            out.append(_byte(data, pos))
            pos += 1
        else:
            first = _byte(data, pos)
            second = _byte(data, pos + 1)
            pos += 2
            if kind == 0x10:
                length = (first >> 4) + 3
                distance = (((first & 0x0F) << 8) | second) + 1
            else:
                nibble = first >> 4
                if nibble == 0:
                    length = 0x11 + ((first & 0x0F) << 4) + (second >> 4)
                    third = _byte(data, pos)
                    pos += 1
                    distance = (((second & 0x0F) << 8) | third) + 1
                elif nibble == 1:
                    third = _byte(data, pos)
                    fourth = _byte(data, pos + 1)
                    pos += 2
                    length = (0x111 + ((first & 0x0F) << 12)
                              + (second << 4) + (third >> 4))
                    distance = (((third & 0x0F) << 8) | fourth) + 1
                else:
                    length = nibble + 1
                    distance = (((first & 0x0F) << 8) | second) + 1
            start = len(out) - distance
            if start < 0:
                raise DecompressionError("référence LZ77 hors tampon")
            # Une copie peut se chevaucher : on lit octet par octet.
            for index in range(length):
                if len(out) >= size:
                    break
                out.append(out[start + index])
        flags = (flags << 1) & 0xFF
    return bytes(out)


# ---------------------------------------------------------------------------
# LC_LZ3 (Super Nintendo)
# ---------------------------------------------------------------------------


def lz3(data: bytes, offset: int = 0, max_size: int = 1 << 24) -> bytes:
    """Décompresse un flux LC_LZ3 (Super Nintendo).

    Le format reprend les commandes de LC_LZ2 et les étend : remplissage de
    zéros à la place du remplissage croissant, répétitions relatives sur un
    octet (bit 7 posé, distance de 1 à 128), répétitions à l'envers, copies
    dont les octets sont inversés bit à bit, et en-tête long sur dix bits.
    ``0xFF`` termine le flux ; il n'y a pas de taille annoncée.

    Référence : `SnesLab, LZ3 <https://sneslab.net/wiki/LZ3>`_ et le
    décompresseur de ``SMW-Editor/snes-squish`` (``src/lib.rs``).
    """
    pos = offset
    out = bytearray()
    while True:
        if pos >= len(data):
            raise DecompressionError("flux LZ3 tronqué")
        header = data[pos]
        pos += 1
        if header == 0xFF:
            break
        command = header >> 5
        length = (header & 0x1F) + 1
        if command == 7:
            command = (header >> 2) & 0x07
            length = (((header & 0x03) << 8) | _byte(data, pos)) + 1
            pos += 1

        if command == 0:                      # copie directe
            if pos + length > len(data):
                raise DecompressionError("copie directe LZ3 hors flux")
            out += data[pos:pos + length]
            pos += length
        elif command == 1:                    # remplissage d'octet
            out += bytes([_byte(data, pos)]) * length
            pos += 1
        elif command == 2:                    # remplissage de mot
            first, second = _byte(data, pos), _byte(data, pos + 1)
            pos += 2
            for index in range(length):
                out.append(first if index % 2 == 0 else second)
        elif command == 3:                    # remplissage de zéros
            out += bytes(length)
        elif command in (4, 5, 6):            # répétitions
            raw = _byte(data, pos)
            pos += 1
            if raw & 0x80:
                address = len(out) - ((raw & 0x7F) + 1)
            else:
                address = (raw << 8) | _byte(data, pos)
                pos += 1
            if not 0 <= address < len(out):
                raise DecompressionError("répétition LZ3 hors tampon")
            if command == 6:
                if address - length + 1 < 0:
                    raise DecompressionError("répétition LZ3 à l'envers hors tampon")
                for index in range(length):
                    out.append(out[address - index])
            else:
                for index in range(length):
                    source = address + index
                    if source >= len(out):
                        raise DecompressionError("répétition LZ3 hors tampon")
                    value = out[source]
                    out.append(_flip_bits(value) if command == 5 else value)
        else:
            raise DecompressionError(f"commande LZ3 inconnue ({command})")
        if len(out) > max_size:
            raise DecompressionError("taille décompressée excessive")
    return bytes(out)


# ---------------------------------------------------------------------------
# Saxman (Mega Drive)
# ---------------------------------------------------------------------------


def saxman(data: bytes, offset: int = 0, max_size: int = 1 << 24,
           compressed_size: int | None = None) -> bytes:
    """Décompresse un flux Saxman (LZSS de Sonic the Hedgehog 2).

    Un octet de description est lu **bit 0 d'abord** : un 1 annonce un octet
    littéral, un 0 une référence arrière de deux octets. Contrairement au LZSS
    d'Okumura, une référence qui pointe avant le début du tampon produit des
    zéros (le « zero fill »).

    Spécification : https://segaretro.org/Saxman_compression
    """
    end = len(data) if compressed_size is None else min(len(data), offset + compressed_size)
    if offset >= end:
        raise DecompressionError("flux Saxman vide")
    pos = offset
    out = bytearray()
    description = 0
    bits = 0
    while pos < end and len(out) < max_size:
        if bits == 0:
            description = data[pos]
            pos += 1
            bits = 8
        literal = description & 1
        description >>= 1
        bits -= 1
        if literal:
            if pos >= end:
                break
            out.append(data[pos])
            pos += 1
            continue
        if pos + 2 > end:
            break
        low, high = data[pos], data[pos + 1]
        pos += 2
        length = (high & 0x0F) + 3
        value = low | ((high & 0xF0) << 4)
        base = (value + 0x12) & 0xFFF
        destination = len(out)
        source = ((base - destination) & 0xFFF) + destination - 0x1000
        if source < 0 or source > destination:
            out.extend(bytes(length))
        else:
            for k in range(length):
                out.append(out[source + k])
    if len(out) > max_size:
        raise DecompressionError("taille décompressée excessive")
    return bytes(out)


def saxman_with_length(data: bytes, offset: int = 0,
                       max_size: int = 1 << 24) -> bytes:
    """Saxman précédé de la longueur des données compressées (16 bits LE)."""
    if offset + 2 > len(data):
        raise DecompressionError("en-tête Saxman tronqué")
    size = data[offset] | (data[offset + 1] << 8)
    if size == 0:
        raise DecompressionError("longueur Saxman nulle")
    return saxman(data, offset + 2, max_size, compressed_size=size)


# ---------------------------------------------------------------------------
# Enigma (Mega Drive)
# ---------------------------------------------------------------------------


def enigma(data: bytes, offset: int = 0, max_size: int = 1 << 24,
           start_tile: int = 0) -> bytes:
    """Décompresse un flux Enigma (RLE de plans de tuiles).

    En-tête de 6 octets : largeur des valeurs en ligne, champ de bits de rendu,
    mot incrémental, mot littéral. Suit une liste d'ordres lus bit à bit.

    Spécification : https://segaretro.org/Enigma_compression
    """
    if offset + 6 > len(data):
        raise DecompressionError("en-tête Enigma tronqué")
    value_bits = data[offset]
    render = data[offset + 1]
    incremental = (data[offset + 2] << 8) | data[offset + 3]
    literal = (data[offset + 4] << 8) | data[offset + 5]
    if not 1 <= value_bits <= 16:
        raise DecompressionError(f"largeur Enigma invalide ({value_bits})")

    # Bits de rendu présents dans l'en-tête, du plus haut au plus bas : le
    # premier bit du champ en ligne correspond au plus haut de ces bits.
    render_positions = [bit for bit in range(7, -1, -1) if render & (1 << bit)]
    reader = _BitReader(data, offset + 6)
    out = bytearray()

    def put(word: int) -> None:
        out.extend(((word + start_tile) & 0xFFFF).to_bytes(2, "big"))

    def read_inline() -> int:
        flags = reader.read(len(render_positions)) if render_positions else 0
        word = reader.read(value_bits)
        for index, position in enumerate(render_positions):
            if (flags >> (len(render_positions) - 1 - index)) & 1:
                word |= 1 << (11 + position)
        return word

    while len(out) < max_size:
        first = reader.read(1)
        kind = 4 | reader.read(2) if first else reader.read(1)
        count = reader.read(4)
        if kind == 0:                       # mot incrémental
            word = incremental
            for _ in range(count + 1):
                put(word)
                word = (word + 1) & 0xFFFF
        elif kind == 1:                     # mot littéral
            for _ in range(count + 1):
                put(literal)
        elif kind == 4:                     # valeur en ligne
            word = read_inline()
            for _ in range(count + 1):
                put(word)
        elif kind == 5:                     # valeur en ligne croissante
            word = read_inline()
            for _ in range(count + 1):
                put(word)
                word = (word + 1) & 0xFFFF
        elif kind == 6:                     # valeur en ligne décroissante
            word = read_inline()
            for _ in range(count + 1):
                put(word)
                word = (word - 1) & 0xFFFF
        else:                               # 7 : fin ou suite de valeurs
            if count == 0x0F:
                return bytes(out)
            for _ in range(count + 1):
                put(read_inline())
        if reader.pos > len(data) + 2:
            raise DecompressionError("flux Enigma tronqué")
    raise DecompressionError("taille décompressée excessive")


# ---------------------------------------------------------------------------
# Comper (Mega Drive)
# ---------------------------------------------------------------------------


def comper(data: bytes, offset: int = 0, max_size: int = 1 << 24) -> bytes:
    """Décompresse un flux Comper (LZSS sur mots de 16 bits).

    Un champ de description de 16 bits (gros-boutiste, bit de poids fort
    d'abord) précède les données ; un 0 annonce un mot littéral, un 1 une
    référence arrière de deux octets (distance, longueur). Une longueur nulle
    termine le flux.

    Référence : implémentation ``comper`` de mdcomp (flamewing).
    """
    pos = offset
    out = bytearray()
    description = 0
    mask = 0
    bits_left = 0
    while True:
        if bits_left == 0:
            if pos + 2 > len(data):
                break
            description = (data[pos] << 8) | data[pos + 1]
            pos += 2
            mask = 0x8000
            bits_left = 16
        literal = not (description & mask)
        mask >>= 1
        bits_left -= 1
        if literal:
            if pos + 2 > len(data):
                raise DecompressionError("mot Comper tronqué")
            out += data[pos:pos + 2]
            pos += 2
            if len(out) > max_size:
                raise DecompressionError("taille décompressée excessive")
            continue
        if pos + 2 > len(data):
            raise DecompressionError("référence Comper tronquée")
        distance = (0x100 - data[pos]) * 2
        length = data[pos + 1]
        pos += 2
        if length == 0:
            break
        for _ in range(length + 1):
            start = len(out) - distance
            if start < 0:
                raise DecompressionError("référence Comper hors tampon")
            out += out[start:start + 2]
            if len(out) > max_size:
                raise DecompressionError("taille décompressée excessive")
    return bytes(out)


# ---------------------------------------------------------------------------
# LZSS Technosoft (Thunder Force IV)
# ---------------------------------------------------------------------------


def technosoft_lzss(data: bytes, offset: int = 0, max_size: int = 1 << 22) -> bytes:
    """Décompresse un flux LZSS Technosoft (Thunder Force IV, 1992).

    Le flux commence par un mot d'indicateurs de 16 bits (petit-boutiste),
    consommé bit 0 d'abord. Quand les 16 bits sont épuisés, le mot suivant est
    lu au fil du flux, juste avant la donnée qu'il décrit.

    - ``1`` : octet littéral ;
    - ``0 1`` : copie longue, distance 13 bits (1 à 8192), longueur 2 à 9 ou
      étendue sur un octet (0 = fin, 1 = saut) ;
    - ``0 0`` : copie courte, longueur 2 à 5, distance 1 à 256.

    Source : routine 68000 en ``0x000EBA`` de la ROM, appelée par le chargeur
    de stage ``0x0040AC``. Le conteneur qui l'accompagne porte le nombre de
    flux en ``+1`` et leurs offsets 32 bits gros-boutistes en ``+2``.
    """
    out = bytearray()
    pos = offset
    if pos + 1 >= len(data):
        raise DecompressionError("flux Technosoft tronqué")
    flag = data[pos] | (data[pos + 1] << 8)
    pos += 2
    bits = 16

    def bit() -> int:
        nonlocal flag, pos, bits
        value = flag & 1
        flag >>= 1
        bits -= 1
        if bits == 0:
            if pos + 1 >= len(data):
                raise DecompressionError("flux Technosoft tronqué")
            flag = data[pos] | (data[pos + 1] << 8)
            pos += 2
            bits = 16
        return value

    while True:
        if bit():
            if pos >= len(data):
                raise DecompressionError("littéral Technosoft hors flux")
            out.append(data[pos])
            pos += 1
            continue
        if bit() == 0:
            length = ((bit() << 1) | bit()) + 2
            if pos >= len(data):
                raise DecompressionError("copie courte Technosoft tronquée")
            distance = 256 - data[pos]
            pos += 1
        else:
            if pos + 1 >= len(data):
                raise DecompressionError("copie longue Technosoft tronquée")
            low, high = data[pos], data[pos + 1]
            pos += 2
            distance = 0x10000 - (0xE000 | ((high >> 3) << 8) | low)
            if high & 7:
                length = (high & 7) + 2
            else:
                if pos >= len(data):
                    raise DecompressionError("longueur Technosoft tronquée")
                count = data[pos]
                pos += 1
                if count in (0, 1):
                    return bytes(out)
                length = count + 1
        if distance > len(out):
            raise DecompressionError("référence Technosoft hors tampon")
        for _ in range(length):
            out.append(out[-distance])
        if len(out) > max_size:
            raise DecompressionError("taille décompressée excessive")


# ---------------------------------------------------------------------------
# Sonic RLE (Mega Drive)
# ---------------------------------------------------------------------------


def sonic_rle(data: bytes, offset: int = 0, max_size: int = 1 << 24) -> bytes:
    """Décompresse un flux « Sonic RLE » (moteur de Sonic 1/2).

    En-tête de 16 bits (gros-boutiste) donnant la taille décompressée, puis un
    flux où deux octets identiques consécutifs annoncent une répétition : le
    troisième octet donne le nombre de copies supplémentaires.

    Référence : implémentation ``snkrle`` de mdcomp (flamewing), elle-même
    d'après snkenjoi.
    """
    if offset + 2 > len(data):
        raise DecompressionError("en-tête Sonic RLE tronqué")
    size = (data[offset] << 8) | data[offset + 1]
    if size == 0:
        return b""
    if size > max_size:
        raise DecompressionError("taille Sonic RLE excessive")
    pos = offset + 2
    out = bytearray()
    current = _byte(data, pos)
    pos += 1
    out.append(current)
    remaining = size - 1
    while remaining > 0:
        value = _byte(data, pos)
        pos += 1
        out.append(value)
        remaining -= 1
        if current != value:
            current = value
            continue
        count = _byte(data, pos)
        pos += 1
        out.extend(bytes([value]) * count)
        remaining -= count
        if count == 255 and remaining > 0:
            # Une répétition plus longue que 257 octets est découpée : le
            # premier octet du segment suivant appartient encore à la série.
            current = _byte(data, pos)
            pos += 1
            out.append(current)
            remaining -= 1
    return bytes(out)


# ---------------------------------------------------------------------------
# LZSS SNES (0x100)
# ---------------------------------------------------------------------------


def snes_lzss(data: bytes, offset: int = 0,
              max_size: int = 1 << 24) -> bytes:
    """Décompresse un flux LZSS « 0x100 » de Super Nintendo.

    Un octet de drapeaux précède chaque groupe de huit jetons, bit 0 en
    premier : ``1`` = octet littéral, ``0`` = référence arrière de deux
    octets. La distance va jusqu'à 4096, la longueur de 3 à 17, et le code
    ``1111`` de longueur annonce un octet supplémentaire (longueur 18 à 273).

    Format utilisé par de nombreux jeux SNES pour les plans de tuiles.
    Référence : ``map_lz.h`` de ``gingerbeardman/snes-lzss``.
    """
    pos = offset
    out = bytearray()
    while pos < len(data) and len(out) < max_size:
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if pos >= len(data) or len(out) >= max_size:
                return bytes(out)
            if flags & (1 << bit):
                out.append(data[pos])
                pos += 1
                continue
            if pos + 2 > len(data):
                return bytes(out)
            low, high = data[pos], data[pos + 1]
            pos += 2
            # b1 = quartet haut de la longueur | quartet bas de (distance - 1)
            distance = (((high & 0x0F) << 8) | low) + 1
            length = (high >> 4) + 3
            if (high >> 4) == 0x0F:
                if pos >= len(data):
                    raise DecompressionError("longueur LZSS SNES tronquée")
                length = 18 + data[pos]
                pos += 1
            start = len(out) - distance
            if start < 0:
                raise DecompressionError("référence LZSS SNES hors tampon")
            for index in range(length):
                out.append(out[start + index])
    return bytes(out)


# ---------------------------------------------------------------------------
# LZ de Pokémon Crystal (Game Boy)
# ---------------------------------------------------------------------------


def _flip_bits(value: int) -> int:
    result = 0
    for bit in range(8):
        result |= ((value >> bit) & 1) << (7 - bit)
    return result


def pokecrystal_lz(data: bytes, offset: int = 0,
                   max_size: int = 1 << 24) -> bytes:
    """Décompresse un flux LZ de Pokémon Crystal (Game Boy).

    Un octet de commande donne trois bits de type et cinq bits de longueur
    moins un. Le type 7 (``LZ_LONG``) étend la longueur à dix bits ; les
    autres types couvrent les littéraux, la répétition d'un octet, l'alternance
    de deux octets, les zéros, et trois copies arrière (normale, bits
    inversés, à l'envers).

    Référence : décompresseur de ``pret/pokecrystal`` (``tools/lzcompress.c``),
    lui-même issu de ``lzcomp``.

    Attention : le flux ne porte **aucune longueur**. Sur des données qui ne
    sont pas du LZ de Pokémon, le décodeur produit un résultat arbitraire au
    lieu d'échouer. Ce format n'est donc pas utilisé par le balayage
    automatique : il faut connaître l'offset.
    """
    pos = offset
    out = bytearray()
    while pos < len(data):
        byte = data[pos]
        pos += 1
        if byte == 0xFF:
            break
        command = byte >> 5
        length = (byte & 0x1F) + 1
        if command == 7:
            if pos >= len(data):
                raise DecompressionError("commande longue tronquée")
            extra = data[pos]
            pos += 1
            command = ((byte & 0x1F) >> 2)
            length = ((((byte & 0x1F) & 0x03) << 8) | extra) + 1

        if command == 0:                       # littéraux
            if pos + length > len(data):
                raise DecompressionError("littéraux tronqués")
            out += data[pos:pos + length]
            pos += length
        elif command == 1:                     # répétition d'un octet
            if pos >= len(data):
                raise DecompressionError("octet manquant")
            out.extend(bytes([data[pos]]) * length)
            pos += 1
        elif command == 2:                     # alternance de deux octets
            if pos + 2 > len(data):
                raise DecompressionError("octets manquants")
            first, second = data[pos], data[pos + 1]
            pos += 2
            for index in range(length):
                out.append(first if index % 2 == 0 else second)
        elif command == 3:                     # zéros
            out.extend(bytes(length))
        elif command in (4, 5, 6):             # copies arrière
            if pos >= len(data):
                raise DecompressionError("décalage manquant")
            raw = data[pos]
            pos += 1
            if raw & 0x80:
                distance = -((raw & 0x7F) + 1)
            else:
                if pos >= len(data):
                    raise DecompressionError("décalage tronqué")
                distance = (raw << 8) | data[pos]
                pos += 1
            base = (len(out) if distance < 0 else 0) + distance
            for index in range(length):
                source = base - index if command == 6 else base + index
                if not 0 <= source < len(out):
                    raise DecompressionError("copie arrière hors tampon")
                value = out[source]
                out.append(_flip_bits(value) if command == 5 else value)
        else:
            raise DecompressionError(f"commande inconnue ({command})")
        if len(out) > max_size:
            raise DecompressionError("taille décompressée excessive")
    return bytes(out)


# ---------------------------------------------------------------------------
# Formats génériques (PackBits, RLE)
# ---------------------------------------------------------------------------


def packbits(data: bytes, offset: int = 0, max_size: int = 1 << 24) -> bytes:
    """Décompresse du PackBits (Apple II, Macintosh, CPC, Amiga).

    Un octet de contrôle ``n`` : ``0..127`` copie ``n + 1`` octets littéraux,
    ``129..255`` répète l'octet suivant ``257 - n`` fois, ``128`` ne fait rien.
    """
    out = bytearray()
    pos = offset
    while pos < len(data) and len(out) < max_size:
        control = data[pos]
        pos += 1
        if control < 128:
            chunk = data[pos:pos + control + 1]
            out.extend(chunk)
            pos += control + 1
        elif control > 128:
            if pos >= len(data):
                break
            out.extend(bytes([data[pos]]) * (257 - control))
            pos += 1
    return bytes(out)


def rle_pairs(data: bytes, offset: int = 0, max_size: int = 1 << 24) -> bytes:
    """RLE par paires ``[valeur][compte]`` jusqu'à la fin du flux.

    Convention fréquente sur 8 bits (Thomson, MSX, CPC) ; il n'y a pas
    d'en-tête, la fin du flux fait foi.
    """
    out = bytearray()
    pos = offset
    while pos + 1 < len(data) and len(out) < max_size:
        value, count = data[pos], data[pos + 1]
        pos += 2
        out.extend(bytes([value]) * count)
    return bytes(out)


def rle_flagged(data: bytes, offset: int = 0, max_size: int = 1 << 24) -> bytes:
    """RLE à octet de contrôle : bit 7 = répétition, sinon littéraux.

    ``count = (octet & 0x7F) + 1`` ; si le bit 7 est posé, l'octet suivant est
    répété ``count`` fois, sinon ``count`` octets littéraux suivent.
    """
    out = bytearray()
    pos = offset
    while pos < len(data) and len(out) < max_size:
        control = data[pos]
        pos += 1
        count = (control & 0x7F) + 1
        if control & 0x80:
            if pos >= len(data):
                break
            out.extend(bytes([data[pos]]) * count)
            pos += 1
        else:
            chunk = data[pos:pos + count]
            out.extend(chunk)
            pos += len(chunk)
    return bytes(out)


# ---------------------------------------------------------------------------
# DEFLATE
# ---------------------------------------------------------------------------


def zlib_stream(data: bytes, offset: int = 0, max_size: int = 1 << 24) -> bytes:
    try:
        return zlib.decompress(data[offset:offset + max_size * 2])
    except Exception as exc:
        raise DecompressionError(f"flux zlib invalide : {exc}") from exc


def gzip_stream(data: bytes, offset: int = 0, max_size: int = 1 << 24) -> bytes:
    try:
        return gzip.decompress(data[offset:offset + max_size * 2])
    except Exception as exc:
        raise DecompressionError(f"flux gzip invalide : {exc}") from exc


# ---------------------------------------------------------------------------
# Imploder et RNC (Amiga)
# ---------------------------------------------------------------------------


def _imploder(data: bytes, offset: int = 0) -> bytes:
    from .imploder import decompress as _explode
    return _explode(data, offset)


def _rnc(data: bytes, offset: int = 0) -> bytes:
    from .rnc import decompress as _unpack
    return _unpack(data, offset)


# ---------------------------------------------------------------------------
# Registre
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decompressor:
    key: str
    name: str
    function: object
    machine: str = ""
    notes: str = ""
    #: Taille de sortie au-delà de laquelle le format n'a plus de sens.
    #: 0 signifie « pas de limite propre » : la limite du balayage s'applique.
    max_size: int = 0


DECOMPRESSORS: list[Decompressor] = [
    Decompressor("kosinski", "Kosinski (Mega Drive)", kosinski, "Mega Drive",
                 "LZSS de Sega : Sonic 2/3, QuackShot, Phantasy Star IV…"),
    Decompressor("nemesis", "Nemesis (Mega Drive)", nemesis, "Mega Drive",
                 "Graphismes Sega : Sonic, Golden Axe, Streets of Rage…"),
    Decompressor("kosinski_moduled", "Kosinski modulé (Mega Drive)",
                 kosinski_moduled, "Mega Drive",
                 "Kosinski découpé en modules de 4 Ko : Sonic 3 & Knuckles."),
    Decompressor("saxman", "Saxman (Mega Drive)", saxman, "Mega Drive",
                 "LZSS de Sonic 2 ; une référence avant le tampon donne des zéros."),
    Decompressor("saxman_len", "Saxman avec longueur (Mega Drive)",
                 saxman_with_length, "Mega Drive",
                 "Saxman précédé de la taille des données compressées."),
    Decompressor("enigma", "Enigma (Mega Drive)", enigma, "Mega Drive",
                 "RLE de plans de tuiles : Sonic, Golden Axe, Chaotix.",
                 max_size=16384),
    Decompressor("snes_lzss", "LZSS SNES (0x100)", snes_lzss, "SNES",
                 "Drapeaux par groupe de huit, distance 12 bits, longueur 4 bits."),
    Decompressor("lz3", "LC_LZ3 (Super Nintendo)", lz3, "SNES",
                 "Commandes LZ2 étendues : zéros, répétitions relatives, "
                 "inversées et longues. Pokémon Or/Argent, hacks SMW."),
    Decompressor("gba_lz77", "LZ77 / LZ11 (GBA, NDS)", gba_lz77,
                 "Game Boy Advance",
                 "En-tête 0x10 ou 0x11 et taille sur 24 bits ; littéraux et "
                 "copies arrière. BIOS GBA, fichiers NDS."),
    Decompressor("lz2", "LC_LZ2 (Super Nintendo)", lz2, "SNES",
                 "Format Nintendo : Super Mario World, Yoshi's Island…"),
    Decompressor("comper", "Comper (Mega Drive)", comper, "Mega Drive",
                 "LZSS sur mots de 16 bits, champ de description de 16 bits."),
    Decompressor("sonic_rle", "Sonic RLE (Mega Drive)", sonic_rle, "Mega Drive",
                 "Répétitions annoncées par deux octets identiques : Sonic 1/2."),
    Decompressor("pokecrystal_lz", "LZ de Pokémon Crystal (Game Boy)",
                 pokecrystal_lz, "Game Boy",
                 "Littéraux, répétitions, alternances et copies arrière "
                 "inversées : graphismes de Pokémon Crystal."),
    Decompressor("technosoft_lzss", "LZSS Technosoft (Mega Drive)",
                 technosoft_lzss, "Mega Drive",
                 "Thunder Force IV : drapeaux de 16 bits entrelacés, copies "
                 "courtes 2-5 et longues 13 bits."),
    Decompressor("packbits", "PackBits", packbits, "",
                 "Apple II, Macintosh, Amstrad CPC, Amiga."),
    Decompressor("rle_pairs", "RLE valeur/compte", rle_pairs, "",
                 "Paires [valeur][compte] jusqu'à la fin du flux."),
    Decompressor("rle_flagged", "RLE à octet de contrôle", rle_flagged, "",
                 "Bit 7 posé : répétition ; sinon littéraux."),
    Decompressor("imploder", "Imploder (Amiga)", _imploder,
                 "Amiga",
                 "Dix signatures (IMP!, ATN!, BDPI, CHFI, Dupa, EDAM, FLT!, "
                 "M.H., PARA, RDC9), bloc compressé en fin de fichier et "
                 "décompression à rebours. Project-X, Team17."),
    Decompressor("rnc", "RNC ProPack (Amiga, Atari ST, Mega Drive)", _rnc,
                 "Amiga",
                 "Rob Northen Computing, méthodes 1 et 2 ; fichiers "
                 "chiffrés refusés sans clé."),
    Decompressor("zlib", "zlib / DEFLATE", zlib_stream, "",
                 "Quelques homebrews et romhacks."),
    Decompressor("gzip", "gzip", gzip_stream, "", "Archive gzip."),
]

DECOMPRESSORS_BY_KEY: dict[str, Decompressor] = {d.key: d for d in DECOMPRESSORS}


def register(key: str, function, name: str = "", machine: str = "",
             notes: str = "") -> None:
    """Ajoute un décompresseur au registre."""
    entry = Decompressor(key, name or key, function, machine, notes)
    DECOMPRESSORS.append(entry)
    DECOMPRESSORS_BY_KEY[key] = entry


def decompress(key: str, data: bytes, offset: int = 0) -> bytes:
    """Décompresse ``data[offset:]`` avec le format demandé."""
    entry = DECOMPRESSORS_BY_KEY.get(key)
    if entry is None:
        raise DecompressionError(f"format de compression inconnu : {key}")
    return entry.function(data, offset)


def graphics_score(data: bytes, fmt, max_tiles: int = 96) -> float:
    """Note de 0 à 1 : ces octets ressemblent-ils à des graphismes ?

    Conservé pour compatibilité : le modèle vit désormais dans
    :mod:`tileforge.core.score`, calibré sur un corpus étiqueté.
    """
    from .score import score as _score
    return _score(data, fmt, max_tiles=max_tiles)


def looks_like_tiles(data: bytes, tile_bytes: int = 32) -> bool:
    """Heuristique : la sortie ressemble-t-elle à une suite de tuiles ?"""
    if len(data) < tile_bytes:
        return False
    if len(data) % tile_bytes != 0:
        return False
    sample = data[: min(len(data), tile_bytes * 64)]
    distinct = len(set(sample))
    if distinct < 3:
        return False
    # une tuile 4bpp ne contient pas que des zéros ni des octets aléatoires
    zeros = sample.count(0)
    return zeros < len(sample) * 0.95


def detect(data: bytes, offset: int = 0, tile_bytes: int = 32,
           max_size: int = 1 << 21) -> list[tuple[str, int]]:
    """Essaie tous les formats et renvoie ceux qui produisent des tuiles.

    Renvoie une liste ``(clé, taille décompressée)`` triée par vraisemblance.
    """
    found: list[tuple[str, int]] = []
    for entry in DECOMPRESSORS:
        try:
            result = entry.function(data, offset)
        except Exception:
            continue
        if not result or len(result) > max_size:
            continue
        if looks_like_tiles(result, tile_bytes):
            found.append((entry.key, len(result)))
    found.sort(key=lambda item: -item[1])
    return found


def decompress_file(path: str, offset: int, key: str, output: str,
                    tile_bytes: int = 32) -> int:
    """Décompresse un fichier et écrit le résultat ; renvoie la taille écrite."""
    with open(path, "rb") as f:
        data = f.read()
    result = decompress(key, data, offset)
    with open(output, "wb") as f:
        f.write(result)
    return len(result)
