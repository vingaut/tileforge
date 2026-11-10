"""Détection récursive des formats imbriqués.

Un fichier de jeu est rarement d'un seul tenant : une archive contient un
exécutable, qui contient des blocs compressés, qui contiennent des bitmaps.
TileForge s'arrêtait autrefois au premier niveau.  Ce module rescane chaque
résultat décompressé et poursuit la descente (profondeur limitée), en
signalant les formats reconnus mais non décodables au lieu de les ignorer.

Formats décodés ici
-------------------
``imploder``
    Les dix signatures d'Imploder (``IMP!``, ``ATN!``, ``BDPI``, ``CHFI``,
    ``Dupa``, ``EDAM``, ``FLT!``, ``M.H.``, ``PARA``, ``RDC9``).
``rnc``
    RNC ProPack méthode 1 ou 2 (clé optionnelle).
``crunchmania`` / ``turbo_packer``
    Signatures reconnues, décompression pas encore implémentée : le blob est
    signalé avec un avertissement, pour ne pas faire croire à un fichier vide.
``hunk``
    Exécutable Amiga (``0x000003F3``) : conteneur, décodé par
    :mod:`tileforge.core.hunk`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import imploder as imploder_mod
from . import rnc as rnc_mod

#: Profondeur maximale de descente.
DEFAULT_DEPTH = 4

#: Taille maximale d'un bloc décompressé (garde-fou mémoire).
MAX_BLOB = 64 << 20

#: Signatures reconnues mais sans décompresseur.
_UNSUPPORTED = {
    b"CrM!": "crunchmania",
    b"CrM2": "crunchmania",
    b"Crm!": "crunchmania",
    b"Crm2": "crunchmania",
    b"TPWM": "turbo_packer",
    b"SC68": "stonecracker",
}


@dataclass
class NestedBlob:
    """Un bloc trouvé dans un fichier, éventuellement décompressé."""

    offset: int
    format: str
    size: int
    depth: int = 0
    parent: int | None = None
    data: bytes | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def decompressed_size(self) -> int:
        return len(self.data) if self.data is not None else 0

    def as_dict(self, with_data: bool = False) -> dict:
        out = {
            "offset": self.offset,
            "format": self.format,
            "size": self.size,
            "depth": self.depth,
            "parent": self.parent,
            "decompressed_size": self.decompressed_size,
            "warnings": list(self.warnings),
        }
        if with_data and self.data is not None:
            out["data"] = self.data
        return out


def _find_all(data: bytes, needle: bytes, start: int = 0):
    index = data.find(needle, start)
    while index >= 0:
        yield index
        index = data.find(needle, index + 1)


def _candidates(data: bytes):
    """Énumère les signatures connues, sans doublon d'offset."""
    seen: set[int] = set()
    for magic in imploder_mod.IMPLODER_MAGICS:
        for offset in _find_all(data, magic):
            if offset not in seen and imploder_mod.is_imploder(data, offset):
                seen.add(offset)
                yield offset, "imploder"
    for offset in _find_all(data, b"RNC"):
        if offset not in seen and rnc_mod.is_rnc(data, offset):
            seen.add(offset)
            yield offset, "rnc"
    for magic, name in _UNSUPPORTED.items():
        for offset in _find_all(data, magic):
            if offset not in seen:
                seen.add(offset)
                yield offset, name
    for offset in _find_all(data, b"\x00\x00\x03\xF3"):
        if offset not in seen:
            seen.add(offset)
            yield offset, "hunk"


def _decompress(data: bytes, offset: int, fmt: str,
                key: int) -> tuple[bytes | None, int, list[str]]:
    """Décompresse un candidat ; renvoie (données, taille lue, avertissements)."""
    if fmt == "imploder":
        info = imploder_mod.inspect(data, offset)
        blob, warnings = imploder_mod.explode(data, offset)
        return blob, info["compressed_size"] + imploder_mod.FOOTER_SIZE, warnings
    if fmt == "rnc":
        info = rnc_mod.inspect(data, offset)
        blob, warnings = rnc_mod.unpack(data, offset, key=key)
        return blob, rnc_mod.HEADER_SIZE + info["packed_size"], warnings
    if fmt == "hunk":
        return None, 4, []
    return None, 4, [
        f"format {fmt} reconnu mais pas encore décompressé — bloc signalé "
        "pour ne pas le confondre avec des données brutes"]


def scan_nested(data: bytes, max_depth: int = DEFAULT_DEPTH,
                key: int = 0, max_total: int = 4 * MAX_BLOB) -> list[NestedBlob]:
    """Descend récursivement dans les formats imbriqués.

    Renvoie les blocs dans l'ordre de découverte, chaque enfant portant
    ``parent`` = offset du bloc qui l'a produit.  Les données décompressées
    sont conservées dans ``blob.data``.
    """
    results: list[NestedBlob] = []
    total = 0
    seen: set[tuple[int, str, int]] = set()

    def walk(payload: bytes, depth: int, parent: int | None) -> None:
        nonlocal total
        if depth > max_depth:
            return
        for offset, fmt in _candidates(payload):
            marker = (offset, fmt, depth)
            if marker in seen:
                continue
            seen.add(marker)
            if fmt == "hunk":
                results.append(NestedBlob(offset, fmt, 4, depth, parent))
                continue
            try:
                blob, size, warnings = _decompress(payload, offset, fmt, key)
            except Exception as exc:  # un candidat invalide ne doit pas arrêter
                results.append(NestedBlob(
                    offset, fmt, 4, depth, parent,
                    warnings=[f"{fmt} : {exc}"]))
                continue
            entry = NestedBlob(offset, fmt, max(4, size), depth, parent,
                               blob, warnings)
            results.append(entry)
            if blob is not None and depth < max_depth:
                total += len(blob)
                if total <= max_total:
                    walk(blob, depth + 1, offset)

    walk(data, 0, None)
    results.sort(key=lambda b: (b.offset, b.depth, b.format))
    return results


def summary(blobs: list[NestedBlob]) -> dict:
    """Résumé sérialisable d'un scan imbriqué."""
    formats: dict[str, int] = {}
    for blob in blobs:
        formats[blob.format] = formats.get(blob.format, 0) + 1
    return {
        "count": len(blobs),
        "formats": formats,
        "max_depth": max((b.depth for b in blobs), default=0),
        "decompressed_bytes": sum(b.decompressed_size for b in blobs),
        "blobs": [b.as_dict() for b in blobs],
    }
