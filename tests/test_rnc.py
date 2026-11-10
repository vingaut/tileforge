"""Tests du décompresseur RNC ProPack.

Les flux ``pack1.rnc1`` / ``pack1.rnc2`` et leurs résultats attendus viennent
de l'implémentation de référence ``bitplane/propack`` (WTFPL) : ce sont des
vecteurs indépendants, pas des données fabriquées par ce décodeur.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import compression as C
from tileforge.core import rnc as R

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_rnc_methode1():
    data, warnings = R.unpack(_fixture("pack1.rnc1"))
    assert data == _fixture("pack1.expected")
    assert warnings == []


def test_rnc_methode2():
    data, warnings = R.unpack(_fixture("pack1.rnc2"))
    assert data == _fixture("pack1_m2.expected")
    assert warnings == []


def test_rnc_registry():
    assert C.decompress("rnc", _fixture("pack1.rnc1")) == _fixture("pack1.expected")


def test_rnc_inspect():
    info = R.inspect(_fixture("pack1.rnc2"))
    assert info["format"] == "rnc"
    assert info["method"] == 2
    assert info["unpacked_size"] == 1024
    assert R.is_rnc(_fixture("pack1.rnc2"))


def test_rnc_crc_avertissement():
    packed = bytearray(_fixture("pack1.rnc1"))
    packed[12] ^= 0xFF                       # CRC des données décompressées
    data, warnings = R.unpack(bytes(packed))
    assert data == _fixture("pack1.expected")
    assert any("CRC" in w for w in warnings)


def test_rnc_crc_verifie():
    packed = bytearray(_fixture("pack1.rnc1"))
    packed[12] ^= 0xFF
    try:
        R.unpack(bytes(packed), verify=True)
    except R.RncError:
        return
    raise AssertionError("verify=True doit lever sur un CRC invalide")


def test_rnc_tronque():
    try:
        R.unpack(_fixture("pack1.rnc1")[:40])
    except R.RncError:
        return
    raise AssertionError("un flux tronqué doit être refusé")
