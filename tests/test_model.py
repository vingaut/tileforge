"""Tests du modèle de données et de la persistance des projets.

Ce sont les fonctions qui protègent le travail de l'utilisateur : un projet
enregistré doit se relire à l'identique, et les exports doivent contenir ce
qu'ils promettent.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from tileforge.core import project_io
from tileforge.core.image import Image, encode_png
from tileforge.core.model import Atlas, Project, Recipe, Sheet, Sprite, Tile

# ---------------------------------------------------------------------------
# Fabrique
# ---------------------------------------------------------------------------


def _sheet(tiles: int = 8, size: int = 8) -> Sheet:
    """Planche synthétique : une grille de tuiles colorées."""
    width = tiles * size
    pixels = np.zeros((size, width, 4), dtype=np.uint8)
    for index in range(tiles):
        pixels[:, index * size:(index + 1) * size, 0] = 20 + index * 25
        pixels[:, index * size:(index + 1) * size, 3] = 255
    image = Image(pixels, None, [[0, 0, 0, 0], [255, 255, 255, 255]])
    sheet = Sheet(image=image, source="test", kind="png")
    for index in range(tiles):
        sheet.tiles.append(Tile(id=index, rect=(index * size, 0, size, size),
                                storage_index=index))
    return sheet


def _project() -> Project:
    project = Project()
    project.sheet = _sheet()
    project.game = "test"
    project.grid.cols = 2
    project.grid.rows = 2
    project.grid.tile_w = 8
    project.grid.tile_h = 8
    sprite = Sprite(id=1, name="pose_00", cols=2, rows=2, tile_w=8, tile_h=8,
                    validated=True)
    sprite.placements = {0: 0, 1: 1, 2: 2, 3: 3}
    project.sprites.append(sprite)
    project.current = Sprite(id=2, name="pose_01", cols=2, rows=2, tile_w=8, tile_h=8)
    project.recipes.append(Recipe(name="recette", cols=2, rows=2,
                                  mapping=[0, 1, 2, 3]))
    return project


# ---------------------------------------------------------------------------
# Modèle
# ---------------------------------------------------------------------------


def test_tuile_et_planche():
    sheet = _sheet()
    assert len(sheet.tiles) == 8
    tile = sheet.tiles[3]
    assert (tile.x, tile.y, tile.w, tile.h) == (24, 0, 8, 8)
    image = sheet.tile_image(3)
    assert image.px.shape == (8, 8, 4)
    assert int(image.px[0, 0, 0]) == 20 + 3 * 25


def test_sprite_valide_et_non_valide():
    project = _project()
    assert len(project.validated_sprites()) == 1
    assert project.sprites[0].name == "pose_00"


def test_atlas_taille_calculee():
    """Six sprites de même taille : grille équilibrée, marges et espacement."""
    atlas = Atlas(gap=2, margin=4)
    sprites = [Sprite(id=k, name=f"p{k}", cols=3, rows=4, tile_w=24, tile_h=21)
               for k in range(6)]
    atlas.compute(sprites)
    assert len(atlas.entries) == 6
    assert atlas.width == 4 * 2 + 3 * 72 + 2 * 2
    assert atlas.height > 0
    # aucune entrée ne se chevauche
    boxes = [entry.rect for entry in atlas.entries]
    for index, (x, y, w, h) in enumerate(boxes):
        for ox, oy, ow, oh in boxes[index + 1:]:
            assert x + w <= ox or ox + ow <= x or y + h <= oy or oy + oh <= y


def test_recette_applique():
    recipe = Recipe(cols=2, rows=2, mapping=[3, 1, 0, 2])
    placements = recipe.apply([10, 11, 12, 13])
    assert placements == {0: 13, 1: 11, 2: 10, 3: 12}


# ---------------------------------------------------------------------------
# Persistance
# ---------------------------------------------------------------------------


def test_aller_retour_projet():
    project = _project()
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "essai.tileforge.json")
        project_io.save_project(project, path)
        assert os.path.exists(path)
        loaded = project_io.load_project(path)

    assert len(loaded.sheet.tiles) == 8
    assert loaded.sheet.image.px.shape == project.sheet.image.px.shape
    assert np.array_equal(loaded.sheet.image.px, project.sheet.image.px)
    assert len(loaded.sprites) == 1
    assert loaded.sprites[0].placements == {0: 0, 1: 1, 2: 2, 3: 3}
    assert loaded.game == "test"
    assert loaded.recipes and loaded.recipes[0].mapping == [0, 1, 2, 3]


def test_projet_sans_planche_embarquee_refuse_si_source_absente():
    """Sans image embarquée et sans fichier source, le chargement doit échouer
    clairement plutôt que de rendre un projet vide."""
    project = _project()
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "essai.json")
        project_io.save_project(project, path, embed_sheet=False)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        assert "image_png" not in data.get("sheet", {})
        try:
            project_io.load_project(path)
        except FileNotFoundError:
            return
    raise AssertionError("un projet sans planche aurait dû être refusé")


def test_export_csv_et_json():
    project = _project()
    with tempfile.TemporaryDirectory() as folder:
        csv_path = os.path.join(folder, "placements.csv")
        json_path = os.path.join(folder, "placements.json")
        txt_path = os.path.join(folder, "permutations.txt")
        count = project_io.export_placements_csv(project, csv_path)
        project_io.export_placements_json(project, json_path)
        project_io.export_permutations_txt(project, txt_path)

        with open(csv_path, encoding="utf-8") as handle:
            csv_text = handle.read()
        with open(json_path, encoding="utf-8") as handle:
            data = json.load(handle)
        with open(txt_path, encoding="utf-8") as handle:
            txt_text = handle.read()

    assert count >= 1
    assert "sprite" in csv_text.splitlines()[0]
    assert data["sprites"]
    assert txt_text.strip()


def test_png_aller_retour():
    sheet = _sheet()
    data = encode_png(sheet.image)
    from tileforge.core.image import decode_png
    decoded = decode_png(data)
    assert np.array_equal(decoded.px, sheet.image.px)
