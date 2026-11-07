"""Tests du désassembleur Z80.

Les séquences sont écrites à la main d'après le décodage officiel du
processeur (champs xx / yyy / zzz).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import disasmz80 as Z


def test_table_principale():
    cas = {
        "00": "nop",
        "3E 42": "ld a,$42",
        "06 10": "ld b,$10",
        "21 34 12": "ld hl,$1234",
        "32 00 40": "ld ($4000),a",
        "3A 00 40": "ld a,($4000)",
        "22 00 40": "ld ($4000),hl",
        "2A 00 40": "ld hl,($4000)",
        "CD 00 80": "call $8000",
        "C3 34 12": "jp $1234",
        "C9": "ret",
        "76": "halt",
        "AF": "xor a",
        "F3": "di",
        "FB": "ei",
        "07": "rlca",
        "F6 0F": "or $0F",
        "E5": "push hl",
        "E1": "pop hl",
        "C5": "push bc",
    }
    for raw, expected in cas.items():
        instruction = Z.decode(bytes.fromhex(raw), 0)
        assert instruction.text == expected, (raw, instruction.text, expected)


def test_conditions_et_sauts():
    assert Z.decode(bytes.fromhex("C2 00 80"), 0).text == "jp nz,$8000"
    assert Z.decode(bytes.fromhex("C0"), 0).text == "ret nz"
    assert Z.decode(bytes.fromhex("C4 00 80"), 0).text == "call nz,$8000"


def test_branchement_relatif():
    """JR +5 depuis l'offset 0 : cible = 0 + 2 + 5."""
    instruction = Z.decode(bytes.fromhex("18 05"), 0)
    assert instruction.text == "jr $0007"
    assert instruction.target == 0x0007

    data = bytes(0x10) + bytes.fromhex("20 FB")     # JR NZ, -5
    back = Z.decode(data, 0x10)
    assert back.target == 0x10 + 2 - 5


def test_prefixe_cb():
    assert Z.decode(bytes.fromhex("CB 40"), 0).text == "bit 0,b"
    assert Z.decode(bytes.fromhex("CB 7F"), 0).text == "bit 7,a"
    assert Z.decode(bytes.fromhex("CB 06"), 0).text == "rlc (hl)"
    assert Z.decode(bytes.fromhex("CB C0"), 0).text == "set 0,b"
    assert Z.decode(bytes.fromhex("CB 86"), 0).text == "res 0,(hl)"


def test_prefixe_ed():
    assert Z.decode(bytes.fromhex("ED B0"), 0).text == "ldir"
    assert Z.decode(bytes.fromhex("ED 43 00 40"), 0).text == "ld ($4000),bc"
    assert Z.decode(bytes.fromhex("ED 4B 00 40"), 0).text == "ld bc,($4000)"
    assert Z.decode(bytes.fromhex("ED 44"), 0).text == "neg"
    assert Z.decode(bytes.fromhex("ED 4D"), 0).text == "reti"


def test_prefixe_ed_indefini():
    instruction = Z.decode(bytes.fromhex("ED 00"), 0)
    assert instruction.mnemonic == ".db"


def test_prefixes_indexes():
    assert Z.decode(bytes.fromhex("DD 21 00 90"), 0).text == "ld ix,$9000"
    assert Z.decode(bytes.fromhex("DD 7E 05"), 0).text == "ld a,(ix+5)"
    assert Z.decode(bytes.fromhex("DD 7E FB"), 0).text == "ld a,(ix-5)"
    assert Z.decode(bytes.fromhex("FD 21 00 90"), 0).text == "ld iy,$9000"
    assert Z.decode(bytes.fromhex("DD E5"), 0).text == "push ix"


def test_taille_des_instructions():
    assert Z.decode(bytes.fromhex("00"), 0).size == 1
    assert Z.decode(bytes.fromhex("3E 42"), 0).size == 2
    assert Z.decode(bytes.fromhex("21 34 12"), 0).size == 3
    assert Z.decode(bytes.fromhex("CB 00"), 0).size == 2
    assert Z.decode(bytes.fromhex("DD 7E 05"), 0).size == 3
    assert Z.decode(bytes.fromhex("DD 21 34 12"), 0).size == 4


def test_tracage_avec_appel():
    code = bytearray(64)
    code[0:3] = bytes.fromhex("CD 10 80")      # call $8010
    code[3] = 0xC9                            # ret
    code[0x10:0x12] = bytes.fromhex("3E 01")
    code[0x12] = 0xC9
    instructions = Z.trace(bytes(code), 0x8000, base=0x8000, max_instructions=32)
    offsets = [ins.offset for ins in instructions]
    assert offsets[:3] == [0x00, 0x10, 0x12]
    assert 0x03 in offsets


def test_listing():
    text = Z.format_listing(Z.disassemble(bytes.fromhex("F3 3E 42 C9"), 0))
    assert "di" in text and "ld a,$42" in text


# ---------------------------------------------------------------------------
# Variante SM83 (Game Boy)
# ---------------------------------------------------------------------------


def test_sm83_opcodes_propres():
    cas = {
        "08 00 40": "ld ($4000),sp",
        "22": "ld (hl+),a",
        "2A": "ld a,(hl+)",
        "32": "ld (hl-),a",
        "3A": "ld a,(hl-)",
        "E0 40": "ldh ($40),a",
        "F0 40": "ldh a,($40)",
        "EA 00 40": "ld ($4000),a",
        "FA 00 40": "ld a,($4000)",
        "10 00": "stop $00",
    }
    for raw, expected in cas.items():
        instruction = Z.decode(bytes.fromhex(raw), 0, variant="sm83")
        assert instruction.text == expected, (raw, instruction.text, expected)


def test_sm83_decalages_signes():
    assert Z.decode(bytes.fromhex("E8 FC"), 0, variant="sm83").text == "add sp,-4"
    assert Z.decode(bytes.fromhex("E8 04"), 0, variant="sm83").text == "add sp,+4"
    assert Z.decode(bytes.fromhex("F8 FC"), 0, variant="sm83").text == "ld hl,sp-4"


def test_sm83_cb_swap():
    assert Z.decode(bytes.fromhex("CB 30"), 0, variant="sm83").text == "swap b"
    assert Z.decode(bytes.fromhex("CB 37"), 0, variant="sm83").text == "swap a"
    assert Z.decode(bytes.fromhex("CB 7F"), 0, variant="sm83").text == "bit 7,a"


def test_sm83_codes_invalides():
    for raw in ("D3", "DB", "DD", "E3", "E4", "EB", "EC", "ED", "F4", "FD"):
        instruction = Z.decode(bytes.fromhex(raw), 0, variant="sm83")
        assert instruction.mnemonic == ".db", raw


def test_sm83_instructions_communes():
    assert Z.decode(bytes.fromhex("3E 42"), 0, variant="sm83").text == "ld a,$42"
    assert Z.decode(bytes.fromhex("21 34 12"), 0, variant="sm83").text == "ld hl,$1234"
    assert Z.decode(bytes.fromhex("CD 00 80"), 0, variant="sm83").text == "call $8000"
