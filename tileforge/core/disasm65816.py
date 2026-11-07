"""Désassembleur 65816 (Super Nintendo).

Le 65816 est le processeur de la SNES. Ce module décode une instruction, une
suite d'instructions, et surtout **les adresses que le code référence** : c'est
ce qui permet de remonter d'une routine jusqu'aux données qu'elle charge, et
donc de retrouver des graphismes quand les formats résistent.

La table des opcodes vient du désassembleur `andlabs/65816disasm` (licence
GPL-3.0), elle-même vérifiée contre la documentation WDC ; elle est reproduite
ici sous forme de données, sans code.

Le module ne dépend ni de Qt ni de l'interface.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Taille de l'opérande, en octets, pour chaque mode d'adressage.
MODE_SIZE: dict[str, int] = {
    "implied": 0,
    "accumulator": 0,
    "immediate": 1,
    "direct": 1,
    "directx": 1,
    "directy": 1,
    "indirect": 1,
    "indirectlong": 1,
    "indirectx": 1,
    "indirecty": 1,
    "indirectlongy": 1,
    "stack": 1,
    "indirectstack": 1,
    "relative": 1,
    "absolute": 2,
    "absolutex": 2,
    "absolutey": 2,
    "indirect16": 2,
    "indirect16x": 2,
    "relative16": 2,
    "transfer": 2,
    "absolutelong": 3,
    "absolutelongx": 3,
    "indirectlong16": 3,
}

#: Modes dont l'opérande est une adresse absolue (donc une référence utile).
ABSOLUTE_MODES = {"absolute", "absolutex", "absolutey", "absolutelong",
                  "absolutelongx"}

#: Instructions qui interrompent le fil d'exécution.
CONTROL_FLOW = {"jsr", "jmp", "jsl", "rts", "rtl", "rti", "bra", "brl",
                "beq", "bne", "bcc", "bcs", "bpl", "bmi", "bvc", "bvs",
                "blt", "bge"}


OPCODES = (
    ("brk", "immediate"),
    ("ora", "indirectx"),
    ("cop", "immediate"),
    ("ora", "stack"),
    ("tsb", "direct"),
    ("ora", "direct"),
    ("asl", "direct"),
    ("ora", "indirectlong"),
    ("php", "implied"),
    ("ora", "immediate"),
    ("asl", "accumulator"),
    ("phd", "implied"),
    ("tsb", "absolute"),
    ("ora", "absolute"),
    ("asl", "absolute"),
    ("ora", "absolutelong"),
    ("bpl", "relative"),
    ("ora", "indirecty"),
    ("ora", "indirect"),
    ("ora", "indirectstack"),
    ("trb", "direct"),
    ("ora", "directx"),
    ("asl", "directx"),
    ("ora", "indirectlongy"),
    ("clc", "implied"),
    ("ora", "absolutey"),
    ("inc", "accumulator"),
    ("tas", "implied"),
    ("trb", "absolute"),
    ("ora", "absolutex"),
    ("asl", "absolutex"),
    ("ora", "absolutelongx"),
    ("jsr", "absolute"),
    ("and", "indirectx"),
    ("jsl", "absolutelong"),
    ("and", "stack"),
    ("bit", "direct"),
    ("and", "direct"),
    ("rol", "direct"),
    ("and", "indirectlong"),
    ("plp", "implied"),
    ("and", "immediate"),
    ("rol", "accumulator"),
    ("pld", "implied"),
    ("bit", "absolute"),
    ("and", "absolute"),
    ("rol", "absolute"),
    ("and", "absolutelong"),
    ("bmi", "relative"),
    ("and", "indirecty"),
    ("and", "indirect"),
    ("and", "indirectstack"),
    ("bit", "directx"),
    ("and", "directx"),
    ("rol", "directx"),
    ("and", "indirectlongy"),
    ("sec", "implied"),
    ("and", "absolutey"),
    ("dec", "accumulator"),
    ("tsa", "implied"),
    ("bit", "absolutex"),
    ("and", "absolutex"),
    ("rol", "absolutex"),
    ("and", "absolutelongx"),
    ("rti", "implied"),
    ("eor", "indirectx"),
    ("wdm", "immediate"),
    ("eor", "stack"),
    ("mvp", "transfer"),
    ("eor", "direct"),
    ("lsr", "direct"),
    ("eor", "indirectlong"),
    ("pha", "implied"),
    ("eor", "immediate"),
    ("lsr", "accumulator"),
    ("phk", "implied"),
    ("jmp", "absolute"),
    ("eor", "absolute"),
    ("lsr", "absolute"),
    ("eor", "absolutelong"),
    ("bvc", "relative"),
    ("eor", "indirecty"),
    ("eor", "indirect"),
    ("eor", "indirectstack"),
    ("mvn", "transfer"),
    ("eor", "directx"),
    ("lsr", "directx"),
    ("eor", "indirectlongy"),
    ("cli", "implied"),
    ("eor", "absolutey"),
    ("phy", "implied"),
    ("tad", "implied"),
    ("jml", "absolutelong"),
    ("eor", "absolutex"),
    ("lsr", "absolutex"),
    ("eor", "absolutelongx"),
    ("rts", "implied"),
    ("adc", "indirectx"),
    ("per", "relative16"),
    ("adc", "stack"),
    ("stz", "direct"),
    ("adc", "direct"),
    ("ror", "direct"),
    ("adc", "indirectlong"),
    ("pla", "implied"),
    ("adc", "immediate"),
    ("ror", "accumulator"),
    ("rtl", "implied"),
    ("jmp", "indirect16"),
    ("adc", "absolute"),
    ("ror", "absolute"),
    ("adc", "absolutelong"),
    ("bvs", "relative"),
    ("adc", "indirecty"),
    ("adc", "indirect"),
    ("adc", "indirectstack"),
    ("stz", "directx"),
    ("adc", "directx"),
    ("ror", "directx"),
    ("adc", "indirectlongy"),
    ("sei", "implied"),
    ("adc", "absolutey"),
    ("ply", "implied"),
    ("tda", "implied"),
    ("jmp", "indirect16x"),
    ("adc", "absolutex"),
    ("ror", "absolutex"),
    ("adc", "absolutelongx"),
    ("bra", "relative"),
    ("sta", "indirectx"),
    ("brl", "relative16"),
    ("sta", "stack"),
    ("sty", "direct"),
    ("sta", "direct"),
    ("stx", "direct"),
    ("sta", "indirectlong"),
    ("dey", "implied"),
    ("bit", "immediate"),
    ("txa", "implied"),
    ("phb", "implied"),
    ("sty", "absolute"),
    ("sta", "absolute"),
    ("stx", "absolute"),
    ("sta", "absolutelong"),
    ("blt", "relative"),
    ("sta", "indirecty"),
    ("sta", "indirect"),
    ("sta", "indirectstack"),
    ("sty", "directx"),
    ("sta", "directx"),
    ("stx", "directy"),
    ("sta", "indirectlongy"),
    ("tya", "implied"),
    ("sta", "absolutey"),
    ("txs", "implied"),
    ("txy", "implied"),
    ("stz", "absolute"),
    ("sta", "absolutex"),
    ("stz", "absolutex"),
    ("sta", "absolutelongx"),
    ("ldy", "immediate"),
    ("lda", "indirectx"),
    ("ldx", "immediate"),
    ("lda", "stack"),
    ("ldy", "direct"),
    ("lda", "direct"),
    ("ldx", "direct"),
    ("lda", "indirectlong"),
    ("tay", "implied"),
    ("lda", "immediate"),
    ("tax", "implied"),
    ("plb", "implied"),
    ("ldy", "absolute"),
    ("lda", "absolute"),
    ("ldx", "absolute"),
    ("lda", "absolutelong"),
    ("bge", "relative"),
    ("lda", "indirecty"),
    ("lda", "indirect"),
    ("lda", "indirectstack"),
    ("ldy", "directx"),
    ("lda", "directx"),
    ("ldx", "directy"),
    ("lda", "indirectlongy"),
    ("clv", "implied"),
    ("lda", "absolutey"),
    ("tsx", "implied"),
    ("tyx", "implied"),
    ("ldy", "absolutex"),
    ("lda", "absolutex"),
    ("ldx", "absolutey"),
    ("lda", "absolutelongx"),
    ("cpy", "immediate"),
    ("cmp", "indirectx"),
    ("rep", "immediate"),
    ("cmp", "stack"),
    ("cpy", "direct"),
    ("cmp", "direct"),
    ("dec", "direct"),
    ("cmp", "indirectlong"),
    ("iny", "implied"),
    ("cmp", "immediate"),
    ("dex", "implied"),
    ("wai", "implied"),
    ("cpy", "absolute"),
    ("cmp", "absolute"),
    ("dec", "absolute"),
    ("cmp", "absolutelong"),
    ("bne", "relative"),
    ("cmp", "indirecty"),
    ("cmp", "indirect"),
    ("cmp", "indirectstack"),
    ("pei", "indirect"),
    ("cmp", "directx"),
    ("dec", "directx"),
    ("cmp", "indirectlongy"),
    ("cld", "implied"),
    ("cmp", "absolutey"),
    ("phx", "implied"),
    ("stp", "implied"),
    ("jmp", "indirectlong16"),
    ("cmp", "absolutex"),
    ("dec", "absolutex"),
    ("cmp", "absolutelongx"),
    ("cpx", "immediate"),
    ("sbc", "indirectx"),
    ("sep", "immediate"),
    ("sbc", "stack"),
    ("cpx", "direct"),
    ("sbc", "direct"),
    ("inc", "direct"),
    ("sbc", "indirectlong"),
    ("inx", "implied"),
    ("sbc", "immediate"),
    ("nop", "implied"),
    ("xba", "implied"),
    ("cpx", "absolute"),
    ("sbc", "absolute"),
    ("inc", "absolute"),
    ("sbc", "absolutelong"),
    ("beq", "relative"),
    ("sbc", "indirecty"),
    ("sbc", "indirect"),
    ("sbc", "indirectstack"),
    ("pea", "absolute"),
    ("sbc", "directx"),
    ("inc", "directx"),
    ("sbc", "indirectlongy"),
    ("sed", "implied"),
    ("sbc", "absolutey"),
    ("plx", "implied"),
    ("xce", "implied"),
    ("jsr", "indirect16x"),
    ("sbc", "absolutex"),
    ("inc", "absolutex"),
    ("sbc", "absolutelongx"),
)


@dataclass
class Instruction:
    """Une instruction décodée."""

    offset: int
    raw: bytes
    mnemonic: str
    mode: str
    operand: str = ""
    target: int | None = None

    @property
    def size(self) -> int:
        return len(self.raw)

    @property
    def text(self) -> str:
        return f"{self.mnemonic} {self.operand}".strip()

    @property
    def is_control_flow(self) -> bool:
        return self.mnemonic in CONTROL_FLOW

    def as_dict(self) -> dict:
        return {"offset": self.offset, "offset_hex": f"0x{self.offset:06X}",
                "bytes": self.raw.hex(" "), "mnemonic": self.mnemonic,
                "operand": self.operand, "text": self.text,
                "target": self.target}


def _format(mode: str, value: int, target: int | None, raw: bytes) -> str:
    """Met en forme l'opérande d'une instruction."""
    if mode in ("implied",):
        return ""
    if mode == "accumulator":
        return "A"
    if mode == "immediate":
        return f"#${value:02X}" if len(raw) < 3 else f"#${value:04X}"
    if mode == "direct":
        return f"${value:02X}"
    if mode == "directx":
        return f"${value:02X},X"
    if mode == "directy":
        return f"${value:02X},Y"
    if mode == "indirect":
        return f"(${value:02X})"
    if mode == "indirectlong":
        return f"[${value:02X}]"
    if mode == "indirectx":
        return f"(${value:02X},X)"
    if mode == "indirecty":
        return f"(${value:02X}),Y"
    if mode == "indirectlongy":
        return f"[${value:02X}],Y"
    if mode == "stack":
        return f"${value:02X},S"
    if mode == "indirectstack":
        return f"(${value:02X},S),Y"
    if mode == "absolute":
        return f"${value:04X}"
    if mode == "absolutex":
        return f"${value:04X},X"
    if mode == "absolutey":
        return f"${value:04X},Y"
    if mode == "absolutelong":
        return f"${value:06X}"
    if mode == "absolutelongx":
        return f"${value:06X},X"
    if mode == "indirect16":
        return f"(${value:04X})"
    if mode == "indirect16x":
        return f"(${value:04X},X)"
    if mode == "indirectlong16":
        return f"[${value:06X}]"
    if mode == "relative":
        return f"${target:04X}" if target is not None else f"${value:02X}"
    if mode == "relative16":
        return f"${target:06X}" if target is not None else f"${value:04X}"
    if mode == "transfer":
        return f"${raw[1]:02X},${raw[2]:02X}"
    return f"${value:02X}"


def decode(data: bytes, offset: int, m_bits: int = 8) -> Instruction:
    """Décode l'instruction à ``offset``.

    ``m_bits`` vaut 8 ou 16 : il ne change pas la taille des instructions du
    65816 (l'opérande immédiat fait toujours un octet dans le flux), mais il
    indique comment l'afficher.
    """
    if offset < 0 or offset >= len(data):
        raise ValueError("offset hors des données")
    opcode = data[offset]
    mnemonic, mode = OPCODES[opcode]
    size = MODE_SIZE.get(mode, 1)
    raw = data[offset:offset + 1 + size]
    if len(raw) < 1 + size:
        raise ValueError("instruction tronquée")

    value = 0
    if size == 1:
        value = raw[1]
    elif size == 2:
        value = raw[1] | (raw[2] << 8)
    elif size == 3:
        value = raw[1] | (raw[2] << 8) | (raw[3] << 16)

    target = None
    if mode in ABSOLUTE_MODES or mode == "indirect16" or mode == "indirect16x":
        target = value
    elif mode == "relative":
        offset_value = raw[1] - 256 if raw[1] >= 128 else raw[1]
        target = (offset + 2 + offset_value) & 0xFFFF
    elif mode == "relative16":
        offset_value = value - 0x10000 if value >= 0x8000 else value
        target = (offset + 3 + offset_value) & 0xFFFFFF
    elif mode == "indirectlong16":
        target = value

    operand = _format(mode, value, target, raw)
    return Instruction(offset=offset, raw=raw, mnemonic=mnemonic, mode=mode,
                       operand=operand, target=target)


def disassemble(data: bytes, offset: int, count: int = 32,
                stop_at_flow: bool = False) -> list[Instruction]:
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
        if stop_at_flow and instruction.mnemonic in ("rts", "rtl", "rti", "jmp"):
            break
    return out


def format_listing(instructions: list[Instruction]) -> str:
    """Rendu texte, une instruction par ligne."""
    return "\n".join(
        f"{ins.offset:06X}: {ins.raw.hex(' '):<12s} {ins.text}"
        for ins in instructions)


def references(data: bytes, start: int = 0, end: int | None = None,
               minimum: int = 2) -> list[dict]:
    """Adresses que le code référence au moins ``minimum`` fois.

    On désassemble linéairement toute la plage et on compte les cibles des
    instructions à adresse absolue. Une adresse référencée plusieurs fois est
    presque toujours une donnée — souvent une banque de graphismes.
    """
    end = len(data) if end is None else min(end, len(data))
    counts: dict[int, int] = {}
    position = max(0, start)
    while position < end:
        try:
            instruction = decode(data, position)
        except ValueError:
            break
        if instruction.target is not None and 0 <= instruction.target < len(data):
            counts[instruction.target] = counts.get(instruction.target, 0) + 1
        position += instruction.size
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"target": target, "target_hex": f"0x{target:06X}", "count": count}
            for target, count in ranked if count >= minimum]


# ---------------------------------------------------------------------------
# Traçage depuis un point d'entrée
# ---------------------------------------------------------------------------


#: Correspondance adresse processeur → offset fichier, selon le mapping.
def rom_to_file(address: int, layout: str = "LoROM") -> int:
    """Convertit une adresse 24 bits en offset de fichier ROM."""
    address &= 0xFFFFFF
    if layout.upper() == "HIROM":
        return (address & 0xFFFF) + ((address >> 16) & 0x3F) * 0x10000
    return (address & 0x7FFF) + ((address >> 16) & 0x7F) * 0x8000


def file_to_rom(offset: int, layout: str = "LoROM") -> int:
    """Inverse de :func:`rom_to_file` (pour l'affichage)."""
    if layout.upper() == "HIROM":
        return 0x800000 | ((offset >> 16) << 16) | (offset & 0xFFFF)
    return 0x800000 | ((offset >> 15) << 16) | (offset & 0x7FFF)


def _jump_table_targets(data: bytes, instruction: Instruction,
                        layout: str = "LoROM",
                        entries: int = 24) -> list[int]:
    """Adresses lues dans la table d'un ``jmp (table,x)``.

    La table est dans la banque de programme de l'instruction. On lit les
    ``entries`` premières valeurs de 16 bits ; les entrées invalides sont
    ignorées par l'appelant.
    """
    if instruction.target is None:
        return []
    program_bank = (file_to_rom(instruction.offset, layout) >> 16) & 0xFF
    base = (program_bank << 16) | (instruction.target & 0xFFFF)
    table_offset = rom_to_file(base, layout)
    out = []
    for index in range(entries):
        position = table_offset + index * 2
        if position + 1 >= len(data):
            break
        out.append(data[position] | (data[position + 1] << 8))
    return out


def trace(data: bytes, entry: int, max_instructions: int = 20000,
          layout: str = "LoROM") -> list[Instruction]:
    """Suit le fil d'exécution depuis ``entry`` (adresse processeur).

    Contrairement au désassemblage linéaire, on ne décode que ce qui est
    réellement atteignable : on suit les sauts et les branches, et on gère les
    sous-programmes avec une **pile de retours** — un ``jsr`` empile l'adresse
    de retour, un ``rts``/``rtl`` la dépile. Sans cette pile, chaque
    sous-programme serait un cul-de-sac et la couverture resterait minuscule.
    """
    seen: set[int] = set()
    pending = [rom_to_file(entry, layout)]
    returns: list[int] = []
    out: list[Instruction] = []

    def valid(address: int | None) -> int | None:
        if address is None:
            return None
        position = rom_to_file(address, layout)
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

            if mnemonic in ("jsr", "jsl"):
                target = valid(instruction.target)
                if target is not None and target not in seen:
                    returns.append(next_position)
                    position = target
                    continue
                position = next_position
                continue

            if mnemonic in ("rts", "rtl", "rti"):
                if returns:
                    position = returns.pop()
                    continue
                break

            if mnemonic in ("jmp", "jml"):
                if instruction.mode in ("indirect16", "indirect16x"):
                    # Saut par table : on ne connaît pas la valeur de l'index,
                    # on suit donc **toutes** les entrées de la table. C'est
                    # une sur-approximation assumée : mieux vaut explorer du
                    # code peut-être inatteignable que rater la machine à
                    # états du jeu.
                    for entry in _jump_table_targets(data, instruction, layout):
                        target = valid(entry)
                        if target is not None and target not in seen:
                            pending.append(target)
                    break
                target = valid(instruction.target)
                if target is not None and target not in seen:
                    position = target
                    continue
                break

            if mnemonic in ("brk", "stp"):
                break

            if instruction.mode in ("relative", "relative16"):
                target = valid(instruction.target)
                if target is not None and target not in seen:
                    pending.append(target)
            position = next_position
    return out


def entry_points(data: bytes, layout: str = "LoROM") -> dict:
    """Vecteurs d'interruption lus dans l'en-tête SNES.

    Disposition de l'en-tête (offsets absolus dans le fichier) : COP à
    0x7FE4, BRK à 0x7FE6, NMI à 0x7FEA, IRQ à 0x7FEE, RESET à 0x7FFC.
    En HiROM, tout est décalé de 0x8000.
    """
    base = 0x7FE4 if layout.upper() != "HIROM" else 0xFFE4
    if len(data) < base + 0x1C:
        return {}
    offsets = {"cop": 0x00, "brk": 0x02, "nmi": 0x06, "irq": 0x0A, "reset": 0x18}
    out = {}
    for name, delta in offsets.items():
        position = base + delta
        out[name] = data[position] | (data[position + 1] << 8)
    return out
