"""Désassembleur 68000 (Mega Drive, Amiga, Atari ST…).

Le 68000 équipe les trois machines 16 bits les plus répandues en Europe. Son
encodage est plus riche que celui du Z80 ou du 6502 : chaque instruction fait
un ou plusieurs mots de 16 bits, et un opérande peut lui-même consommer des
mots d'extension (déplacement, valeur immédiate, adresse absolue, index).

Le module décode les familles qui constituent l'essentiel du code réel :

* chargements et déplacements : ``MOVE``, ``MOVEA``, ``MOVEQ``, ``LEA``,
  ``PEA``, ``MOVEM``, ``LINK``, ``UNLK``, ``EXG``, ``SWAP``, ``EXT`` ;
* arithmétique et logique : ``ADD``, ``SUB``, ``CMP``, ``AND``, ``OR``,
  ``EOR``, ``ADDQ``, ``SUBQ``, ``MULU``, ``MULS``, ``DIVU``, ``DIVS``,
  ``NEG``, ``NOT``, ``CLR``, ``TST``, ``ADDA``, ``SUBA``, ``CMPA`` ;
* contrôle : ``BRA``, ``BSR``, ``Bcc``, ``DBcc``, ``Scc``, ``JMP``, ``JSR``,
  ``RTS``, ``RTE``, ``RTR``, ``TRAP``, ``STOP``, ``NOP``, ``RESET``, ``ILLEGAL``.

Les familles non décodées (ligne A, ligne F, ``MOVEP``, BCD, ``CHK``, les
décalages mémoire) sortent en ``.dc.w`` : une lacune visible vaut mieux qu'une
instruction inventée.

Le module ne dépend ni de Qt ni de l'interface.
"""

from __future__ import annotations

from .disasm65816 import Instruction

#: Tailles indexées par les bits 7-6 (00 octet, 01 mot, 10 long).
SIZES = {0: "b", 1: "w", 2: "l"}

#: Conditions de branchement.
CONDITIONS = ("t", "f", "hi", "ls", "cc", "cs", "ne", "eq",
              "vc", "vs", "pl", "mi", "ge", "lt", "gt", "le")


class Unsupported(Exception):
    """Encodage non décodé : l'appelant rend ``.dc.w``."""


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------


def _word(data: bytes, position: int) -> int:
    if position + 1 >= len(data):
        raise ValueError("mot tronqué")
    return (data[position] << 8) | data[position + 1]


def _long(data: bytes, position: int) -> int:
    return (_word(data, position) << 16) | _word(data, position + 2)


def _signed8(value: int) -> int:
    return value - 256 if value >= 128 else value


def _signed16(value: int) -> int:
    return value - 65536 if value >= 0x8000 else value


def _signed_hex(value: int, digits: int) -> str:
    """Déplacement en hexadécimal signé : ``$2F00`` ou ``-$00FF``."""
    if value < 0:
        return f"-${-value:0{digits}X}"
    return f"${value:0{digits}X}"


# ---------------------------------------------------------------------------
# Modes d'adressage
# ---------------------------------------------------------------------------


def _index_text(extension: int) -> str:
    """Registre d'index d'un mot d'extension bref."""
    register = (extension >> 12) & 7
    name = f"a{register}" if extension & 0x8000 else f"d{register}"
    size = "l" if extension & 0x0800 else "w"
    scale = 1 << ((extension >> 9) & 3)
    return f"{name}.{size}" if scale == 1 else f"{name}.{size}*{scale}"


def effective_address(data: bytes, position: int, mode: int, register: int,
                      size: str, base: int = 0) -> tuple[str, int, int | None]:
    """Décode un opérande ; renvoie (texte, octets consommés, adresse visée)."""
    if mode == 0:
        return f"d{register}", 0, None
    if mode == 1:
        return f"a{register}", 0, None
    if mode == 2:
        return f"(a{register})", 0, None
    if mode == 3:
        return f"(a{register})+", 0, None
    if mode == 4:
        return f"-(a{register})", 0, None
    if mode == 5:
        displacement = _signed16(_word(data, position))
        return f"{_signed_hex(displacement, 4)}(a{register})", 2, None
    if mode == 6:
        extension = _word(data, position)
        if (extension & 0x0700) == 0:
            displacement = _signed8(extension & 0xFF)
            return (f"{_signed_hex(displacement, 2)}(a{register},"
                    f"{_index_text(extension)})", 2, None)
        return f"${extension:04X}.w", 2, extension
    if register == 0:
        value = _word(data, position)
        return f"${value:04X}.w", 2, value
    if register == 1:
        value = _long(data, position)
        return f"${value:08X}.l", 4, value
    if register == 2:
        displacement = _signed16(_word(data, position))
        target = (position + base + displacement) & 0xFFFFFF
        return f"${target:06X}(pc)", 2, target
    if register == 3:
        extension = _word(data, position)
        displacement = _signed8(extension & 0xFF)
        target = (position + base + displacement) & 0xFFFFFF
        return f"${target:06X}(pc,{_index_text(extension)})", 2, target
    if register == 4:
        if size == "l":
            return f"#${_long(data, position):08X}", 4, None
        return f"#${_word(data, position):04X}", 2, None
    raise Unsupported("mode 7 register 5")


def _ea_pair(data: bytes, position: int, mode: int, register: int, size: str,
             base: int) -> tuple[str, int, int | None]:
    return effective_address(data, position, mode, register, size, base)


# ---------------------------------------------------------------------------
# Familles
# ---------------------------------------------------------------------------


def _move(top: int, data: bytes, position: int, base: int):
    size_code = (top >> 12) & 3
    size = {1: "b", 2: "l", 3: "w"}[size_code]
    destination_mode = (top >> 6) & 7
    destination_register = (top >> 9) & 7
    source_mode = (top >> 3) & 7
    source_register = top & 7
    source, used, target = effective_address(
        data, position, source_mode, source_register, size, base)
    destination, used2, _ = effective_address(
        data, position + used, destination_mode, destination_register, size, base)
    mnemonic = "movea" if destination_mode == 1 else "move"
    if mnemonic == "movea" and size == "b":
        raise Unsupported("movea byte")
    return f"{mnemonic}.{size}", used + used2, target, f"{source},{destination}"


def _arithmetic(name: str, top: int, data: bytes, position: int, base: int,
                allow_an_destination: bool = True):
    """ADD, SUB, AND, OR, EOR, CMP : la forme dépend des bits 8-6."""
    opmode = (top >> 6) & 7
    size_code = opmode & 3
    if size_code == 3:
        # forme ADDA/SUBA/CMPA
        if not allow_an_destination:
            raise Unsupported("addition to address register")
        size = "l" if opmode & 4 else "w"
        text, used, target = effective_address(
            data, position, (top >> 3) & 7, top & 7, size, base)
        return f"{name}a.{size}", used, target, f"{text},a{(top >> 9) & 7}"
    size = SIZES[size_code]
    register = (top >> 9) & 7
    mode = (top >> 3) & 7
    ea_register = top & 7
    if opmode & 4:
        # Dn → <ea>
        text, used, target = effective_address(
            data, position, mode, ea_register, size, base)
        return f"{name}.{size}", used, target, f"d{register},{text}"
    text, used, target = effective_address(
        data, position, mode, ea_register, size, base)
    return f"{name}.{size}", used, target, f"{text},d{register}"


def _quick(name: str, top: int, data: bytes, position: int, base: int):
    size_code = (top >> 6) & 3
    if size_code == 3:
        raise Unsupported("quick size")
    size = SIZES[size_code]
    value = (top >> 9) & 7
    if value == 0:
        value = 8
    text, used, target = effective_address(
        data, position, (top >> 3) & 7, top & 7, size, base)
    return f"{name}.{size}", used, target, f"#{value},{text}"


def _register_list(mask: int) -> str:
    """Liste ``d0-d3/a2`` à partir d'un masque MOVEM.

    Convention : le bit 0 correspond à ``d0``. Pour le mode pré-décrément, le
    processeur range le masque dans l'ordre inverse ; l'appelant le retourne
    avant de nous le confier.
    """
    parts = []
    for name, base in (("d", 0), ("a", 8)):
        start = None
        for index in range(8):
            bit = 1 << (base + index)
            if mask & bit:
                if start is None:
                    start = index
            elif start is not None:
                parts.append(f"{name}{start}-{name}{index - 1}"
                             if index - 1 > start else f"{name}{start}")
                start = None
        if start is not None:
            parts.append(f"{name}{start}-{name}7" if start < 7 else f"{name}7")
    return "/".join(parts) if parts else "-"


def _shift(top: int, data: bytes, position: int, base: int):
    """ASL, ASR, LSL, LSR, ROL, ROR, ROXL, ROXR.

    Deux formes : sur un registre de données (compte immédiat ou registre),
    et sur un opérande mémoire avec un compte de 1.
    """
    direction = "l" if top & 0x0100 else "r"
    size_code = (top >> 6) & 3
    if size_code == 3:
        kind = ("as", "ls", "rox", "ro")[(top >> 9) & 3]
        text, used, target = effective_address(
            data, position, (top >> 3) & 7, top & 7, "w", base)
        return f"{kind}{direction}.w", used, target, text
    size = SIZES[size_code]
    kind = ("as", "ls", "rox", "ro")[(top >> 3) & 3]
    name = f"{kind}{direction}.{size}"
    if top & 0x0020:
        return name, 0, None, f"d{(top >> 9) & 7},d{top & 7}"
    count = (top >> 9) & 7 or 8
    return name, 0, None, f"#{count},d{top & 7}"


def _muldiv(family: str, top: int, data: bytes, position: int, base: int):
    """MULU, MULS, DIVU, DIVS : bit 8 distingue signé et non signé.

    Le multiplicateur fait 16 bits, le diviseur 32 ; l'opérande source suit
    les modes d'adressage habituels.
    """
    signed = ((top >> 6) & 7) == 7
    name = f"{family}{'s' if signed else 'u'}"
    size = "w" if family == "mul" else "l"
    text, used, target = effective_address(
        data, position, (top >> 3) & 7, top & 7, size, base)
    return f"{name}.{size}", used, target, f"{text},d{(top >> 9) & 7}"


def _group5(top: int, data: bytes, position: int, base: int):
    """Groupe 5 : ADDQ, SUBQ, Scc, DBcc.

    Les bits 7-6 donnent la taille, sauf quand ils valent 11 : c'est alors
    soit un DBcc (mode 1, registre de données), soit un Scc. La direction
    d'ADDQ/SUBQ est portée par le bit 8.
    """
    mode = (top >> 3) & 7
    register = top & 7
    condition = (top >> 8) & 0x0F
    if (top & 0x00C0) == 0x00C0:
        if mode == 1:
            displacement = _signed16(_word(data, position))
            target = (position + 2 + base + displacement) & 0xFFFFFF
            return (f"db{CONDITIONS[condition]}", 2, target,
                    f"d{register},${target:06X}")
        text, used, target = effective_address(
            data, position, mode, register, "b", base)
        return f"s{CONDITIONS[condition]}", used, target, text
    return _quick("subq" if top & 0x0100 else "addq", top, data, position, base)


def _group6(top: int, data: bytes, position: int, base: int):
    condition = (top >> 8) & 0x0F
    displacement = _signed8(top & 0xFF)
    if displacement == 0:
        displacement = _signed16(_word(data, position))
        used = 2
    else:
        used = 0
    target = (position + base + displacement) & 0xFFFFFF
    name = "bra" if condition == 0 else "bsr" if condition == 1 \
        else f"b{CONDITIONS[condition]}"
    return name, used, target, f"${target:06X}"


def _group7(top: int, data: bytes, position: int, base: int):
    register = (top >> 9) & 7
    value = top & 0xFF
    signed = _signed8(value)
    return "moveq", 0, None, f"#${signed & 0xFF:02X},d{register}"


def _group4_misc(top: int, data: bytes, position: int, base: int):
    """RTS, RTE, NOP, STOP, TRAP, LINK, UNLK, SWAP, EXT, RESET, TRAPV."""
    code = top & 0xFFFF
    simple = {
        0x4E71: ("nop", 0), 0x4E72: ("stop", 2), 0x4E73: ("rte", 0),
        0x4E75: ("rts", 0), 0x4E76: ("trapv", 0), 0x4E77: ("rtr", 0),
        0x4E70: ("reset", 0), 0x4AFC: ("illegal", 0),
    }
    if code in simple:
        name, used = simple[code]
        if name == "stop":
            return name, used, None, f"#${_word(data, position):04X}"
        return name, used, None, ""
    if (code & 0xFFF0) == 0x4E40:
        return "trap", 0, None, f"#{code & 0x0F}"
    if (code & 0xFFF8) == 0x4E50:
        displacement = _signed16(_word(data, position))
        return "link", 2, None, f"a{code & 7},#${displacement & 0xFFFF:04X}"
    if (code & 0xFFF8) == 0x4E58:
        return "unlk", 0, None, f"a{code & 7}"
    if (code & 0xFF00) in (0x4000, 0x4200, 0x4400, 0x4600, 0x4A00):
        # NEGX / CLR / NEG / NOT / TST sur un opérande
        operation = {0x4000: "negx", 0x4200: "clr", 0x4400: "neg",
                     0x4600: "not", 0x4A00: "tst"}[code & 0xFF00]
        size_code = (code >> 6) & 3
        if size_code == 3:
            raise Unsupported("one-operand size")
        size = SIZES[size_code]
        text, used, target = effective_address(
            data, position, (code >> 3) & 7, code & 7, size, base)
        return f"{operation}.{size}", used, target, text
    if (code & 0xF1C0) == 0x41C0:
        # LEA : bits 8-6 = 111
        text, used, target = effective_address(
            data, position, (code >> 3) & 7, code & 7, "l", base)
        return "lea.l", used, target, f"{text},a{(code >> 9) & 7}"
    if (code & 0xFFC0) == 0x4840 and (code & 7):
        # PEA (le mode 0 est SWAP)
        text, used, target = effective_address(
            data, position, (code >> 3) & 7, code & 7, "l", base)
        return "pea.l", used, target, text
    if (code & 0xFFF8) == 0x4840:
        return "swap", 0, None, f"d{code & 7}"
    if (code & 0xFFF8) == 0x4880:
        return "ext.w", 0, None, f"d{code & 7}"
    if (code & 0xFFF8) == 0x48C0:
        return "ext.l", 0, None, f"d{code & 7}"
    if (code & 0xFF80) == 0x4E80:
        # JSR / JMP : bit 6 distingue le saut du sous-programme
        mode = (code >> 3) & 7
        register = code & 7
        text, used, target = effective_address(data, position, mode, register, "l", base)
        return ("jmp" if code & 0x40 else "jsr"), used, target, text
    if (code & 0xFB80) == 0x4880:
        # MOVEM : bit 10 = sens, bit 6 = taille
        to_registers = bool(code & 0x0400)
        size = "l" if code & 0x0040 else "w"
        mask = _word(data, position)
        mode = (code >> 3) & 7
        register = code & 7
        text, used, target = effective_address(
            data, position + 2, mode, register, size, base)
        if mode == 4:            # pré-décrément : masque inversé
            mask = int(f"{mask:016b}"[::-1], 2)
        names = _register_list(mask)
        if to_registers:
            return f"movem.{size}", 2 + used, target, f"{text},{names}"
        return f"movem.{size}", 2 + used, target, f"{names},{text}"
    if (code & 0xFFC0) == 0x4E00:
        # TRAP
        return "trap", 0, None, f"#{code & 0x0F}"
    raise Unsupported("group 4 misc")


# ---------------------------------------------------------------------------
# Décodage
# ---------------------------------------------------------------------------


def decode(data: bytes, offset: int, base: int = 0) -> Instruction:
    """Décode l'instruction 68000 à ``offset``."""
    if offset < 0 or offset + 1 >= len(data):
        raise ValueError("offset hors des données")
    top = _word(data, offset)
    position = offset + 2
    group = (top >> 12) & 0xF

    try:
        if group in (1, 2, 3):
            mnemonic, used, target, operand = _move(top, data, position, base)
        elif group == 0:
            mnemonic, used, target, operand = _group0(top, data, position, base)
        elif group == 4:
            mnemonic, used, target, operand = _group4_misc(top, data, position, base)
        elif group == 5:
            mnemonic, used, target, operand = _group5(top, data, position, base)
        elif group == 6:
            mnemonic, used, target, operand = _group6(top, data, position, base)
        elif group == 7:
            mnemonic, used, target, operand = _group7(top, data, position, base)
        elif group == 8:
            if ((top >> 6) & 7) in (3, 7):
                mnemonic, used, target, operand = _muldiv("div", top, data, position, base)
            else:
                mnemonic, used, target, operand = _arithmetic("or", top, data, position, base)
        elif group == 9:
            mnemonic, used, target, operand = _arithmetic("sub", top, data, position, base)
        elif group == 0xB:
            mnemonic, used, target, operand = _arithmetic("cmp", top, data, position, base)
        elif group == 0xC:
            if ((top >> 6) & 7) in (3, 7):
                mnemonic, used, target, operand = _muldiv("mul", top, data, position, base)
            else:
                mnemonic, used, target, operand = _arithmetic("and", top, data, position, base)
        elif group == 0xD:
            mnemonic, used, target, operand = _arithmetic("add", top, data, position, base)
        elif group == 0xE:
            mnemonic, used, target, operand = _shift(top, data, position, base)
        else:
            raise Unsupported(f"groupe {group}")
    except Unsupported:
        return Instruction(offset=offset, raw=data[offset:offset + 2],
                           mnemonic=".dc.w", mode="", operand=f"${top:04X}")

    raw = data[offset:offset + 2 + used]
    return Instruction(offset=offset, raw=raw, mnemonic=mnemonic, mode="",
                       operand=operand, target=target)


def _group0(top: int, data: bytes, position: int, base: int):
    """Groupe 0 : immédiats, BTST, décalages."""
    high = top & 0x0F00
    if high in (0x0000, 0x0200, 0x0400, 0x0600, 0x0A00, 0x0C00) \
            and (top & 0x00C0) != 0x00C0:
        operation = {0x0000: "ori", 0x0200: "andi", 0x0400: "subi",
                     0x0600: "addi", 0x0A00: "eori", 0x0C00: "cmpi"}[high]
        size_code = (top >> 6) & 3
        if size_code == 3:
            raise Unsupported("immediate size")
        size = SIZES[size_code]
        value = _long(data, position) if size == "l" else _word(data, position)
        used = 4 if size == "l" else 2
        text, used2, target = effective_address(
            data, position + used, (top >> 3) & 7, top & 7, size, base)
        literal = f"#${value:08X}" if size == "l" else f"#${value:04X}"
        return f"{operation}.{size}", used + used2, target, f"{literal},{text}"
    if high == 0x0800:
        # BTST/BCHG/BCLR/BSET avec un numéro de bit immédiat
        operation = ("btst", "bchg", "bclr", "bset")[(top >> 6) & 3]
        bit = _word(data, position)
        text, used, target = effective_address(
            data, position + 2, (top >> 3) & 7, top & 7, "b", base)
        return operation, 2 + used, target, f"#{bit},{text}"
    if high == 0x0000 and (top & 0x00C0) == 0x00C0:
        # BTST/BCHG/BCLR/BSET avec un registre
        operation = ("btst", "bchg", "bclr", "bset")[(top >> 6) & 3]
        text, used, target = effective_address(
            data, position, (top >> 3) & 7, top & 7, "b", base)
        return operation, used, target, f"d{(top >> 9) & 7},{text}"
    raise Unsupported("group 0")


def disassemble(data: bytes, offset: int, count: int = 32,
                base: int = 0) -> list[Instruction]:
    """Désassemble ``count`` instructions à partir de ``offset``."""
    out: list[Instruction] = []
    position = offset
    while len(out) < count and position < len(data) - 1:
        try:
            instruction = decode(data, position, base)
        except ValueError:
            break
        out.append(instruction)
        position += instruction.size
    return out


def format_listing(instructions: list[Instruction]) -> str:
    """Rendu texte, une instruction par ligne."""
    return "\n".join(
        f"{ins.offset:06X}: {ins.raw.hex(' '):<14s} {ins.text}"
        for ins in instructions)


def trace(data: bytes, entry: int, max_instructions: int = 20000,
          base: int = 0) -> list[Instruction]:
    """Suit le fil d'exécution depuis l'adresse ``entry``.

    Les sous-programmes sont suivis avec une pile de retours : ``jsr``/``bsr``
    empilent l'adresse suivante, ``rts``/``rte``/``rtr`` la dépilent.
    """
    seen: set[int] = set()
    pending = [entry - base]
    returns: list[int] = []
    out: list[Instruction] = []
    bit_ops = ("btst", "bchg", "bclr", "bset")

    def valid(address: int | None) -> int | None:
        if address is None:
            return None
        position = address - base
        return position if 0 <= position < len(data) - 1 else None

    while pending and len(out) < max_instructions:
        position = pending.pop()
        while 0 <= position < len(data) - 1 and len(out) < max_instructions:
            if position in seen:
                break
            seen.add(position)
            try:
                instruction = decode(data, position, base)
            except ValueError:
                break
            out.append(instruction)
            next_position = position + instruction.size
            mnemonic = instruction.mnemonic

            if mnemonic in ("jsr", "bsr"):
                target = valid(instruction.target)
                if target is not None and target not in seen:
                    returns.append(next_position)
                    position = target
                    continue
                position = next_position
                continue

            if mnemonic in ("rts", "rte", "rtr"):
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

            if mnemonic.startswith("b") and mnemonic not in bit_ops:
                target = valid(instruction.target)
                if target is not None and target not in seen:
                    pending.append(target)
                if mnemonic == "bra":
                    break
                position = next_position
                continue

            if mnemonic in ("illegal", "stop"):
                break
            position = next_position
    return out


def entry_points(data: bytes) -> dict:
    """Vecteurs du 68000 d'une cartouche Mega Drive.

    Le premier long est la pile initiale, le second l'adresse d'exécution.
    """
    if len(data) < 8:
        return {}
    return {"stack": _long(data, 0), "reset": _long(data, 4)}
