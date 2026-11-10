"""Tests du système de fichiers AmigaDOS (ADF/ADZ).

Les images sont fabriquées par le test : aucun contenu de jeu commercial
n'est utilisé.  Le générateur construit un volume 880 Ko minimal (bloc de
démarrage, racine, en-tête de fichier, blocs de données), en OFS et en FFS,
avec ou sans checksums valides.
"""

from __future__ import annotations

import gzip
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import amigadisk as D


def _put(block: bytearray, offset: int, value: int, size: int = 4) -> None:
    block[offset:offset + size] = value.to_bytes(size, "big")


def _bstr(block: bytearray, offset: int, text: str) -> None:
    raw = text.encode("latin-1")
    block[offset] = len(raw)
    block[offset + 1:offset + 1 + len(raw)] = raw


def _checksum(block: bytearray, offset: int = 20) -> None:
    _put(block, offset, 0)
    total = sum(int.from_bytes(block[i:i + 4], "big")
                for i in range(0, len(block), 4)) & 0xFFFFFFFF
    _put(block, offset, (-total) & 0xFFFFFFFF)


def make_adf(ffs: bool = False, corrupt: bool = False,
             directory: bool = False,
             protection: bool = False) -> tuple[bytes, bytes]:
    """Construit une image ADF minimale et renvoie (image, contenu attendu)."""
    blocks = 1760
    block_size = 512
    image = bytearray(blocks * block_size)

    boot = bytearray(1024)
    boot[0:3] = b"DOS"
    boot[3] = 1 if ffs else 0
    _put(boot, 8, 880)
    _put(boot, 12, 0x2E)
    _put(boot, 4, 0)
    total = sum(int.from_bytes(boot[i:i + 4], "big")
                for i in range(0, 1024, 4)) & 0xFFFFFFFF
    _put(boot, 4, (-total) & 0xFFFFFFFF)
    if protection:
        boot[64:72] = b"Copylock"
    image[0:1024] = boot

    root = bytearray(block_size)
    _put(root, 0, D.T_HEADER)
    _put(root, 12, D.ROOT_HASH_SIZE)
    _put(root, 312, 0xFFFFFFFF)
    _bstr(root, 432, "TestVol")
    _checksum(root)

    content = b"Hello, Amiga! " * 10
    step = 512 if ffs else 488

    def add_file(header_block: int, parent: int, name: str, data: bytes) -> None:
        header = bytearray(block_size)
        _put(header, 0, D.T_HEADER)
        _put(header, 4, header_block)
        _put(header, 8, 1 + (len(data) + step - 1) // step)
        _put(header, 12, len(data))
        _put(header, 16, header_block + 1)
        _put(header, 316, parent)
        _put(header, 324, D.ST_FILE & 0xFFFFFFFF)
        _bstr(header, 432, name)
        chunks = [data[i:i + step] for i in range(0, len(data), step)]
        for index, chunk in enumerate(chunks):
            number = header_block + 1 + index
            _put(header, 24 + index * 4, number)
            block = bytearray(block_size)
            if not ffs:
                _put(block, 0, D.T_DATA)
                _put(block, 4, header_block)
                _put(block, 8, index + 1)
                _put(block, 12, len(chunk))
                block[24:24 + len(chunk)] = chunk
                _checksum(block)
            else:
                block[0:len(chunk)] = chunk
            image[number * block_size:(number + 1) * block_size] = block
        _checksum(header)
        image[header_block * block_size:(header_block + 1) * block_size] = header

    if directory:
        folder = bytearray(block_size)
        _put(folder, 0, D.T_HEADER)
        _put(folder, 4, 890)
        _put(folder, 12, D.ROOT_HASH_SIZE)
        _put(folder, 316, 880)
        _put(folder, 324, D.ST_USERDIR)
        _bstr(folder, 432, "SUB")
        add_file(891, 890, "INNER.TXT", content)
        bucket = D._hash_name("SUB") % D.ROOT_HASH_SIZE
        _put(root, 24 + bucket * 4, 890)
        _checksum(root)
        image[880 * block_size:881 * block_size] = root
        bucket = D._hash_name("INNER.TXT") % D.ROOT_HASH_SIZE
        _put(folder, 24 + bucket * 4, 891)
        _checksum(folder)
        image[890 * block_size:891 * block_size] = folder
    else:
        add_file(881, 880, "HELLO.TXT", content)
        bucket = D._hash_name("HELLO.TXT") % D.ROOT_HASH_SIZE
        _put(root, 24 + bucket * 4, 881)
        _checksum(root)
        if corrupt:
            root[20] ^= 0xFF
        image[880 * block_size:881 * block_size] = root

    return bytes(image), content


def test_adf_ofs():
    image, content = make_adf()
    volume = D.open_disk(data=image)
    assert volume.name == "TestVol"
    assert not volume.ffs
    assert [f.path for f in volume.files()] == ["TestVol/HELLO.TXT"]
    assert volume.extract("HELLO.TXT") == content
    assert volume.warnings == []


def test_adf_ffs():
    image, content = make_adf(ffs=True)
    volume = D.open_disk(data=image)
    assert volume.ffs
    assert volume.extract("hello.txt") == content


def test_adf_checksum_invalide_tolere():
    image, content = make_adf(corrupt=True)
    volume = D.open_disk(data=image)
    assert volume.extract("HELLO.TXT") == content
    assert any("checksum invalide" in w for w in volume.warnings)


def test_adf_repertoire():
    image, content = make_adf(directory=True)
    volume = D.open_disk(data=image)
    tree = volume.list()
    assert tree[0]["name"] == "SUB"
    assert tree[0]["children"][0]["name"] == "INNER.TXT"
    assert volume.extract("SUB/INNER.TXT") == content


def test_adf_protection_detectee():
    image, _ = make_adf(protection=True)
    volume = D.open_disk(data=image)
    assert any("Copylock" in w for w in volume.warnings)


def test_adz_gzip():
    image, content = make_adf()
    volume = D.open_disk(data=gzip.compress(image), kind="adz")
    assert volume.extract("HELLO.TXT") == content


def test_ipf_explique():
    try:
        D.open_disk(data=b"CAPS" + b"\x00" * 200)
    except D.UnsupportedDiskError as exc:
        assert "ADF" in str(exc)
        return
    raise AssertionError("un IPF doit être refusé avec une explication")


def test_dms_explique():
    try:
        D.open_disk(data=b"DMS!" + b"\x00" * 200)
    except D.UnsupportedDiskError as exc:
        assert "ADF" in str(exc)
        return
    raise AssertionError("un DMS doit être refusé avec une explication")


def test_inspect_file_disque():
    from tileforge.mcp import tools

    image, _ = make_adf()
    with tempfile.NamedTemporaryFile(suffix=".adf", delete=False) as handle:
        handle.write(image)
        path = handle.name
    try:
        info = tools.inspect_file(path)
        assert info["kind"] == "disque"
        assert info["machine"] == "Amiga"
        assert info["file_count"] == 1
    finally:
        os.unlink(path)
