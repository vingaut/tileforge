"""Réglages persistants de TileForge.

Stockés en JSON dans un dossier propre à l'utilisateur :

* Linux   : ``~/.config/tileforge/settings.json``
* Windows : ``%APPDATA%/tileforge/settings.json``
* Android : ``<dossier de données de l'app>/settings.json``

Les réglages sont volontairement tolérants : un fichier absent ou corrompu
retombe sur les valeurs par défaut, sans jamais empêcher le démarrage.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULTS: dict = {
    "help_interactive": False,
    "help_delay_ms": 2000,
    "check_updates_startup": True,
    "update_url": "",
    "update_channel": "stable",
    "last_project": "",
    "recent_projects": [],
    "window_geometry": "",
    "mobile_panels_visible": False,
    "weights": {"silhouette": 1.0, "color": 0.55, "gradient": 0.25,
                "hole": 0.45, "palette": 0.20, "duplicate": 0.35},
    "show_welcome": True,
    "language": "auto",
}


def is_android() -> bool:
    """Vrai si l'application tourne sous Android."""
    return (sys.platform == "android"
            or "ANDROID_ARGUMENT" in os.environ
            or "ANDROID_PRIVATE" in os.environ)


def config_dir() -> Path:
    """Dossier de configuration, créé au besoin."""
    if is_android():
        base = os.environ.get("ANDROID_PRIVATE") or os.environ.get("ANDROID_APP_PATH")
        folder = Path(base) if base else Path.home() / ".tileforge"
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        folder = Path(base) / "tileforge"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        folder = Path(base) / "tileforge"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except Exception:
        folder = Path.home() / ".tileforge"
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def data_dir() -> Path:
    """Dossier de données (téléchargements de mises à jour, caches)."""
    if is_android():
        base = os.environ.get("ANDROID_PRIVATE") or os.environ.get("ANDROID_APP_PATH")
        folder = Path(base) / "data" if base else Path.home() / ".tileforge" / "data"
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        folder = Path(base) / "tileforge" / "data"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        folder = Path(base) / "tileforge"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except Exception:
        folder = Path.home() / ".tileforge"
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def default_dir(kind: str = "projects") -> str:
    """Dossier proposé par les dialogues d'ouverture et d'enregistrement.

    Sur Android, les chemins du bureau n'existent pas : on retombe sur le
    dossier de données de l'application.  Sur poste de travail, on privilégie
    l'arborescence du projet si elle existe.
    """
    if is_android():
        folder = data_dir() / kind
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)
    root = Path.home() / "Partage" / "codage" / "atari_st"
    if root.exists():
        folder = root / kind
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)
    folder = Path.home() / kind
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def settings_path() -> Path:
    return config_dir() / "settings.json"


class Settings:
    """Dictionnaire de réglages avec sauvegarde automatique."""

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else settings_path()
        self._data = dict(DEFAULTS)
        self.load()

    # -- accès --------------------------------------------------------------

    def get(self, key: str, default=None):
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value, save: bool = True) -> None:
        self._data[key] = value
        if save:
            self.save()

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)

    def update(self, values: dict, save: bool = True) -> None:
        self._data.update(values)
        if save:
            self.save()

    def as_dict(self) -> dict:
        return dict(self._data)

    # -- persistance --------------------------------------------------------

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data.update({k: v for k, v in data.items() if k in DEFAULTS})
                # les clés inconnues sont conservées : une version plus récente
                # peut en avoir ajouté
                self._data.update({k: v for k, v in data.items() if k not in DEFAULTS})
        except FileNotFoundError:
            pass
        except Exception:
            # fichier illisible : on repart des valeurs par défaut
            pass

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(self.path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
            return True
        except Exception:
            return False

    # -- historique de fichiers --------------------------------------------

    def add_recent(self, path: str, limit: int = 8) -> None:
        if not path:
            return
        recent = [p for p in self.get("recent_projects", []) if p != path]
        recent.insert(0, path)
        self._data["recent_projects"] = recent[:limit]
        self._data["last_project"] = path
        self.save()
