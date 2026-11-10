"""Tests du décompresseur Imploder (Amiga).

Le fichier ``imploder_data.imp`` a été produit par ``im-tools`` de Franck
Charlet (BSD 2-Clause), à partir de ``imploder_data.raw``.  Les variantes de
signature sont obtenues en remplaçant les quatre premiers octets : le reste
du flux est identique, comme sur les clones d'Imploder.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import compression as C
from tileforge.core import imploder as I

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_imploder_roundtrip():
    packed = _fixture("imploder_data.imp")
    expected = _fixture("imploder_data.raw")
    data, warnings = I.explode(packed)
    assert data == expected, "données Imploder différentes de la référence"
    assert warnings == [], warnings


def test_imploder_registry():
    packed = _fixture("imploder_data.imp")
    expected = _fixture("imploder_data.raw")
    assert C.decompress("imploder", packed) == expected


def test_imploder_dix_signatures():
    packed = _fixture("imploder_data.imp")
    expected = _fixture("imploder_data.raw")
    for magic in I.IMPLODER_MAGICS:
        variant = magic + packed[4:]
        assert I.is_imploder(variant), magic
        assert I.exploded_size(variant) == len(expected)
        assert I.explode(variant)[0] == expected, magic


def test_imploder_inspect():
    packed = _fixture("imploder_data.imp")
    info = I.inspect(packed)
    assert info["format"] == "imploder"
    assert info["magic"] == "IMP!"
    assert info["uncompressed_size"] == len(_fixture("imploder_data.raw"))
    assert info["compressed_size"] == int.from_bytes(packed[8:12], "big")


def test_imploder_checksum_avertissement():
    packed = bytearray(_fixture("imploder_data.imp"))
    end = int.from_bytes(packed[8:12], "big")
    packed[end + 0x2E] ^= 0xFF
    data, warnings = I.explode(bytes(packed))
    assert data == _fixture("imploder_data.raw")
    assert any("somme de contrôle" in w for w in warnings)


def test_imploder_tronque():
    packed = _fixture("imploder_data.imp")[:40]
    try:
        I.explode(packed)
    except I.ImploderError:
        return
    raise AssertionError("un flux tronqué doit être refusé")


def test_imploder_mauvais_magic():
    assert not I.is_imploder(b"RNC\x01" + b"\x00" * 40)
    try:
        I.explode(b"XXXX" + b"\x00" * 40)
    except I.ImploderError:
        return
    raise AssertionError("une signature inconnue doit être refusée")
