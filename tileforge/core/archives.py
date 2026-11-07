"""Lecture des ROMs stockées dans des archives zip ou 7z.

Les packs de ROMs sont presque toujours distribués en archives : un fichier
``.zip`` ou ``.7z`` contient la ROM, parfois une notice ou plusieurs disques.
TileForge doit pouvoir ouvrir l'archive directement, sans demander à
l'utilisateur de l'extraire à la main.

Le module reste sans dépendance obligatoire :

* **zip** : :mod:`zipfile` de la bibliothèque standard ;
* **7z** : :mod:`py7zr` s'il est installé, sinon la commande ``7z`` / ``7za``
  / ``7zr`` du système.

L'API principale est :func:`open_rom` : elle renvoie le contenu de la ROM et le
nom du membre choisi. :func:`list_archive` sert aux interfaces (humaines ou MCP)
qui veulent proposer la liste des fichiers.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

#: Extensions d'archives reconnues.
ARCHIVE_SUFFIXES: tuple[str, ...] = (".zip", ".7z")

#: Extensions qui ressemblent à une ROM. Sert à choisir automatiquement le bon
#: membre quand l'archive en contient plusieurs.
ROM_SUFFIXES: tuple[str, ...] = (
    ".nes", ".fds", ".unf", ".unif", ".smc", ".sfc", ".bin", ".md", ".gen",
    ".smd", ".32x", ".sms", ".gg", ".sg", ".gb", ".gbc", ".gba", ".pce",
    ".a26", ".a78", ".col", ".int", ".dsk", ".d64", ".t64", ".tap", ".tzx",
    ".z80", ".sna", ".st", ".stx", ".msa", ".adf", ".adz", ".ipf", ".rom",
    ".cue", ".iso", ".chd", ".lnx", ".vec", ".crt", ".prg", ".xex", ".atr",
    ".cas", ".cdt", ".m3u", ".nsp", ".gcm", ".dol", ".elf", ".cof", ".j64",
    ".jag", ".abs", ".cpr", ".mx1", ".mx2", ".ri", ".sc", ".sgx",
)

#: Fichiers manifestement annexes : notices, vignettes, métadonnées.
_JUNK_SUFFIXES: tuple[str, ...] = (
    ".txt", ".nfo", ".md", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".xml", ".json", ".html", ".htm", ".pdf", ".url", ".ini", ".cfg",
)


class ArchiveError(Exception):
    """Archive illisible, membre absent ou outil 7z indisponible."""


@dataclass(frozen=True)
class ArchiveEntry:
    """Un fichier contenu dans une archive."""

    name: str
    size: int
    is_rom: bool = False

    def as_dict(self) -> dict:
        return {"name": self.name, "size": self.size, "is_rom": self.is_rom}


@dataclass(frozen=True)
class RomSource:
    """Contenu d'une ROM, éventuellement extrait d'une archive."""

    path: str
    member: str
    data: bytes
    archive: bool = False

    @property
    def display_name(self) -> str:
        return f"{Path(self.path).name}/{self.member}" if self.member else Path(self.path).name

    @property
    def suffix(self) -> str:
        return Path(self.member or self.path).suffix.lower()

    def as_dict(self) -> dict:
        return {"path": self.path, "member": self.member,
                "display_name": self.display_name, "size": len(self.data),
                "archive": self.archive}


# ---------------------------------------------------------------------------
# Détection
# ---------------------------------------------------------------------------


def is_archive(path: str | Path) -> bool:
    """Vrai si le fichier est une archive zip ou 7z (extension ou signature)."""
    target = Path(path)
    if target.suffix.lower() in ARCHIVE_SUFFIXES:
        return True
    try:
        with open(target, "rb") as handle:
            magic = handle.read(8)
    except OSError:
        return False
    return magic.startswith(b"PK\x03\x04") or magic == b"7z\xbc\xaf\x27\x1c"


def is_rom_name(name: str, size: int = 0) -> bool:
    """Vrai si le nom ressemble à une ROM plutôt qu'à une notice.

    ``.md`` est ambigu : Markdown pour une notice, Mega Drive pour une ROM.
    On tranche sur la taille quand elle est connue.
    """
    suffix = Path(name).suffix.lower()
    if suffix == ".md":
        return size == 0 or size >= 64 * 1024
    if suffix in _JUNK_SUFFIXES:
        return False
    return suffix in ROM_SUFFIXES or suffix not in _JUNK_SUFFIXES


def _seven_zip() -> str | None:
    for name in ("7z", "7za", "7zr"):
        path = shutil.which(name)
        if path:
            return path
    return None


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_archive(path: str | Path) -> list[ArchiveEntry]:
    """Liste les fichiers d'une archive (vide si ce n'est pas une archive)."""
    target = Path(path)
    if not target.exists():
        raise ArchiveError(f"archive introuvable : {target}")
    suffix = target.suffix.lower()
    if suffix == ".zip":
        return _list_zip(target)
    if suffix == ".7z":
        return _list_7z(target)
    return []


def _list_zip(target: Path) -> list[ArchiveEntry]:
    try:
        with zipfile.ZipFile(target) as archive:
            entries = [
                ArchiveEntry(info.filename, info.file_size,
                             is_rom=is_rom_name(info.filename, info.file_size))
                for info in archive.infolist() if not info.is_dir()
            ]
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveError(f"zip illisible : {exc}") from exc
    return entries


def _list_7z(target: Path) -> list[ArchiveEntry]:
    try:
        import py7zr  # type: ignore
    except Exception:
        py7zr = None
    if py7zr is not None:
        try:
            with py7zr.SevenZipFile(target) as archive:
                return [ArchiveEntry(item.filename, int(item.uncompressed or 0),
                                     is_rom=is_rom_name(item.filename,
                                                        int(item.uncompressed or 0)))
                        for item in archive.list() if not item.is_directory]
        except Exception as exc:
            raise ArchiveError(f"7z illisible : {exc}") from exc
    tool = _seven_zip()
    if tool is None:
        raise ArchiveError(
            "lecture 7z impossible : installez py7zr ou la commande 7z")
    result = subprocess.run([tool, "l", "-slt", "--", str(target)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise ArchiveError(f"7z illisible : {result.stderr.strip() or result.stdout.strip()}")
    entries: list[ArchiveEntry] = []
    name = ""
    size = 0
    folder = False
    started = False

    def flush() -> None:
        nonlocal name, size, folder
        if name and not folder:
            entries.append(ArchiveEntry(name, size, is_rom=is_rom_name(name, size)))
        name, size, folder = "", 0, False

    for line in result.stdout.splitlines():
        if line.startswith("----------"):
            flush()
            started = True
            continue
        if not started:
            continue
        if not line.strip():
            flush()
            continue
        if line.startswith("Path = "):
            flush()
            name = line[7:]
        elif line.startswith("Size = "):
            try:
                size = int(line[7:])
            except ValueError:
                size = 0
        elif line.startswith("Folder = "):
            folder = line[9:].strip() == "+"
    flush()
    return entries


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------


def read_member(path: str | Path, member: str) -> bytes:
    """Lit un membre précis d'une archive."""
    target = Path(path)
    suffix = target.suffix.lower()
    if suffix == ".zip":
        try:
            with zipfile.ZipFile(target) as archive:
                return archive.read(member)
        except KeyError as exc:
            raise ArchiveError(f"membre absent de l'archive : {member}") from exc
        except (zipfile.BadZipFile, OSError) as exc:
            raise ArchiveError(f"zip illisible : {exc}") from exc
    if suffix == ".7z":
        return _read_7z_member(target, member)
    raise ArchiveError(f"format d'archive non pris en charge : {target.suffix}")


def _read_7z_member(target: Path, member: str) -> bytes:
    try:
        import py7zr  # type: ignore
    except Exception:
        py7zr = None
    if py7zr is not None:
        try:
            with py7zr.SevenZipFile(target) as archive:
                data = archive.read(targets=[member])
                if member not in data:
                    raise ArchiveError(f"membre absent de l'archive : {member}")
                return data[member].read()
        except ArchiveError:
            raise
        except Exception as exc:
            raise ArchiveError(f"7z illisible : {exc}") from exc
    tool = _seven_zip()
    if tool is None:
        raise ArchiveError(
            "lecture 7z impossible : installez py7zr ou la commande 7z")
    result = subprocess.run([tool, "x", "-so", "--", str(target), member],
                            capture_output=True)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise ArchiveError(f"7z illisible : {message}")
    return result.stdout


def choose_member(entries: list[ArchiveEntry]) -> str:
    """Choisit le membre qui ressemble le plus à la ROM principale.

    Priorité aux fichiers dont l'extension est connue, puis au plus gros
    fichier non-annexe. Une archive à plusieurs disques doit être ouverte
    explicitement avec ``member``.
    """
    candidates = [entry for entry in entries if entry.is_rom]
    if not candidates:
        candidates = [entry for entry in entries
                      if Path(entry.name).suffix.lower() not in _JUNK_SUFFIXES]
    if not candidates:
        # Aucun nom reconnu : on prend le plus gros fichier, quitte à laisser
        # l'utilisateur choisir un autre membre.
        candidates = sorted(entries, key=lambda entry: -entry.size)
    if not candidates:
        raise ArchiveError("l'archive ne contient aucun fichier lisible")
    known = [entry for entry in candidates
             if Path(entry.name).suffix.lower() in ROM_SUFFIXES]
    pool = known or candidates
    # Le premier fichier dans l'ordre alphabétique est généralement le disque 1.
    pool = sorted(pool, key=lambda entry: (entry.name.lower(), -entry.size))
    return pool[0].name


def open_rom(path: str | Path, member: str = "") -> RomSource:
    """Ouvre une ROM, directement ou dans une archive.

    Sans ``member``, une archive à un seul fichier est ouverte
    automatiquement ; sinon le premier fichier qui ressemble à une ROM est
    choisi. Le nom effectivement retenu est renvoyé dans :attr:`RomSource.member`.
    """
    target = Path(path).expanduser()
    if not target.exists():
        raise ArchiveError(f"fichier introuvable : {target}")
    if not is_archive(target):
        return RomSource(str(target), "", target.read_bytes(), archive=False)
    entries = list_archive(target)
    if not entries:
        raise ArchiveError(f"archive vide : {target}")
    chosen = member or choose_member(entries)
    names = {entry.name for entry in entries}
    if chosen not in names:
        raise ArchiveError(
            f"membre absent : {chosen} (disponibles : {', '.join(sorted(names)[:8])})")
    return RomSource(str(target), chosen, read_member(target, chosen), archive=True)


def read_rom(path: str | Path, member: str = "") -> bytes:
    """Raccourci : contenu de la ROM, archive ou fichier nu."""
    return open_rom(path, member).data


# ---------------------------------------------------------------------------
# Aide pour les émulateurs qui exigent un chemin
# ---------------------------------------------------------------------------


def extract_to_temp(source: RomSource, directory: str | Path | None = None) -> str:
    """Écrit la ROM dans un fichier temporaire et renvoie son chemin.

    Certains cœurs libretro exigent un chemin réel (``need_fullpath``) : on
    extrait alors le membre de l'archive. L'appelant doit supprimer le fichier.
    """
    import tempfile

    suffix = source.suffix or ".bin"
    folder = Path(directory) if directory else None
    with tempfile.NamedTemporaryFile(
            prefix="tileforge-rom-", suffix=suffix,
            dir=str(folder) if folder else None, delete=False) as handle:
        handle.write(source.data)
        return handle.name


def archive_summary(path: str | Path, member: str = "") -> dict:
    """Résumé sérialisable d'une archive et de son membre choisi."""
    target = Path(path).expanduser()
    if not is_archive(target):
        return {"archive": False, "path": str(target)}
    entries = list_archive(target)
    chosen = member or (choose_member(entries) if entries else "")
    return {
        "archive": True,
        "path": str(target),
        "member": chosen,
        "entries": [entry.as_dict() for entry in entries],
    }
