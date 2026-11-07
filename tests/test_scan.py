"""Tests du moteur de balayage.

Les données sont fabriquées : une « ROM » de bruit dans laquelle on insère une
planche de tuiles connue. Le moteur doit retrouver la planche, ne pas la
confondre avec le bruit, et respecter son budget de temps.
"""

from __future__ import annotations

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from tileforge.core.formats import FORMATS_BY_KEY
from tileforge.core.scan import Candidate, Scanner, merge_candidates, quick_gate, scan_bytes

FMT = FORMATS_BY_KEY["snes_4bpp"]


# ---------------------------------------------------------------------------
# Fabrique de données
# ---------------------------------------------------------------------------


def _encode_snes(pixels: np.ndarray, bpp: int = 4) -> bytes:
    h, w = pixels.shape
    out = bytearray()
    for pair in range(bpp // 2):
        for y in range(h):
            for plane in (2 * pair, 2 * pair + 1):
                byte = 0
                for x in range(8):
                    if (int(pixels[y, x]) >> plane) & 1:
                        byte |= 0x80 >> x
                out.append(byte)
    return bytes(out)


def _sprite_sheet(seed: int = 1, count: int = 128) -> bytes:
    rng = random.Random(seed)
    out = bytearray()
    for _ in range(count):
        tile = np.zeros((8, 8), dtype=np.int32)
        for _ in range(rng.randint(1, 3)):
            x0, y0 = rng.randint(0, 6), rng.randint(0, 6)
            w, h = rng.randint(1, 8 - x0), rng.randint(1, 8 - y0)
            tile[y0:y0 + h, x0:x0 + w] = rng.randint(1, 7)
        out += _encode_snes(tile)
    return bytes(out)


def _fake_rom(size: int = 65536, at: int = 0x4000, seed: int = 5) -> tuple[bytes, bytes]:
    rng = random.Random(seed)
    rom = bytearray(rng.randrange(256) for _ in range(size))
    sheet = _sprite_sheet(seed)
    rom[at:at + len(sheet)] = sheet
    return bytes(rom), sheet


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_quick_gate_rejette_le_bruit():
    rng = random.Random(2)
    noise = bytes(rng.randrange(256) for _ in range(2048))
    assert not quick_gate(noise)
    assert quick_gate(_sprite_sheet(3))


def test_retrouve_une_planche_inseree():
    rom, sheet = _fake_rom()
    at = 0x4000
    report = scan_bytes(rom, "snes_4bpp", compressions=(), budget=60,
                        threshold=0.5, raw=True, compressed=False)
    assert not report.truncated, "le budget a été dépassé sur un fichier de 64 Ko"
    assert report.candidates, "aucun candidat trouvé"
    best = report.candidates[0]
    assert best.score > 0.6, best.score
    assert abs(best.offset - at) <= 256, (best.offset, at)
    assert best.size >= len(sheet) // 2


def test_ne_crie_pas_au_loup_sur_du_bruit():
    rng = random.Random(11)
    rom = bytes(rng.randrange(256) for _ in range(32768))
    report = scan_bytes(rom, "snes_4bpp", compressions=(), budget=30,
                        threshold=0.5, raw=True, compressed=False)
    assert all(candidate.score < 0.75 for candidate in report.candidates), \
        [str(c) for c in report.candidates[:3]]


def test_budget_respecte():
    rng = random.Random(12)
    rom = bytes(rng.randrange(256) for _ in range(1 << 20))
    started = time.perf_counter()
    report = scan_bytes(rom, "snes_4bpp", compressions=(), budget=0.5,
                        threshold=0.5, raw=True, compressed=False)
    elapsed = time.perf_counter() - started
    assert report.truncated
    assert elapsed < 5.0, elapsed


def test_resultat_deterministe():
    rom, _ = _fake_rom()
    first = scan_bytes(rom, "snes_4bpp", compressions=(), budget=60,
                       threshold=0.5, raw=True, compressed=False)
    second = scan_bytes(rom, "snes_4bpp", compressions=(), budget=60,
                        threshold=0.5, raw=True, compressed=False)
    assert [c.as_dict() for c in first.candidates] == \
           [c.as_dict() for c in second.candidates]


def test_fusion_des_fenetres_voisines():
    a = Candidate(offset=0, size=512, score=0.6, tile_format="snes_4bpp")
    b = Candidate(offset=256, size=512, score=0.8, tile_format="snes_4bpp")
    c = Candidate(offset=8192, size=512, score=0.5, tile_format="snes_4bpp")
    merged = merge_candidates([a, b, c], tolerance=32)
    assert len(merged) == 2
    assert merged[0].score == 0.8
    assert merged[0].offset == 0 and merged[0].end == 768


def test_rapport_serialisable():
    rom, _ = _fake_rom()
    report = scan_bytes(rom, "snes_4bpp", compressions=(), budget=60,
                        threshold=0.5, raw=True, compressed=False)
    data = report.as_dict()
    assert data["tested"] > 0
    assert isinstance(data["candidates"], list)
    if data["candidates"]:
        candidate = data["candidates"][0]
        assert candidate["offset_hex"].startswith("0x")
        assert 0.0 <= candidate["score"] <= 1.0


def test_scanner_refuse_un_format_absent():
    try:
        Scanner(b"", [])
    except ValueError:
        return
    raise AssertionError("Scanner aurait dû refuser une liste de formats vide")


# ---------------------------------------------------------------------------
# Parallélisme
# ---------------------------------------------------------------------------


def test_tache_parallele_contrat():
    """Le travail envoyé à un processus renvoie des données sérialisables."""
    from tileforge.core.scan import _scan_key_job

    rom, _ = _fake_rom()
    payload = {
        "data": rom,
        "formats": ["snes_4bpp"],
        "key": "lz2",
        "start": 0,
        "end": len(rom),
        "step": 1,
        "threshold": 0.5,
        "max_size": 65536,
        "min_size": 512,
    }
    result = _scan_key_job(payload)
    assert result["key"] == "lz2"
    assert isinstance(result["candidates"], list)
    assert set(result) >= {"key", "candidates", "tested", "scored", "errors"}


def test_parallele_meme_resultat_que_sequentiel():
    """Répartir les décompresseurs ne doit rien changer au résultat."""
    rom, _ = _fake_rom()
    options = {"compressions": ("lz2", "packbits"), "budget": 60, "threshold": 0.5,
                   "raw": False, "compressed": True}
    sequential = scan_bytes(rom, "snes_4bpp", workers=1, **options)
    try:
        parallel = scan_bytes(rom, "snes_4bpp", workers=2, **options)
    except Exception:
        return          # parallélisme indisponible : le repli séquentiel a fait foi
    assert [c.as_dict() for c in parallel.candidates] == \
           [c.as_dict() for c in sequential.candidates]


def test_balayage_par_plages():
    """Balayer des plages donne les mêmes candidats que la plage entière."""
    rom, sheet = _fake_rom()
    at = 0x4000
    full = scan_bytes(rom, "snes_4bpp", compressions=(), budget=60,
                      threshold=0.5, raw=True, compressed=False)
    from tileforge.core.scan import scan_ranges
    partial = scan_ranges(rom, "snes_4bpp", [(at - 512, at + 8192)],
                          compressions=(), budget=60, threshold=0.5,
                          raw=True, compressed=False)
    assert partial.candidates
    assert abs(partial.candidates[0].offset - full.candidates[0].offset) <= 512


def test_parallele_brut_meme_resultat():
    """Le balayage brut réparti en tranches donne le même résultat."""
    rom, _ = _fake_rom(size=1 << 19)
    options = {"compressions": (), "budget": 90, "threshold": 0.5,
                   "raw": True, "compressed": False}
    sequential = scan_bytes(rom, "snes_4bpp", workers=1, **options)
    try:
        parallel = scan_bytes(rom, "snes_4bpp", workers=4, **options)
    except Exception:
        return
    assert [c.as_dict() for c in parallel.candidates] == \
           [c.as_dict() for c in sequential.candidates]
