"""Lire la mémoire décodée par un émulateur (cœurs libretro).

Certains jeux compressent leurs graphismes avec un algorithme maison, ou les
fabriquent en mémoire au chargement d'un niveau. Quand l'analyse statique de la
ROM ne suffit plus, le chemin le plus court est de **laisser le jeu faire le
travail** : on lance la ROM dans un émulateur, on avance de quelques centaines
de trames, puis on lit la RAM système et la VRAM. Les données y sont déjà
décompressées, dans le format natif de la machine.

Ce module implémente l'hôte libretro minimal nécessaire — chargement d'un cœur,
exécution sans fenêtre, lecture des blocs mémoire — en n'utilisant que la
bibliothèque standard (``ctypes``). Aucun cœur n'est fourni : l'utilisateur
installe celui de son choix (RetroArch, paquet système, compilation), et
TileForge le découvre dans les dossiers habituels ou reçoit son chemin.

Deux principes :

* **aucune dépendance obligatoire** : sans cœur libretro, le reste de
  TileForge fonctionne comme avant ;
* **la mémoire est la vérité** : un instantané est enregistré avec ses métadonnées
  (cœur, ROM, nombre de trames, régions, adresses de base indicatives), pour
  être rouvert, balayé et comparé plus tard.

Utilisation en script ::

    from tileforge.core.emulation import discover_cores, run_rom
    cores = discover_cores()
    result = run_rom(cores[0].path, "jeu.gba", frames=600,
                     output_dir="memoire", screenshot=True)

Ligne de commande : ``python tools/emulator_memory.py --help``.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes libretro
# ---------------------------------------------------------------------------

RETRO_API_VERSION = 1

RETRO_MEMORY_SAVE_RAM = 0
RETRO_MEMORY_RTC = 1
RETRO_MEMORY_SYSTEM_RAM = 2
RETRO_MEMORY_VIDEO_RAM = 3

RETRO_DEVICE_JOYPAD = 1
RETRO_DEVICE_ANALOG = 5
RETRO_DEVICE_ID_JOYPAD_MASK = 256

RETRO_PIXEL_FORMAT_0RGB1555 = 0
RETRO_PIXEL_FORMAT_XRGB8888 = 1
RETRO_PIXEL_FORMAT_RGB565 = 2

#: Commandes d'environnement auxquelles l'hôte répond.
RETRO_ENVIRONMENT_SET_ROTATION = 1
RETRO_ENVIRONMENT_GET_OVERSCAN = 2
RETRO_ENVIRONMENT_GET_CAN_DUPE = 3
RETRO_ENVIRONMENT_SET_MESSAGE = 6
RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL = 8
RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY = 9
RETRO_ENVIRONMENT_SET_PIXEL_FORMAT = 10
RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS = 11
RETRO_ENVIRONMENT_SET_HW_RENDER = 14
RETRO_ENVIRONMENT_GET_VARIABLE = 15
RETRO_ENVIRONMENT_SET_VARIABLES = 16
RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE = 17
RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME = 18
RETRO_ENVIRONMENT_GET_LIBRETRO_PATH = 19
RETRO_ENVIRONMENT_GET_RUMBLE_INTERFACE = 23
RETRO_ENVIRONMENT_GET_SENSOR_INTERFACE = 25
RETRO_ENVIRONMENT_GET_CAMERA_INTERFACE = 26
RETRO_ENVIRONMENT_GET_LOG_INTERFACE = 27
RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY = 31
RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO = 32
RETRO_ENVIRONMENT_SET_SUBSYSTEM_INFO = 34
RETRO_ENVIRONMENT_SET_CONTROLLER_INFO = 35
RETRO_ENVIRONMENT_SET_MEMORY_MAPS = 36
RETRO_ENVIRONMENT_SET_GEOMETRY = 37
RETRO_ENVIRONMENT_GET_USERNAME = 38
RETRO_ENVIRONMENT_GET_LANGUAGE = 39
RETRO_ENVIRONMENT_GET_HW_RENDER_INTERFACE = 41
RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS = 42
RETRO_ENVIRONMENT_SET_SERIALIZATION_QUIRKS = 44
RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE = 47
RETRO_ENVIRONMENT_GET_FASTFORWARDING = 49
RETRO_ENVIRONMENT_GET_TARGET_REFRESH_RATE = 50
RETRO_ENVIRONMENT_GET_INPUT_BITMASKS = 51
RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION = 52
RETRO_ENVIRONMENT_SET_CORE_OPTIONS = 53
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_INTL = 54
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_DISPLAY = 55
RETRO_ENVIRONMENT_GET_PREFERRED_HW_RENDER = 56
RETRO_ENVIRONMENT_GET_DISK_CONTROL_INTERFACE_VERSION = 57
RETRO_ENVIRONMENT_GET_MESSAGE_INTERFACE_VERSION = 59
RETRO_ENVIRONMENT_SET_MESSAGE_EXT = 60
RETRO_ENVIRONMENT_GET_INPUT_MAX_USERS = 61
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2 = 67
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL = 68
RETRO_ENVIRONMENT_SET_VARIABLE = 70
RETRO_ENVIRONMENT_GET_JIT_CAPABLE = 74

#: Noms des boutons libretro, pour les scripts d'entrée.
BUTTONS: dict[str, int] = {
    "b": 0, "y": 1, "select": 2, "start": 3,
    "up": 4, "down": 5, "left": 6, "right": 7,
    "a": 8, "x": 9, "l": 10, "r": 11,
    "l2": 12, "r2": 13, "l3": 14, "r3": 15,
}

#: Régions mémoire lues après exécution.
MEMORY_REGIONS: tuple[tuple[int, str], ...] = (
    (RETRO_MEMORY_SYSTEM_RAM, "system_ram"),
    (RETRO_MEMORY_VIDEO_RAM, "video_ram"),
    (RETRO_MEMORY_SAVE_RAM, "save_ram"),
    (RETRO_MEMORY_RTC, "rtc"),
)

#: Adresses de base indicatives, pour interpréter les pointeurs du jeu.
#: Un cœur libretro ne les expose pas : ce sont les adresses des machines
#: d'origine, et elles ne sont exactes que si le cœur expose le bloc complet.
MEMORY_BASES: dict[str, dict[str, int]] = {
    "gba": {"system_ram": 0x02000000, "video_ram": 0x06000000,
            "save_ram": 0x0E000000},
    "gameboy": {"system_ram": 0xC000, "video_ram": 0x8000, "save_ram": 0xA000},
    "snes": {"system_ram": 0x7E0000, "video_ram": 0x0000, "save_ram": 0x700000},
    "nes": {"system_ram": 0x0000, "video_ram": 0x2000, "save_ram": 0x6000},
    "megadrive": {"system_ram": 0xFF0000, "video_ram": 0xC0000000,
                  "save_ram": 0x200000},
    "pcengine": {"system_ram": 0x1F0000, "video_ram": 0x0000},
    "atarist": {"system_ram": 0x000000, "video_ram": 0x000000},
}

#: Dossiers où chercher les cœurs.
CORE_SUFFIXES = (".so", ".dylib", ".dll")


class EmulationError(Exception):
    """Cœur introuvable, API incompatible ou chargement refusé."""


# ---------------------------------------------------------------------------
# Structures libretro
# ---------------------------------------------------------------------------


class RetroSystemInfo(ctypes.Structure):
    _fields_ = [
        ("library_name", ctypes.c_char_p),
        ("library_version", ctypes.c_char_p),
        ("valid_extensions", ctypes.c_char_p),
        ("need_fullpath", ctypes.c_bool),
        ("block_extract", ctypes.c_bool),
    ]


class RetroGameInfo(ctypes.Structure):
    _fields_ = [
        ("path", ctypes.c_char_p),
        ("data", ctypes.c_void_p),
        ("size", ctypes.c_size_t),
        ("meta", ctypes.c_char_p),
    ]


class RetroVariable(ctypes.Structure):
    _fields_ = [("key", ctypes.c_char_p), ("value", ctypes.c_char_p)]


_ENV_CB = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint, ctypes.c_void_p)
_VIDEO_CB = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint,
                             ctypes.c_uint, ctypes.c_size_t)
_AUDIO_CB = ctypes.CFUNCTYPE(None, ctypes.c_int16, ctypes.c_int16)
_AUDIO_BATCH_CB = ctypes.CFUNCTYPE(ctypes.c_size_t,
                                   ctypes.POINTER(ctypes.c_int16),
                                   ctypes.c_size_t)
_INPUT_POLL_CB = ctypes.CFUNCTYPE(None)
_INPUT_STATE_CB = ctypes.CFUNCTYPE(ctypes.c_int16, ctypes.c_uint,
                                   ctypes.c_uint, ctypes.c_uint, ctypes.c_uint)


# ---------------------------------------------------------------------------
# Description d'un cœur
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoreInfo:
    """Un cœur libretro et ce qu'il émule."""

    path: str
    name: str
    system: str = ""
    extensions: tuple[str, ...] = ()
    need_fullpath: bool = False

    def as_dict(self) -> dict:
        return {"path": self.path, "name": self.name, "system": self.system,
                "extensions": list(self.extensions),
                "need_fullpath": self.need_fullpath}


#: Motifs de noms de cœurs, du plus spécifique au plus général.
_SYSTEM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("mesen-s", "snes"), ("snes9x", "snes"), ("bsnes", "snes"),
    ("genesis_plus_gx", "megadrive"), ("picodrive", "megadrive"),
    ("blastem", "megadrive"), ("genesis", "megadrive"),
    ("mgba", "gba"), ("gambatte", "gameboy"), ("sameboy", "gameboy"),
    ("gearboy", "gameboy"), ("hatari", "atarist"),
    ("nestopia", "nes"), ("fceumm", "nes"), ("mesen", "nes"),
    ("beetle-pce", "pcengine"), ("mednafen-pce", "pcengine"),
    ("beetle-saturn", "saturn"), ("yabause", "saturn"),
    ("beetle-vb", "virtualboy"), ("beetle-lynx", "lynx"),
    ("handy", "lynx"), ("prosystem", "atari7800"),
    ("stella", "atari2600"), ("vecx", "vectrex"),
    ("vice", "c64"), ("fuse", "zxspectrum"),
    ("cap32", "cpc"), ("hatari", "atarist"),
    ("puae", "amiga"), ("fs-uae", "amiga"),
)


def guess_system(name: str) -> str:
    """Devine la machine d'un cœur à partir de son nom de fichier."""
    lowered = name.lower()
    for pattern, system in _SYSTEM_PATTERNS:
        if pattern in lowered:
            return system
    return ""


def _pretty_name(path: str) -> str:
    stem = Path(path).stem
    for suffix in ("_libretro", "-libretro"):
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
    return stem.replace("_", " ").replace("-", " ").strip() or Path(path).name


def default_core_paths() -> list[Path]:
    """Dossiers de recherche, dans l'ordre : variable, utilisateur, système."""
    paths: list[Path] = []
    env = os.environ.get("TILEFORGE_CORES", "")
    if env:
        paths.extend(Path(item).expanduser() for item in env.split(os.pathsep)
                     if item.strip())
    paths.extend([
        Path.home() / ".config" / "retroarch" / "cores",
        Path.home() / ".local" / "lib" / "libretro",
        Path("/usr/lib/libretro"),
        Path("/usr/local/lib/libretro"),
        Path.cwd() / "cores",
        Path.cwd() / "libretro",
    ])
    return paths


def discover_cores(extra_paths: list[str | Path] | None = None) -> list[CoreInfo]:
    """Liste les cœurs libretro présents sur la machine.

    La découverte ne charge pas les bibliothèques : elle se contente de lire
    les noms de fichiers, ce qui est rapide et sans risque. Utilisez
    :func:`probe_core` pour obtenir le nom et les extensions réels d'un cœur.
    """
    folders = default_core_paths()
    folders.extend(Path(item).expanduser() for item in (extra_paths or ()))
    seen: dict[str, CoreInfo] = {}
    for folder in folders:
        try:
            if not folder.is_dir():
                continue
            entries = sorted(folder.iterdir())
        except OSError:
            continue
        for path in entries:
            if path.suffix.lower() not in CORE_SUFFIXES or not path.is_file():
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen[key] = CoreInfo(path=str(path), name=_pretty_name(path.name),
                                 system=guess_system(path.name))
    return sorted(seen.values(), key=lambda core: (core.system, core.name.lower()))


def probe_core(path: str | Path) -> CoreInfo:
    """Charge un cœur et lit ses métadonnées (nom, extensions, chemin requis)."""
    core_path = str(Path(path).expanduser())
    try:
        library = ctypes.CDLL(core_path)
    except OSError as exc:
        raise EmulationError(f"cœur illisible : {exc}") from exc
    try:
        function = library.retro_get_system_info
    except AttributeError as exc:
        raise EmulationError("ce fichier n'expose pas retro_get_system_info") from exc
    function.argtypes = [ctypes.POINTER(RetroSystemInfo)]
    function.restype = None
    info = RetroSystemInfo()
    function(ctypes.byref(info))
    name = (info.library_name or b"").decode("utf-8", "replace")
    extensions = (info.valid_extensions or b"").decode("ascii", "replace")
    return CoreInfo(
        path=core_path,
        name=name or _pretty_name(core_path),
        system=guess_system(Path(core_path).name),
        extensions=tuple(part for part in extensions.split("|") if part),
        need_fullpath=bool(info.need_fullpath),
    )


# ---------------------------------------------------------------------------
# Instantané de mémoire
# ---------------------------------------------------------------------------


@dataclass
class MemoryRegion:
    """Un bloc de mémoire lu dans l'émulateur."""

    name: str
    data: bytes
    base: int = 0
    region_id: int = -1

    def as_dict(self) -> dict:
        return {"name": self.name, "base": self.base, "base_hex": f"0x{self.base:X}",
                "size": len(self.data), "region_id": self.region_id}


@dataclass
class MemorySnapshot:
    """Mémoire d'un jeu après quelques trames d'émulation."""

    core: str
    rom: str
    system: str
    frames: int
    regions: dict[str, MemoryRegion] = field(default_factory=dict)
    screenshot: bytes | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "format": "tileforge/memory/1",
            "core": self.core,
            "rom": self.rom,
            "system": self.system,
            "frames": self.frames,
            "regions": [region.as_dict() for region in self.regions.values()],
            "notes": list(self.notes),
        }

    def combined(self) -> tuple[bytes, list[dict]]:
        """Concatène les régions dans l'ordre système, vidéo, sauvegarde, RTC."""
        blob = bytearray()
        index: list[dict] = []
        for region in self.regions.values():
            index.append({"name": region.name, "offset": len(blob),
                          "size": len(region.data), "base": region.base})
            blob.extend(region.data)
        return bytes(blob), index

    def save(self, directory: str | Path, name: str = "") -> dict:
        """Écrit les régions, un fichier concaténé et un manifeste JSON."""
        folder = Path(directory).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        stem = _safe_stem(name or (Path(self.rom).stem + "-memoire"))
        manifest = self.as_dict()
        manifest["files"] = {}
        for region in self.regions.values():
            filename = f"{stem}.{region.name}.bin"
            (folder / filename).write_bytes(region.data)
            manifest["files"][region.name] = filename
        combined, index = self.combined()
        combined_name = f"{stem}.bin"
        (folder / combined_name).write_bytes(combined)
        manifest["combined"] = {"file": combined_name, "size": len(combined),
                                "regions": index}
        if self.screenshot:
            shot_name = f"{stem}.png"
            (folder / shot_name).write_bytes(self.screenshot)
            manifest["screenshot"] = shot_name
        manifest_path = folder / f"{stem}.memory.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
        screenshot_path = (str(folder / manifest["screenshot"])
                           if manifest.get("screenshot") else "")
        return {"manifest": str(manifest_path), "combined": str(folder / combined_name),
                "directory": str(folder), "regions": manifest["regions"],
                "screenshot": screenshot_path}

    @classmethod
    def load(cls, path: str | Path) -> MemorySnapshot:
        """Recharge un instantané écrit par :meth:`save` (ou un binaire brut)."""
        target = Path(path).expanduser()
        if target.is_dir():
            candidates = sorted(target.glob("*.memory.json"))
            if not candidates:
                raise EmulationError(f"aucun manifeste de mémoire dans {target}")
            target = candidates[0]
        if target.suffix.lower() != ".json":
            data = target.read_bytes()
            return cls(core="", rom=str(target), system="", frames=0,
                       regions={"memory": MemoryRegion("memory", data)})
        manifest = json.loads(target.read_text(encoding="utf-8"))
        regions: dict[str, MemoryRegion] = {}
        for item in manifest.get("regions", []):
            name = item["name"]
            filename = manifest.get("files", {}).get(name)
            if not filename:
                continue
            data = (target.parent / filename).read_bytes()
            regions[name] = MemoryRegion(name, data, base=int(item.get("base", 0)),
                                         region_id=int(item.get("region_id", -1)))
        screenshot = None
        if manifest.get("screenshot"):
            screenshot_path = target.parent / manifest["screenshot"]
            if screenshot_path.exists():
                screenshot = screenshot_path.read_bytes()
        return cls(core=manifest.get("core", ""), rom=manifest.get("rom", ""),
                   system=manifest.get("system", ""),
                   frames=int(manifest.get("frames", 0)), regions=regions,
                   screenshot=screenshot, notes=list(manifest.get("notes", [])))


def _safe_stem(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_." else "_"
                      for char in value)
    return cleaned.strip("._") or "memoire"


# ---------------------------------------------------------------------------
# Script d'entrée
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ButtonPress:
    """Un bouton maintenu entre deux trames (``end`` exclu, ``None`` = fin)."""

    button: int
    start: int = 0
    end: int | None = None


def parse_buttons(spec: str) -> list[ButtonPress]:
    """Analyse ``"start@120-140,a@200"``.

    Un nom seul est maintenu pendant toute l'exécution ; ``@N`` le presse à
    partir de la trame N ; ``@N-M`` le maintient de N inclus à M exclu.
    """
    presses: list[ButtonPress] = []
    for token in (spec or "").replace(";", ",").split(","):
        token = token.strip().lower()
        if not token:
            continue
        timing = ""
        if "@" in token:
            token, timing = token.split("@", 1)
        button = BUTTONS.get(token)
        if button is None:
            raise EmulationError(f"bouton inconnu : {token}")
        start, end = 0, None
        if timing:
            try:
                if "-" in timing:
                    first, second = timing.split("-", 1)
                    start = int(first) if first else 0
                    end = int(second) if second else None
                else:
                    start = int(timing)
            except ValueError as exc:
                raise EmulationError(
                    f"trame invalide dans le script d'entrée : {token}@{timing}"
                ) from exc
        presses.append(ButtonPress(button, start, end))
    return presses


def _mask_at(presses: list[ButtonPress], frame: int) -> int:
    mask = 0
    for press in presses:
        if frame >= press.start and (press.end is None or frame < press.end):
            mask |= 1 << press.button
    return mask


# ---------------------------------------------------------------------------
# Hôte libretro
# ---------------------------------------------------------------------------


class LibretroCore:
    """Un cœur libretro chargé, prêt à exécuter une ROM sans interface.

    Le cycle de vie est explicite ::

        with LibretroCore("mgba_libretro.so") as core:
            core.load_game("jeu.gba")
            core.run(600)
            snapshot = core.snapshot()

    Les rappels vidéo et audio sont silencieux ; seule la dernière image est
    conservée pour produire une capture PNG.
    """

    def __init__(self, core_path: str | Path):
        self.path = str(Path(core_path).expanduser())
        self.library = self._open_library(self.path)
        self.info = self._read_info()
        self.frame = 0
        self.pixel_format = RETRO_PIXEL_FORMAT_0RGB1555
        self.last_frame: tuple[bytes, int, int, int, int] | None = None
        self._system_dir = str(Path.cwd())
        self._save_dir = str(Path.cwd())
        self._system_dir_bytes = os.fsencode(self._system_dir)
        self._save_dir_bytes = os.fsencode(self._save_dir)
        self._loaded = False
        self.rom_path = ""
        self.rom_member = ""
        self._temp_rom = ""
        self._rom_buffer = None
        self._presses: list[ButtonPress] = []
        self._set_prototypes()
        self._callbacks = self._install_callbacks()
        self.library.retro_init()
        self._initialised = True

    # -- chargement de la bibliothèque -------------------------------------

    @staticmethod
    def _open_library(path: str):
        if not os.path.exists(path):
            raise EmulationError(f"cœur introuvable : {path}")
        try:
            library = ctypes.CDLL(path)
        except OSError as exc:
            raise EmulationError(f"chargement du cœur impossible : {exc}") from exc
        if not hasattr(library, "retro_api_version"):
            raise EmulationError("ce fichier n'est pas un cœur libretro")
        if library.retro_api_version() != RETRO_API_VERSION:
            raise EmulationError("version d'API libretro incompatible")
        return library

    def _set_prototypes(self) -> None:
        """Déclare les signatures : sans cela, ctypes tronque les pointeurs."""
        library = self.library
        library.retro_api_version.argtypes = []
        library.retro_api_version.restype = ctypes.c_uint
        library.retro_init.argtypes = []
        library.retro_init.restype = None
        library.retro_deinit.argtypes = []
        library.retro_deinit.restype = None
        library.retro_run.argtypes = []
        library.retro_run.restype = None
        library.retro_load_game.argtypes = [ctypes.POINTER(RetroGameInfo)]
        library.retro_load_game.restype = ctypes.c_bool
        library.retro_unload_game.argtypes = []
        library.retro_unload_game.restype = None
        library.retro_get_memory_data.argtypes = [ctypes.c_uint]
        library.retro_get_memory_data.restype = ctypes.c_void_p
        library.retro_get_memory_size.argtypes = [ctypes.c_uint]
        library.retro_get_memory_size.restype = ctypes.c_size_t
        library.retro_set_controller_port_device.argtypes = [ctypes.c_uint,
                                                             ctypes.c_uint]
        library.retro_set_controller_port_device.restype = None
        library.retro_get_system_info.argtypes = [ctypes.POINTER(RetroSystemInfo)]
        library.retro_get_system_info.restype = None

    def _read_info(self) -> CoreInfo:
        if not hasattr(self.library, "retro_get_system_info"):
            raise EmulationError("ce cœur n'expose pas retro_get_system_info")
        function = self.library.retro_get_system_info
        function.argtypes = [ctypes.POINTER(RetroSystemInfo)]
        function.restype = None
        info = RetroSystemInfo()
        function(ctypes.byref(info))
        name = (info.library_name or b"").decode("utf-8", "replace")
        extensions = (info.valid_extensions or b"").decode("ascii", "replace")
        return CoreInfo(
            path=self.path, name=name or _pretty_name(self.path),
            system=guess_system(Path(self.path).name),
            extensions=tuple(part for part in extensions.split("|") if part),
            need_fullpath=bool(info.need_fullpath))

    def _install_callbacks(self) -> list:
        library = self.library

        def environment(command, data):
            try:
                return self._environment(command & 0xFFFF, data)
            except Exception:
                return False

        def video(data, width, height, pitch):
            if data:
                try:
                    self.last_frame = (ctypes.string_at(data, pitch * height),
                                       int(width), int(height), int(pitch),
                                       self.pixel_format)
                except Exception:
                    self.last_frame = None

        def audio(_left, _right):
            return None

        def audio_batch(_data, frames):
            return frames

        def input_poll():
            return None

        def input_state(port, device, _index, ident):
            if port != 0 or device not in (RETRO_DEVICE_JOYPAD, RETRO_DEVICE_ANALOG):
                return 0
            mask = _mask_at(self._presses, self.frame)
            if ident == RETRO_DEVICE_ID_JOYPAD_MASK:
                return ctypes.c_int16(mask).value
            if 0 <= ident < 16:
                return 1 if mask & (1 << ident) else 0
            return 0

        callbacks = [
            _ENV_CB(environment), _VIDEO_CB(video), _AUDIO_CB(audio),
            _AUDIO_BATCH_CB(audio_batch), _INPUT_POLL_CB(input_poll),
            _INPUT_STATE_CB(input_state),
        ]
        setters = [
            ("retro_set_environment", _ENV_CB),
            ("retro_set_video_refresh", _VIDEO_CB),
            ("retro_set_audio_sample", _AUDIO_CB),
            ("retro_set_audio_sample_batch", _AUDIO_BATCH_CB),
            ("retro_set_input_poll", _INPUT_POLL_CB),
            ("retro_set_input_state", _INPUT_STATE_CB),
        ]
        for name, kind in setters:
            function = getattr(library, name)
            function.argtypes = [kind]
            function.restype = None
        library.retro_set_environment(callbacks[0])
        library.retro_set_video_refresh(callbacks[1])
        library.retro_set_audio_sample(callbacks[2])
        library.retro_set_audio_sample_batch(callbacks[3])
        library.retro_set_input_poll(callbacks[4])
        library.retro_set_input_state(callbacks[5])
        return callbacks

    # -- environnement ------------------------------------------------------

    def _environment(self, command: int, data) -> bool:
        if command == RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
            self.pixel_format = ctypes.cast(
                data, ctypes.POINTER(ctypes.c_int)).contents.value
            return True
        if command == RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
            pointer = ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p))
            pointer[0] = self._system_dir_bytes
            return True
        if command == RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
            pointer = ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p))
            pointer[0] = self._save_dir_bytes
            return True
        if command == RETRO_ENVIRONMENT_GET_CAN_DUPE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = True
            return True
        if command == RETRO_ENVIRONMENT_GET_OVERSCAN:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = True
            return True
        if command == RETRO_ENVIRONMENT_GET_VARIABLE:
            variable = ctypes.cast(data, ctypes.POINTER(RetroVariable)).contents
            variable.value = None
            return False
        if command == RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = False
            return True
        if command == RETRO_ENVIRONMENT_GET_INPUT_BITMASKS:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = True
            return True
        if command == RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_int))[0] = 3
            return True
        if command == RETRO_ENVIRONMENT_GET_FASTFORWARDING:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = False
            return True
        if command == RETRO_ENVIRONMENT_GET_TARGET_REFRESH_RATE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_float))[0] = 60.0
            return True
        if command == RETRO_ENVIRONMENT_GET_LANGUAGE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 0
            return True
        if command == RETRO_ENVIRONMENT_GET_PREFERRED_HW_RENDER:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 0
            return True
        if command == RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 0
            return True
        if command == RETRO_ENVIRONMENT_GET_MESSAGE_INTERFACE_VERSION:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 0
            return True
        if command == RETRO_ENVIRONMENT_GET_INPUT_MAX_USERS:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 1
            return True
        if command == RETRO_ENVIRONMENT_GET_DISK_CONTROL_INTERFACE_VERSION:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 1
            return True
        if command == RETRO_ENVIRONMENT_GET_JIT_CAPABLE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = False
            return True
        if command == RETRO_ENVIRONMENT_GET_LOG_INTERFACE:
            return False
        if command in (
                RETRO_ENVIRONMENT_SET_ROTATION, RETRO_ENVIRONMENT_SET_MESSAGE,
                RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL,
                RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS,
                RETRO_ENVIRONMENT_SET_VARIABLES,
                RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME,
                RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO,
                RETRO_ENVIRONMENT_SET_SUBSYSTEM_INFO,
                RETRO_ENVIRONMENT_SET_CONTROLLER_INFO,
                RETRO_ENVIRONMENT_SET_MEMORY_MAPS,
                RETRO_ENVIRONMENT_SET_GEOMETRY,
                RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS,
                RETRO_ENVIRONMENT_SET_SERIALIZATION_QUIRKS,
                RETRO_ENVIRONMENT_SET_CORE_OPTIONS,
                RETRO_ENVIRONMENT_SET_CORE_OPTIONS_INTL,
                RETRO_ENVIRONMENT_SET_CORE_OPTIONS_DISPLAY,
                RETRO_ENVIRONMENT_SET_MESSAGE_EXT,
                RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2,
                RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL,
                RETRO_ENVIRONMENT_SET_VARIABLE):
            return True
        if command in (RETRO_ENVIRONMENT_SET_HW_RENDER,
                       RETRO_ENVIRONMENT_GET_RUMBLE_INTERFACE,
                       RETRO_ENVIRONMENT_GET_SENSOR_INTERFACE,
                       RETRO_ENVIRONMENT_GET_CAMERA_INTERFACE,
                       RETRO_ENVIRONMENT_GET_USERNAME,
                       RETRO_ENVIRONMENT_GET_HW_RENDER_INTERFACE,
                       RETRO_ENVIRONMENT_GET_LIBRETRO_PATH):
            return False
        return False

    # -- jeu ----------------------------------------------------------------

    def load_game(self, rom_path: str | Path, system_dir: str | Path | None = None,
                  save_dir: str | Path | None = None, member: str = "") -> None:
        """Charge une ROM dans le cœur, directement ou depuis une archive.

        Une archive est extraite dans un fichier temporaire (certains cœurs
        exigent un chemin réel) et le fichier est supprimé à la fermeture.
        """
        from . import archives

        rom = Path(rom_path).expanduser()
        if not rom.exists():
            raise EmulationError(f"ROM introuvable : {rom}")
        try:
            source = archives.open_rom(rom, member)
        except archives.ArchiveError as exc:
            raise EmulationError(str(exc)) from exc
        self._system_dir = str(Path(system_dir).expanduser()) if system_dir else str(rom.parent)
        self._save_dir = str(Path(save_dir).expanduser()) if save_dir else str(rom.parent)
        self._system_dir_bytes = os.fsencode(self._system_dir)
        self._save_dir_bytes = os.fsencode(self._save_dir)
        self.rom_path = source.path
        self.rom_member = source.member
        if source.archive:
            self._temp_rom = archives.extract_to_temp(source, rom.parent)
            core_path = self._temp_rom
        else:
            core_path = source.path
        info = RetroGameInfo()
        info.path = os.fsencode(core_path)
        info.meta = None
        if self.info.need_fullpath:
            info.data = None
            info.size = 0
        else:
            data = source.data
            self._rom_buffer = ctypes.create_string_buffer(data, len(data))
            info.data = ctypes.cast(self._rom_buffer, ctypes.c_void_p)
            info.size = len(data)
        if not self.library.retro_load_game(ctypes.byref(info)):
            raise EmulationError(f"le cœur refuse la ROM : {source.display_name}")
        self._loaded = True
        self.frame = 0
        with contextlib.suppress(AttributeError):
            self.library.retro_set_controller_port_device(0, RETRO_DEVICE_JOYPAD)

    def run(self, frames: int = 1, buttons: str | list[ButtonPress] = "") -> int:
        """Exécute ``frames`` trames ; renvoie le nombre de trames jouées."""
        if not self._loaded:
            raise EmulationError("aucune ROM chargée")
        self._presses = (parse_buttons(buttons) if isinstance(buttons, str)
                         else list(buttons))
        start = self.frame
        for _ in range(max(0, int(frames))):
            self.library.retro_run()
            self.frame += 1
        return self.frame - start

    def memory(self, region_id: int) -> bytes:
        """Lit un bloc mémoire libretro (0 = sauvegarde, 2 = RAM, 3 = VRAM)."""
        size = int(self.library.retro_get_memory_size(region_id))
        pointer = self.library.retro_get_memory_data(region_id)
        if not pointer or size <= 0:
            return b""
        return ctypes.string_at(pointer, size)

    def snapshot(self, with_screenshot: bool = False) -> MemorySnapshot:
        """Copie les régions mémoire et, si demandé, la dernière image."""
        if not self._loaded:
            raise EmulationError("aucune ROM chargée")
        bases = MEMORY_BASES.get(self.info.system, {})
        regions: dict[str, MemoryRegion] = {}
        for region_id, name in MEMORY_REGIONS:
            data = self.memory(region_id)
            if data:
                regions[name] = MemoryRegion(name, data,
                                             base=bases.get(name, 0),
                                             region_id=region_id)
        screenshot = self.screenshot_png() if with_screenshot else None
        rom_name = (f"{self.rom_path}/{self.rom_member}"
                    if self.rom_member else self.rom_path)
        return MemorySnapshot(core=self.info.name, rom=rom_name,
                              system=self.info.system, frames=self.frame,
                              regions=regions, screenshot=screenshot)

    # -- image --------------------------------------------------------------

    def screenshot_png(self) -> bytes | None:
        """Convertit la dernière image en PNG (ou ``None`` sans image)."""
        if not self.last_frame:
            return None
        try:
            import numpy as np

            from .image import Image, save_image
        except Exception:
            return None
        raw, width, height, pitch, pixel_format = self.last_frame
        if width <= 0 or height <= 0:
            return None
        try:
            if pixel_format == RETRO_PIXEL_FORMAT_XRGB8888:
                rows = np.frombuffer(raw, dtype=np.uint8).reshape(height, pitch)
                rgb = rows[:, : width * 4].reshape(height, width, 4)[..., [2, 1, 0]]
            else:
                rows = np.frombuffer(raw, dtype=np.uint8).reshape(height, pitch)
                values = rows[:, : width * 2].copy().view("<u2").reshape(height, width)
                if pixel_format == RETRO_PIXEL_FORMAT_RGB565:
                    red = ((values >> 11) & 0x1F).astype(np.uint16)
                    green = ((values >> 5) & 0x3F).astype(np.uint16)
                    blue = (values & 0x1F).astype(np.uint16)
                    rgb = np.stack([(red << 3) | (red >> 2),
                                    (green << 2) | (green >> 4),
                                    (blue << 3) | (blue >> 2)], axis=-1)
                else:
                    red = ((values >> 10) & 0x1F).astype(np.uint16)
                    green = ((values >> 5) & 0x1F).astype(np.uint16)
                    blue = (values & 0x1F).astype(np.uint16)
                    rgb = np.stack([(red << 3) | (red >> 2),
                                    (green << 3) | (green >> 2),
                                    (blue << 3) | (blue >> 2)], axis=-1)
            image = Image.from_rgb(rgb.astype(np.uint8))
            handle, temp_name = tempfile.mkstemp(suffix=".png")
            os.close(handle)
            try:
                save_image(temp_name, image)
                return Path(temp_name).read_bytes()
            finally:
                Path(temp_name).unlink(missing_ok=True)
        except Exception:
            return None

    def close(self) -> None:
        """Décharge le jeu et le cœur."""
        if getattr(self, "_loaded", False):
            with contextlib.suppress(Exception):
                self.library.retro_unload_game()
            self._loaded = False
        if getattr(self, "_initialised", False):
            with contextlib.suppress(Exception):
                self.library.retro_deinit()
            self._initialised = False
        if getattr(self, "_temp_rom", ""):
            with contextlib.suppress(OSError):
                Path(self._temp_rom).unlink()
            self._temp_rom = ""

    def __enter__(self) -> LibretroCore:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Raccourcis
# ---------------------------------------------------------------------------


def run_rom(core_path: str | Path, rom_path: str | Path, frames: int = 600,
            buttons: str = "", output_dir: str | Path | None = None,
            name: str = "", system_dir: str | Path | None = None,
            save_dir: str | Path | None = None,
            screenshot: bool = False, member: str = "") -> MemorySnapshot | dict:
    """Charge une ROM, avance de ``frames`` trames et renvoie la mémoire.

    Si ``output_dir`` est fourni, l'instantané y est écrit et la fonction
    renvoie le manifeste produit ; sinon elle renvoie l'instantané lui-même.
    """
    with LibretroCore(core_path) as core:
        core.load_game(rom_path, system_dir=system_dir, save_dir=save_dir,
                       member=member)
        core.run(frames, buttons=buttons)
        snapshot = core.snapshot(with_screenshot=screenshot)
        snapshot.rom = (f"{Path(rom_path).expanduser()}/{core.rom_member}"
                        if core.rom_member
                        else str(Path(rom_path).expanduser()))
        if output_dir is None:
            return snapshot
        result = snapshot.save(output_dir, name=name)
        result["snapshot"] = snapshot.as_dict()
        return result


def scan_snapshot(snapshot: MemorySnapshot, tile_format: str = "snes_4bpp",
                  compressions: list[str] | None = None, **options) -> dict:
    """Balaye les régions d'un instantané avec le moteur de TileForge.

    Chaque région est balayée séparément : les offsets renvoyés sont relatifs
    à la région, et son adresse de base est rappelée dans le résultat.
    """
    from . import scan as scan_mod

    keys = (compressions if compressions is not None
            else scan_mod.compressions_for(tile_format))
    results = []
    for region in snapshot.regions.values():
        report = scan_mod.scan_bytes(region.data, tile_format,
                                     compressions=keys, **options)
        results.append({
            "region": region.name, "base": region.base,
            "size": len(region.data),
            "candidates": [candidate.as_dict() for candidate in report.candidates],
            "tested": report.tested, "scored": report.scored,
            "elapsed": round(report.elapsed, 3),
            "truncated": report.truncated,
        })
    return {"system": snapshot.system, "frames": snapshot.frames,
            "regions": results}
