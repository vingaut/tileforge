"""Tests du parseur d'exécutables hunk Amiga."""

from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import hunk as H


def _be(*values: int) -> bytes:
    return b"".join(struct.pack(">I", value) for value in values)


def _build(sizes: tuple[int, ...] = (4, 8), flags: int = 0) -> bytes:
    code = bytes(range(16))
    data = b"D" * 32
    out = _be(H.HUNK_HEADER, len(sizes), 0, len(sizes) - 1)
    out += b"".join(struct.pack(">I", size | flags) for size in sizes)
    out += _be(H.HUNK_CODE, 4) + code
    out += _be(H.HUNK_RELOC32, 1, 1, 2, 0)
    out += _be(H.HUNK_END)
    out += _be(H.HUNK_DATA, 8) + data
    out += _be(H.HUNK_END)
    return out


def test_hunk_segments():
    parsed = H.parse(_build(), base=0x8000)
    assert len(parsed.segments) == 2
    code, data = parsed.segments
    assert code.kind == "code"
    assert code.size == 16
    assert code.data == bytes(range(16))
    assert code.vaddr == 0
    assert data.kind == "data"
    assert data.size == 32
    assert data.vaddr == 16
    assert code.relocations[0]["target"] == 1
    assert code.relocations[0]["offsets"] == [2]


def test_hunk_adresses():
    parsed = H.parse(_build(), base=0x8000)
    assert parsed.address_to_offset(0x8000) == parsed.segments[0].file_offset
    assert parsed.address_to_offset(0x8004) == parsed.segments[0].file_offset + 4
    assert parsed.address_to_offset(0x8010) == parsed.segments[1].file_offset
    assert parsed.address_to_offset(0x9000) is None
    assert parsed.offset_to_address(parsed.segments[1].file_offset) == 0x8010


def test_hunk_drapeaux_taille():
    parsed = H.parse(_build(flags=0x40000000), base=0)
    assert parsed.segments[0].size == 16
    assert any("drapeaux" in w for w in parsed.warnings)


def test_hunk_recherche():
    blob = b"JUNK" * 4 + _build()
    assert H.find_hunk(blob) == 16
    assert H.is_hunk(blob, 16)
    parsed = H.parse(blob, 16)
    assert parsed.offset == 16


def test_hunk_invalide():
    try:
        H.parse(b"\x00\x00\x03\xF3" + b"\x00" * 8)
    except H.HunkError:
        return
    raise AssertionError("un hunk tronqué doit être refusé")
