"""Tests du parseur de listes copper Amiga."""

from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import copper as C


def _instr(register: int, value: int) -> bytes:
    return struct.pack(">HH", register, value)


def _list() -> bytes:
    instructions = [
        (C.REG_BPLCON0, 0x6200),
        (C.REG_COLOR00, 0x0000),
        (C.REG_COLOR00 + 2, 0x0F00),
        (C.REG_COLOR00 + 4, 0x00F0),
        (C.REG_BPL1PTH, 0x0001),
        (C.REG_BPL1PTL, 0x2345),
        (C.REG_BPL1PTH + 4, 0x0002),
        (C.REG_BPL1PTH + 6, 0x3456),
        (C.REG_DIWSTRT, 0x2C81),
        (C.REG_DIWSTOP, 0xF4C1),
        (C.REG_DDFSTRT, 0x0038),
        (C.REG_DDFSTOP, 0x00D0),
        (C.REG_BPL1MOD, 0x0000),
        (C.COPPER_END, 0xFFFE),
    ]
    return b"".join(_instr(reg, value) for reg, value in instructions)


def test_copper_lecture():
    parsed = C.parse(b"JUNK" + _list(), 4)
    assert parsed.instructions == 13
    assert parsed.bitplanes == 6
    assert parsed.width == 320
    assert parsed.plane_ptrs[0] == 0x00012345
    assert parsed.plane_ptrs[1] == 0x00023456
    assert parsed.colors[1] == 0x0F00
    assert parsed.palette[1] == (255, 0, 0)


def test_copper_geometrie():
    parsed = C.parse(_list())
    geometry = parsed.geometry()
    assert geometry["bitplanes"] == 6
    assert geometry["width"] == 320
    assert geometry["diwstrt"] == 0x2C81


def test_copper_recherche():
    blob = b"\x00" * 32 + _list() + b"\x00" * 32
    lists = C.find_lists(blob)
    assert lists
    assert lists[0].offset == 32
    assert lists[0].bitplanes == 6


def test_copper_palette_defaut():
    parsed = C.parse(b"")
    assert parsed.instructions == 0
    assert parsed.palette[0] == (0, 0, 0)
