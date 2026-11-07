"""Tests du désassembleur 6502.

Les séquences sont écrites à la main d'après la matrice d'opcodes officielle.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import disasm6502 as D


def test_table_complete():
    assert len(D.OPCODES) == 256
    legal = sum(1 for mnemonic, _ in D.OPCODES if mnemonic != ".byte")
    assert legal == 179          # 151 documentés + les NOP non documentés
    for mnemonic, mode in D.OPCODES:
        if mnemonic != ".byte":
            assert mode in D.MODE_SIZE


def test_instructions_documentees():
    code = bytes.fromhex("A9 01 8D 18 21 20 10 80 60 EA")
    instructions = D.disassemble(code, 0)
    assert [i.text for i in instructions] == [
        "lda #$01", "sta $2118", "jsr $8010", "rts", "nop"]
    assert [i.size for i in instructions] == [2, 3, 3, 1, 1]


def test_codes_invalides():
    """Les 77 opcodes non documentés sortent en ``.byte``."""
    instruction = D.decode(bytes([0x02]), 0)
    assert instruction.mnemonic == ".byte"
    assert instruction.size == 1


def test_branchement_relatif():
    instruction = D.decode(bytes.fromhex("D0 05"), 0)
    assert instruction.text == "bne $0007"
    data = bytes(0x20) + bytes.fromhex("F0 FB")
    back = D.decode(data, 0x20)
    assert back.target == 0x20 + 2 - 5


def test_modes_indirects():
    cas = {
        "A1 10": "lda ($10,X)",
        "B1 10": "lda ($10),Y",
        "6C 34 12": "jmp ($1234)",
        "A5 10": "lda $10",
        "B5 10": "lda $10,X",
        "B6 10": "ldx $10,Y",
        "AD 34 12": "lda $1234",
        "BD 34 12": "lda $1234,X",
        "B9 34 12": "lda $1234,Y",
    }
    for raw, expected in cas.items():
        instruction = D.decode(bytes.fromhex(raw), 0)
        assert instruction.text == expected, (raw, instruction.text, expected)


def test_tracage_avec_sous_programme():
    code = bytearray(64)
    code[0:3] = bytes.fromhex("20 10 80")      # jsr $8010
    code[3] = 0x60                             # rts
    code[0x10:0x12] = bytes.fromhex("A9 01")
    code[0x12] = 0x60
    instructions = D.trace(bytes(code), 0x8000, max_instructions=32, base=0x8000)
    offsets = [ins.offset for ins in instructions]
    assert offsets[:3] == [0x00, 0x10, 0x12]
    assert 0x03 in offsets


def test_tracage_avec_base():
    """Une cartouche NES est chargée à $8000 : le fichier commence à zéro."""
    code = bytes.fromhex("A9 01 60")
    instructions = D.trace(code, 0x8000, base=0x8000)
    assert instructions[0].text == "lda #$01"


def test_references():
    data = bytes(0x100) + bytes.fromhex("AD 00 02 AD 00 02 60")
    refs = D.references(data, 0x100, base=0x8000, minimum=1)
    assert refs
    assert refs[0]["target"] == 0x8200
    assert refs[0]["count"] == 2
