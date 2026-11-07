"""Gestionnaire de mises à jour de TileForge.

Fonctionnement
--------------
1. On lit un **manifeste JSON** publié quelque part (serveur web, dossier
   partagé, clé USB).  Il décrit la dernière version de chaque canal.
2. On compare avec la version installée.
3. On télécharge l'archive, on vérifie son empreinte **SHA-256**, on l'extrait
   dans un dossier temporaire et on vérifie que la version annoncée est bien
   celle du paquet.
4. On sauvegarde le paquet ``tileforge/`` courant, puis on le remplace.
   En cas de problème, :meth:`UpdateManager.rollback` restaure la sauvegarde.

Seul le paquet ``tileforge/`` est remplacé : ni l'environnement virtuel, ni les
projets, ni les images exportées ne sont touchés.

Format du manifeste
-------------------
.. code-block:: json

    {
      "format": "tileforge/update/1",
      "app": "tileforge",
      "channels": {
        "stable": {
          "version": "1.2.0",
          "date": "2026-12-01",
          "url": "https://exemple.org/tileforge-1.2.0.zip",
          "sha256": "…",
          "size": 123456,
          "notes": "Corrections et nouvelles machines.",
          "min_version": "1.0.0"
        }
      }
    }
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..version import __version__

MANIFEST_FORMAT = "tileforge/update/1"
USER_AGENT = f"TileForge/{__version__}"


class UpdateError(Exception):
    """Erreur de mise à jour (réseau, manifeste, archive, droits…)."""


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


def parse_version(text: str) -> tuple[int, ...]:
    """« v1.2.3-beta » → (1, 2, 3). Tolérant sur les suffixes."""
    if not text:
        return (0,)
    text = str(text).strip().lower()
    if text.startswith("v"):
        text = text[1:]
    for sep in ("-", "+", " "):
        text = text.split(sep)[0]
    parts = []
    for chunk in text.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def version_gt(a: str, b: str) -> bool:
    """Vrai si la version ``a`` est plus récente que ``b``."""
    ta, tb = parse_version(a), parse_version(b)
    length = max(len(ta), len(tb))
    ta = ta + (0,) * (length - len(ta))
    tb = tb + (0,) * (length - len(tb))
    return ta > tb


# ---------------------------------------------------------------------------
# Manifeste et téléchargement
# ---------------------------------------------------------------------------


@dataclass
class ReleaseInfo:
    version: str
    url: str
    sha256: str = ""
    size: int = 0
    date: str = ""
    notes: str = ""
    channel: str = "stable"
    min_version: str = ""
    extra: dict = field(default_factory=dict)

    def is_newer(self, current: str = __version__) -> bool:
        return version_gt(self.version, current)

    def as_dict(self) -> dict:
        return {"version": self.version, "url": self.url, "sha256": self.sha256,
                "size": self.size, "date": self.date, "notes": self.notes,
                "channel": self.channel, "min_version": self.min_version}


def _is_url(location: str) -> bool:
    return location.lower().startswith(("http://", "https://", "ftp://"))


def fetch_manifest(location: str, timeout: float = 12.0) -> dict:
    """Lit le manifeste depuis une URL ou un chemin local."""
    location = (location or "").strip()
    if not location:
        raise UpdateError("aucune adresse de manifeste n'est configurée")
    try:
        if _is_url(location):
            request = urllib.request.Request(location, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        else:
            path = Path(os.path.expanduser(location))
            if not path.exists():
                raise UpdateError(f"manifeste introuvable : {path}")
            raw = path.read_bytes()
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError(f"impossible de lire le manifeste : {exc}") from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise UpdateError(f"manifeste illisible (JSON) : {exc}") from exc
    if not isinstance(data, dict):
        raise UpdateError("manifeste invalide : objet JSON attendu")
    fmt = data.get("format", MANIFEST_FORMAT)
    if not str(fmt).startswith("tileforge/update"):
        raise UpdateError(f"format de manifeste inconnu : {fmt}")
    return data


def release_from_manifest(data: dict, channel: str = "stable") -> ReleaseInfo | None:
    """Extrait l'entrée d'un canal du manifeste."""
    channels = data.get("channels") or {}
    entry = channels.get(channel)
    if entry is None:
        entry = data.get("latest")
        if isinstance(entry, dict) and "version" not in entry:
            entry = entry.get(channel)
    if not isinstance(entry, dict) or "version" not in entry:
        return None
    return ReleaseInfo(
        version=str(entry.get("version", "")),
        url=str(entry.get("url", "")),
        sha256=str(entry.get("sha256", "")).lower(),
        size=int(entry.get("size", 0) or 0),
        date=str(entry.get("date", "")),
        notes=str(entry.get("notes", "")),
        channel=channel,
        min_version=str(entry.get("min_version", "")),
        extra={k: v for k, v in entry.items()
               if k not in ("version", "url", "sha256", "size", "date", "notes")},
    )


def _resolve_relative(base: str, url: str) -> str:
    """Résout une URL relative par rapport au manifeste."""
    if not url or _is_url(url) or os.path.isabs(url):
        return url
    if _is_url(base):
        return urllib.parse.urljoin(base, url)
    return str(Path(base).parent / url)


def sha256_of(path: str | os.PathLike, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def download(url: str, destination: str | os.PathLike,
             progress=None, timeout: float = 30.0) -> str:
    """Télécharge (ou copie) un fichier, avec progression 0..1."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _is_url(url):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                with open(destination, "wb") as out:
                    while True:
                        block = response.read(1 << 16)
                        if not block:
                            break
                        out.write(block)
                        done += len(block)
                        if progress and total:
                            progress(min(1.0, done / total))
        except Exception as exc:
            raise UpdateError(f"téléchargement impossible : {exc}") from exc
    else:
        source = Path(os.path.expanduser(url))
        if not source.exists():
            raise UpdateError(f"archive introuvable : {source}")
        total = source.stat().st_size
        done = 0
        with open(source, "rb") as src, open(destination, "wb") as out:
            while True:
                block = src.read(1 << 16)
                if not block:
                    break
                out.write(block)
                done += len(block)
                if progress and total:
                    progress(min(1.0, done / total))
    if progress:
        progress(1.0)
    return str(destination)


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


def install_root() -> Path:
    """Dossier contenant le paquet ``tileforge`` (racine de l'application)."""
    return Path(__file__).resolve().parent.parent.parent


def package_dir() -> Path:
    """Le paquet lui-même."""
    return Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def read_package_version(package: Path) -> str:
    """Lit la version d'un paquet extrait (sans l'importer)."""
    version_file = package / "version.py"
    if not version_file.exists():
        return ""
    try:
        text = version_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("__version__"):
                return line.split("=", 1)[1].strip().strip("'\"")
    except Exception:
        pass
    return ""


def _find_package_in(folder: Path) -> Path | None:
    """Trouve le dossier ``tileforge`` dans une archive extraite."""
    direct = folder / "tileforge"
    if (direct / "version.py").exists():
        return direct
    for child in folder.iterdir():
        if child.is_dir():
            nested = child / "tileforge"
            if (nested / "version.py").exists():
                return nested
    return None


def extract_archive(archive: str | os.PathLike, destination: str | os.PathLike) -> Path:
    """Extrait une archive zip et renvoie le dossier de travail."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                # protection contre les chemins absolus et les « .. »
                target = (destination / member.filename).resolve()
                if not str(target).startswith(str(destination.resolve())):
                    raise UpdateError(f"chemin suspect dans l'archive : {member.filename}")
            zf.extractall(destination)
    except zipfile.BadZipFile as exc:
        raise UpdateError(f"archive illisible : {exc}") from exc
    return destination


def copy_package(source: Path, target: Path, backup: Path | None = None,
                 progress=None) -> None:
    """Remplace ``target`` par ``source`` (sauvegarde préalable optionnelle)."""
    if backup is not None and target.exists():
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        shutil.copytree(target, backup,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    files = [p for p in source.rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    total = max(1, len(files))
    for index, item in enumerate(files, 1):
        relative = item.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        if progress:
            progress(index / total)
    # retire les fichiers supprimés dans la nouvelle version
    keep = {p.relative_to(source) for p in files}
    for old in target.rglob("*.py"):
        if "__pycache__" in old.parts:
            continue
        if old.relative_to(target) not in keep:
            with contextlib.suppress(OSError):
                old.unlink()


# ---------------------------------------------------------------------------
# Gestionnaire
# ---------------------------------------------------------------------------


class UpdateManager:
    """Vérifie, télécharge, installe et annule les mises à jour."""

    def __init__(self, manifest_url: str = "", channel: str = "stable",
                 data_folder: str | os.PathLike | None = None):
        self.manifest_url = manifest_url
        self.channel = channel
        self.data_folder = Path(data_folder) if data_folder else (
            Path(tempfile.gettempdir()) / "tileforge-updates")
        self.data_folder.mkdir(parents=True, exist_ok=True)
        self.last_manifest: dict | None = None

    # -- état ---------------------------------------------------------------

    @property
    def current_version(self) -> str:
        return __version__

    @property
    def backup_dir(self) -> Path:
        return self.data_folder / "backup"

    def has_backup(self) -> bool:
        return (self.backup_dir / "tileforge" / "version.py").exists()

    def backup_version(self) -> str:
        package = self.backup_dir / "tileforge"
        return read_package_version(package) if package.exists() else ""

    # -- vérification -------------------------------------------------------

    def check(self) -> ReleaseInfo | None:
        """Renvoie la version disponible si elle est plus récente, sinon None."""
        data = fetch_manifest(self.manifest_url)
        self.last_manifest = data
        release = release_from_manifest(data, self.channel)
        if release is None:
            raise UpdateError(f"aucune version publiée sur le canal « {self.channel} »")
        release.url = _resolve_relative(self.manifest_url, release.url)
        return release if release.is_newer(self.current_version) else None

    # -- installation -------------------------------------------------------

    def download(self, release: ReleaseInfo, progress=None) -> Path:
        name = f"tileforge-{release.version}.zip"
        target = self.data_folder / name
        if (target.exists() and release.sha256
                and sha256_of(target) == release.sha256):
            if progress:
                progress(1.0)
            return target
        download(release.url, target, progress)
        if release.sha256:
            actual = sha256_of(target)
            if actual != release.sha256:
                with contextlib.suppress(OSError):
                    target.unlink()
                raise UpdateError(
                    "l'empreinte SHA-256 ne correspond pas : archive corrompue ou "
                    "manifeste obsolète")
        return target

    def install(self, archive: str | os.PathLike, expected_version: str = "",
                progress=None) -> str:
        """Extrait et installe une archive déjà téléchargée."""
        if is_frozen():
            raise UpdateError(
                "l'application est compilée : remplacez le dossier de l'application "
                "par le paquet téléchargé (l'archive reste disponible).")
        staging = Path(tempfile.mkdtemp(prefix="tileforge-stage-"))
        try:
            extract_archive(archive, staging)
            package = _find_package_in(staging)
            if package is None:
                raise UpdateError("l'archive ne contient pas le paquet tileforge/")
            found = read_package_version(package)
            if expected_version and found and parse_version(found) != parse_version(expected_version):
                raise UpdateError(
                    f"l'archive annonce la version {expected_version} mais contient {found}")
            copy_package(package, package_dir(),
                         backup=self.backup_dir / "tileforge", progress=progress)
            return found or expected_version
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def rollback(self, progress=None) -> str:
        """Restaure la version sauvegardée avant la dernière mise à jour."""
        backup = self.backup_dir / "tileforge"
        if not (backup / "version.py").exists():
            raise UpdateError("aucune sauvegarde disponible")
        version = read_package_version(backup)
        copy_package(backup, package_dir(), progress=progress)
        return version

    def cleanup_downloads(self, keep: int = 2) -> None:
        archives = sorted(self.data_folder.glob("tileforge-*.zip"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        for old in archives[keep:]:
            with contextlib.suppress(OSError):
                old.unlink()
