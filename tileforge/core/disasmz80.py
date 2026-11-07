"""Désassembleur Z80 (ZX Spectrum, Amstrad CPC, MSX, Game Boy…).

Le Z80 équipe la plupart des ordinateurs 8 bits européens et japonais des
années 1980. Son encodage est remarquablement régulier : un octet se lit comme
``xx yyy zzz`` (deux bits de groupe, trois bits d'opération, trois bits
d'opérande). Plutôt que de recopier une table de 1 500 entrées, ce module
**reconstruit** les instructions à partir de ces règles, ce qui rend les
erreurs de transcription impossibles et le code lisible.

Les préfixes ``CB``, ``ED``, ``DD`` et ``FD`` sont traités séparément, comme le
fait le processeur. Les codes réellement indéfinis sortent en ``.db``.

Le Game Boy utilise un dérivé (SM83) : la majorité des opcodes se lit de la
même façon, mais certains diffèrent — voir ``SM83_DIFFERENCES``.

Le module ne dépend ni de Qt ni de l'interface.
"""

from __future__ import annotations

from .disasm65816 import Instruction

#: Registres 8 bits, indexés par les trois bits ``zzz``.
R8 = ("b", "c", "d", "e", "h", "l", "(hl)", "a")

#: Paires de registres 16 bits.
RP = ("bc", "de", "hl", "sp")

#: Paires utilisées par PUSH et POP.
RP2 = ("bc", "de", "hl", "af")

#: Conditions de saut.
CC = ("nz", "z", "nc", "c", "po", "pe", "p", "m")

#: Opérations arithmétiques et logiques du groupe 2.
ALU = ("add a,", "adc a,", "sub ", "sbc a,", "and ", "xor ", "or ", "cp ")

#: Opérations de rotation du préfixe CB.
CB_ROT = ("rlc", "rrc", "rl", "rr", "sla", "sra", "sll", "srl")

#: Opérations du préfixe ED qui suivent la règle ``ED y z``.
ED_BLOCK = {
    0x40: "in b,(c)", 0x41: "out (c),b", 0x42: "sbc hl,bc", 0x43: "ld (nn),bc",
    0x44: "neg", 0x45: "retn", 0x46: "im 0", 0x47: "ld i,a",
    0x48: "in c,(c)", 0x49: "out (c),c", 0x4A: "adc hl,bc", 0x4B: "ld bc,(nn)",
    0x4C: "neg", 0x4D: "reti", 0x4E: "im 0", 0x4F: "ld r,a",
    0x50: "in d,(c)", 0x51: "out (c),d", 0x52: "sbc hl,de", 0x53: "ld (nn),de",
    0x54: "neg", 0x55: "retn", 0x56: "im 1", 0x57: "ld a,i",
    0x58: "in e,(c)", 0x59: "out (c),e", 0x5A: "adc hl,de", 0x5B: "ld de,(nn)",
    0x5C: "neg", 0x5D: "retn", 0x5E: "im 2", 0x5F: "ld a,r",
    0x60: "in h,(c)", 0x61: "out (c),h", 0x62: "sbc hl,hl", 0x63: "ld (nn),hl",
    0x64: "neg", 0x65: "retn", 0x66: "im 0", 0x67: "rrd",
    0x68: "in l,(c)", 0x69: "out (c),l", 0x6A: "adc hl,hl", 0x6B: "ld hl,(nn)",
    0x6C: "neg", 0x6D: "retn", 0x6E: "im 0", 0x6F: "rld",
    0x70: "in (c)", 0x71: "out (c),0", 0x72: "sbc hl,sp", 0x73: "ld (nn),sp",
    0x74: "neg", 0x75: "retn", 0x76: "im 1", 0x77: "nop",
    0x78: "in a,(c)", 0x79: "out (c),a", 0x7A: "adc hl,sp", 0x7B: "ld sp,(nn)",
    0x7C: "neg", 0x7D: "retn", 0x7E: "im 2", 0x7F: "nop",
    0xA0: "ldi", 0xA1: "cpi", 0xA2: "ini", 0xA3: "outi",
    0xA8: "ldd", 0xA9: "cpd", 0xAA: "ind", 0xAB: "outd",
    0xB0: "ldir", 0xB1: "cpir", 0xB2: "inir", 0xB3: "otir",
    0xB8: "lddr", 0xB9: "cpdr", 0xBA: "indr", 0xBB: "otdr",
}

#: Opcodes du SM83 (Game Boy) qui diffèrent du Z80.
#:
#: Chaque entrée donne (mnemonic, taille de l'opérande, texte). Les valeurs
#: ``None`` marquent un code invalide, rendu en ``.db``.
SM83_OPS: dict[int, tuple[str, int, str] | None] = {
    0x08: ("ld", 2, "ld ({nn}),sp"),
    0x10: ("stop", 1, "stop {n}"),
    0x22: ("ld", 0, "ld (hl+),a"),
    0x2A: ("ld", 0, "ld a,(hl+)"),
    0x32: ("ld", 0, "ld (hl-),a"),
    0x3A: ("ld", 0, "ld a,(hl-)"),
    0xD3: None, 0xDB: None, 0xDD: None,
    0xE0: ("ldh", 1, "ldh ({n}),a"),
    0xE3: None, 0xE4: None,
    0xE8: ("add sp", 1, "add sp,{off}"),
    0xEA: ("ld", 2, "ld ({nn}),a"),
    0xEB: None, 0xEC: None, 0xED: None,
    0xF0: ("ldh", 1, "ldh a,({n})"),
    0xF4: None,
    0xF8: ("ld hl", 1, "ld hl,sp{off}"),
    0xFA: ("ld", 2, "ld a,({nn})"),
    0xFD: None,
}

#: Opérations CB propres au SM83 (0x30-0x37 : SWAP au lieu de SLL).
SM83_CB_ROT = ("rlc", "rrc", "rl", "rr", "sla", "sra", "swap", "srl")


def _signed(value: int) -> int:
    return value - 256 if value >= 128 else value


def _hex8(value: int) -> str:
    return f"${value:02X}"


def _hex16(value: int) -> str:
    return f"${value:04X}"


def _decode_main(opcode: int, prefix: str = "") -> tuple[str, int, str]:
    """Décode un octet de la table principale.

    Renvoie ``(mnemonic, taille_opérande, texte)`` ; la taille ne compte pas
    l'octet d'opcode lui-même.
    """
    x, y, z = opcode >> 6, (opcode >> 3) & 7, opcode & 7
    p, q = y >> 1, y & 1
    # substitutions pour les préfixes DD/FD (IX/IY à la place de HL)
    high = "ix" if prefix == "dd" else "iy" if prefix == "fd" else "hl"
    reg = list(R8)
    if prefix in ("dd", "fd"):
        reg[4] = high[0] + high[1] if False else ("ixh" if prefix == "dd" else "iyh")
        reg[5] = "ixl" if prefix == "dd" else "iyl"
        reg[6] = f"({high}+d)"
    pair = list(RP)
    if prefix in ("dd", "fd"):
        pair[2] = high
    pair2 = list(RP2)
    if prefix in ("dd", "fd"):
        pair2[2] = high

    if x == 0:
        if z == 0:
            if y == 0:
                return "nop", 0, "nop"
            if y == 1:
                return "ex af,af'", 0, "ex af,af'"
            if y == 2:
                return "djnz", 1, "djnz {d}"
            if y == 3:
                return "jr", 1, "jr {d}"
            return "jr", 1, f"jr {CC[y - 4]},{{d}}"
        if z == 1:
            if q == 0:
                return "ld", 2, f"ld {pair[p]},{{nn}}"
            return "add hl", 0, f"add {high},{pair[p]}"
        if z == 2:
            if q == 0:
                if p == 0:
                    return "ld", 0, "ld (bc),a"
                if p == 1:
                    return "ld", 0, "ld (de),a"
                if p == 2:
                    return "ld", 2, f"ld ({{nn}}),{high}"
                return "ld", 2, "ld ({nn}),a"
            if p == 0:
                return "ld", 0, "ld a,(bc)"
            if p == 1:
                return "ld", 0, "ld a,(de)"
            if p == 2:
                return "ld", 2, f"ld {high},({{nn}})"
            return "ld", 2, "ld a,({nn})"
        if z == 3:
            return ("inc" if q == 0 else "dec"), 0, \
                f"{'inc' if q == 0 else 'dec'} {pair[p]}"
        if z == 4:
            return "inc", 0, f"inc {reg[y]}"
        if z == 5:
            return "dec", 0, f"dec {reg[y]}"
        if z == 6:
            return "ld", 1, f"ld {reg[y]},{{n}}"
        ops = ("rlca", "rrca", "rla", "rra", "daa", "cpl", "scf", "ccf")
        return ops[y], 0, ops[y]

    if x == 1:
        if y == 6 and z == 6:
            return "halt", 0, "halt"
        return "ld", 0, f"ld {reg[y]},{reg[z]}"

    if x == 2:
        return "alu", 0, f"{ALU[y]}{reg[z]}"

    # x == 3
    if z == 0:
        return "ret", 0, f"ret {CC[y]}"
    if z == 1:
        if q == 0:
            return "pop", 0, f"pop {pair2[p]}"
        if p == 0:
            return "ret", 0, "ret"
        if p == 1:
            return "exx", 0, "exx"
        if p == 2:
            return "jp", 0, f"jp ({high})"
        return "ld sp", 0, f"ld sp,{high}"
    if z == 2:
        return "jp", 2, f"jp {CC[y]},{{nn}}"
    if z == 3:
        if y == 0:
            return "jp", 2, "jp {nn}"
        if y == 1:
            return "prefix", 0, "cb"
        if y == 2:
            return "out", 1, "out ({n}),a"
        if y == 3:
            return "in", 1, "in a,({n})"
        if y == 4:
            return "ex (sp),hl", 0, f"ex (sp),{high}"
        if y == 5:
            return "ex de,hl", 0, "ex de,hl"
        if y == 6:
            return "di", 0, "di"
        return "ei", 0, "ei"
    if z == 4:
        return "call", 2, f"call {CC[y]},{{nn}}"
    if z == 5:
        if q == 0:
            return "push", 0, f"push {pair2[p]}"
        if p == 0:
            return "call", 2, "call {nn}"
        if p == 1:
            return "prefix", 0, "dd"
        if p == 2:
            return "prefix", 0, "ed"
        return "prefix", 0, "fd"
    if z == 6:
        return "alu", 1, f"{ALU[y]}{{n}}"
    return "rst", 0, f"rst ${y * 8:02X}"


def _decode_cb(opcode: int, index: str = "") -> tuple[str, int, str]:
    """Décode un opcode du préfixe CB (rotations, bit, res, set)."""
    x, y, z = opcode >> 6, (opcode >> 3) & 7, opcode & 7
    target = R8[z]
    if index:
        target = f"({index}+d)" if z == 6 else R8[z]
    if x == 0:
        return CB_ROT[y], 0, f"{CB_ROT[y]} {target}"
    if x == 1:
        return "bit", 0, f"bit {y},{target}"
    if x == 2:
        return "res", 0, f"res {y},{target}"
    return "set", 0, f"set {y},{target}"


def _decode_ed(opcode: int) -> tuple[str, int, str] | None:
    """Décode un opcode du préfixe ED, ou ``None`` s'il est indéfini."""
    if opcode in ED_BLOCK:
        text = ED_BLOCK[opcode].replace("(nn)", "({nn})")
        size = 2 if "{nn}" in text else 0
        return "ed", size, text
    # les formes (nn) du bloc
    x, y, z = opcode >> 6, (opcode >> 3) & 7, opcode & 7
    if x == 1 and z == 3 and y in (0, 1, 2, 3, 6, 7):
        names = {0: "ld ({nn}),bc", 1: "ld ({nn}),de", 2: "ld ({nn}),hl",
                 3: "ld ({nn}),sp", 6: "ld hl,({nn})", 7: "ld sp,({nn})"}
        if y in names:
            return "ed", 2, names[y]
    if x == 1 and z == 2 and y in (4, 5, 6, 7):
        return "ed", 2, ("sbc hl,bc", "adc hl,bc", "sbc hl,de", "adc hl,de")[y - 4]
    return None


def _format_with_operand(text: str, raw: bytes, position: int,
                         base: int = 0) -> tuple[str, int | None]:
    """Remplace ``{n}``, ``{nn}`` et ``{d}`` par les octets lus."""
    target = None
    if "{n}" in text:
        value = raw[0] if len(raw) > 0 else 0
        text = text.replace("{n}", _hex8(value))
    if "{nn}" in text:
        value = raw[0] | (raw[1] << 8) if len(raw) > 1 else 0
        text = text.replace("{nn}", _hex16(value))
        # nn est déjà une adresse processeur : on n'y ajoute pas la base
        target = value
    if "{off}" in text:
        value = _signed(raw[0]) if len(raw) > 0 else 0
        text = text.replace("{off}", f"{value:+d}".replace("+-", "-"))
    if "{d}" in text:
        delta = _signed(raw[0]) if len(raw) > 0 else 0
        address = (position + len(raw) + delta + base) & 0xFFFF
        text = text.replace("{d}", _hex16(address))
        target = address
    return text, target


def decode(data: bytes, offset: int, base: int = 0,
           variant: str = "z80") -> Instruction:
    """Décode l'instruction Z80 (ou SM83) à ``offset``.

    ``variant="sm83"`` applique les différences du Game Boy : pas de
    préfixes IX/IY, quelques opcodes réaffectés, ``swap`` à la place de
    ``sll``, et dix codes invalides.
    """
    if offset < 0 or offset >= len(data):
        raise ValueError("offset hors des données")
    start = offset
    prefix = ""
    opcode = data[offset]
    consumed = 1

    if variant == "sm83":
        special = SM83_OPS.get(opcode)
        if opcode in SM83_OPS and special is None:
            return Instruction(offset=start, raw=data[offset:offset + 1],
                               mnemonic=".db", mode="", operand=f"${opcode:02X}")
        if special is not None:
            mnemonic, size, text = special
            raw = data[offset:offset + 1 + size]
            if len(raw) < 1 + size:
                raise ValueError("instruction tronquée")
            text, target = _format_with_operand(text, raw[1:], offset + 1, base)
            parts = text.split(" ", 1)
            return Instruction(offset=start, raw=raw, mnemonic=parts[0],
                               mode="sm83", operand=parts[1] if len(parts) > 1 else "",
                               target=target)
        if opcode in (0xCB,):
            if offset + 1 >= len(data):
                raise ValueError("préfixe CB tronqué")
            cb = data[offset + 1]
            x, y, z = cb >> 6, (cb >> 3) & 7, cb & 7
            target_name = R8[z]
            if x == 0:
                operation = SM83_CB_ROT[y]
                return Instruction(offset=start, raw=data[offset:offset + 2],
                                   mnemonic=operation, mode="cb",
                                   operand=target_name)
            operation = ("bit", "res", "set")[x - 1]
            return Instruction(offset=start, raw=data[offset:offset + 2],
                               mnemonic=operation, mode="cb",
                               operand=f"{y},{target_name}")
        if opcode in (0xDD, 0xFD, 0xED):
            return Instruction(offset=start, raw=data[offset:offset + 1],
                               mnemonic=".db", mode="", operand=f"${opcode:02X}")

    if opcode in (0xDD, 0xFD) and offset + 1 < len(data):
        prefix = "dd" if opcode == 0xDD else "fd"
        opcode = data[offset + 1]
        consumed = 2
        if opcode == 0xCB:
            # DDCB : un octet de déplacement, puis l'opcode
            if offset + 3 >= len(data):
                raise ValueError("préfixe DDCB tronqué")
            displacement = data[offset + 2]
            cb = data[offset + 3]
            index = "ix" if prefix == "dd" else "iy"
            mnemonic, size, text = _decode_cb(cb, index)
            raw = data[offset:offset + 4]
            text = text.replace("+d", f"+{_signed(displacement):+d}".replace("+-", "-"))
            if cb < 0x40 or cb >= 0x80:
                # les formes indexées avec registre de destination
                z = cb & 7
                if z != 6:
                    text += f",{R8[z]}"
            return Instruction(offset=start, raw=raw, mnemonic=mnemonic,
                               mode="indexed", operand=text.split(" ", 1)[1]
                               if " " in text else "")
        if opcode in (0xDD, 0xFD):
            # préfixe redoublé : ignoré par le processeur
            return decode(data, offset + 1, base)

    if opcode == 0xCB and not prefix:
        if offset + 1 >= len(data):
            raise ValueError("préfixe CB tronqué")
        cb = data[offset + 1]
        mnemonic, _, text = _decode_cb(cb)
        return Instruction(offset=start, raw=data[offset:offset + 2],
                           mnemonic=mnemonic, mode="cb",
                           operand=text.split(" ", 1)[1] if " " in text else "")

    if opcode == 0xED and not prefix:
        if offset + 1 >= len(data):
            raise ValueError("préfixe ED tronqué")
        ed = data[offset + 1]
        result = _decode_ed(ed)
        if result is None:
            return Instruction(offset=start, raw=data[offset:offset + 2],
                               mnemonic=".db", mode="", operand="ed")
        _, size, text = result
        raw = data[offset:offset + 2 + size]
        if len(raw) < 2 + size:
            raise ValueError("instruction ED tronquée")
        text, target = _format_with_operand(text, raw[2:], offset + 2, base)
        mnemonic = text.split(" ", 1)[0]
        operand = text.split(" ", 1)[1] if " " in text else ""
        return Instruction(offset=start, raw=raw, mnemonic=mnemonic,
                           mode="ed", operand=operand, target=target)

    mnemonic, size, text = _decode_main(opcode, prefix)
    if prefix and ("(ix+d)" in text or "(iy+d)" in text):
        text = text.replace("(ix+d)", "(ix{off})").replace("(iy+d)", "(iy{off})")
        size = 1
    if mnemonic == "prefix":
        # un préfixe sans suite valable : on le rend tel quel
        return Instruction(offset=start, raw=data[offset:offset + consumed],
                           mnemonic=f".{text}", mode="", operand="")
    if mnemonic == "alu":
        text = text
    raw = data[offset:offset + consumed + size]
    if len(raw) < consumed + size:
        raise ValueError("instruction tronquée")
    operand_bytes = raw[consumed:]
    text, target = _format_with_operand(text, operand_bytes, offset + consumed, base)
    parts = text.split(" ", 1)
    return Instruction(offset=start, raw=raw, mnemonic=parts[0],
                       mode=prefix or "main",
                       operand=parts[1] if len(parts) > 1 else "",
                       target=target)


def disassemble(data: bytes, offset: int, count: int = 32,
                base: int = 0, variant: str = "z80") -> list[Instruction]:
    """Désassemble ``count`` instructions à partir de ``offset``."""
    out: list[Instruction] = []
    position = offset
    while len(out) < count and position < len(data):
        try:
            instruction = decode(data, position, base, variant)
        except ValueError:
            break
        out.append(instruction)
        position += instruction.size
    return out


def format_listing(instructions: list[Instruction]) -> str:
    """Rendu texte, une instruction par ligne."""
    return "\n".join(
        f"{ins.offset:06X}: {ins.raw.hex(' '):<12s} {ins.text}"
        for ins in instructions)


def trace(data: bytes, entry: int, max_instructions: int = 20000,
          base: int = 0, variant: str = "z80") -> list[Instruction]:
    """Suit le fil d'exécution depuis l'adresse ``entry``."""
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
                instruction = decode(data, position, base, variant)
            except ValueError:
                break
            out.append(instruction)
            next_position = position + instruction.size
            mnemonic = instruction.mnemonic

            if mnemonic in ("call", "call nz", "call z", "call nc", "call c",
                            "call po", "call pe", "call p", "call m"):
                target = valid(instruction.target)
                if target is not None and target not in seen:
                    returns.append(next_position)
                    position = target
                    continue
                position = next_position
                continue

            if mnemonic in ("ret", "retn", "reti") or mnemonic.startswith("ret "):
                if returns:
                    position = returns.pop()
                    continue
                break

            if mnemonic in ("jp", "jp nz", "jp z", "jp nc", "jp c", "jp po",
                            "jp pe", "jp p", "jp m"):
                target = valid(instruction.target)
                if target is not None and target not in seen:
                    position = target
                    continue
                break

            if mnemonic == "jr" or (mnemonic.startswith("jr ") and mnemonic != "jr"):
                target = valid(instruction.target)
                if target is not None and target not in seen:
                    pending.append(target)
                position = next_position
                continue

            if mnemonic in ("djnz",):
                target = valid(instruction.target)
                if target is not None and target not in seen:
                    pending.append(target)
                position = next_position
                continue

            if mnemonic == "halt":
                break
            position = next_position
    return out
