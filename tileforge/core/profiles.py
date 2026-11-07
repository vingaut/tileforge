"""Profils de jeu : la recette de chargement d'une banque, réutilisable.

Un profil décrit **où** et **comment** lire les graphismes d'un jeu : offset,
format de tuile, compression, palette, grille.  C'est ce qui rend le travail
reproductible : une fois qu'on a trouvé les bons réglages, on les enregistre et
on les rejoue en un clic — ou on les partage avec quelqu'un d'autre.

Les profils sont de simples fichiers JSON, lisibles et modifiables à la main :

.. code-block:: json

    {
      "format": "tileforge/profile/1",
      "key": "mon_jeu",
      "name": "Mon jeu (1993)",
      "machine": "megadrive",
      "rom_name": "Mon Jeu.md",
      "offset": 123456,
      "tile_format": "megadrive",
      "compression": "nemesis",
      "count": 0,
      "per_row": 16,
      "palette": {"kind": "megadrive", "offset": 512, "count": 16},
      "grid": [2, 4],
      "notes": "Sprites des personnages."
    }
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .settings import config_dir

PROFILE_FORMAT = "tileforge/profile/1"


@dataclass
class GameProfile:
    key: str
    name: str
    offset: int = 0
    tile_format: str = "snes_4bpp"
    compression: str = ""
    count: int = 0
    per_row: int = 16
    machine: str = ""
    rom_name: str = ""
    palette_kind: str = ""
    palette_offset: int = -1
    palette_count: int = 16
    grid: tuple[int, int] = (2, 4)
    notes: str = ""
    builtin: bool = False
    path: str = ""

    @property
    def palette_enabled(self) -> bool:
        return self.palette_offset >= 0 and bool(self.palette_kind)

    def as_dict(self) -> dict:
        data = {
            "format": PROFILE_FORMAT,
            "key": self.key,
            "name": self.name,
            "machine": self.machine,
            "rom_name": self.rom_name,
            "offset": self.offset,
            "tile_format": self.tile_format,
            "compression": self.compression,
            "count": self.count,
            "per_row": self.per_row,
            "grid": list(self.grid),
            "notes": self.notes,
        }
        if self.palette_enabled:
            data["palette"] = {"kind": self.palette_kind,
                               "offset": self.palette_offset,
                               "count": self.palette_count}
        return data

    @classmethod
    def from_dict(cls, data: dict, builtin: bool = False, path: str = "") -> GameProfile:
        palette = data.get("palette") or {}
        grid = data.get("grid") or (2, 4)
        return cls(
            key=str(data.get("key", "")),
            name=str(data.get("name", data.get("key", "profil"))),
            offset=int(data.get("offset", 0) or 0),
            tile_format=str(data.get("tile_format", "snes_4bpp")),
            compression=str(data.get("compression", "") or ""),
            count=int(data.get("count", 0) or 0),
            per_row=int(data.get("per_row", 16) or 16),
            machine=str(data.get("machine", "")),
            rom_name=str(data.get("rom_name", "")),
            palette_kind=str(palette.get("kind", "")),
            palette_offset=int(palette.get("offset", -1)),
            palette_count=int(palette.get("count", 16)),
            grid=(int(grid[0]), int(grid[1])) if len(grid) >= 2 else (2, 4),
            notes=str(data.get("notes", "")),
            builtin=builtin,
            path=path,
        )


# ---------------------------------------------------------------------------
# Profils fournis
# ---------------------------------------------------------------------------

BUILTIN_PROFILES: list[GameProfile] = [
    GameProfile(
        key="barbarian_st_bank1", name="Barbarian — banque 1 (Atari ST)",
        offset=0x33A52, tile_format="barbarian_st", count=252, per_row=16,
        machine="atari-st", rom_name="BARB.DAT", grid=(2, 4),
        notes="252 tuiles de 24×21 px, 2 plans, palette du jeu.", builtin=True),
    GameProfile(
        key="barbarian_st_bank2", name="Barbarian — banque 2 (Atari ST)",
        offset=0x3B65A, tile_format="barbarian_st", count=252, per_row=16,
        machine="atari-st", rom_name="BARB.DAT", grid=(2, 4),
        notes="Deuxième banque de sprites.", builtin=True),
]


# ---------------------------------------------------------------------------
# Chargement / enregistrement
# ---------------------------------------------------------------------------


def profiles_dir() -> Path:
    folder = config_dir() / "profiles"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load_profile(path: str | os.PathLike) -> GameProfile:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not str(data.get("format", "")).startswith("tileforge/profile"):
        raise ValueError("ce fichier n'est pas un profil TileForge")
    return GameProfile.from_dict(data, builtin=False, path=str(path))


def save_profile(profile: GameProfile, path: str | os.PathLike) -> str:
    path = Path(path)
    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile.as_dict(), f, ensure_ascii=False, indent=1)
    profile.path = str(path)
    return str(path)


def user_profiles() -> list[GameProfile]:
    out = []
    for path in sorted(profiles_dir().glob("*.json")):
        try:
            out.append(load_profile(path))
        except Exception:
            continue
    return out


def all_profiles() -> list[GameProfile]:
    return list(BUILTIN_PROFILES) + user_profiles()


def find_for_rom(rom_path: str) -> list[GameProfile]:
    """Profils dont le nom de fichier correspond à celui de la ROM."""
    name = os.path.basename(rom_path).lower()
    stem = os.path.splitext(name)[0]
    matches = []
    for profile in all_profiles():
        hint = (profile.rom_name or "").lower()
        if not hint:
            continue
        if hint == name or os.path.splitext(hint)[0] == stem:
            matches.append(profile)
    return matches


def guess_rom_for(profile: GameProfile, folders: list[str],
                  max_depth: int = 2) -> str:
    """Cherche la ROM du profil dans quelques dossiers et leurs sous-dossiers.

    La recherche s'arrête à ``max_depth`` niveaux pour rester instantanée même
    si l'utilisateur pointe un dossier volumineux.
    """
    if not profile.rom_name:
        return ""
    wanted = profile.rom_name.lower()
    seen = set()
    for folder in folders:
        root = Path(folder)
        if not root.exists():
            continue
        direct = root / profile.rom_name
        if direct.exists():
            return str(direct)
        base_depth = len(root.parts)
        try:
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if len(path.parts) - base_depth > max_depth:
                    continue
                if path.name.lower() == wanted:
                    resolved = str(path)
                    if resolved not in seen:
                        return resolved
        except (PermissionError, OSError):
            continue
    return ""
