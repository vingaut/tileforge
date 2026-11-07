"""Implémentation des outils MCP de TileForge.

Chaque fonction reçoit les arguments du client, travaille sur des fichiers et
renvoie un dictionnaire sérialisable.  Les aperçus sont écrits en PNG dans un
dossier de travail : un assistant peut les ouvrir pour vérifier le résultat.

Aucune dépendance à Qt : le serveur tourne sans interface graphique.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..core import archives as archives_mod
from ..core import cartography as cartography_mod
from ..core import compression as compression_mod
from ..core import disasm6502 as disasm6502_mod
from ..core import disasm65816 as disasm_mod
from ..core import disasm68000 as disasm68000_mod
from ..core import disasmz80 as disasmz80_mod
from ..core import emulation as emulation_mod
from ..core import identify as identify_mod
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
