"""Exécutables Amiga au format hunk.

Un exécutable Amiga n'est pas un fichier plat : c'est une suite de segments
(``HUNK_CODE``, ``HUNK_DATA``, ``HUNK_BSS``) décrits par un en-tête, avec des
tables de relogement qui disent au chargeur où insérer l'adresse de chaque
segment.  Pour retrouver un graphisme référencé par une adresse absolue, il
faut donc connaître la **table des segments** et l'**adresse de chargement**.

Ce module ne désassemble pas : il donne la carte du fichier (offset, taille,
type, adresse relative) et convertit une adresse en offset.  C'est la brique
qui manquait pour relier le code aux données sur Project-X.

Les tailles de segments peuvent porter des drapeaux dans les bits hauts
(rencontré sur ``lv1f``) : ils sont masqués et signalés.

Référence : la spécification des hunks du RKM Amiga (« AmigaDOS »), et le
comportement de rizin/radare2 (``arch m68k / os AmigaOS``, section
``hunk_0_code paddr 0x20 vaddr 0x8000``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Signature d'un exécutable hunk.
HUNK_HEADER = 0x3F3
HUNK_CODE = 0x3E9
HUNK_DATA = 0x3EA
HUNK_BSS = 0x3EB
HUNK_RELOC32 = 0x3EC
HUNK_RELOC16 = 0x3ED
HUNK_RELOC8 = 0x3EE
HUNK_EXT = 0x3EF
HUNK_SYMBOL = 0x3F0
HUNK_DEBUG = 0x3F1
HUNK_END = 0x3F2
HUNK_OVERLAY = 0x3F5
HUNK_BREAK = 0x3F6
HUNK_DREL32 = 0x3F7
HUNK_DREL16 = 0x3F8
HUNK_DREL8 = 0x3F9
HUNK_LIB = 0x3FA
HUNK_INDEX = 0x3FB

SEGMENT_TYPES = {
    HUNK_CODE: "code",
    HUNK_DATA: "data",
    HUNK_BSS: "bss",
}

#: Adresse de chargement conventionnelle utilisée par les désassembleurs.
DEFAULT_BASE = 0x8000

#: Masque des drapeaux dans la table des tailles.
SIZE_MASK = 0x3FFFFFFF


class HunkError(Exception):
    """Fichier hunk invalide ou tronqué."""


@dataclass
class HunkSegment:
    """Un segment de l'exécutable."""

    index: int
    kind: str                       # "code" | "data" | "bss"
    file_offset: int                # offset du contenu dans le fichier
    size: int                       # taille en octets
    vaddr: int = 0                  # adresse relative au début du fichier
    data: bytes = b""
    relocations: list[dict] = field(default_factory=list)

    @property
    def end_offset(self) -> int:
        return self.file_offset + self.size

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "kind": self.kind,
            "file_offset": self.file_offset,
            "size": self.size,
            "vaddr": self.vaddr,
            "relocations": len(self.relocations),
        }


@dataclass
class HunkFile:
    """Exécutable hunk analysé."""

    segments: list[HunkSegment] = field(default_factory=list)
    first_hunk: int = 0
    last_hunk: int = 0
    sizes: list[int] = field(default_factory=list)
    base: int = DEFAULT_BASE
    warnings: list[str] = field(default_factory=list)
    offset: int = 0
    size: int = 0

    def segment(self, index: int) -> HunkSegment | None:
        for seg in self.segments:
            if seg.index == index:
                return seg
        return None

    def address_to_offset(self, address: int) -> int | None:
        """Convertit une adresse absolue en offset fichier."""
        relative = address - self.base
        for seg in self.segments:
            if seg.vaddr <= relative < seg.vaddr + seg.size:
                return seg.file_offset + (relative - seg.vaddr)
        return None

    def offset_to_address(self, offset: int) -> int | None:
        for seg in self.segments:
            if seg.file_offset <= offset < seg.end_offset:
                return self.base + seg.vaddr + (offset - seg.file_offset)
        return None

    def summary(self) -> dict:
        return {
            "format": "hunk",
            "offset": self.offset,
            "size": self.size,
            "base": self.base,
            "first_hunk": self.first_hunk,
            "last_hunk": self.last_hunk,
            "segments": [s.as_dict() for s in self.segments],
            "warnings": self.warnings,
        }


class _Reader:
    def __init__(self, data: bytes, offset: int = 0):
        self.data = data
        self.pos = offset

    def u32(self) -> int:
        if self.pos + 4 > len(self.data):
            raise HunkError("fin de fichier inattendue")
        value = int.from_bytes(self.data[self.pos:self.pos + 4], "big")
        self.pos += 4
        return value

    def take(self, count: int) -> bytes:
        if count < 0 or self.pos + count > len(self.data):
            raise HunkError("fin de fichier inattendue")
        chunk = self.data[self.pos:self.pos + count]
        self.pos += count
        return chunk

    def skip(self, count: int) -> None:
        if count < 0 or self.pos + count > len(self.data):
            raise HunkError("fin de fichier inattendue")
        self.pos += count


def is_hunk(data: bytes, offset: int = 0) -> bool:
    """Vrai si les octets à ``offset`` commencent par un en-tête hunk."""
    if offset < 0 or offset + 4 > len(data):
        return False
    return int.from_bytes(data[offset:offset + 4], "big") == HUNK_HEADER


def find_hunk(data: bytes, start: int = 0) -> int | None:
    """Premier offset d'un en-tête hunk, ou ``None``."""
    marker = HUNK_HEADER.to_bytes(4, "big")
    index = data.find(marker, start)
    return index if index >= 0 else None


def _skip_symbol(reader: _Reader) -> None:
    while True:
        length = reader.u32()
        if length == 0:
            return
        reader.skip((length + 3) & ~3)
        reader.u32()  # valeur


def _skip_ext(reader: _Reader) -> None:
    """Saute un bloc HUNK_EXT (références et définitions externes)."""
    while True:
        kind = reader.u32()
        if kind == 0:
            return
        if kind == 1:                      # référence externe
            count = reader.u32()
            reader.skip(count * 4)
        elif kind == 2:                    # définition externe
            count = reader.u32()
            for _ in range(count):
                reader.u32()               # valeur
                length = reader.u32()
                reader.skip((length + 3) & ~3)
        elif kind in (3, 4):               # absolu / relatif
            count = reader.u32()
            reader.skip(count * 4)
        else:
            raise HunkError(f"type d'extension hunk inconnu : {kind}")


def parse(data: bytes, offset: int = 0,
          base: int = DEFAULT_BASE) -> HunkFile:
    """Analyse un exécutable hunk à partir de ``offset``."""
    if not is_hunk(data, offset):
        raise HunkError("signature hunk absente")
    reader = _Reader(data, offset)
    reader.u32()                            # HUNK_HEADER
    count = reader.u32()
    first = reader.u32()
    last = reader.u32()
    if count > 4096:
        raise HunkError(f"nombre de hunks invalide : {count}")
    sizes: list[int] = []
    hunk_file = HunkFile(first_hunk=first, last_hunk=last, base=base,
                         offset=offset, size=len(data) - offset)
    for index in range(count):
        raw = reader.u32()
        if raw & ~SIZE_MASK:
            hunk_file.warnings.append(
                f"segment {index} : drapeaux 0x{raw & ~SIZE_MASK:08X} dans la "
                "taille — masqués")
        # Les tailles de la table sont exprimées en mots de 32 bits.
        sizes.append((raw & SIZE_MASK) * 4)
    hunk_file.sizes = sizes

    vaddr = 0
    for index in range(count):
        hunk_type = reader.u32()
        kind = SEGMENT_TYPES.get(hunk_type)
        if kind is None:
            raise HunkError(f"type de hunk inattendu : 0x{hunk_type:X}")
        declared = reader.u32()
        size = declared * 4
        if size != sizes[index]:
            hunk_file.warnings.append(
                f"segment {index} : taille déclarée {size} octets, table "
                f"{sizes[index]} — la table fait foi")
        if size > len(data):
            raise HunkError(f"segment {index} : taille invalide {size}")
        if kind == "bss":
            segment = HunkSegment(index, kind, reader.pos, size, vaddr)
        else:
            segment = HunkSegment(index, kind, reader.pos, size, vaddr,
                                  reader.take(size))
        hunk_file.segments.append(segment)
        vaddr += size

        # blocs annexes jusqu'à HUNK_END
        while True:
            block_type = reader.u32()
            if block_type == HUNK_END:
                break
            if block_type == HUNK_RELOC32:
                segment.relocations.extend(_parse_reloc32(reader, 4))
            elif block_type in (HUNK_RELOC16, HUNK_RELOC8):
                segment.relocations.extend(_parse_reloc32(reader, 2))
            elif block_type == HUNK_DREL32:
                segment.relocations.extend(_parse_reloc32(reader, 4))
            elif block_type == HUNK_SYMBOL:
                _skip_symbol(reader)
            elif block_type == HUNK_DEBUG:
                length = reader.u32()
                reader.skip(length * 4)
            elif block_type == HUNK_EXT:
                _skip_ext(reader)
            elif block_type == HUNK_BREAK:
                continue
            else:
                raise HunkError(f"bloc hunk inattendu : 0x{block_type:X}")
    return hunk_file


def _parse_reloc32(reader: _Reader, width: int) -> list[dict]:
    relocs: list[dict] = []
    while True:
        count = reader.u32()
        if count == 0:
            return relocs
        target = reader.u32()
        offsets = [reader.u32() for _ in range(count)]
        relocs.append({"target": target, "width": width, "offsets": offsets})
