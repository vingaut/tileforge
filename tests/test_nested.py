"""Tests de la détection récursive des formats imbriqués."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import nested as N

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_nested_imploder_puis_rnc():
    data = (FIXTURES / "nested_imploder_rnc.imp").read_bytes()
    blobs = N.scan_nested(data)
    formats = [(b.format, b.depth) for b in blobs]
    assert ("imploder", 0) in formats
    assert ("rnc", 1) in formats
    rnc_blob = next(b for b in blobs if b.format == "rnc")
    assert rnc_blob.data == (FIXTURES / "rnc_m1.raw").read_bytes()
    assert rnc_blob.parent == 0


def test_nested_resume():
    data = (FIXTURES / "nested_imploder_rnc.imp").read_bytes()
    report = N.summary(N.scan_nested(data))
    assert report["count"] == 2
    assert report["formats"] == {"imploder": 1, "rnc": 1}
    assert report["max_depth"] == 1
    assert report["decompressed_bytes"] >= 383 + 256


def test_nested_format_non_decode():
    data = b"JUNK" + b"CrM!" + b"\x00" * 64
    blobs = N.scan_nested(data)
    assert any(b.format == "crunchmania" for b in blobs)
    unsupported = next(b for b in blobs if b.format == "crunchmania")
    assert unsupported.data is None
    assert unsupported.warnings


def test_nested_hunk_signale():
    data = b"\x00" * 8 + b"\x00\x00\x03\xF3" + b"\x00" * 32
    blobs = N.scan_nested(data)
    assert any(b.format == "hunk" and b.offset == 8 for b in blobs)


def test_nested_profondeur_limitee():
    data = (FIXTURES / "nested_imploder_rnc.imp").read_bytes()
    blobs = N.scan_nested(data, max_depth=0)
    assert all(b.depth == 0 for b in blobs)
    assert not any(b.format == "rnc" for b in blobs)
