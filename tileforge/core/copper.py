"""Listes copper Amiga : plans, palette et géométrie.

Sur Amiga, l'image n'est pas décrite par un en-tête : elle est programmée par
le coprocesseur copper, qui reçoit une suite de couples ``(registre, valeur)``.
Cette liste est la source de vérité du jeu : elle donne le nombre de plans
(``BPLCON0``), les adresses des plans (``BPLxPT``), la palette
(``COLOR00``…``COLOR31``), la fenêtre d'affichage (``DIWSTRT``/``DIWSTOP``),
la fenêtre DMA (``DDFSTRT``/``DDFSTOP``) et le modulo, c'est-à-dire le
bourrage de fin de ligne (``BPL1MOD``/``BPL2MOD``).

Le module sait aussi **chercher** une liste dans un binaire : un candidat est
une suite d'instructions dont les registres sont connus ; il est noté par la
présence d'une palette, d'un ``BPLCON0`` et de pointeurs de plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .palettes import Palette, amiga_to_rgb

#: Registres copper utiles.
REG_DIWSTRT = 0x008E
REG_DIWSTOP = 0x0090
REG_DDFSTRT = 0x0092
REG_DDFSTOP = 0x0094
REG_BPLCON0 = 0x0100
REG_BPLCON1 = 0x0102
REG_BPLCON2 = 0x0104
REG_BPL1MOD = 0x0108
REG_BPL2MOD = 0x010A
REG_BPL1PTH = 0x00E0
REG_BPL1PTL = 0x00E2
REG_BPL8PTH = 0x00EE
REG_COLOR00 = 0x0180
REG_COLOR31 = 0x01BE

#: Fin de liste classique.
COPPER_END = 0xFFFF

#: Nombre maximal d'instructions lues dans une liste.
MAX_INSTRUCTIONS = 2048


@dataclass
class CopperList:
    """Liste copper analysée."""

    offset: int
    registers: dict[int, int] = field(default_factory=dict)
    colors: dict[int, int] = field(default_factory=dict)
    plane_ptrs: list[int] = field(default_factory=list)
    waits: int = 0
    instructions: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def bitplanes(self) -> int:
        value = self.registers.get(REG_BPLCON0, 0)
        return (value >> 12) & 0x07

    @property
    def palette(self) -> Palette:
        if not self.colors:
            return Palette([(0, 0, 0)], "copper")
        count = max(self.colors) + 1
        colors = [amiga_to_rgb(self.colors.get(i, 0)) for i in range(count)]
        return Palette(colors, f"copper@{self.offset:#x}")

    @property
    def width(self) -> int:
        """Largeur déduite de DDFSTRT/DDFSTOP (en pixels)."""
        start = self.registers.get(REG_DDFSTRT)
        stop = self.registers.get(REG_DDFSTOP)
        if start is None or stop is None:
            return 0
        # Le compteur horizontal avance de deux pixels par unité DDF ; la
        # fenêtre standard 320 px vaut 0x38..0xD0.
        units = (stop & 0xFC) - (start & 0xFC)
        return max(0, units * 2 + 16)

    @property
    def modulo(self) -> int:
        return self.registers.get(REG_BPL1MOD, 0)

    def geometry(self) -> dict:
        return {
            "bitplanes": self.bitplanes,
            "width": self.width,
            "modulo": self.modulo,
            "diwstrt": self.registers.get(REG_DIWSTRT),
            "diwstop": self.registers.get(REG_DIWSTOP),
            "ddfstrt": self.registers.get(REG_DDFSTRT),
            "ddfstop": self.registers.get(REG_DDFSTOP),
            "bplcon0": self.registers.get(REG_BPLCON0),
            "bplcon1": self.registers.get(REG_BPLCON1),
            "plane_ptrs": list(self.plane_ptrs),
        }

    def summary(self) -> dict:
        return {
            "offset": self.offset,
            "instructions": self.instructions,
            "waits": self.waits,
            "bitplanes": self.bitplanes,
            "width": self.width,
            "modulo": self.modulo,
            "colors": len(self.colors),
            "palette": [[*amiga_to_rgb(word)] for _, word in
                        sorted(self.colors.items())],
            "geometry": self.geometry(),
            "warnings": self.warnings,
        }


def is_register(word: int) -> bool:
    """Registre copper matériel (ou WAIT/SKIP) plausible."""
    if word == COPPER_END:
        return True
    if word & 1:
        return word >= 0x0002
    return (0x0080 <= word <= 0x01BE
            or 0x00E0 <= word <= 0x00FE
            or 0x0100 <= word <= 0x011E)


def _parse_at(data: bytes, offset: int, max_instructions: int) -> CopperList:
    result = CopperList(offset=offset)
    pos = offset
    for _ in range(max_instructions):
        if pos + 4 > len(data):
            break
        register = int.from_bytes(data[pos:pos + 2], "big")
        value = int.from_bytes(data[pos + 2:pos + 4], "big")
        if register == COPPER_END and value in (0xFFFE, 0xFFFF):
            break
        if not is_register(register):
            break
        pos += 4
        result.instructions += 1
        if register & 1:
            result.waits += 1
            continue
        result.registers[register] = value
        if REG_COLOR00 <= register <= REG_COLOR31 and not register & 1:
            index = (register - REG_COLOR00) // 2
            result.colors[index] = value
        elif REG_BPL1PTH <= register <= REG_BPL8PTH:
            # Les pointeurs de plans s'écrivent en deux mots : PTH puis PTL.
            delta = register - REG_BPL1PTH
            index = delta // 4
            while len(result.plane_ptrs) <= index:
                result.plane_ptrs.append(0)
            if delta % 4 == 0:
                result.plane_ptrs[index] = (
                    (result.plane_ptrs[index] & 0x0000FFFF) | (value << 16))
            else:
                result.plane_ptrs[index] = (
                    (result.plane_ptrs[index] & 0xFFFF0000) | value)
    if result.instructions == 0:
        result.warnings.append("aucune instruction copper reconnue")
    return result


def _score(list_: CopperList) -> float:
    score = min(list_.instructions, 64) / 64.0
    if list_.colors:
        score += 0.35
    if list_.bitplanes:
        score += 0.25
    if list_.plane_ptrs:
        score += 0.15
    if list_.width:
        score += 0.10
    return score


def find_lists(data: bytes, limit: int = 8,
               min_instructions: int = 4) -> list[CopperList]:
    """Cherche les listes copper les plus plausibles d'un binaire."""
    found: list[CopperList] = []
    seen: set[int] = set()
    for offset in range(0, max(0, len(data) - 4), 2):
        if offset in seen:
            continue
        first = int.from_bytes(data[offset:offset + 2], "big")
        if first not in (REG_BPLCON0, REG_COLOR00, REG_BPL1PTH,
                         REG_DDFSTRT, REG_DIWSTRT):
            continue
        candidate = _parse_at(data, offset, MAX_INSTRUCTIONS)
        if candidate.instructions < min_instructions:
            continue
        found.append(candidate)
        # Sauter la liste pour ne pas la redétecter à chaque instruction.
        seen.update(range(offset, offset + candidate.instructions * 4, 2))
    found.sort(key=_score, reverse=True)
    return found[:limit]


def parse(data: bytes, offset: int = 0,
          max_instructions: int = MAX_INSTRUCTIONS) -> CopperList:
    """Analyse la liste copper à ``offset``."""
    return _parse_at(data, offset, max_instructions)
