"""Décompression RNC ProPack (Rob Northen Computing).

RNC ProPack est utilisé sur Amiga, Atari ST, Mega Drive, PC et Game Boy.
Le fichier commence par un en-tête de 18 octets ::

    +0x00  "RNC" + méthode (1 ou 2)
    +0x04  taille décompressée (32 bits)
    +0x08  taille compressée (32 bits)
    +0x0C  CRC des données décompressées (16 bits)
    +0x0E  CRC des données compressées (16 bits)
    +0x10  marge (octets de bourrage en fin de flux)
    +0x11  nombre de blocs
    +0x12  données compressées

La méthode 1 utilise trois tables de Huffman (littéraux, positions,
longueurs) et un flux de bits de 16 bits ; la méthode 2 est un LZSS plus
simple.  Les deux peuvent être chiffrées par une clé de 16 bits : la clé
tourne d'un bit vers la droite après chaque passage littéral.

Comme pour Imploder, un CRC faux ne doit pas faire échouer la
décompression : les protections et les versions anciennes de ProPack en
produisent régulièrement.  ``verify=False`` (par défaut) renvoie donc des
avertissements au lieu de lever une exception.

Référence : l'implémentation Python de ``bitplane/propack`` (WTFPL) et le
manuel ProPack de Rob Northen Computing (février 1992), dont les sources
d'assembleur sont dans ``tobiasvl/rnc_propack``.
"""

from __future__ import annotations

from .compression import DecompressionError

HEADER_SIZE = 18
SIGNATURE = b"RNC"

#: Taille maximale acceptée pour la sortie (garde-fou mémoire).
MAX_OUTPUT = 64 << 20


class RncError(DecompressionError):
    """Flux RNC invalide, tronqué ou chiffré sans clé."""


def _make_crc_table() -> tuple[int, ...]:
    table = []
    for value in range(256):
        crc = value
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        table.append(crc)
    return tuple(table)


_CRC_TABLE = _make_crc_table()


def crc16(data: bytes | bytearray, offset: int = 0,
          size: int | None = None) -> int:
    """CRC-16/ARC utilisé par ProPack."""
    if size is None:
        size = len(data) - offset
    crc = 0
    table = _CRC_TABLE
    for i in range(offset, offset + size):
        crc = (crc >> 8) ^ table[(crc ^ data[i]) & 0xFF]
    return crc


def _ror16(key: int) -> int:
    key &= 0xFFFF
    return 0x8000 | (key >> 1) if key & 1 else key >> 1


def _inverse_bits(value: int, count: int) -> int:
    result = 0
    for _ in range(count):
        result = (result << 1) | (value & 1)
        value >>= 1
    return result


class _BitReader:
    """Lecteur de bits des deux méthodes ProPack."""

    def __init__(self, data: bytes | bytearray, offset: int, end: int):
        self.data = data
        self.pos = offset
        self.end = end
        self.bit_buffer = 0
        self.bit_count = 0

    def _peek(self, offset: int) -> int:
        index = self.pos + offset
        return self.data[index] if index < self.end else 0

    def read_byte(self) -> int:
        if self.pos >= self.end:
            raise RncError("fin du flux RNC inattendue")
        value = self.data[self.pos]
        self.pos += 1
        return value

    def _read_token_byte(self) -> int:
        # La méthode 1 peut omettre jusqu'à deux octets de bourrage à zéro
        # dans son dernier jeton de 16 bits.
        if self.pos >= self.end + 2:
            raise RncError("fin du flux RNC inattendue")
        value = self._peek(0)
        self.pos += 1
        return value

    def read_bits_m1(self, count: int) -> int:
        bits = 0
        previous = 1
        for _ in range(count):
            if not self.bit_count:
                low = self._read_token_byte()
                high = self._read_token_byte()
                # Regard de deux octets en avant : le flux est lu par mots
                # de 16 bits alors que le pointeur avance d'un octet.
                self.bit_buffer = ((self._peek(1) << 24)
                                   | (self._peek(0) << 16)
                                   | (high << 8) | low)
                self.bit_count = 16
            if self.bit_buffer & 1:
                bits |= previous
            self.bit_buffer >>= 1
            previous <<= 1
            self.bit_count -= 1
        return bits

    def read_bits_m2(self, count: int) -> int:
        bits = 0
        for _ in range(count):
            if not self.bit_count:
                self.bit_buffer = self.read_byte()
                self.bit_count = 8
            bits = (bits << 1) | (1 if self.bit_buffer & 0x80 else 0)
            self.bit_buffer = (self.bit_buffer << 1) & 0xFF
            self.bit_count -= 1
        return bits


def _copy_match(output: bytearray, offset: int, count: int,
                limit: int) -> None:
    if offset < 1 or offset > len(output):
        raise RncError("distance de copie RNC invalide")
    if len(output) + count > limit:
        raise RncError("données RNC plus longues que la taille annoncée")
    for _ in range(count):
        output.append(output[-offset])


def _make_huftable(reader: _BitReader) -> list[tuple[int, int]]:
    leaves = reader.read_bits_m1(5)
    if not leaves:
        return []
    leaves = min(leaves, 16)
    depths = [reader.read_bits_m1(4) for _ in range(leaves)]
    codes = [0] * leaves
    value = 0
    divisor = 0x80000000
    for depth in range(1, 17):
        for i in range(leaves):
            if depths[i] == depth:
                codes[i] = _inverse_bits(value // divisor, depth)
                value += divisor
        divisor >>= 1
    return [(depths[i], codes[i]) for i in range(leaves)]


def _decode_table(reader: _BitReader, table: list[tuple[int, int]]) -> int:
    for i, (depth, code) in enumerate(table):
        if depth and code == (reader.bit_buffer & ((1 << depth) - 1)):
            reader.read_bits_m1(depth)
            if i < 2:
                return i
            return reader.read_bits_m1(i - 1) | (1 << (i - 1))
    raise RncError("code de Huffman RNC invalide")


def _reload_lookahead(reader: _BitReader) -> None:
    """Recharge le regard après une lecture d'octets bruts (méthode 1)."""
    low = reader.data[reader.pos] if reader.pos < reader.end else 0
    mid = reader.data[reader.pos + 1] if reader.pos + 1 < reader.end else 0
    high = reader.data[reader.pos + 2] if reader.pos + 2 < reader.end else 0
    mask = (1 << reader.bit_count) - 1
    reader.bit_buffer = (((high << 16) | (mid << 8) | low) << reader.bit_count) | (
        reader.bit_buffer & mask)


def _unpack_m1(reader: _BitReader, unpacked_size: int, key: int) -> bytearray:
    output = bytearray()
    processed = 0
    while processed < unpacked_size:
        raw_table = _make_huftable(reader)
        len_table = _make_huftable(reader)
        pos_table = _make_huftable(reader)
        subchunks = reader.read_bits_m1(16)
        if subchunks == 0:
            raise RncError("bloc RNC vide : flux corrompu")
        for index in range(subchunks):
            data_length = _decode_table(reader, raw_table)
            processed += data_length
            if processed > unpacked_size:
                raise RncError("taille décompressée RNC dépassée")
            if data_length:
                for _ in range(data_length):
                    value = (key ^ reader.read_byte()) & 0xFF
                    output.append(value)
                key = _ror16(key)
                _reload_lookahead(reader)
            if index < subchunks - 1:
                match_offset = _decode_table(reader, len_table) + 1
                match_count = _decode_table(reader, pos_table) + 2
                processed += match_count
                _copy_match(output, match_offset, match_count, unpacked_size)
    return output


def _decode_match_count_m2(reader: _BitReader) -> int:
    count = reader.read_bits_m2(1) + 4
    if reader.read_bits_m2(1):
        count = ((count - 1) << 1) + reader.read_bits_m2(1)
    return count


def _decode_match_offset_m2(reader: _BitReader) -> int:
    offset = 0
    if reader.read_bits_m2(1):
        offset = reader.read_bits_m2(1)
        if reader.read_bits_m2(1):
            offset = ((offset << 1) | reader.read_bits_m2(1)) | 4
            if not reader.read_bits_m2(1):
                offset = (offset << 1) | reader.read_bits_m2(1)
        elif not offset:
            offset = reader.read_bits_m2(1) + 2
    return ((offset << 8) | reader.read_byte()) + 1


def _unpack_m2(reader: _BitReader, unpacked_size: int, key: int) -> bytearray:
    output = bytearray()
    processed = 0
    while processed < unpacked_size:
        while True:
            if not reader.read_bits_m2(1):
                processed += 1
                if processed > unpacked_size:
                    raise RncError("taille décompressée RNC dépassée")
                output.append((key ^ reader.read_byte()) & 0xFF)
                key = _ror16(key)
                continue
            if reader.read_bits_m2(1):
                if reader.read_bits_m2(1):
                    if reader.read_bits_m2(1):
                        count = reader.read_byte() + 8
                        if count == 8:
                            # Fin de bloc : le bit suivant est un bourrage.
                            reader.read_bits_m2(1)
                            break
                    else:
                        count = 3
                    offset = _decode_match_offset_m2(reader)
                else:
                    count = 2
                    offset = reader.read_byte() + 1
                processed += count
                _copy_match(output, offset, count, unpacked_size)
            else:
                count = _decode_match_count_m2(reader)
                if count != 9:
                    offset = _decode_match_offset_m2(reader)
                    processed += count
                    _copy_match(output, offset, count, unpacked_size)
                else:
                    length = (reader.read_bits_m2(4) << 2) + 12
                    processed += length
                    if processed > unpacked_size:
                        raise RncError("taille décompressée RNC dépassée")
                    for _ in range(length):
                        output.append((key ^ reader.read_byte()) & 0xFF)
                    key = _ror16(key)
    return output


def is_rnc(data: bytes | bytearray, offset: int = 0) -> bool:
    """Vrai si les octets à ``offset`` commencent par un en-tête RNC."""
    if offset < 0 or offset + HEADER_SIZE > len(data):
        return False
    if bytes(data[offset:offset + 3]) != SIGNATURE:
        return False
    return data[offset + 3] in (1, 2)


def inspect(data: bytes | bytearray, offset: int = 0) -> dict:
    """Décrit un flux RNC sans le décompresser."""
    if not is_rnc(data, offset):
        return {}
    header = data[offset:offset + HEADER_SIZE]
    return {
        "format": "rnc",
        "method": header[3],
        "offset": offset,
        "unpacked_size": int.from_bytes(header[4:8], "big"),
        "packed_size": int.from_bytes(header[8:12], "big"),
        "unpacked_crc": int.from_bytes(header[12:14], "big"),
        "packed_crc": int.from_bytes(header[14:16], "big"),
        "leeway": header[16],
        "chunks": header[17],
    }


def unpack(data: bytes | bytearray, offset: int = 0, key: int = 0,
           verify: bool = False) -> tuple[bytes, list[str]]:
    """Décompresse un flux RNC ; renvoie ``(données, avertissements)``."""
    if not is_rnc(data, offset):
        raise RncError("signature RNC absente")
    header = bytes(data[offset:offset + HEADER_SIZE])
    method = header[3]
    unpacked_size = int.from_bytes(header[4:8], "big")
    packed_size = int.from_bytes(header[8:12], "big")
    unpacked_crc = int.from_bytes(header[12:14], "big")
    packed_crc = int.from_bytes(header[14:16], "big")

    if unpacked_size == 0 or unpacked_size > MAX_OUTPUT:
        raise RncError(f"taille décompressée RNC invalide : {unpacked_size}")
    if packed_size < 2 or offset + HEADER_SIZE + packed_size > len(data):
        raise RncError("données compressées RNC tronquées")

    warnings: list[str] = []
    actual_packed_crc = crc16(data, offset + HEADER_SIZE, packed_size)
    if actual_packed_crc != packed_crc:
        warnings.append(
            f"CRC des données compressées invalide (0x{packed_crc:04X} attendu, "
            f"0x{actual_packed_crc:04X} calculé) — décompression tentée quand même")

    reader = _BitReader(data, offset + HEADER_SIZE,
                        offset + HEADER_SIZE + packed_size)
    if reader.read_bits_m1(1) if method == 1 else reader.read_bits_m2(1):
        raise RncError("fichier RNC verrouillé : décompression impossible sans "
                       "la clé d'origine")
    encrypted = reader.read_bits_m1(1) if method == 1 else reader.read_bits_m2(1)
    if encrypted and not key:
        raise RncError("fichier RNC chiffré : fournir la clé de 16 bits")

    if method == 1:
        output = _unpack_m1(reader, unpacked_size, key)
    else:
        output = _unpack_m2(reader, unpacked_size, key)

    if len(output) != unpacked_size:
        raise RncError(f"taille décompressée incohérente : {len(output)} "
                       f"au lieu de {unpacked_size}")

    actual_unpacked_crc = crc16(output)
    if actual_unpacked_crc != unpacked_crc:
        message = (f"CRC des données décompressées invalide "
                   f"(0x{unpacked_crc:04X} attendu, "
                   f"0x{actual_unpacked_crc:04X} calculé)")
        if verify:
            raise RncError(message)
        warnings.append(message + " — décompression tentée quand même")
    return bytes(output), warnings


def decompress(data: bytes | bytearray, offset: int = 0) -> bytes:
    """Décompresseur au contrat du registre (fichiers non chiffrés)."""
    return unpack(data, offset)[0]
