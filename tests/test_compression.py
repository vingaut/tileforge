"""Tests des décompresseurs (Kosinski, Nemesis, LC_LZ2).

Les trois exemples Kosinski viennent de la page officielle Sega Retro
(https://segaretro.org/Kosinski_compression) : ce sont de vrais vecteurs de
test, pas des données fabriquées avec le décodeur lui-même.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import compression as C

# ---------------------------------------------------------------------------
# Kosinski — vecteurs officiels
# ---------------------------------------------------------------------------


def test_kosinski_litteraux():
    data = bytes.fromhex("FF5F000102030405060708090A0B0C00F000")
    assert C.kosinski(data) == bytes(range(0x0D))


def test_kosinski_copie_courte():
    data = bytes.fromhex("510025FF00F000")
    assert C.kosinski(data) == bytes([0x25] * 4)


def test_kosinski_complet():
    data = bytes.fromhex(
        "FF3F543BC4445433335B2D5C445CC4C5FC15FEC3447888984430FFFF00F800")
    expected = (bytes.fromhex("543BC4445433335B2D5C445CC4C5C4C5C3447888984430")
                + bytes([0x30]) * 9)
    assert C.kosinski(data) == expected


def test_kosinski_offset():
    data = b"\x00\x00\x00" + bytes.fromhex("510025FF00F000")
    assert C.kosinski(data, 3) == bytes([0x25] * 4)


# ---------------------------------------------------------------------------
# Nemesis
# ---------------------------------------------------------------------------


class _BitWriter:
    def __init__(self):
        self.bits = []

    def write(self, value: int, count: int) -> None:
        for k in range(count - 1, -1, -1):
            self.bits.append((value >> k) & 1)

    def to_bytes(self) -> bytes:
        while len(self.bits) % 8:
            self.bits.append(0)
        out = bytearray()
        for i in range(0, len(self.bits), 8):
            byte = 0
            for k in range(8):
                byte = (byte << 1) | self.bits[i + k]
            out.append(byte)
        return bytes(out)


def test_nemesis_inline():
    """Table vide : tout passe par les données en ligne (6 bits + 7 bits)."""
    writer = _BitWriter()
    pixels = [5, 0, 0x0A, 0x0F]
    for pixel in pixels:
        writer.write(0b111111, 6)
        writer.write(0b111, 3)
        writer.write(pixel, 4)
    stream = bytes([0x00, 0x01, 0xFF]) + writer.to_bytes()
    expected = b"".join(bytes([pixel * 0x11] * 4) for pixel in pixels)
    assert C.nemesis(stream) == expected


def test_nemesis_table():
    """Un code de 1 bit qui remplit une ligne de 8 pixels de couleur 3."""
    stream = bytes([0x00, 0x01, 0x03, 0x71, 0x00, 0xFF, 0x00, 0x00])
    assert C.nemesis(stream) == bytes([0x33] * 16)


def test_nemesis_xor():
    writer = _BitWriter()
    for pixel in (1, 0, 1, 0):
        writer.write(0b111111, 6)
        writer.write(0b111, 3)
        writer.write(pixel, 4)
    stream = bytes([0x80, 0x01, 0xFF]) + writer.to_bytes()
    # le mode XOR est cumulatif : 11, 11, 00, 00
    expected = bytes([0x11] * 8) + bytes([0x00] * 8)
    assert C.nemesis(stream) == expected


# ---------------------------------------------------------------------------
# LC_LZ2
# ---------------------------------------------------------------------------


def test_lz2_commandes():
    stream = bytes([0x00, 0x41,          # copie directe de 1 octet
                    0x01, 0x42, 0x43,    # copie directe de 2 octets
                    0x21, 0x44,          # remplissage d'octet, 2 fois
                    0x42, 0x45, 0x46,    # remplissage de mot, 3 octets
                    0x63, 0x10,          # remplissage croissant, 4 octets
                    0x83, 0x00, 0x00,    # répétition depuis l'adresse 0
                    0xFF])
    expected = bytes([0x41, 0x42, 0x43, 0x44, 0x44, 0x45, 0x46, 0x45,
                      0x10, 0x11, 0x12, 0x13, 0x41, 0x42, 0x43, 0x44])
    assert C.lz2(stream) == expected


def test_lz2_fin_immediate():
    assert C.lz2(bytes([0xFF])) == b""


# ---------------------------------------------------------------------------
# Note graphique
# ---------------------------------------------------------------------------


def test_graphics_score_discrimine():
    import random

    from tileforge.core.formats import FORMATS_BY_KEY

    fmt = FORMATS_BY_KEY["barbarian_st"]
    rng = random.Random(1)
    noise = bytes(rng.getrandbits(8) for _ in range(126 * 40))
    assert C.graphics_score(noise, fmt) < 0.2

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dat = os.path.join(root, "extract", "BARB.DAT")
    if os.path.exists(dat):
        with open(dat, "rb") as f:
            f.seek(0x33A52)
            real = f.read(126 * 40)
        assert C.graphics_score(real, fmt) > 0.6


# ---------------------------------------------------------------------------
# Saxman — vecteur officiel et cas de référence arrière
# ---------------------------------------------------------------------------


def test_saxman_vecteur_officiel():
    """Exemple de Sega Retro : un « zero fill » de 18 octets."""
    stream = bytes.fromhex("03 00 00 00 FF")
    assert C.saxman_with_length(stream) == bytes(18)


def test_saxman_reference_arriere():
    """Deux littéraux puis une copie de 3 octets depuis le début."""
    stream = bytes.fromhex("03 41 42 EE F0")
    assert C.saxman(stream) == b"ABABA"


def test_saxman_borne_la_sortie():
    """Un flux mal interprété ne peut pas dépasser la taille demandée."""
    data = bytes(range(256)) * 4
    try:
        out = C.saxman(data, 0, max_size=1024)
    except C.DecompressionError:
        return
    assert len(out) <= 1024


# ---------------------------------------------------------------------------
# Enigma — vecteurs officiels
# ---------------------------------------------------------------------------


ENIGMA_VECTEUR = bytes.fromhex("07 0C 00 00 00 10 05 3D 11 8F E0")
ENIGMA_ATTENDU = bytes.fromhex(
    "00 00 00 01 00 10 00 10 00 10 00 10 "
    "40 18 40 17 40 16 40 15 40 14 40 13 40 12 40 11 40 10")
ENIGMA_ATTENDU_DECALE = bytes.fromhex(
    "10 00 10 01 10 10 10 10 10 10 10 10 "
    "50 18 50 17 50 16 50 15 50 14 50 13 50 12 50 11 50 10")


def test_enigma_vecteur_officiel():
    assert C.enigma(ENIGMA_VECTEUR) == ENIGMA_ATTENDU


def test_enigma_tuile_de_depart():
    assert C.enigma(ENIGMA_VECTEUR, start_tile=0x1000) == ENIGMA_ATTENDU_DECALE


def test_enigma_valeur_en_ligne():
    """Ordre 100 : une valeur en ligne unique, sans bits de rendu.

    Le flux de bits est continu : le terminateur (111 + 1111) commence
    immédiatement après la valeur, sans alignement sur l'octet.
    """
    # 1 | 00 | 0000 | 0000101 | 111 | 1111 | 000  ->  80 17 F8
    stream = bytes.fromhex("07 00 00 00 00 00 80 17 F8")
    assert C.enigma(stream) == bytes.fromhex("00 05")


# ---------------------------------------------------------------------------
# PackBits et RLE
# ---------------------------------------------------------------------------


def _packbits_encode(data: bytes) -> bytes:
    """Encodeur PackBits minimal, pour l'aller-retour."""
    out = bytearray()
    index = 0
    while index < len(data):
        run = 1
        while (index + run < len(data) and data[index + run] == data[index]
               and run < 128):
            run += 1
        if run >= 3:
            out.append(257 - run)
            out.append(data[index])
            index += run
            continue
        start = index
        while index < len(data) and index - start < 128:
            if (index + 2 < len(data) and data[index] == data[index + 1]
                    == data[index + 2]):
                break
            index += 1
        length = index - start
        out.append(length - 1)
        out += data[start:index]
    return bytes(out)


def test_packbits_aller_retour():
    import random
    rng = random.Random(3)
    sample = bytes(rng.choice([0x00, 0x11, 0x22, 0x33]) for _ in range(600))
    encoded = _packbits_encode(sample)
    assert C.packbits(encoded) == sample


def test_rle_pairs():
    data = bytes([0xAA, 3, 0xBB, 2, 0xCC, 1])
    assert C.rle_pairs(data) == bytes([0xAA] * 3 + [0xBB] * 2 + [0xCC])


def test_rle_flagged():
    data = bytes([0x03, 1, 2, 3, 4, 0x82, 0x99])
    assert C.rle_flagged(data) == bytes([1, 2, 3, 4]) + bytes([0x99]) * 3


# ---------------------------------------------------------------------------
# Kosinski modulé
# ---------------------------------------------------------------------------


def test_kosinski_moduled_un_module():
    """Un seul module : l'en-tête donne sa taille décompressée."""
    stream = bytes.fromhex("000D FF5F000102030405060708090A0B0C00F000")
    assert C.kosinski_moduled(stream) == bytes(range(0x0D))


def test_kosinski_moduled_deux_modules():
    """Deux modules : 0x1000 octets puis la taille annoncée par l'en-tête."""
    def fake(data, position, size):
        return bytes([position & 0xFF]) * size, position + 1

    # en-tête 0x1010 : deux modules, dernier module de 0x010 octets
    out = C.kosinski_moduled(bytes.fromhex("1010"), decoder=fake)
    assert len(out) == 0x1000 + 0x10
    assert out[:4] == bytes([2, 2, 2, 2])          # position 2 = après l'en-tête


def test_kosinski_moduled_refuse_un_module_incomplet():
    def short(data, position, size):
        return bytes(size - 1), position + 1

    try:
        C.kosinski_moduled(bytes.fromhex("000D"), decoder=short)
    except C.DecompressionError:
        return
    raise AssertionError("un module incomplet aurait dû être refusé")


# ---------------------------------------------------------------------------
# Sonic RLE et Comper (Mega Drive)
# ---------------------------------------------------------------------------


def test_sonic_rle_litteraux():
    """En-tête 16 bits gros-boutiste, puis trois octets distincts."""
    assert C.sonic_rle(bytes.fromhex("0003 41 42 43")) == b"ABC"


def test_sonic_rle_repetition():
    """Deux octets identiques annoncent une répétition de N copies de plus."""
    assert C.sonic_rle(bytes.fromhex("0004 AA AA 01 BB")) == b"\xAA\xAA\xAA\xBB"
    assert C.sonic_rle(bytes.fromhex("0005 AA AA 02 BB")) == b"\xAA" * 4 + b"\xBB"


def test_sonic_rle_taille_nulle():
    assert C.sonic_rle(bytes.fromhex("0000")) == b""


def test_comper_litteraux():
    """Description 0x2000 : deux mots littéraux puis le terminateur."""
    assert C.comper(bytes.fromhex("2000 1234 5678 0000")) == bytes.fromhex("1234 5678")


def test_comper_reference():
    """Une référence de distance 2 répète le mot précédent."""
    stream = bytes.fromhex("6000 1234 FF01 0000")
    assert C.comper(stream) == bytes.fromhex("1234 1234 1234")


def test_comper_reference_hors_tampon():
    """Une référence qui pointe avant le début du flux doit échouer."""
    try:
        C.comper(bytes.fromhex("4000 1234 0101 0000"))
    except C.DecompressionError:
        return
    raise AssertionError("une référence hors tampon aurait dû être refusée")


# ---------------------------------------------------------------------------
# LZ de Pokémon Crystal (Game Boy)
# ---------------------------------------------------------------------------


def test_pokecrystal_litteraux_et_repetition():
    """Littéraux « AB » puis « X » répété trois fois."""
    stream = bytes([0x01, 0x41, 0x42, 0x22, 0x58, 0xFF])
    assert C.pokecrystal_lz(stream) == b"ABXXX"


def test_pokecrystal_copie_arriere():
    """« AB » puis une copie de deux octets à deux octets en arrière."""
    stream = bytes([0x01, 0x41, 0x42, 0x81, 0x81, 0xFF])
    assert C.pokecrystal_lz(stream) == b"ABAB"


def test_pokecrystal_zeros():
    assert C.pokecrystal_lz(bytes([0x64, 0xFF])) == bytes(5)


def test_pokecrystal_commande_longue():
    """Le type 7 étend la longueur au-delà de 32 octets."""
    data = bytes(range(40))
    stream = bytes([0xE0, 0x27]) + data + bytes([0xFF])
    assert C.pokecrystal_lz(stream) == data


def test_pokecrystal_bits_inverses():
    """Type 5 : copie les octets en inversant leurs bits."""
    stream = bytes([0x01, 0x41, 0x42, 0xA1, 0x81, 0xFF])
    decoded = C.pokecrystal_lz(stream)
    assert decoded[:2] == b"AB"
    assert decoded[2] == 0x82          # 0x41 inversé
    assert decoded[3] == 0x42          # 0x42 est symétrique


def test_pokecrystal_fin_absente():
    """Sans octet de fin, le flux s'arrête à la fin des données."""
    assert C.pokecrystal_lz(bytes([0x00, 0x41])) == b"A"


# ---------------------------------------------------------------------------
# LZSS SNES (0x100)
# ---------------------------------------------------------------------------


def test_snes_lzss_litteraux():
    """Un octet de drapeaux, bit 0 en premier : 1 = littéral."""
    assert C.snes_lzss(bytes([0x03, 0x41, 0x42])) == b"AB"


def test_snes_lzss_reference():
    """Distance 3, longueur 3 : « ABC » puis la copie."""
    assert C.snes_lzss(bytes([0x07, 0x41, 0x42, 0x43, 0x02, 0x00])) == b"ABCABC"


def test_snes_lzss_longueur_etendue():
    """Le code de longueur 1111 annonce un octet supplémentaire."""
    decoded = C.snes_lzss(bytes([0x01, 0x41, 0x00, 0xF0, 0x05]))
    assert len(decoded) == 24          # 1 littéral + 23 copies
    assert set(decoded) == {0x41}


def test_snes_lzss_distance_elevee():
    """La distance tient sur 12 bits : ici huit octets en arrière."""
    stream = bytes([0xFF]) + bytes(range(8)) + bytes([0x00, 0x07, 0x00])
    assert C.snes_lzss(stream) == bytes(range(8)) + bytes([0, 1, 2])


def test_snes_lzss_reference_hors_tampon():
    try:
        C.snes_lzss(bytes([0x00, 0xFF, 0x0F]))
    except C.DecompressionError:
        return
    raise AssertionError("une référence hors tampon aurait dû être refusée")


# ---------------------------------------------------------------------------
# LZ77 / LZ11 (Game Boy Advance, Nintendo DS)
# ---------------------------------------------------------------------------


def test_gba_lz77_litteraux_et_copie():
    """LZ10 : drapeau 0 = littéral, 1 = copie ; « AB » puis 4 octets à distance 2."""
    stream = bytes.fromhex("10 06 00 00 20 41 42 10 01")
    assert C.gba_lz77(stream) == b"ABABAB"


def test_gba_lz11_courte():
    """LZ11 court : la longueur vaut le quartet haut plus un."""
    stream = bytes.fromhex("11 06 00 00 20 41 42 30 01")
    assert C.gba_lz77(stream) == b"ABABAB"


def test_gba_lz11_longue_forme_zero():
    """LZ11, forme 0 : longueur 0x11 + 0x03 = 20, distance 1."""
    stream = bytes.fromhex("11 15 00 00 40 41 00 30 00")
    assert C.gba_lz77(stream) == b"A" * 21


def test_gba_lz11_longue_forme_un():
    """LZ11, forme 1 : longueur 0x111 + 1 = 274, distance 1."""
    stream = bytes.fromhex("11 13 01 00 40 41 10 00 10 00")
    assert C.gba_lz77(stream) == b"A" * 275


def test_gba_lz77_prefixe_lz77():
    """Les fichiers DS peuvent précéder le flux du préfixe « LZ77 »."""
    stream = b"LZ77" + bytes.fromhex("10 06 00 00 20 41 42 10 01")
    assert C.gba_lz77(stream) == b"ABABAB"


def test_gba_lz77_refuse_un_mauvais_en_tete():
    try:
        C.gba_lz77(bytes.fromhex("20 06 00 00 20 41 42 10 01"))
    except C.DecompressionError:
        return
    raise AssertionError("un en-tête inconnu aurait dû être refusé")


def test_gba_lz77_reference_hors_tampon():
    try:
        C.gba_lz77(bytes.fromhex("10 04 00 00 80 FF FF"))
    except C.DecompressionError:
        return
    raise AssertionError("une référence hors tampon aurait dû être refusée")


# ---------------------------------------------------------------------------
# LC_LZ3 (Super Nintendo)
# ---------------------------------------------------------------------------


def test_lz3_copie_directe():
    assert C.lz3(bytes.fromhex("02 41 42 43 FF")) == b"ABC"


def test_lz3_remplissages():
    assert C.lz3(bytes.fromhex("23 58 FF")) == b"XXXX"
    assert C.lz3(bytes.fromhex("45 41 42 FF")) == b"ABABAB"
    assert C.lz3(bytes.fromhex("63 FF")) == bytes(4)


def test_lz3_repetition_relative():
    """Après « AB », une distance de 2 répète la paire."""
    stream = bytes.fromhex("01 41 42 83 81 FF")
    assert C.lz3(stream) == b"ABABAB"


def test_lz3_repetition_absolue():
    """Après « ABCD », l'adresse absolue 1 copie « BCD »."""
    stream = bytes.fromhex("03 41 42 43 44 82 00 01 FF")
    assert C.lz3(stream) == b"ABCDBCD"


def test_lz3_bits_inverses():
    """Commande 5 : les octets copiés sont inversés bit à bit."""
    stream = bytes.fromhex("01 41 42 A2 81 FF")
    assert C.lz3(stream) == bytes([0x41, 0x42, 0x82, 0x42, 0x41])


def test_lz3_repetition_a_l_envers():
    """Après « ABC », une distance de 1 recopie C, B puis A."""
    stream = bytes.fromhex("02 41 42 43 C2 80 FF")
    assert C.lz3(stream) == b"ABCCBA"


def test_lz3_longueur_etendue():
    """En-tête long : commande 0, longueur 32."""
    data = bytes(range(32))
    stream = bytes.fromhex("E0 1F") + data + bytes.fromhex("FF")
    assert C.lz3(stream) == data


def test_lz3_fin_immediate():
    assert C.lz3(bytes.fromhex("FF")) == b""


def test_lz3_reference_hors_tampon():
    try:
        C.lz3(bytes.fromhex("82 81 FF"))
    except C.DecompressionError:
        return
    raise AssertionError("une référence hors tampon aurait dû être refusée")


def test_lz3_flux_tronque():
    try:
        C.lz3(bytes.fromhex("02 41"))
    except C.DecompressionError:
        return
    raise AssertionError("un flux tronqué aurait dû être refusé")


#: Flux LC_LZ3 produit par l'implémentation de référence ``snes-squish``
#: (SMW-Editor) sur un motif de 426 octets. Ce n'est pas un aller-retour avec
#: notre propre décodeur : le vecteur vient d'un autre compresseur.
LZ3_VECTEUR_REFERENCE = bytes.fromhex(
    "0f000102030405060708090a0b0c0d0e0ff02f8f03414243449b837f7fe427aaf427"
    "808f003012101112131415161718191a1b1c1d1e1f58595af056825f0ff07fff")
LZ3_ATTENDU_REFERENCE = bytes.fromhex(
    "000102030405060708090a0b0c0d0e0f" * 4
    + "4142434441424344414243444142434441424344414243444142434441424344"
    + "00" * 64 + "aa" * 40 + "55aa" * 20
    + "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
    + "58595a" * 30 + "0ff0" * 16 + "00" * 32)


def test_lz3_vecteur_de_reference():
    """Vecteur produit par snes-squish, décodé par notre implémentation."""
    assert C.lz3(LZ3_VECTEUR_REFERENCE) == LZ3_ATTENDU_REFERENCE
