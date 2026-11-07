"""Tests du désassembleur 65816.

Les séquences sont écrites à la main à partir de la documentation du
processeur : ce sont des cas connus, pas des octets tirés au hasard.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import disasm65816 as D


def test_table_complete():
    assert len(D.OPCODES) == 256
    for mnemonic, mode in D.OPCODES:
        assert mnemonic and mode
        assert mode in D.MODE_SIZE


def test_instructions_courantes():
    code = bytes.fromhex("A9 01 8D 18 21 60")
    instructions = D.disassemble(code, 0)
    assert [i.text for i in instructions] == ["lda #$01", "sta $2118", "rts"]
    assert [i.size for i in instructions] == [2, 3, 1]


def test_sauts_et_sous_programmes():
    code = bytes.fromhex("20 00 80 22 00 00 80 5C 34 12 80 6B")
    instructions = D.disassemble(code, 0)
    assert instructions[0].text == "jsr $8000"
    assert instructions[0].target == 0x8000
    assert instructions[1].text == "jsl $800000"
    assert instructions[2].text == "jml $801234"
    assert instructions[3].mnemonic == "rtl"


def test_branchement_relatif():
    """BRA +5 depuis l'offset 0 : cible = 0 + 2 + 5 = 7."""
    instruction = D.decode(bytes.fromhex("80 05"), 0)
    assert instruction.text == "bra $0007"
    assert instruction.target == 0x0007


def test_branchement_negatif():
    """Un décalage négatif remonte avant l'instruction."""
    data = bytes(0x10) + bytes.fromhex("80 FB")
    instruction = D.decode(data, 0x10)
    assert instruction.target == 0x10 + 2 - 5


def test_adressages_indirects():
    cas = {
        "B2 10": "lda ($10)",
        "A7 10": "lda [$10]",
        "A1 10": "lda ($10,X)",
        "B1 10": "lda ($10),Y",
        "B7 10": "lda [$10],Y",
        "A3 10": "lda $10,S",
        "B3 10": "lda ($10,S),Y",
        "AD 00 20": "lda $2000",
        "BD 00 20": "lda $2000,X",
        "B9 00 20": "lda $2000,Y",
        "AF 00 20 00": "lda $002000",
        "BF 00 20 00": "lda $002000,X",
        "6C 00 20": "jmp ($2000)",
        "7C 00 20": "jmp ($2000,X)",
    }
    for raw, expected in cas.items():
        instruction = D.decode(bytes.fromhex(raw), 0)
        assert instruction.text == expected, (raw, instruction.text, expected)


def test_transfert_de_bloc():
    instruction = D.decode(bytes.fromhex("54 01 02"), 0)
    assert instruction.mnemonic == "mvn"
    assert instruction.size == 3


def test_instruction_tronquee():
    try:
        D.decode(b"\xad\x00", 0)
    except ValueError:
        return
    raise AssertionError("une instruction tronquée aurait dû échouer")


def test_references_comptees():
    rom = bytes(4096) + bytes.fromhex("AD 00 10 AD 00 10 8D 00 10 60")
    refs = D.references(rom, 4096, minimum=1)
    assert refs
    assert refs[0]["target"] == 4096
    assert refs[0]["count"] == 3


def test_references_ignorent_les_registres():
    """Un accès aux registres matériels (0x2118) n'est pas une référence ROM."""
    rom = bytes.fromhex("8D 18 21 60")
    assert D.references(rom, 0, minimum=1) == []


def test_listing():
    text = D.format_listing(D.disassemble(bytes.fromhex("A9 01 60"), 0))
    assert "lda #$01" in text
    assert "rts" in text


# ---------------------------------------------------------------------------
# Mapping et traçage
# ---------------------------------------------------------------------------


def test_mapping_lorom():
    assert D.rom_to_file(0x8000) == 0
    assert D.rom_to_file(0x818000) == 0x8000
    assert D.rom_to_file(0x828000) == 0x10000
    assert D.rom_to_file(0x00FFFC) == 0x7FFC


def test_mapping_hirom():
    assert D.rom_to_file(0xC00000, "HiROM") == 0
    assert D.rom_to_file(0xC10000, "HiROM") == 0x10000


def test_vecteurs_entree():
    data = bytearray(0x8000)
    # en-tête LoROM : RESET à 0x7FFC, NMI à 0x7FEA
    data[0x7FFC:0x7FFE] = (0x8000).to_bytes(2, "little")
    data[0x7FEA:0x7FEC] = (0x832F).to_bytes(2, "little")
    vectors = D.entry_points(bytes(data))
    assert vectors["reset"] == 0x8000
    assert vectors["nmi"] == 0x832F


def test_tracage_suit_un_sous_programme():
    """Un JSR doit être suivi, puis le RTS doit arrêter la branche."""
    code = bytearray(64)
    # 0x00 : jsr $800A ; 0x03 : rts
    code[0:3] = bytes.fromhex("20 0A 80")
    code[3] = 0x60
    # 0x0A : lda #$01 ; 0x0C : rts
    code[0x0A:0x0C] = bytes.fromhex("A9 01")
    code[0x0C] = 0x60
    instructions = D.trace(bytes(code), 0x8000, max_instructions=32)
    offsets = {ins.offset for ins in instructions}
    assert 0 in offsets and 0x0A in offsets
    assert 3 in offsets          # retour de sous-programme


def test_tracage_s_arrete_au_retour():
    code = bytes.fromhex("A9 01 60 A9 02 60")
    instructions = D.trace(code, 0x8000, max_instructions=32)
    assert [ins.mnemonic for ins in instructions] == ["lda", "rts"]


def test_tracage_appels_imbriques():
    """Deux sous-programmes imbriqués : la pile de retours doit revenir au bon endroit."""
    code = bytearray(64)
    # 0x00 : jsr $8006 ; 0x03 : lda #$02 ; 0x05 : rts
    code[0:3] = bytes.fromhex("20 06 80")
    code[3:5] = bytes.fromhex("A9 02")
    code[5] = 0x60
    # 0x06 : jsr $800B ; 0x09 : rts
    code[6:9] = bytes.fromhex("20 0B 80")
    code[9] = 0x60
    # 0x0B : lda #$01 ; 0x0D : rts
    code[0x0B:0x0D] = bytes.fromhex("A9 01")
    code[0x0D] = 0x60

    instructions = D.trace(bytes(code), 0x8000, max_instructions=32)
    offsets = [ins.offset for ins in instructions]
    assert offsets[:5] == [0x00, 0x06, 0x0B, 0x0D, 0x09]
    # après le retour du sous-programme imbriqué, on reprend au 0x03
    assert 0x03 in offsets and 0x05 in offsets


def test_suivi_d_une_table_de_sauts():
    """Un ``jmp (table,x)`` : toutes les entrées de la table sont explorées.

    On ne connaît pas la valeur de X ; mieux vaut explorer du code
    peut-être inatteignable que rater la machine à états du jeu.
    """
    code = bytearray(64)
    code[0:3] = bytes.fromhex("7C 10 80")       # jmp ($8010,x)
    code[0x10:0x12] = (0x8020).to_bytes(2, "little")
    code[0x12:0x14] = (0x8030).to_bytes(2, "little")
    code[0x20:0x22] = bytes.fromhex("A9 01")
    code[0x22] = 0x60
    code[0x30:0x32] = bytes.fromhex("A9 02")
    code[0x32] = 0x60

    instructions = D.trace(bytes(code), 0x8000, max_instructions=32)
    offsets = {ins.offset for ins in instructions}
    assert 0x20 in offsets
    assert 0x30 in offsets
