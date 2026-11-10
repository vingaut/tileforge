"""Implémentation des outils MCP de TileForge.

Chaque fonction reçoit les arguments du client, travaille sur des fichiers et
renvoie un dictionnaire sérialisable.  Les aperçus sont écrits en PNG dans un
dossier de travail : un assistant peut les ouvrir pour vérifier le résultat.

Aucune dépendance à Qt : le serveur tourne sans interface graphique.
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

from ..core import amigadisk as amigadisk_mod
from ..core import amigasprites as amigasprites_mod
from ..core import archives as archives_mod
from ..core import cartography as cartography_mod
from ..core import compression as compression_mod
from ..core import copper as copper_mod
from ..core import disasm6502 as disasm6502_mod
from ..core import disasm65816 as disasm_mod
from ..core import disasm68000 as disasm68000_mod
from ..core import disasmz80 as disasmz80_mod
from ..core import emulation as emulation_mod
from ..core import hunk as hunk_mod
from ..core import identify as identify_mod
from ..core import imploder as imploder_mod
from ..core import nested as nested_mod
from ..core import planar as planar_mod
from ..core import rnc as rnc_mod
from ..core import scan as scan_mod
from ..core.formats import FORMATS, FORMATS_BY_KEY, load_raw_bank
from ..core.image import load_image, save_image
from ..core.model import Project, Sprite
from ..core.palettes import BUILTIN_PALETTES, read_rom_palette
from ..core.settings import data_dir
from ..core.systems import SYSTEMS

# ---------------------------------------------------------------------------
# État du serveur
# ---------------------------------------------------------------------------

_STATE: dict = {"project": None, "source": None}


def work_dir() -> Path:
    folder = Path(os.environ.get("TILEFORGE_MCP_DIR") or (data_dir() / "mcp"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _preview_path(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return str(work_dir() / f"{safe}.png")


def _read(path: str, member: str = "") -> bytes:
    """Lit un fichier, ou un membre d'archive zip/7z."""
    return archives_mod.read_rom(path, member)


def list_archive(path: str) -> dict:
    """Liste les fichiers d'une archive zip/7z et le membre choisi par défaut."""
    return archives_mod.archive_summary(path)


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------


def inspect_file(path: str, archive_member: str = "") -> dict:
    """Décrit un fichier : ROM SNES/Mega Drive, image, projet, archive."""
    full = os.path.expanduser(path)
    if not os.path.exists(full):
        raise FileNotFoundError(f"fichier introuvable : {full}")
    summary = archives_mod.archive_summary(full, archive_member)

    if not summary["archive"] and full.lower().endswith((".png", ".gif", ".bmp")):
        img = load_image(full)
        return {"path": os.path.abspath(full), "size": os.path.getsize(full),
                "kind": "image", "width": img.w, "height": img.h,
                "colors": img.color_count()}

    if not summary["archive"] and full.lower().endswith(".json"):
        with open(full, encoding="utf-8") as f:
            data = json.load(f)
        return {"path": os.path.abspath(full), "size": os.path.getsize(full),
                "kind": "projet", "format": data.get("format"),
                "tiles": len(data.get("sheet", {}).get("tiles", [])),
                "sprites": len(data.get("sprites", []))}

    data = _read(full, archive_member)
    info: dict = {"path": os.path.abspath(full), "size": len(data)}
    if summary["archive"]:
        info["archive"] = summary
    # Une image ADZ est une image ADF compressée en gzip.
    if data[:2] == b"\x1f\x8b":
        try:
            inner = gzip.decompress(data)
        except OSError:
            inner = b""
        if inner[:3] == b"DOS":
            data = inner
            info["compressed_size"] = info["size"]
            info["size"] = len(data)
            info["format_hint"] = "ADZ"
    # -- disques Amiga
    if data[:4] == b"CAPS" or full.lower().endswith(".ipf"):
        info.update({"kind": "disque", "machine": "Amiga", "format": "IPF",
                     "warning": "IPF (CAPS/SPS) : convertir en ADF pour "
                                "l'ouvrir (la bibliothèque SPS n'est pas libre)"})
        return info
    if data[:4] == b"DMS!" or full.lower().endswith(".dms"):
        info.update({"kind": "disque", "machine": "Amiga", "format": "DMS",
                     "warning": "archive DMS : convertir en ADF (xdms)"})
        return info
    if data[:3] == b"DOS" and len(data) >= 901120:
        entry = {"kind": "disque", "machine": "Amiga",
                 "format": info.get("format_hint") or "ADF"}
        try:
            volume = amigadisk_mod.open_disk(full, member=archive_member)
            entry.update({"volume": volume.name,
                          "filesystem": "FFS" if volume.ffs else "OFS",
                          "file_count": len(volume.files()),
                          "warnings": volume.warnings,
                          "files": [f.path for f in volume.files()[:24]]})
        except Exception as exc:
            entry["warning"] = str(exc)
        info.update(entry)
        return info
    # -- exécutable Amiga
    if hunk_mod.is_hunk(data):
        try:
            parsed = hunk_mod.parse(data)
            info.update({"kind": "exécutable", "machine": "Amiga",
                         "format": "hunk", "segments": len(parsed.segments),
                         "hunk": parsed.summary()})
        except Exception as exc:
            info.update({"kind": "exécutable", "machine": "Amiga",
                         "format": "hunk", "warning": str(exc)})
        return info
    # -- blocs compressés Amiga
    if imploder_mod.is_imploder(data):
        info.update({"kind": "binaire", "machine": "Amiga",
                     "format": "Imploder", "compressions": ["imploder"]})
        info.update(imploder_mod.inspect(data))
        return info
    if rnc_mod.is_rnc(data):
        info.update({"kind": "binaire", "machine": "Amiga",
                     "format": "RNC ProPack", "compressions": ["rnc"]})
        info.update(rnc_mod.inspect(data))
        return info
    # -- Mega Drive
    if len(data) > 0x120 and data[0x100:0x110] == b"SEGA MEGA DRIVE":
        info.update({"kind": "rom", "machine": "Mega Drive",
                     "title": data[0x120:0x150].decode("latin-1").strip(),
                     "tile_format": "megadrive", "compressions": ["kosinski", "nemesis"]})
        return info
    # -- Super Nintendo (LoROM ou HiROM)
    for base in (0x7FC0, 0xFFC0):
        if len(data) > base + 0x20:
            title = data[base:base + 21].decode("latin-1", "replace").strip()
            if title and all(32 <= ord(c) < 127 for c in title):
                info.update({"kind": "rom", "machine": "Super Nintendo",
                             "title": title, "mapping": "LoROM" if base == 0x7FC0 else "HiROM",
                             "tile_format": "snes_4bpp",
                             "compressions": ["lz2"]})
                return info
    info.update({"kind": "binaire", "tile_format": "chunky8",
                 "compressions": [d.key for d in compression_mod.DECOMPRESSORS]})
    return info


def list_tile_formats() -> list[dict]:
    return [{"key": f.key, "name": f.name, "tile_w": f.tile_w, "tile_h": f.tile_h,
             "bpp": f.bpp, "bytes_per_tile": f.real_bytes, "layout": f.layout,
             "system": f.system_key, "notes": f.notes} for f in FORMATS]


def list_systems(family: str = "") -> list[dict]:
    out = []
    for spec in SYSTEMS:
        if family and spec.family != family:
            continue
        out.append({"key": spec.key, "name": spec.name, "family": spec.family,
                    "year": spec.year,
                    "resolutions": [list(r) for r in spec.resolutions],
                    "colors": spec.colors, "bpp": spec.bpp,
                    "tile_sizes": [list(t) for t in spec.tile_sizes]})
    return out


def read_palette(path: str, offset: int, kind: str = "snes",
                 count: int = 16, archive_member: str = "") -> dict:
    data = _read(path, archive_member)
    palette = read_rom_palette(data, offset, count, kind)
    return {"offset": offset, "kind": kind, "count": len(palette),
            "colors": [list(c) for c in palette.colors]}


# ---------------------------------------------------------------------------
# Découverte de graphismes
# ---------------------------------------------------------------------------


def scan_graphics(path: str, start: int = 0, end: int | None = None,
                  tile_format: str = "", compression: str = "auto",
                  min_size: int = 512, max_size: int = 262144,
                  threshold: float = 0.45, limit: int = 8,
                  preview: bool = True, step: int = 1,
                  budget: float = 30.0,
                  structured_only: bool = False,
                  extended: bool = False,
                  workers: int = 1,
                  archive_member: str = "") -> dict:
    """Cherche des graphismes : données brutes et blocs compressés.

    S'appuie sur le moteur :mod:`tileforge.core.scan` : balayage grossier puis
    affiné pour les données brutes, offset par offset pour les blocs
    compressés, budget de temps respecté et fusion des zones voisines.
    """
    data = _read(path, archive_member)
    info = inspect_file(path, archive_member)
    fmt_key = tile_format or info.get("tile_format") or "snes_4bpp"
    fmt = FORMATS_BY_KEY.get(fmt_key)
    if fmt is None:
        raise ValueError(f"format de tuile inconnu : {fmt_key}")

    if compression in ("", "auto", None):
        keys = scan_mod.compressions_for(fmt_key, extended=extended)
    elif compression in ("aucune", "none"):
        keys = []
    else:
        keys = [compression]

    options = {"start": max(0, int(start)),
                   "end": None if end is None else int(end),
                   "step": max(1, int(step)),
                   "threshold": threshold,
                   "budget": budget,
                   "min_size": min_size,
                   "max_size": max_size,
                   "max_candidates": limit,
                   "raw": True,
                   "compressed": bool(keys)}
    if structured_only:
        ranges = cartography_mod.structured_ranges(
            data, min_size=min_size, window=4096)
        ranges = [(max(a, options["start"]), min(b, options["end"] or len(data)))
                  for a, b in ranges]
        ranges = [(a, b) for a, b in ranges if b - a >= min_size]
        if ranges:
            report = scan_mod.scan_ranges(data, fmt_key, ranges, **options)
        else:
            report = scan_mod.Scanner(data, [fmt], keys, source=path).run(**options)
    else:
        report = scan_mod.Scanner(data, [fmt], keys, source=path).run(**options)

    candidates = [candidate.as_dict() for candidate in report.candidates]
    for index, candidate in enumerate(report.candidates):
        if not preview:
            continue
        try:
            if candidate.compression:
                payload = compression_mod.decompress(
                    candidate.compression, data, candidate.offset)
                offset = 0
            else:
                payload = data
                offset = candidate.offset
            count = min(256, (len(payload) - offset) // fmt.real_bytes)
            bank = load_raw_bank(None, offset, count, fmt, per_row=16, gap=1,
                                 data=payload)
            out = _preview_path(f"scan_{Path(path).stem}_{index}")
            save_image(out, bank.image)
            candidates[index]["preview_png"] = out
        except Exception:
            continue

    return {"path": os.path.abspath(path), "tile_format": fmt_key,
            "candidates": candidates, "tested": report.tested,
            "scored": report.scored, "elapsed": round(report.elapsed, 2),
            "truncated": report.truncated, "budget": budget}


def disassemble(path: str, offset: int = 0, count: int = 64,
                entry: int = -1, layout: str = "LoROM", cpu: str = "65816",
                base: int = 0, archive_member: str = "") -> dict:
    """Désassemble du 65816, linéairement ou en suivant le fil d'exécution.

    ``entry`` est une adresse processeur (par exemple 0x8000 pour le vecteur
    de reset d'une ROM LoROM) : le traçage ne décode alors que le code
    réellement atteignable, ce qui distingue le code des données.
    """
    data = _read(path, archive_member)
    key = cpu.lower()
    if key in ("6502", "nes", "c64"):
        module = disasm6502_mod
    elif key in ("z80", "spectrum", "cpc", "msx"):
        module = disasmz80_mod
    elif key in ("sm83", "gameboy", "gb"):
        module = disasmz80_mod
        cpu = "sm83"
    elif key in ("68000", "68k", "megadrive", "genesis", "amiga", "atarist"):
        module = disasm68000_mod
    else:
        module = disasm_mod
    if entry >= 0:
        if module in (disasm6502_mod, disasmz80_mod, disasm68000_mod):
            kwargs = {"variant": "sm83"} if cpu.lower() == "sm83" else {}
            instructions = module.trace(data, int(entry),
                                        max_instructions=max(1, int(count)),
                                        base=int(base), **kwargs)
        else:
            instructions = module.trace(data, int(entry),
                                        max_instructions=max(1, int(count)),
                                        layout=layout)
    else:
        instructions = module.disassemble(data, max(0, int(offset)),
                                          max(1, int(count)))
    return {
        "path": os.path.abspath(path),
        "count": len(instructions),
        "cpu": cpu,
        "layout": layout,
        "base": int(base),
        "entry": int(entry) if entry >= 0 else None,
        "instructions": [ins.as_dict() for ins in instructions],
        "listing": disasm_mod.format_listing(instructions),
    }


def cartography(path: str, window: int = 4096,
                archive_member: str = "") -> dict:
    """Cartographie une ROM : plateforme, zones d'entropie, tables de pointeurs."""
    data = _read(path, archive_member)
    report = cartography_mod.cartography(data, max(512, int(window)))
    report["path"] = os.path.abspath(path)
    report["description"] = cartography_mod.describe(report)
    return report


def identify_format(path: str, offset: int = 0, length: int = 16384,
                    formats: list[str] | None = None,
                    archive_member: str = "") -> dict:
    """Devine le format de tuiles d'un bloc et renvoie un classement.

    Chaque format candidat est comparé à son propre plancher de bruit : un
    format à 1 bit « explique » n'importe quelle donnée, il ne doit donc pas
    gagner au seul score brut.
    """
    data = _read(path, archive_member)
    chunk = data[max(0, int(offset)):max(0, int(offset)) + max(512, int(length))]
    result = identify_mod.explain(chunk, formats)
    result.update({"path": os.path.abspath(path), "offset": int(offset),
                   "length": len(chunk)})
    return result


def preview_tiles(path: str, offset: int = 0, tile_format: str = "snes_4bpp",
                  compression: str = "", palette: str = "",
                  palette_offset: int = -1, palette_kind: str = "snes",
                  count: int = 64, per_row: int = 16,
                  output: str = "", archive_member: str = "") -> dict:
    data = _read(path, archive_member)
    if compression and compression not in ("aucune", "none", ""):
        data = compression_mod.decompress(compression, data, offset)
        offset = 0
    fmt = FORMATS_BY_KEY.get(tile_format)
    if fmt is None:
        raise ValueError(f"format de tuile inconnu : {tile_format}")

    pal = None
    if palette_offset >= 0:
        pal = read_rom_palette(data, palette_offset, 16, palette_kind)
    elif palette:
        pal = BUILTIN_PALETTES.get(palette)

    total = max(0, (len(data) - offset) // fmt.real_bytes)
    count = min(count or total, total)
    bank = load_raw_bank(None, offset, count, fmt, per_row=per_row, gap=1,
                         palette=pal, data=data)
    out = output or _preview_path(f"preview_{Path(path).stem}_{offset:x}")
    save_image(out, bank.image)
    return {"tiles": bank.count, "width": bank.image.w, "height": bank.image.h,
            "bytes_per_tile": fmt.real_bytes, "available_tiles": total,
            "preview_png": out}


# ---------------------------------------------------------------------------
# Projet
# ---------------------------------------------------------------------------


def open_bank(path: str, offset: int = 0, tile_format: str = "snes_4bpp",
              compression: str = "", count: int = 0, per_row: int = 16,
              palette: str = "", palette_offset: int = -1,
              palette_kind: str = "snes", archive_member: str = "") -> dict:
    """Charge une banque dans le projet du serveur."""
    data = _read(path, archive_member)
    if compression and compression not in ("aucune", "none", ""):
        data = compression_mod.decompress(compression, data, offset)
        offset = 0
    fmt = FORMATS_BY_KEY.get(tile_format)
    if fmt is None:
        raise ValueError(f"format de tuile inconnu : {tile_format}")

    pal = None
    if palette_offset >= 0:
        pal = read_rom_palette(data, palette_offset, 16, palette_kind)
    elif palette:
        pal = BUILTIN_PALETTES.get(palette)

    total = max(0, (len(data) - offset) // fmt.real_bytes)
    count = min(count or total, total)
    bank = load_raw_bank(None, offset, count, fmt, per_row=per_row, gap=1,
                         palette=pal, data=data)

    project = Project()
    project.sheet = __import__("tileforge.core.model", fromlist=["Sheet"]).Sheet(
        image=bank.image, source=os.path.abspath(path), kind="raw",
        info={"offset": offset, "format": fmt.key, "count": bank.count,
              "per_row": per_row, "gap": bank.gap,
              "compression": compression or "", "palette": palette or ""})
    for index, rect in enumerate(bank.tile_rects()):
        project.sheet.add_tile(rect, storage_index=index, label=str(index))
    project.grid.tile_w = fmt.tile_w
    project.grid.tile_h = fmt.tile_h
    project.game = Path(path).stem
    _STATE["project"] = project
    _STATE["source"] = os.path.abspath(path)
    return {"tiles": len(project.sheet.tiles), "tile_w": fmt.tile_w,
            "tile_h": fmt.tile_h, "bytes_per_tile": fmt.real_bytes,
            "image_width": bank.image.w, "image_height": bank.image.h,
            "format": fmt.name}


def project_info() -> dict:
    project = _STATE.get("project")
    if project is None:
        return {"open": False}
    sheet = project.sheet
    return {"open": True, "tiles": len(sheet.tiles) if sheet else 0,
            "grid": project.grid.as_dict(),
            "sprites": len(project.validated_sprites()),
            "atlas": {"width": project.atlas.width,
                      "height": project.atlas.height},
            "source": _STATE.get("source")}


def list_tiles(offset: int = 0, limit: int = 128) -> dict:
    project = _STATE.get("project")
    if project is None or project.sheet is None:
        raise RuntimeError("aucun projet ouvert : appelez tileforge_open_bank")
    tiles = project.sheet.tiles_sorted()
    window = tiles[offset:offset + limit]
    return {"total": len(tiles), "offset": offset,
            "tiles": [{"id": t.id, "storage_index": t.storage_index,
                       "rect": list(t.rect)} for t in window]}


def _group_tiles(project, group: int, cols: int, rows: int) -> list[int]:
    tiles = project.sheet.tiles_sorted()
    start = group * cols * rows
    return [t.id for t in tiles[start:start + cols * rows]]


def auto_assemble(cols: int = 2, rows: int = 4, group: int = 0,
                  method: str = "M1", limit: int = 5) -> dict:
    from ..assemble import solvers
    from ..assemble.cost import build_cost_model

    project = _STATE.get("project")
    if project is None or project.sheet is None:
        raise RuntimeError("aucun projet ouvert : appelez tileforge_open_bank")
    tile_ids = _group_tiles(project, group, cols, rows)
    if len(tile_ids) < cols * rows:
        raise ValueError("pas assez de tuiles pour cette grille")
    model = build_cost_model(project.sheet, tile_ids)
    solutions = solvers.solve(method, model, cols, rows, {"limit": limit})
    return {"group": group, "cols": cols, "rows": rows, "tile_ids": tile_ids,
            "solutions": [{"method": s.method, "cost": round(s.cost, 4),
                           "label": s.label, "order": s.order}
                          for s in solutions[:limit]]}


def render_sprite(tiles: list[int], cols: int = 2, rows: int = 4,
                  output: str = "") -> dict:
    project = _STATE.get("project")
    if project is None or project.sheet is None:
        raise RuntimeError("aucun projet ouvert")
    sprite = Sprite(0, "apercu", cols, rows,
                    project.grid.tile_w, project.grid.tile_h)
    for slot, tile_id in enumerate(tiles[:cols * rows]):
        sprite.placements[slot] = int(tile_id)
    image = sprite.render(project.sheet)
    out = output or _preview_path("sprite")
    save_image(out, image)
    return {"width": image.w, "height": image.h, "preview_png": out}


def validate_sprite(tiles: list[int], cols: int = 2, rows: int = 4,
                    name: str = "") -> dict:
    project = _STATE.get("project")
    if project is None or project.sheet is None:
        raise RuntimeError("aucun projet ouvert")
    project.grid.cols, project.grid.rows = cols, rows
    project.next_sprite_id += 1
    sprite = Sprite(project.next_sprite_id, name or f"pose_{project.next_sprite_id:02d}",
                    cols, rows, project.grid.tile_w, project.grid.tile_h)
    for slot, tile_id in enumerate(tiles[:cols * rows]):
        sprite.placements[slot] = int(tile_id)
    project.current = sprite
    project.validate_current()
    return {"sprites": len(project.validated_sprites()),
            "atlas": {"width": project.atlas.width,
                      "height": project.atlas.height}}


def save_project(path: str) -> dict:
    from ..core import project_io
    project = _STATE.get("project")
    if project is None:
        raise RuntimeError("aucun projet ouvert")
    full = os.path.expanduser(path)
    project_io.save_project(project, full)
    return {"path": full, "size": os.path.getsize(full)}


def export_atlas(path: str) -> dict:
    project = _STATE.get("project")
    if project is None:
        raise RuntimeError("aucun projet ouvert")
    sprites = project.validated_sprites()
    if not sprites:
        raise RuntimeError("aucun sprite validé")
    image = project.atlas.render({s.id: s for s in sprites}, project.sheet)
    full = os.path.expanduser(path)
    save_image(full, image)
    return {"path": full, "sprites": len(sprites),
            "width": image.w, "height": image.h}


# ---------------------------------------------------------------------------
# Mémoire d'émulateur
# ---------------------------------------------------------------------------


def list_emulator_cores(extra_paths: list[str] | None = None) -> list[dict]:
    """Liste les cœurs libretro installés (RetroArch, paquets système…)."""
    return [core.as_dict()
            for core in emulation_mod.discover_cores(extra_paths or [])]


def emulator_memory(core: str, rom: str, frames: int = 600,
                    buttons: str = "", output: str = "", name: str = "",
                    screenshot: bool = False, scan: bool = False,
                    tile_format: str = "", compression: str = "auto",
                    budget: float = 30.0, limit: int = 8,
                    extended: bool = False, archive_member: str = "",
                    system_dir: str = "") -> dict:
    """Exécute une ROM dans un cœur libretro et lit la mémoire décodée.

    C'est la voie de secours quand un jeu utilise un compresseur maison : on
    laisse le jeu décompresser ses graphismes en RAM, puis on balaye la mémoire
    comme n'importe quelle banque brute.
    """
    core_path = os.path.expanduser(core)
    rom_path = os.path.expanduser(rom)
    if not os.path.exists(core_path):
        raise FileNotFoundError(f"cœur introuvable : {core_path}")
    if not os.path.exists(rom_path):
        raise FileNotFoundError(f"ROM introuvable : {rom_path}")
    folder = os.path.expanduser(output) if output else str(
        work_dir() / "memory" / Path(rom_path).stem)
    result = emulation_mod.run_rom(
        core_path, rom_path, frames=max(1, int(frames)), buttons=buttons,
        output_dir=folder, name=name, screenshot=screenshot,
        member=archive_member, system_dir=system_dir or None)
    result["core"] = core_path
    result["rom"] = rom_path
    if scan:
        snapshot = emulation_mod.MemorySnapshot.load(result["manifest"])
        info = inspect_file(rom_path, archive_member)
        defaults = {
            "gba": "gba_4bpp", "gameboy": "gameboy", "snes": "snes_4bpp",
            "nes": "nes", "megadrive": "megadrive",
            "atarist": "st_sprite_4pl", "pcengine": "pc_engine",
        }
        fmt_key = tile_format or defaults.get(snapshot.system) or info.get(
            "tile_format") or "snes_4bpp"
        # La mémoire est déjà décompressée par le jeu : le balayage brut est
        # le mode par défaut. Un décompresseur explicite reste possible.
        if compression in ("", "auto", None, "aucune", "none"):
            keys = (scan_mod.compressions_for(fmt_key, extended=True)
                    if extended else [])
        else:
            keys = [compression]
        result["scan"] = emulation_mod.scan_snapshot(
            snapshot, fmt_key, compressions=keys, budget=budget,
            max_candidates=max(1, int(limit)), min_size=512,
            max_size=262144, threshold=0.45)
    return result


# ---------------------------------------------------------------------------
# Amiga : disques, écrans, sprites, exécutables
# ---------------------------------------------------------------------------


def _write_blob(name: str, data: bytes, suffix: str = ".bin") -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    path = work_dir() / f"{safe}{suffix}"
    path.write_bytes(data)
    return str(path)


def open_disk(path: str, archive_member: str = "") -> dict:
    """Ouvre une image de disquette Amiga (ADF, ADZ, HDF) et liste ses fichiers.

    Les checksums invalides ne bloquent pas l'ouverture : ils sont signalés,
    car une bonne partie du catalogue Amiga est protégée (Copylock).
    """
    volume = amigadisk_mod.open_disk(path, member=archive_member)
    return volume.summary(max_depth=4)


def extract_disk_file(path: str, node_path: str, output: str = "",
                      archive_member: str = "") -> dict:
    """Extrait un fichier d'un disque Amiga vers le dossier de travail."""
    volume = amigadisk_mod.open_disk(path, member=archive_member)
    node = volume.find(node_path)
    data = volume.extract(node)
    target = os.path.expanduser(output) if output else _write_blob(
        f"disk_{node.name}", data)
    if output:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(data)
    return {
        "path": os.path.abspath(target),
        "size": len(data),
        "node": node.path,
        "warnings": volume.warnings,
        "head": data[:32].hex(),
    }


def decompress_nested(path: str, offset: int = 0, max_depth: int = 4,
                      key: int = 0, archive_member: str = "") -> dict:
    """Descend récursivement dans les formats imbriqués (Imploder, RNC…).

    Chaque bloc décompressé est écrit dans le dossier de travail ; le rapport
    indique l'offset, la profondeur, le format et les avertissements.
    """
    data = _read(path, archive_member)
    start = max(0, int(offset))
    blobs = nested_mod.scan_nested(data[start:], max_depth=max_depth, key=key)
    report = nested_mod.summary(blobs)
    for index, blob in enumerate(blobs):
        blob.offset += start
        if blob.parent is not None:
            blob.parent += start
        if blob.data is not None:
            blob_name = f"nested_{index:02d}_{blob.format}_d{blob.depth}_{blob.offset:08x}"
            report["blobs"][index]["path"] = _write_blob(blob_name, blob.data)
    report["source"] = os.path.abspath(os.path.expanduser(path))
    return report


def _resolve_palette(data: bytes, index, palette_offset: int,
                     palette_count: int, planes: int):
    """Palette explicite, sinon meilleure palette du fichier, sinon défaut."""
    if palette_offset >= 0:
        count = palette_count or (1 << planes)
        return planar_mod.read_palette(data, palette_offset, count), "explicite"
    candidates = planar_mod.scan_palettes(data, count=1 << planes, limit=8)
    if candidates:
        best, _ = planar_mod.best_palette(index, candidates)
        if best is not None:
            return best.palette, f"0x0RGB@{best.offset:#x}"
    return planar_mod.DEFAULT_PALETTE, "défaut"


def amiga_screen(path: str, offset: int = 0, width: int = 0, height: int = 256,
                 planes: int = 0, layout: str = "", stride: int = 0,
                 palette_offset: int = -1, palette_count: int = 0,
                 output: str = "", archive_member: str = "") -> dict:
    """Rend un écran Amiga planaire (row-major ou plane-major).

    Sans largeur ni nombre de plans, la géométrie est détectée par cohérence
    de voisinage.  Le rendu est écrit en PNG ; les plans vides sont signalés.
    """
    data = _read(path, archive_member)
    warnings: list[str] = []
    if width <= 0 or planes <= 0:
        candidates = planar_mod.detect_geometry(
            data, start=max(0, offset), height=max(16, height),
            width=max(0, width), planes=max(0, planes),
            layout=layout or "", limit=1, step=64, budget=10.0)
        if not candidates:
            raise ValueError(
                "aucune géométrie planaire cohérente trouvée ; préciser "
                "largeur, hauteur et nombre de plans")
        best = candidates[0]
        offset, width, planes = best.offset, best.width, best.planes
        layout = best.layout
        stride = best.stride
        warnings.append(
            f"géométrie détectée : {width}×{height}, {planes} plans, "
            f"{layout}, pas {stride} (note {best.score:.2f})")
    stride = stride or (width + 7) // 8
    index = planar_mod.decode_indices(data, offset, width, height, planes,
                                      layout or "row", stride)
    palette, palette_source = _resolve_palette(
        data, index, palette_offset, palette_count, planes)
    density = [float((index >> bit & 1).mean()) for bit in range(planes)]
    for bit, value in enumerate(density):
        if value < 1e-4:
            warnings.append(f"plan {bit} vide : probablement {planes - 1} "
                            "plans utiles")
    content_width, strength = planar_mod.detect_padding(index)
    if strength >= 3.0 and content_width < width:
        warnings.append(
            f"bourrage détecté : {content_width} pixels utiles sur {width} "
            f"(discontinuité ×{strength:.1f})")
    image = planar_mod.render_screen(data, offset, width, height, planes,
                                     layout or "row", stride, palette,
                                     transparent=0)
    target = os.path.expanduser(output) if output else _preview_path(
        f"amiga_screen_{offset:08x}")
    save_image(target, image)
    return {
        "path": os.path.abspath(target),
        "offset": offset,
        "width": width,
        "height": height,
        "planes": planes,
        "layout": layout or "row",
        "stride": stride,
        "palette_source": palette_source,
        "palette": [[*color] for color in palette.colors],
        "plane_density": [round(v, 4) for v in density],
        "content_width": content_width,
        "warnings": warnings,
    }


def amiga_sprites(path: str, offset: int = 0, width: int = 0,
                  height: int = 0, planes: int = 0, layout: str = "",
                  stride: int = 0, palette_offset: int = -1,
                  palette_count: int = 0, min_area: int = 8,
                  close_radius: int = 1, columns: int = 8,
                  output: str = "", archive_member: str = "") -> dict:
    """Découpe une planche Amiga en sprites (composantes connexes).

    Écrit une planche PNG des sprites extraits et renvoie leur nombre, la
    grille détectée et les copies pré-décalées repérées.
    """
    data = _read(path, archive_member)
    warnings: list[str] = []
    if width <= 0 or planes <= 0:
        candidates = planar_mod.detect_geometry(
            data, start=max(0, offset), height=max(16, height or 256),
            width=max(0, width), planes=max(0, planes),
            layout=layout or "", limit=1, step=64, budget=10.0)
        if not candidates:
            raise ValueError(
                "aucune planche planaire cohérente trouvée ; préciser "
                "largeur, hauteur et nombre de plans")
        best = candidates[0]
        offset, width, height, planes = (best.offset, best.width,
                                         height or best.height, best.planes)
        layout, stride = best.layout, best.stride
        warnings.append(
            f"géométrie détectée : {width}×{height}, {planes} plans, "
            f"{layout}, pas {stride}")
    height = height or 256
    stride = stride or (width + 7) // 8
    index = planar_mod.decode_indices(data, offset, width, height, planes,
                                      layout or "plane", stride)
    palette, palette_source = _resolve_palette(
        data, index, palette_offset, palette_count, planes)
    sprites = amigasprites_mod.components(index, min_area=min_area,
                                          close_radius=close_radius)
    grid = amigasprites_mod.detect_grid(index)
    shifts = amigasprites_mod.detect_preshift(sprites)
    groups = amigasprites_mod.group_animations(sprites)
    target = os.path.expanduser(output) if output else _preview_path(
        f"amiga_sprites_{offset:08x}")
    written = amigasprites_mod.export_sheet(
        sprites, palette, target, columns=max(1, int(columns)))
    return {
        "path": os.path.abspath(target),
        "offset": offset,
        "width": width,
        "height": height,
        "planes": planes,
        "layout": layout or "plane",
        "stride": stride,
        "palette_source": palette_source,
        "sprites": written,
        "grid": grid.as_dict(),
        "preshifted": shifts[:32],
        "animation_groups": [len(g) for g in groups if len(g) > 1][:32],
        "warnings": warnings,
        "first_sprites": [s.as_dict() for s in sprites[:16]],
    }


def amiga_analyze(path: str, offset: int = 0, archive_member: str = "") -> dict:
    """Analyse un binaire Amiga : hunk, listes copper, blocs imbriqués.

    C'est l'outil d'entrée pour un exécutable ou un fichier décompressé :
    il donne la table des segments, les palettes copper et les formats
    imbriqués qu'il reste à décompresser.
    """
    data = _read(path, archive_member)
    start = max(0, int(offset))
    report: dict = {"source": os.path.abspath(os.path.expanduser(path)),
                    "size": len(data)}
    if hunk_mod.is_hunk(data, start):
        try:
            report["hunk"] = hunk_mod.parse(data, start).summary()
        except Exception as exc:
            report["hunk"] = {"error": str(exc)}
    else:
        found = hunk_mod.find_hunk(data, start)
        if found is not None:
            report["hunk_at"] = found
    lists = copper_mod.find_lists(data[start:], limit=4)
    report["copper_lists"] = [item.summary() for item in lists]
    blobs = nested_mod.scan_nested(data[start:], max_depth=3)
    report["nested"] = nested_mod.summary(blobs)
    return report
