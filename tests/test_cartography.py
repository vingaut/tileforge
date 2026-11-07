"""Tests de la cartographie de ROM.

Les ROMs sont fabriquées : on pose un en-tête connu dans un tampon et on
vérifie que la plateforme, les zones et les tables de pointeurs sont bien
retrouvées.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import cartography as C

# ---------------------------------------------------------------------------
# Fabrique d'en-têtes
# ---------------------------------------------------------------------------


def _nes_rom() -> bytes:
    header = bytearray(16)
    header[0:4] = b"NES\x1a"
    header[4] = 8          # 8 banques PRG
    header[5] = 4          # 4 banques CHR
    header[6] = 0x10       # mapper 1 (nibble bas)
    header[7] = 0x00
    return bytes(header) + bytes(4096)


def _megadrive_rom() -> bytes:
    data = bytearray(0x200)
    data[0x100:0x104] = b"SEGA"
    data[0x110:0x120] = b"SEGA MEGA DRIVE "
    data[0x120:0x130] = b"TEST GAME       "
    return bytes(data) + bytes(4096)


def _gameboy_rom() -> bytes:
    data = bytearray(0x200)
    data[0x104:0x10C] = bytes([0xCE, 0xED, 0x66, 0x66, 0xCC, 0x0D, 0x00, 0x0B])
    data[0x134:0x13C] = b"TETRIS  "
    return bytes(data) + bytes(4096)


def _snes_rom(valid: bool = True) -> bytes:
    data = bytearray(0x10000)
    base = 0x7FC0
    data[base:base + 21] = b"SUPER TEST GAME 2026 ".ljust(21, b" ")
    data[base + 0x15] = 0x20          # LoROM
    checksum = 0x1234
    complement = 0xFFFF ^ checksum if valid else 0x0000
    data[base + 0x1C] = complement & 0xFF
    data[base + 0x1D] = complement >> 8
    data[base + 0x1E] = checksum & 0xFF
    data[base + 0x1F] = checksum >> 8
    return bytes(data)


# ---------------------------------------------------------------------------
# Plateforme
# ---------------------------------------------------------------------------


def test_plateforme_nes():
    platform = C.detect_platform(_nes_rom())
    assert platform.key == "nes"
    assert platform.details["mapper"] == 1


def test_plateforme_megadrive():
    platform = C.detect_platform(_megadrive_rom())
    assert platform.key == "megadrive"
    assert "MEGA DRIVE" in platform.details["console"]


def test_plateforme_gameboy():
    platform = C.detect_platform(_gameboy_rom())
    assert platform.key == "gameboy"
    assert platform.title.startswith("TETRIS")


def test_plateforme_snes_avec_somme_valide():
    platform = C.detect_platform(_snes_rom(valid=True))
    assert platform.key == "snes"
    assert platform.confidence >= 0.9
    assert platform.details["checksum_ok"] is True


def test_plateforme_snes_sans_somme_valide():
    platform = C.detect_platform(_snes_rom(valid=False))
    assert platform.key == "snes"
    assert platform.confidence < 0.9


def test_plateforme_inconnue():
    rng = random.Random(3)
    assert C.detect_platform(bytes(rng.randrange(256) for _ in range(8192))).key == "unknown"


# ---------------------------------------------------------------------------
# Entropie
# ---------------------------------------------------------------------------


def test_entropie_cas_limites():
    assert C.shannon_entropy(b"") == 0.0
    assert C.shannon_entropy(bytes(4096)) == 0.0
    assert C.shannon_entropy(bytes([0, 1]) * 2048) == 1.0
    rng = random.Random(5)
    assert C.shannon_entropy(bytes(rng.randrange(256) for _ in range(8192))) > 7.5


def test_profil_et_fusion():
    rng = random.Random(1)
    data = bytes(4096) + bytes(rng.randrange(256) for _ in range(4096))
    zones = C.merge_zones(C.entropy_profile(data, window=1024))
    assert zones[0].kind == "vide"
    assert zones[-1].kind in ("compressé ou aléatoire", "code probable")
    assert sum(zone.size for zone in zones) == len(data)


# ---------------------------------------------------------------------------
# Tables de pointeurs
# ---------------------------------------------------------------------------


def _table(values: list[int], width: int = 2, big_endian: bool = True) -> bytes:
    out = bytearray()
    for value in values:
        out += value.to_bytes(width, "big" if big_endian else "little")
    return bytes(out)


def test_table_de_pointeurs_trouvee():
    body = bytes(8192)
    table = _table([0x1000 + index * 16 for index in range(40)])
    data = body + table + body
    tables = C.find_pointer_tables(data)
    assert tables, "aucune table trouvée"
    best = max(tables, key=lambda item: item.count)
    assert best.count >= 40
    assert best.offset == len(body)
    assert best.width == 2 and best.big_endian is True


def test_pas_de_table_dans_du_bruit():
    rng = random.Random(9)
    data = bytes(rng.randrange(256) for _ in range(16384))
    # Du bruit peut produire des suites courtes ; on exige une longueur franche.
    tables = C.find_pointer_tables(data, min_count=16)
    assert all(table.count < 64 for table in tables)


def test_rapport_complet():
    report = C.cartography(_snes_rom())
    assert report["platform"]["key"] == "snes"
    assert report["size"] == len(_snes_rom())
    assert report["summary"]["zones"] == len(report["zones"])
    assert isinstance(report["pointer_tables"], list)
    assert isinstance(report["blocks"], list)
    text = C.describe(report)
    assert "Super Nintendo" in text


def test_blocs_delimites_par_les_pointeurs():
    """Chaque pointeur ouvre un bloc qui va jusqu'au suivant."""
    body = bytes(4096)
    # huit pointeurs au moins : en dessous, le hasard produit trop de faux
    # positifs et la détection exige une fenêtre de départ plus longue.
    starts = [0x1000, 0x1200, 0x1500, 0x1900, 0x1A00, 0x1B00, 0x1C00]
    table = _table(starts + [0x1D00])
    data = body + table + bytes(8192)
    tables = C.find_pointer_tables(data)
    blocks = C.table_blocks(data, tables, min_size=16)
    assert blocks, "aucun bloc"
    sizes = {block["offset"]: block["size"] for block in blocks}
    assert sizes.get(0x1000) == 0x200
    assert sizes.get(0x1200) == 0x300
    assert sizes.get(0x1500) == 0x400


def test_plages_structurees():
    """Les zones de données sont retrouvées, le vide et le bruit écartés."""
    rng = random.Random(7)
    data = (bytes(4096)
            + bytes(rng.randrange(4) for _ in range(4096))     # structuré
            + bytes(rng.randrange(256) for _ in range(4096)))  # bruit
    ranges = C.structured_ranges(data, window=1024, min_size=512)
    assert ranges
    assert all(start >= 4096 and end <= 8192 for start, end in ranges)
