"""Tests des outils MCP Amiga (disque, écran, sprites, analyse)."""

from __future__ import annotations

import os
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.mcp import tools

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _encode(index: np.ndarray, planes: int, layout: str = "plane") -> bytes:
    height, width = index.shape
    stride = (width + 7) // 8
    out = bytearray()
    if layout == "plane":
        for plane in range(planes):
            for y in range(height):
                for bx in range(stride):
                    byte = 0
                    for k in range(8):
                        x = bx * 8 + k
                        bit = (index[y, x] >> plane) & 1 if x < width else 0
                        byte = (byte << 1) | int(bit)
                    out.append(byte)
    else:
        for y in range(height):
            for plane in range(planes):
                for bx in range(stride):
                    byte = 0
                    for k in range(8):
                        x = bx * 8 + k
                        bit = (index[y, x] >> plane) & 1 if x < width else 0
                        byte = (byte << 1) | int(bit)
                    out.append(byte)
    return bytes(out)


def _palette_bytes(count: int = 32) -> bytes:
    out = bytearray()
    for i in range(count):
        word = 0 if i == 0 else (((i * 3) & 0xF) << 8) | (((i * 5) & 0xF) << 4) | (i & 0xF)
        out += word.to_bytes(2, "big")
    return bytes(out)


def _temp_file(data: bytes, suffix: str = ".bin") -> str:
    descriptor, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
    return path


def test_decompress_nested():
    path = _temp_file((FIXTURES / "nested_imploder_rnc.imp").read_bytes())
    folder = tempfile.mkdtemp()
    previous = os.environ.get("TILEFORGE_MCP_DIR")
    os.environ["TILEFORGE_MCP_DIR"] = folder
    try:
        report = tools.decompress_nested(path)
        assert report["count"] == 2
        assert report["formats"] == {"imploder": 1, "rnc": 1}
        assert all("path" in blob for blob in report["blobs"])
        assert all(os.path.exists(blob["path"]) for blob in report["blobs"])
    finally:
        if previous is None:
            os.environ.pop("TILEFORGE_MCP_DIR", None)
        else:
            os.environ["TILEFORGE_MCP_DIR"] = previous
        os.unlink(path)


def test_amiga_screen():
    height, width, planes = 64, 64, 3
    index = np.zeros((height, width), dtype=np.int32)
    index[8:24, 8:24] = 1
    index[8:24, 32:48] = 2
    data = _encode(index, planes) + _palette_bytes()
    path = _temp_file(data)
    output = os.path.join(tempfile.mkdtemp(), "screen.png")
    try:
        report = tools.amiga_screen(path, offset=0, width=width,
                                    height=height, planes=planes,
                                    layout="plane", stride=8,
                                    palette_offset=-1, output=output)
        assert report["width"] == width
        assert report["planes"] == planes
        assert report["palette_source"]
        assert os.path.getsize(output) > 0
    finally:
        os.unlink(path)


def test_amiga_sprites():
    height, width, planes = 64, 64, 3
    index = np.zeros((height, width), dtype=np.int32)
    index[4:12, 4:12] = 1
    index[20:28, 20:28] = 2
    index[40:48, 40:48] = 3
    data = _encode(index, planes)
    path = _temp_file(data)
    output = os.path.join(tempfile.mkdtemp(), "sprites.png")
    try:
        report = tools.amiga_sprites(path, offset=0, width=width,
                                     height=height, planes=planes,
                                     layout="plane", stride=8, min_area=4,
                                     close_radius=0, output=output)
        assert report["sprites"] == 3
        assert report["grid"]["cell_w"] > 0
        assert os.path.getsize(output) > 0
    finally:
        os.unlink(path)


def test_amiga_analyze_hunk():
    def be(*values):
        return b"".join(struct.pack(">I", value) for value in values)

    code = bytes(range(16))
    data = (be(0x3F3, 1, 0, 0, 4) + be(0x3E9, 4) + code
            + be(0x3F2))
    path = _temp_file(data)
    try:
        report = tools.amiga_analyze(path)
        assert report["hunk"]["segments"][0]["kind"] == "code"
        assert report["hunk"]["segments"][0]["size"] == 16
    finally:
        os.unlink(path)
