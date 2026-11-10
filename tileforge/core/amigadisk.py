"""Disques Amiga : ADF, ADZ et système de fichiers AmigaDOS.

Ce module ouvre une image de disquette Amiga et donne accès à ses fichiers
comme s'il s'agissait d'une archive.  Il est volontairement **tolérant aux
checksums invalides** : une grande partie du catalogue Amiga est protégée
(Rob Northen Copylock, SPS…), et un outil qui refuse le volume est
inutilisable sur ces disques.  Les incohérences sont signalées, jamais
fatales.

Formats
-------
``.adf`` / ``.adz``
    Image de disquette brute (901 120 octets pour une disquette 880 Ko) ou
    compressée en gzip.  Blocs de 512 ou 1024 octets, OFS ou FFS.
``.hdf``
    Disque dur brut : même système de fichiers, géométrie déduite de la
    taille.
``.ipf``
    Flux de cellules CAPS/SPS : détecté et expliqué, mais pas décodé (la
    licence SPS n'est pas libre).  La conversion en ADF est proposée.
``.dms``
    Archive disque DMS : détectée, pas encore décodée.

Système de fichiers
-------------------
Bloc racine au milieu du volume, table de hachage de 72 entrées, chaînes
``next_hash`` / ``parent``, blocs d'en-tête de fichier et blocs d'extension.
En OFS, chaque bloc de données porte un en-tête de 24 octets (488 octets
utiles) ; en FFS, les données sont contiguës par blocs de 512 octets.

API
---
::

    volume = open_disk("jeu.adf")
    volume.warnings          # ["checksums AmigaDOS invalides…"]
    volume.list()            # arborescence sérialisable
    data = volume.extract("NIVEAU1/SPRITES.BIN")

Références : la structure AmigaDOS est décrite dans le Guide du développeur
Amiga (RKM « Devices »), et les tolérances de protection ont été vérifiées
sur les disques Team17 de Project-X.
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass, field

#: Taille d'une disquette Amiga 880 Ko.
ADF_SIZE = 901120

#: Taille d'un bloc AmigaDOS standard.
DEFAULT_BLOCK_SIZE = 512

#: Nombre d'entrées de la table de hachage de la racine.
ROOT_HASH_SIZE = 72

#: Types de blocs AmigaDOS.
T_HEADER = 2
T_LIST = 16
T_DATA = 8
T_BITMAP = 5

#: Types secondaires d'un bloc d'en-tête.
ST_FILE = -3
ST_USERDIR = 2
ST_SOFTLINK = 3
ST_LINKDIR = 4


class DiskError(Exception):
    """Image de disque illisible."""


class UnsupportedDiskError(DiskError):
    """Format de disque reconnu mais non pris en charge nativement."""


def _u32(block: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(block[offset:offset + 4], "big")


def _u16(block: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(block[offset:offset + 2], "big")


def _bstr(block: bytes | bytearray, offset: int) -> str:
    length = block[offset] if offset < len(block) else 0
    length = min(length, 30, max(0, len(block) - offset - 1))
    return bytes(block[offset + 1:offset + 1 + length]).decode(
        "latin-1", "replace").strip("\x00 ")


def _hash_name(name: str) -> int:
    """Fonction de hachage AmigaDOS (init = longueur, ×13 + octet)."""
    value = len(name)
    for char in name.upper().encode("latin-1", "replace"):
        value = (value * 13 + char) & 0x7FF
    return value


@dataclass
class DiskNode:
    """Fichier ou répertoire d'un volume AmigaDOS."""

    name: str
    block: int
    is_dir: bool
    size: int = 0
    parent: int = 0
    path: str = ""
    children: list[DiskNode] = field(default_factory=list)

    def as_dict(self, depth: int = 0, max_depth: int = 4) -> dict:
        out = {
            "name": self.name,
            "path": self.path,
            "block": self.block,
            "type": "dir" if self.is_dir else "file",
            "size": self.size,
        }
        if self.is_dir and depth < max_depth:
            out["children"] = [c.as_dict(depth + 1, max_depth)
                               for c in self.children]
        elif self.is_dir:
            out["children_count"] = len(self.children)
        return out


class Volume:
    """Volume AmigaDOS ouvert, avec sa tolérance aux protections."""

    def __init__(self, data: bytes, source: str = "", kind: str = "adf"):
        self.source = source
        self.kind = kind
        self.data = data
        self.warnings: list[str] = []
        self.block_size = DEFAULT_BLOCK_SIZE
        self.ffs = False
        self.boot: dict = {}
        self.name = ""
        self.root_block = 0
        self.root: DiskNode | None = None
        self._headers: dict[int, bytes] = {}
        self._visited_dirs: set[int] = set()
        self._parse()

    # -- accès aux blocs ----------------------------------------------------

    @property
    def block_count(self) -> int:
        return len(self.data) // self.block_size

    def block(self, number: int) -> bytes:
        if number < 0 or number >= self.block_count:
            raise DiskError(f"bloc {number} hors du volume")
        start = number * self.block_size
        return self.data[start:start + self.block_size]

    def _checksum_ok(self, block: bytes) -> bool:
        """Somme des longs du bloc, checksum compris : elle doit être nulle."""
        total = 0
        for offset in range(0, len(block) - 3, 4):
            total = (total + _u32(block, offset)) & 0xFFFFFFFF
        return total == 0

    # -- analyse ------------------------------------------------------------

    def _parse(self) -> None:
        if len(self.data) < 100 * 1024:
            raise DiskError(f"image trop petite : {len(self.data)} octets")
        if len(self.data) % 512:
            raise DiskError("taille d'image non multiple de 512 octets")

        boot = self.data[:1024]
        if len(boot) >= 4 and boot[:3] == b"DOS":
            flags = boot[3]
            self.ffs = bool(flags & 1)
            self.boot = {
                "magic": "DOS",
                "flags": flags,
                "filesystem": "FFS" if self.ffs else "OFS",
                "version": _u32(boot, 12) if len(boot) >= 16 else 0,
            }
            if flags & ~0x07:
                self.warnings.append(
                    f"drapeaux de démarrage inhabituels : 0x{flags:02X}")
            if not self._boot_checksum_ok(boot):
                self.warnings.append(
                    "bloc de démarrage : checksum invalide — protection probable "
                    "(Copylock ou équivalent)")
        else:
            self.warnings.append(
                "pas de bloc de démarrage DOS : volume ouvert en lecture brute")

        self._choose_block_size()
        self.root_block = self.block_count // 2
        root = self.block(self.root_block)
        if _u32(root, 0) != T_HEADER:
            # Certaines images ont un bloc racine ailleurs : on cherche un
            # en-tête plausible avec une table de hachage.
            found = self._find_root()
            if found is None:
                raise DiskError("bloc racine AmigaDOS introuvable")
            self.root_block = found
            root = self.block(self.root_block)

        if not self._checksum_ok(root):
            self.warnings.append(
                f"bloc racine ({self.root_block}) : checksum invalide — "
                "probablement une protection (Copylock ?)")
        self.name = _bstr(root, 432) or "Volume"
        self.root = DiskNode(self.name, self.root_block, True, 0, 0, self.name)
        self._read_directory(self.root, root, root_block=self.root_block)
        self._detect_protection()

    def _boot_checksum_ok(self, boot: bytes) -> bool:
        total = 0
        for offset in range(0, 1024, 4):
            total = (total + _u32(boot, offset)) & 0xFFFFFFFF
        return total == 0

    def _choose_block_size(self) -> None:
        for size in (512, 1024):
            if len(self.data) % size:
                continue
            count = len(self.data) // size
            root_number = count // 2
            if root_number * size + 512 > len(self.data):
                continue
            block = self.data[root_number * size:root_number * size + size]
            if _u32(block, 0) == T_HEADER:
                ht_size = _u32(block, 12)
                if 1 <= ht_size <= 256:
                    self.block_size = size
                    return
        self.block_size = 512

    def _find_root(self) -> int | None:
        for number in range(self.block_count - 1, 0, -1):
            block = self.block(number)
            if _u32(block, 0) != T_HEADER:
                continue
            ht_size = _u32(block, 12)
            if 1 <= ht_size <= 256 and block[432] <= 30:
                return number
        return None

    def _detect_protection(self) -> None:
        haystack = (self.data[:1024] + self.block(self.root_block)).lower()
        for needle, label in (
                (b"copylock", "Copylock"),
                (b"rob northen", "Rob Northen"),
                (b"rnc", "RNC ProPack"),
                (b"sps", "SPS/CAPS")):
            if needle in haystack:
                self.warnings.append(
                    f"chaîne « {label} » trouvée : les checksums peuvent être "
                    "falsifiés et les données chiffrées")
        # Les protections rendent les checksums faux : on le dit une fois.
        invalid = [w for w in self.warnings if "checksum invalide" in w]
        if len(invalid) > 1:
            self.warnings.append(
                f"{len(invalid)} blocs à checksum invalide : lecture brute "
                "poursuivie, les données restent accessibles")

    # -- arborescence -------------------------------------------------------

    def _read_directory(self, node: DiskNode, block: bytes,
                        root_block: int) -> None:
        if node.block in self._visited_dirs:
            return
        self._visited_dirs.add(node.block)
        ht_size = _u32(block, 12)
        if ht_size < 1 or ht_size > 256:
            ht_size = ROOT_HASH_SIZE
        seen: set[int] = set()
        for index in range(ht_size):
            entry_offset = 24 + index * 4
            if entry_offset + 4 > len(block):
                break
            number = _u32(block, entry_offset)
            while number:
                if number in seen or number <= 0 or number >= self.block_count:
                    break
                seen.add(number)
                header = self.block(number)
                if _u32(header, 0) != T_HEADER:
                    break
                child = self._node_from_header(number, header, node.path)
                if child is not None:
                    node.children.append(child)
                number = _u32(header, 312)

    def _node_from_header(self, number: int, header: bytes,
                          parent_path: str) -> DiskNode | None:
        name = _bstr(header, 432)
        if not name:
            name = f"bloc_{number}"
        sec_type = int.from_bytes(header[324:328], "big", signed=True)
        is_dir = sec_type == ST_USERDIR
        size = _u32(header, 12)
        path = f"{parent_path}/{name}" if parent_path else name
        node = DiskNode(name, number, is_dir, size, 0, path)
        if not self._checksum_ok(header):
            self.warnings.append(
                f"en-tête « {name} » (bloc {number}) : checksum invalide")
        if is_dir:
            self._read_directory(node, header, root_block=number)
        else:
            self._headers[number] = header
        return node

    # -- extraction ---------------------------------------------------------

    def find(self, path: str) -> DiskNode:
        """Retrouve un nœud par chemin (insensible à la casse)."""
        if self.root is None:
            raise DiskError("volume non analysé")
        cleaned = path.replace("\\", "/").strip("/")
        parts = [p for p in cleaned.split("/") if p]
        if parts and parts[0].upper() == self.name.upper():
            parts = parts[1:]
        node = self.root
        for part in parts:
            match = next((c for c in node.children
                          if c.name.upper() == part.upper()), None)
            if match is None:
                raise DiskError(f"chemin introuvable : {path}")
            node = match
        return node

    def _data_blocks(self, header_block: int) -> tuple[list[int], int]:
        """Liste des blocs de données d'un fichier, dans l'ordre."""
        blocks: list[int] = []
        block = self.block(header_block)
        size = _u32(block, 12)
        current = block
        guard = 0
        while True:
            for index in range(72):
                number = _u32(current, 24 + index * 4)
                if number:
                    blocks.append(number)
            extension = _u32(current, 320)
            if not extension:
                break
            guard += 1
            if guard > 256 or extension >= self.block_count:
                self.warnings.append(
                    f"chaîne d'extension suspecte pour le bloc {header_block}")
                break
            current = self.block(extension)
            if _u32(current, 0) != T_LIST:
                break
        if not blocks:
            first = _u32(block, 16)
            if first and first < self.block_count:
                if self.ffs:
                    count = (size + self.block_size - 1) // self.block_size
                    blocks = [first + index for index in range(count)
                              if first + index < self.block_count]
                else:
                    number = first
                    guard = 0
                    while number and number < self.block_count and guard < 4096:
                        blocks.append(number)
                        number = _u32(self.block(number), 16)
                        guard += 1
        return blocks, size

    def extract(self, node: DiskNode | str) -> bytes:
        """Extrait le contenu d'un fichier."""
        if isinstance(node, str):
            node = self.find(node)
        if node.is_dir:
            raise DiskError(f"« {node.name} » est un répertoire")
        blocks, size = self._data_blocks(node.block)
        out = bytearray()
        if self.ffs:
            for number in blocks:
                out += self.block(number)
                if len(out) >= size:
                    break
        else:
            for number in blocks:
                block = self.block(number)
                if _u32(block, 0) != T_DATA:
                    continue
                chunk = block[24:24 + 488]
                out += chunk
                if len(out) >= size:
                    break
                following = _u32(block, 16)
                if following and following not in blocks:
                    # Chaîne next_data : certains disques ne listent que la
                    # première entrée dans la table de l'en-tête.
                    seen = set(blocks)
                    while following and following not in seen:
                        seen.add(following)
                        extra = self.block(following)
                        if _u32(extra, 0) != T_DATA:
                            break
                        out += extra[24:24 + 488]
                        if len(out) >= size:
                            break
                        following = _u32(extra, 16)
        return bytes(out[:size])

    # -- sérialisation ------------------------------------------------------

    def files(self) -> list[DiskNode]:
        out: list[DiskNode] = []
        if self.root is None:
            return out

        def walk(node: DiskNode) -> None:
            for child in node.children:
                if child.is_dir:
                    walk(child)
                else:
                    out.append(child)

        walk(self.root)
        return out

    def list(self, max_depth: int = 4) -> list[dict]:
        if self.root is None:
            return []
        return [child.as_dict(0, max_depth) for child in self.root.children]

    def summary(self, max_depth: int = 3) -> dict:
        files = self.files()
        return {
            "source": self.source,
            "kind": self.kind,
            "size": len(self.data),
            "volume": self.name,
            "filesystem": "FFS" if self.ffs else "OFS",
            "block_size": self.block_size,
            "block_count": self.block_count,
            "root_block": self.root_block,
            "boot": self.boot,
            "warnings": self.warnings,
            "file_count": len(files),
            "total_size": sum(f.size for f in files),
            "tree": self.list(max_depth),
        }


def _maybe_gunzip(data: bytes) -> bytes:
    if data[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(data)
        except (OSError, EOFError) as exc:
            raise DiskError(f"archive ADZ illisible : {exc}") from exc
    return data


def open_disk(path: str | None = None, data: bytes | None = None,
              member: str = "", kind: str = "") -> Volume:
    """Ouvre une image de disque Amiga (ADF, ADZ, HDF).

    ``path`` peut désigner une archive zip/7z ; ``member`` choisit alors le
    fichier à lire.  ``data`` permet d'ouvrir une image déjà en mémoire.
    """
    if data is None:
        if not path:
            raise DiskError("chemin ou données requis")
        from . import archives
        data = archives.read_rom(path, member)
        if not kind:
            name = (member or path).lower()
            for suffix, label in ((".adz", "adz"), (".adf", "adf"),
                                  (".hdf", "hdf"), (".ipf", "ipf"),
                                  (".dms", "dms")):
                if name.endswith(suffix):
                    kind = label
                    break
    data = _maybe_gunzip(data)
    kind = kind or "adf"

    if data[:4] == b"CAPS" or kind == "ipf":
        raise UnsupportedDiskError(
            "image IPF (CAPS/SPS) : ce format décrit un flux de cellules "
            "magnétiques, pas des secteurs. La bibliothèque SPS n'est pas "
            "libre ; convertir l'image en ADF (par exemple avec capsimage et "
            "un ipf2adf) puis rouvrir le fichier.")
    if data[:4] == b"DMS!" or kind == "dms":
        raise UnsupportedDiskError(
            "archive DMS : le conteneur est reconnu, mais son décodage n'est "
            "pas encore implémenté. Convertir en ADF (xdms) puis rouvrir.")
    if data[:4] == b"RDSK":
        raise UnsupportedDiskError(
            "disque Amiga partitionné (RDSK) : ouvrir directement la "
            "partition ou extraire une image HDF de partition.")

    return Volume(data, source=path or "<mémoire>", kind=kind)
