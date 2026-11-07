"""Tests du désassembleur 68000.

Les séquences sont écrites à la main d'après la documentation du processeur.
Le dernier test utilise le code d'amorçage réel d'une cartouche Mega Drive :
l'écriture de « SEGA » dans le registre TMSS est une signature connue.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import disasm68000 as D


def _decode(hexadecimal: str):
    return D.decode(bytes.fromhex(hexadecimal.replace(" ", "")), 0)


def test_instructions_simples():
    cas = {
        "4E71": "nop",
        "4E75": "rts",
        "4E73": "rte",
        "4E70": "reset",
        "4E76": "trapv",
        "4E77": "rtr",
        "4AFC": "illegal",
        "4E40": "trap #0",
        "4E4F": "trap #15",
    }
    for raw, expected in cas.items():
        assert _decode(raw).text == expected, (raw, _decode(raw).text)


def test_deplacements():
    assert _decode("7000").text == "moveq #$00,d0"
    assert _decode("7201").text == "moveq #$01,d1"
    assert _decode("2000").text == "move.l d0,d0"
    assert _decode("2240").text == "movea.l d0,a1"
    assert _decode("3001").text == "move.w d1,d0"
    assert _decode("1001").text == "move.b d1,d0"


def test_modes_d_adressage():
    assert _decode("2001").text == "move.l d1,d0"
    assert _decode("2008").text == "move.l a0,d0"
    assert _decode("2010").text == "move.l (a0),d0"
    assert _decode("2018").text == "move.l (a0)+,d0"
    assert _decode("2020").text == "move.l -(a0),d0"
    assert _decode("2028 0004").text == "move.l $0004(a0),d0"
    assert _decode("2038 1234").text == "move.l $1234.w,d0"
    assert _decode("2039 0000 1234").text == "move.l $00001234.l,d0"
    assert _decode("203C 0000 0001").text == "move.l #$00000001,d0"
    assert _decode("303C 0001").text == "move.w #$0001,d0"


def test_sauts():
    bra = _decode("6004")
    assert bra.text == "bra $000006"
    assert bra.target == 0x06

    bsr = _decode("6100 0100")
    assert bsr.text == "bsr $000102"

    bne = _decode("66F8")
    assert bne.mnemonic == "bne"

    assert _decode("4EB9 0000 1234").text == "jsr $00001234.l"
    assert _decode("4EF9 0000 1234").text == "jmp $00001234.l"
    assert _decode("4E90").text == "jsr (a0)"
    assert _decode("4ED0").text == "jmp (a0)"


def test_arithmetique():
    assert _decode("D081").text == "add.l d1,d0"
    assert _decode("D041").text == "add.w d1,d0"
    assert _decode("D001").text == "add.b d1,d0"
    assert _decode("9081").text == "sub.l d1,d0"
    assert _decode("B081").text == "cmp.l d1,d0"
    assert _decode("C081").text == "and.l d1,d0"
    assert _decode("8081").text == "or.l d1,d0"
    assert _decode("0640 0001").text == "addi.w #$0001,d0"
    assert _decode("0240 000F").text == "andi.w #$000F,d0"


def test_immediats_et_quick():
    assert _decode("0600 0001").text == "addi.b #$0001,d0"
    assert _decode("5240").text == "addq.w #1,d0"
    assert _decode("5340").text == "subq.w #1,d0"
    assert _decode("5040").text == "addq.w #8,d0"     # 0 signifie 8
    assert _decode("5080").text == "addq.l #8,d0"


def test_pile_et_cadre():
    assert _decode("4E56 FFFC").text == "link a6,#$FFFC"
    assert _decode("4E5E").text == "unlk a6"
    assert _decode("2F00").text == "move.l d0,-(a7)"


def test_movem():
    assert _decode("4CDF 00FF").text == "movem.l (a7)+,d0-d7"
    assert _decode("48E7 C0C0").text == "movem.l d0-d1/a0-a1,-(a7)"
    assert _decode("4CDF FFFF").text == "movem.l (a7)+,d0-d7/a0-a7"


def test_lea_et_tst():
    assert _decode("41F8 1234").text == "lea.l $1234.w,a0"
    assert _decode("4AB9 00A1 0008").text == "tst.l $00A10008.l"
    assert _decode("4A79 00A1 000C").text == "tst.w $00A1000C.l"


def test_instruction_non_decodee():
    """Les lignes A et F ne sont pas décodées : elles sortent en .dc.w."""
    assert _decode("A000").mnemonic == ".dc.w"
    assert _decode("F000").mnemonic == ".dc.w"


def test_tailles():
    assert _decode("4E71").size == 2
    assert _decode("7000").size == 2
    assert _decode("203C 0000 0001").size == 6
    assert _decode("4A79 00A1 000C").size == 6


def test_code_d_amorcage_megadrive():
    """Le début d'Aero Blasters écrit « SEGA » dans le registre TMSS."""
    rom = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "megadrive", "Aero Blasters.md")
    if not os.path.exists(rom):
        return                      # ROM absente : test sauté
    with open(rom, "rb") as handle:
        data = handle.read()
    vectors = D.entry_points(data)
    assert vectors["stack"] == 0x00FFFE00
    instructions = D.disassemble(data, vectors["reset"], 12)
    text = D.format_listing(instructions)
    assert "tst.l $00A10008" in text
    assert "SEGA" in text or "$53454741" in text


def test_multiplications_et_divisions():
    assert _decode("C1FC 000C").text == "muls.w #$000C,d0"
    assert _decode("C0FC 0010").text == "mulu.w #$0010,d0"
    assert _decode("81FC 0000 0005").text == "divs.l #$00000005,d0"
    assert _decode("80FC 0000 0003").text == "divu.l #$00000003,d0"


def test_decalages():
    assert _decode("E380").text == "asl.l #1,d0"
    assert _decode("E240").text == "asr.w #1,d0"
    assert _decode("E108").text == "lsl.b #8,d0"
    assert _decode("E3A0").text == "asl.l d1,d0"
    assert _decode("E368").text == "lsl.w d1,d0"
    assert _decode("E0A0").text == "asr.l d0,d0"


def test_sequence_reelle_de_calcul_d_adresse():
    """Extrait d'A.PRG : index → table de mots → enregistrement de 12 octets."""
    rom = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "extract", "A.PRG")
    if not os.path.exists(rom):
        return
    with open(rom, "rb") as handle:
        data = handle.read()
    text = D.format_listing(D.disassemble(data, 0xC26, 7))
    assert "asl.l #1,d0" in text
    assert "muls.w #$000C,d0" in text
    assert "lea.l -$2F22(a4),a0" in text
