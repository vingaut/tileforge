"""Désassembleur 6502 (NES, Commodore 64, Apple II, Atari 8 bits…).

Le 6502 équipe la quasi-totalité des machines 8 bits des années 1977-1990.
Ce module partage la mécanique du désassembleur 65816 (mêmes noms de modes,
même mise en forme) et n'en diffère que par sa table d'opcodes : 151
instructions documentées, plus les NOP non documentés qui servent de
remplissage, et 77 codes réellement invalides rendus en ``.byte``.

La table vient de la matrice d'opcodes d'oxyron.de (Graham), qui recense
aussi les codes non documentés.

Le module ne dépend ni de Qt ni de l'interface.
"""

from __future__ import annotations

from .disasm65816 import ABSOLUTE_MODES, MODE_SIZE, Instruction, _format
from .disasm65816 import format_listing as _format_listing


def format_listing(instructions: list[Instruction]) -> str:
    """Rendu texte, identique à celui du désassembleur 65816."""
    return _format_listing(instructions)

OPCODES = (
    ("brk", "implied"),
    ("ora", "indirectx"),
    (".byte", ""),
    (".byte", ""),
    ("nop", "direct"),
    ("ora", "direct"),
    ("asl", "direct"),
    (".byte", ""),
    ("php", "implied"),
    ("ora", "immediate"),
    ("asl", "implied"),
    (".byte", ""),
    ("nop", "absolute"),
    ("ora", "absolute"),
    ("asl", "absolute"),
    (".byte", ""),
    ("bpl", "relative"),
    ("ora", "indirecty"),
    (".byte", ""),
    (".byte", ""),
    ("nop", "directx"),
    ("ora", "directx"),
    ("asl", "directx"),
    (".byte", ""),
    ("clc", "implied"),
    ("ora", "absolutey"),
    ("nop", "implied"),
    (".byte", ""),
    ("nop", "absolutex"),
    ("ora", "absolutex"),
    ("asl", "absolutex"),
    (".byte", ""),
    ("jsr", "absolute"),
    ("and", "indirectx"),
    (".byte", ""),
    (".byte", ""),
    ("bit", "direct"),
    ("and", "direct"),
    ("rol", "direct"),
    (".byte", ""),
    ("plp", "implied"),
    ("and", "immediate"),
    ("rol", "implied"),
    (".byte", ""),
    ("bit", "absolute"),
    ("and", "absolute"),
    ("rol", "absolute"),
    (".byte", ""),
    ("bmi", "relative"),
    ("and", "indirecty"),
    (".byte", ""),
    (".byte", ""),
    ("nop", "directx"),
    ("and", "directx"),
    ("rol", "directx"),
    (".byte", ""),
    ("sec", "implied"),
    ("and", "absolutey"),
    ("nop", "implied"),
    (".byte", ""),
    ("nop", "absolutex"),
    ("and", "absolutex"),
    ("rol", "absolutex"),
    (".byte", ""),
    ("rti", "implied"),
    ("eor", "indirectx"),
    (".byte", ""),
    (".byte", ""),
    ("nop", "direct"),
    ("eor", "direct"),
    ("lsr", "direct"),
    (".byte", ""),
    ("pha", "implied"),
    ("eor", "immediate"),
    ("lsr", "implied"),
    (".byte", ""),
    ("jmp", "absolute"),
    ("eor", "absolute"),
    ("lsr", "absolute"),
    (".byte", ""),
    ("bvc", "relative"),
    ("eor", "indirecty"),
    (".byte", ""),
    (".byte", ""),
    ("nop", "directx"),
    ("eor", "directx"),
    ("lsr", "directx"),
    (".byte", ""),
    ("cli", "implied"),
    ("eor", "absolutey"),
    ("nop", "implied"),
    (".byte", ""),
    ("nop", "absolutex"),
    ("eor", "absolutex"),
    ("lsr", "absolutex"),
    (".byte", ""),
    ("rts", "implied"),
    ("adc", "indirectx"),
    (".byte", ""),
    (".byte", ""),
    ("nop", "direct"),
    ("adc", "direct"),
    ("ror", "direct"),
    (".byte", ""),
    ("pla", "implied"),
    ("adc", "immediate"),
    ("ror", "implied"),
    (".byte", ""),
    ("jmp", "indirect16"),
    ("adc", "absolute"),
    ("ror", "absolute"),
    (".byte", ""),
    ("bvs", "relative"),
    ("adc", "indirecty"),
    (".byte", ""),
    (".byte", ""),
    ("nop", "directx"),
    ("adc", "directx"),
    ("ror", "directx"),
    (".byte", ""),
    ("sei", "implied"),
    ("adc", "absolutey"),
    ("nop", "implied"),
    (".byte", ""),
    ("nop", "absolutex"),
    ("adc", "absolutex"),
    ("ror", "absolutex"),
    (".byte", ""),
    ("nop", "immediate"),
    ("sta", "indirectx"),
    ("nop", "immediate"),
    (".byte", ""),
    ("sty", "direct"),
    ("sta", "direct"),
    ("stx", "direct"),
    (".byte", ""),
    ("dey", "implied"),
    ("nop", "immediate"),
    ("txa", "implied"),
    (".byte", ""),
    ("sty", "absolute"),
    ("sta", "absolute"),
    ("stx", "absolute"),
    (".byte", ""),
    ("bcc", "relative"),
    ("sta", "indirecty"),
    (".byte", ""),
    (".byte", ""),
    ("sty", "directx"),
    ("sta", "directx"),
    ("stx", "directy"),
    (".byte", ""),
    ("tya", "implied"),
    ("sta", "absolutey"),
    ("txs", "implied"),
    (".byte", ""),
    (".byte", ""),
    ("sta", "absolutex"),
    (".byte", ""),
    (".byte", ""),
    ("ldy", "immediate"),
    ("lda", "indirectx"),
    ("ldx", "immediate"),
    (".byte", ""),
    ("ldy", "direct"),
    ("lda", "direct"),
    ("ldx", "direct"),
    (".byte", ""),
    ("tay", "implied"),
    ("lda", "immediate"),
    ("tax", "implied"),
    (".byte", ""),
    ("ldy", "absolute"),
    ("lda", "absolute"),
    ("ldx", "absolute"),
    (".byte", ""),
    ("bcs", "relative"),
    ("lda", "indirecty"),
    (".byte", ""),
    (".byte", ""),
    ("ldy", "directx"),
    ("lda", "directx"),
    ("ldx", "directy"),
    (".byte", ""),
    ("clv", "implied"),
    ("lda", "absolutey"),
    ("tsx", "implied"),
    (".byte", ""),
    ("ldy", "absolutex"),
    ("lda", "absolutex"),
    ("ldx", "absolutey"),
    (".byte", ""),
    ("cpy", "immediate"),
    ("cmp", "indirectx"),
    ("nop", "immediate"),
    (".byte", ""),
    ("cpy", "direct"),
    ("cmp", "direct"),
    ("dec", "direct"),
    (".byte", ""),
    ("iny", "implied"),
    ("cmp", "immediate"),
    ("dex", "implied"),
    (".byte", ""),
    ("cpy", "absolute"),
    ("cmp", "absolute"),
    ("dec", "absolute"),
    (".byte", ""),
    ("bne", "relative"),
    ("cmp", "indirecty"),
    (".byte", ""),
    (".byte", ""),
    ("nop", "directx"),
    ("cmp", "directx"),
    ("dec", "directx"),
    (".byte", ""),
    ("cld", "implied"),
    ("cmp", "absolutey"),
    ("nop", "implied"),
    (".byte", ""),
    ("nop", "absolutex"),
    ("cmp", "absolutex"),
    ("dec", "absolutex"),
    (".byte", ""),
    ("cpx", "immediate"),
    ("sbc", "indirectx"),
    ("nop", "immediate"),
    (".byte", ""),
    ("cpx", "direct"),
    ("sbc", "direct"),
    ("inc", "direct"),
    (".byte", ""),
    ("inx", "implied"),
    ("sbc", "immediate"),
    ("nop", "implied"),
    ("sbc", "immediate"),
    ("cpx", "absolute"),
    ("sbc", "absolute"),
    ("inc", "absolute"),
    (".byte", ""),
    ("beq", "relative"),
    ("sbc", "indirecty"),
    (".byte", ""),
    (".byte", ""),
    ("nop", "directx"),
    ("sbc", "directx"),
    ("inc", "directx"),
    (".byte", ""),
    ("sed", "implied"),
    ("sbc", "absolutey"),
    ("nop", "implied"),
    (".byte", ""),
    ("nop", "absolutex"),
    ("sbc", "absolutex"),
    ("inc", "absolutex"),
    (".byte", ""),
)


def decode(data: bytes, offset: int) -> Instruction:
    """Décode l'instruction 6502 à ``offset``."""
    if offset < 0 or offset >= len(data):
        raise ValueError("offset hors des données")
    opcode = data[offset]
    mnemonic, mode = OPCODES[opcode]
    if mnemonic == ".byte":
        return Instruction(offset=offset, raw=data[offset:offset + 1],
                           mnemonic=".byte", mode="", operand=f"${opcode:02X}")
    size = MODE_SIZE.get(mode, 1)
    raw = data[offset:offset + 1 + size]
    if len(raw) < 1 + size:
        raise ValueError("instruction tronquée")

    value = 0
    if size == 1:
        value = raw[1]
    elif size == 2:
        value = raw[1] | (raw[2] << 8)

    target = None
    if mode in ABSOLUTE_MODES or mode == "indirect16":
        target = value
    elif mode == "relative":
        delta = raw[1] - 256 if raw[1] >= 128 else raw[1]
        target = (offset + 2 + delta) & 0xFFFF

    operand = _format(mode, value, target, raw)
    return Instruction(offset=offset, raw=raw, mnemonic=mnemonic, mode=mode,
                       operand=operand, target=target)


def disassemble(data: bytes, offset: int, count: int = 32) -> list[Instruction]:
    """Désassemble ``count`` instructions à partir de ``offset``."""
    out: list[Instruction] = []
    position = offset
    while len(out) < count and position < len(data):
        try:
            instruction = decode(data, position)
        except ValueError:
            break
        out.append(instruction)
        position += instruction.size
    return out


def trace(data: bytes, entry: int, max_instructions: int = 20000,
          base: int = 0) -> list[Instruction]:
    """Suit le fil d'exécution depuis l'adresse ``entry``.

    ``base`` est l'adresse de chargement du fichier : pour une cartouche NES,
    le code commence à ``$8000`` alors que le fichier commence à zéro, donc
    ``base = 0x8000``.
    """
    seen: set[int] = set()
    pending = [entry - base]
    returns: list[int] = []
    out: list[Instruction] = []

    def valid(address: int | None) -> int | None:
        if address is None:
            return None
        position = address - base
        return position if 0 <= position < len(data) else None

    while pending and len(out) < max_instructions:
        position = pending.pop()
        while 0 <= position < len(data) and len(out) < max_instructions:
            if position in seen:
                break
            seen.add(position)
            try:
                instruction = decode(data, position)
            except ValueError:
                break
            out.append(instruction)
            next_position = position + instruction.size
            mnemonic = instruction.mnemonic

            if mnemonic == "jsr":
                target = valid(instruction.target)
                if target is not None and target not in seen:
                    returns.append(next_position)
                    position = target
                    continue
                position = next_position
                continue

            if mnemonic in ("rts", "rti"):
                if returns:
                    position = returns.pop()
                    continue
                break

            if mnemonic == "jmp":
                target = valid(instruction.target)
                if target is not None and target not in seen:
                    position = target
                    continue
                break

            if mnemonic == "brk":
                break

            if instruction.mode == "relative":
                target = valid(instruction.target)
                if target is not None and target not in seen:
                    pending.append(target)
            position = next_position
    return out


def references(data: bytes, start: int = 0, end: int | None = None,
               minimum: int = 2, base: int = 0) -> list[dict]:
    """Adresses référencées au moins ``minimum`` fois par le code."""
    end = len(data) if end is None else min(end, len(data))
    counts: dict[int, int] = {}
    position = max(0, start)
    while position < end:
        try:
            instruction = decode(data, position)
        except ValueError:
            break
        if instruction.target is not None:
            address = instruction.target + base
            counts[address] = counts.get(address, 0) + 1
        position += instruction.size
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"target": address, "target_hex": f"0x{address:04X}", "count": count}
            for address, count in ranked if count >= minimum]
