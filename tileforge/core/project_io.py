"""Sauvegarde et chargement des projets TileForge (``.tileforge.json``).

Le projet embarque l'image de la planche (PNG en base 64) tant qu'elle reste
raisonnable, ce qui rend les fichiers autonomes : on peut rouvrir un projet
sans retrouver la ROM d'origine.  Au-delà d'une certaine taille, on se contente
de référencer le fichier source.
"""

from __future__ import annotations

import base64
import json
import os

from .image import decode_png, encode_png, load_image
from .model import Project, Sheet, Tile

FORMAT = "tileforge/2"
MAX_EMBED_BYTES = 6 * 1024 * 1024


def save_project(project: Project, path: str, embed_sheet: bool = True) -> None:
    """Écrit le projet sur disque (écriture atomique)."""
    d = project.as_dict()
    d["format"] = FORMAT

    if project.sheet is not None and embed_sheet:
        try:
            png = encode_png(project.sheet.image)
        except Exception:
            png = b""
        if 0 < len(png) <= MAX_EMBED_BYTES:
            d["sheet"]["image_png"] = base64.b64encode(png).decode("ascii")

    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    project.path = path
    project.dirty = False


def load_project(path: str) -> Project:
    """Lit un projet et reconstruit la planche."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)

    project = Project.from_dict(d)
    sheet_info = d.get("sheet")
    if sheet_info:
        image = None
        if sheet_info.get("image_png"):
            try:
                image = decode_png(base64.b64decode(sheet_info["image_png"]))
            except Exception:
                image = None
        if image is None:
            src = sheet_info.get("source", "")
            if src and not os.path.isabs(src):
                cand = os.path.join(os.path.dirname(os.path.abspath(path)), src)
                if os.path.exists(cand):
                    src = cand
            if src and os.path.exists(src):
                image = load_image(src)
        if image is None:
            raise FileNotFoundError(
                "l'image de la planche est introuvable : ni embarquée dans le "
                "projet, ni accessible à l'emplacement enregistré")
        tiles = [Tile.from_dict(t) for t in sheet_info.get("tiles", [])]
        project.sheet = Sheet(image=image, source=sheet_info.get("source", ""),
                              kind=sheet_info.get("kind", "png"),
                              info=sheet_info.get("info", {}) or {},
                              tiles=tiles)
        project.sheet._next_id = 1 + max((t.id for t in tiles), default=-1)

    project.path = path
    project.dirty = False
    if project.sprites:
        project.atlas.compute(project.validated_sprites())
    return project


# ---------------------------------------------------------------------------
# Recettes
# ---------------------------------------------------------------------------


def save_recipe(recipe, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"format": "tileforge/recipe/1", **recipe.as_dict()}, f,
                  ensure_ascii=False, indent=1)


def load_recipe(path: str):
    from .model import Recipe
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return Recipe.from_dict(d)


# ---------------------------------------------------------------------------
# Exports d'analyse
# ---------------------------------------------------------------------------


def export_placements_csv(project: Project, path: str) -> int:
    """CSV ``sprite,storage_index,gx,gy,slot,grid_cols,grid_rows``."""
    sheet = project.sheet
    rows = []
    for sp in project.validated_sprites():
        for slot, tid in sorted(sp.placements.items()):
            t = sheet.tile(tid) if sheet else None
            si = t.storage_index if t is not None else ""
            gx, gy = slot % sp.cols, slot // sp.cols
            rows.append((sp.id, si, gx, gy, slot, sp.cols, sp.rows, sp.name))
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("sprite,storage_index,gx,gy,slot,grid_cols,grid_rows,name\n")
        for r in rows:
            f.write(",".join(str(v) for v in r) + "\n")
    return len(rows)


def export_placements_json(project: Project, path: str) -> None:
    sheet = project.sheet
    data = {
        "format": "tileforge/placements/1",
        "game": project.game,
        "system": project.system,
        "grid": project.grid.as_dict(),
        "sprites": [],
    }
    for sp in project.validated_sprites():
        placements = []
        for slot, tid in sorted(sp.placements.items()):
            t = sheet.tile(tid) if sheet else None
            placements.append({
                "slot": slot, "gx": slot % sp.cols, "gy": slot // sp.cols,
                "storage_index": t.storage_index if t is not None else None,
            })
        data["sprites"].append({
            "id": sp.id, "name": sp.name, "cols": sp.cols, "rows": sp.rows,
            "cost": sp.cost, "placements": placements,
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def export_permutations_txt(project: Project, path: str) -> None:
    """Permutation lisible de chaque sprite (stockage → case)."""
    sheet = project.sheet
    lines = ["# Permutations observées (indice de stockage → case de grille)",
             "# case = gy * cols + gx", ""]
    for sp in project.validated_sprites():
        n = sp.cols * sp.rows
        arr = ["?"] * n
        for slot, tid in sp.placements.items():
            t = sheet.tile(tid) if sheet else None
            if t is None or t.storage_index is None:
                continue
            base = min((sheet.tile(x).storage_index for x in sp.placements.values()
                        if sheet.tile(x) is not None and sheet.tile(x).storage_index is not None),
                       default=0)
            off = t.storage_index - base
            if 0 <= off < n:
                arr[off] = str(slot)
        lines.append(f"{sp.name:16s} (id {sp.id}, {sp.cols}×{sp.rows}) : " + " ".join(arr))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
