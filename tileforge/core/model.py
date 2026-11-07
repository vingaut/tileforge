"""Modèle de données de TileForge.

Le modèle est indépendant de Qt : il décrit une planche, ses tuiles, la grille
d'assemblage, les sprites reconstruits, l'atlas de sortie, le journal des
mouvements et les recettes d'ordonnancement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime

from .image import Image


def now_stamp() -> str:
    """Horodatage ISO local, à la milliseconde."""
    return datetime.now().isoformat(timespec="milliseconds")


# ---------------------------------------------------------------------------
# Tuiles
# ---------------------------------------------------------------------------


@dataclass
class Tile:
    """Rectangle découpé dans la planche."""

    id: int
    rect: tuple[int, int, int, int]          # (x, y, largeur, hauteur)
    storage_index: int | None = None         # indice d'origine dans la banque
    label: str = ""
    locked: bool = False

    @property
    def x(self) -> int:
        return self.rect[0]

    @property
    def y(self) -> int:
        return self.rect[1]

    @property
    def w(self) -> int:
        return self.rect[2]

    @property
    def h(self) -> int:
        return self.rect[3]

    def moved(self, dx: int, dy: int) -> Tile:
        return replace(self, rect=(self.rect[0] + dx, self.rect[1] + dy,
                                   self.rect[2], self.rect[3]))

    def resized(self, x, y, w, h) -> Tile:
        return replace(self, rect=(x, y, max(1, w), max(1, h)))

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h

    def as_dict(self) -> dict:
        return {"id": self.id, "rect": list(self.rect),
                "storage_index": self.storage_index, "label": self.label}

    @classmethod
    def from_dict(cls, d: dict) -> Tile:
        return cls(id=int(d["id"]), rect=tuple(int(v) for v in d["rect"]),
                   storage_index=d.get("storage_index"), label=d.get("label", ""))


# ---------------------------------------------------------------------------
# Planche
# ---------------------------------------------------------------------------


@dataclass
class Sheet:
    """Image source et découpage en tuiles."""

    image: Image
    source: str = ""
    kind: str = "png"                        # "png" | "raw"
    info: dict = field(default_factory=dict)  # offset, format, compte, palette...
    tiles: list[Tile] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._cache: dict[tuple, Image] = {}
        self._next_id = 1 + max((t.id for t in self.tiles), default=-1)

    # -- tuiles -------------------------------------------------------------

    @property
    def next_id(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    def tile(self, tile_id: int) -> Tile | None:
        for t in self.tiles:
            if t.id == tile_id:
                return t
        return None

    def index_of(self, tile_id: int) -> int:
        for i, t in enumerate(self.tiles):
            if t.id == tile_id:
                return i
        return -1

    def add_tile(self, rect, storage_index=None, label="") -> Tile:
        t = Tile(id=self.next_id, rect=tuple(int(v) for v in rect),
                 storage_index=storage_index, label=label)
        self.tiles.append(t)
        return t

    def remove_tiles(self, ids) -> None:
        ids = set(ids)
        self.tiles = [t for t in self.tiles if t.id not in ids]
        for k in list(self._cache):
            if k[0] in ids:
                del self._cache[k]

    def invalidate(self, tile_id: int | None = None) -> None:
        if tile_id is None:
            self._cache.clear()
        else:
            for k in list(self._cache):
                if k[0] == tile_id:
                    del self._cache[k]

    def tile_image(self, tile_id: int, flip_h: bool = False, flip_v: bool = False,
                   quarter_turns: int = 0) -> Image:
        """Image d'une tuile (mise en cache par combinaison de transformations)."""
        key = (tile_id, flip_h, flip_v, quarter_turns % 4)
        img = self._cache.get(key)
        if img is not None:
            return img
        t = self.tile(tile_id)
        if t is None:
            img = Image.blank(1, 1)
        else:
            img = self.image.cropped(*t.rect)
            if quarter_turns:
                img = img.rotated_quarter(quarter_turns)
            if flip_h or flip_v:
                img = img.flipped(flip_h, flip_v)
        self._cache[key] = img
        return img

    def tiles_sorted(self) -> list[Tile]:
        """Tuiles triées par indice de stockage quand il existe, sinon par id."""
        if all(t.storage_index is not None for t in self.tiles):
            return sorted(self.tiles, key=lambda t: (t.storage_index, t.id))
        return sorted(self.tiles, key=lambda t: t.id)

    def by_storage_index(self) -> dict[int, Tile]:
        return {t.storage_index: t for t in self.tiles if t.storage_index is not None}

    # -- géométrie ----------------------------------------------------------

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size

    def tile_size_histogram(self) -> dict[tuple[int, int], int]:
        hist: dict[tuple[int, int], int] = {}
        for t in self.tiles:
            hist[(t.w, t.h)] = hist.get((t.w, t.h), 0) + 1
        return hist

    def dominant_tile_size(self) -> tuple[int, int]:
        hist = self.tile_size_histogram()
        if not hist:
            return (8, 8)
        return max(hist.items(), key=lambda kv: kv[1])[0]


# ---------------------------------------------------------------------------
# Grille d'assemblage
# ---------------------------------------------------------------------------


@dataclass
class Grid:
    """Grille d'assemblage : ``cols`` × ``rows`` cellules de ``tile_w`` × ``tile_h``."""

    cols: int = 3
    rows: int = 4
    tile_w: int = 24
    tile_h: int = 21

    @property
    def count(self) -> int:
        return self.cols * self.rows

    @property
    def width(self) -> int:
        return self.cols * self.tile_w

    @property
    def height(self) -> int:
        return self.rows * self.tile_h

    def xy(self, slot: int) -> tuple[int, int]:
        return (slot % self.cols, slot // self.cols)

    def slot(self, gx: int, gy: int) -> int:
        return gy * self.cols + gx

    def slot_at(self, x: float, y: float) -> int | None:
        if x < 0 or y < 0:
            return None
        gx, gy = int(x // self.tile_w), int(y // self.tile_h)
        if gx >= self.cols or gy >= self.rows:
            return None
        return gy * self.cols + gx

    def slots(self):
        return range(self.count)

    def as_dict(self) -> dict:
        return {"cols": self.cols, "rows": self.rows,
                "tile_w": self.tile_w, "tile_h": self.tile_h}

    @classmethod
    def from_dict(cls, d: dict) -> Grid:
        return cls(cols=int(d.get("cols", 3)), rows=int(d.get("rows", 4)),
                   tile_w=int(d.get("tile_w", 24)), tile_h=int(d.get("tile_h", 21)))

    def copy(self) -> Grid:
        return Grid(self.cols, self.rows, self.tile_w, self.tile_h)


# ---------------------------------------------------------------------------
# Sprites
# ---------------------------------------------------------------------------


@dataclass
class Sprite:
    """Assemblage validé : association case de grille → tuile."""

    id: int
    name: str
    cols: int
    rows: int
    tile_w: int
    tile_h: int
    placements: dict[int, int] = field(default_factory=dict)   # slot -> tile id
    transforms: dict[int, tuple[bool, bool, int]] = field(default_factory=dict)  # slot -> (flip_h, flip_v, rot)
    validated: bool = False
    created_at: str = field(default_factory=now_stamp)
    cost: float | None = None
    origin_tile: int | None = None

    # -- utilitaires --------------------------------------------------------

    @property
    def grid(self) -> Grid:
        return Grid(self.cols, self.rows, self.tile_w, self.tile_h)

    @property
    def width(self) -> int:
        return self.cols * self.tile_w

    @property
    def height(self) -> int:
        return self.rows * self.tile_h

    @property
    def tile_ids(self) -> list[int]:
        return list(self.placements.values())

    def is_complete(self) -> bool:
        return len(self.placements) == self.cols * self.rows

    def slot_of_tile(self, tile_id: int) -> int | None:
        for slot, tid in self.placements.items():
            if tid == tile_id:
                return slot
        return None

    def place(self, slot: int, tile_id: int) -> int | None:
        """Place une tuile ; renvoie l'id de la tuile éventuellement éjectée."""
        old_slot = self.slot_of_tile(tile_id)
        ejected = self.placements.get(slot)
        if old_slot is not None:
            del self.placements[old_slot]
        if ejected == tile_id:
            ejected = None
        self.placements[slot] = tile_id
        return ejected

    def remove(self, slot: int) -> int | None:
        return self.placements.pop(slot, None)

    def render(self, sheet: Sheet) -> Image:
        """Compose l'image du sprite."""
        img = Image.blank(self.width, self.height)
        for slot, tid in sorted(self.placements.items()):
            gx, gy = slot % self.cols, slot // self.cols
            fh, fv, rot = self.transforms.get(slot, (False, False, 0))
            tile_img = sheet.tile_image(tid, fh, fv, rot)
            img.paste(tile_img, gx * self.tile_w, gy * self.tile_h)
        return img

    def render_slot(self, sheet: Sheet, slot: int) -> Image | None:
        tid = self.placements.get(slot)
        if tid is None:
            return None
        fh, fv, rot = self.transforms.get(slot, (False, False, 0))
        return sheet.tile_image(tid, fh, fv, rot)

    def content_bbox(self, sheet: Sheet) -> tuple[int, int, int, int]:
        """Boîte englobante des pixels opaques (en pixels sprite)."""
        img = self.render(sheet)
        m = img.alpha_mask()
        if not m.any():
            return (0, 0, self.width, self.height)
        ys, xs = m.any(axis=1), m.any(axis=0)
        y0, y1 = int(ys.argmax()), int(len(ys) - 1 - ys[::-1].argmax())
        x0, x1 = int(xs.argmax()), int(len(xs) - 1 - xs[::-1].argmax())
        return (x0, y0, x1 - x0 + 1, y1 - y0 + 1)

    def signature(self) -> tuple:
        return tuple(sorted(self.placements.items()))

    def copy_as(self, new_id: int, name: str | None = None) -> Sprite:
        return Sprite(id=new_id, name=name or self.name, cols=self.cols,
                      rows=self.rows, tile_w=self.tile_w, tile_h=self.tile_h,
                      placements=dict(self.placements),
                      transforms=dict(self.transforms),
                      origin_tile=self.origin_tile)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "cols": self.cols, "rows": self.rows,
            "tile_w": self.tile_w, "tile_h": self.tile_h,
            "placements": [{"slot": s, "tile": t} for s, t in sorted(self.placements.items())],
            "transforms": {str(k): list(v) for k, v in self.transforms.items()},
            "validated": self.validated, "created_at": self.created_at,
            "cost": self.cost, "origin_tile": self.origin_tile,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Sprite:
        sp = cls(id=int(d["id"]), name=d.get("name", ""),
                 cols=int(d["cols"]), rows=int(d["rows"]),
                 tile_w=int(d["tile_w"]), tile_h=int(d["tile_h"]),
                 validated=bool(d.get("validated", False)),
                 created_at=d.get("created_at", now_stamp()),
                 cost=d.get("cost"), origin_tile=d.get("origin_tile"))
        for p in d.get("placements", []):
            sp.placements[int(p["slot"])] = int(p["tile"])
        for k, v in (d.get("transforms") or {}).items():
            sp.transforms[int(k)] = (bool(v[0]), bool(v[1]), int(v[2]) % 4)
        return sp


# ---------------------------------------------------------------------------
# Atlas
# ---------------------------------------------------------------------------


@dataclass
class AtlasEntry:
    sprite_id: int
    name: str
    rect: tuple[int, int, int, int]


@dataclass
class Atlas:
    """Planche de sortie regroupant les sprites validés."""

    gap: int = 2
    margin: int = 2
    mode: str = "auto"          # "auto" | "shelf" | "columns"
    width: int = 0
    height: int = 0
    columns_hint: int = 0
    entries: list[AtlasEntry] = field(default_factory=list)

    def compute(self, sprites: list[Sprite]) -> None:
        """Calcule la disposition et les dimensions de l'atlas."""
        self.entries = []
        if not sprites:
            self.width = self.height = 0
            return
        sizes = [(sp.width, sp.height) for sp in sprites]
        uniform = len(set(sizes)) == 1
        gap, margin = self.gap, self.margin

        if uniform or self.mode == "columns":
            w, h = sizes[0]
            n = len(sprites)
            cols = max(1, min(n, math.ceil(math.sqrt(n * h / w))))
            if self.mode == "columns":
                cols = max(1, min(n, self.columns_hint or cols))
            rows = math.ceil(n / cols)
            self.width = margin * 2 + cols * w + (cols - 1) * gap
            self.height = margin * 2 + rows * h + (rows - 1) * gap
            for k, sp in enumerate(sprites):
                gx, gy = k % cols, k // cols
                self.entries.append(AtlasEntry(
                    sp.id, sp.name,
                    (margin + gx * (w + gap), margin + gy * (h + gap), w, h)))
        else:
            self._shelf(sprites, sizes, gap, margin)

    def _shelf(self, sprites, sizes, gap, margin) -> None:
        total_area = sum(w * h for w, h in sizes)
        target = max(max(w for w, _ in sizes),
                     math.ceil(math.sqrt(total_area) * 1.15))
        x = y = margin
        row_h = 0
        used_w = margin
        for sp, (w, h) in zip(sprites, sizes, strict=False):
            if x + w + margin > target and x > margin:
                y += row_h + gap
                x = margin
                row_h = 0
            self.entries.append(AtlasEntry(sp.id, sp.name, (x, y, w, h)))
            x += w + gap
            used_w = max(used_w, x)
            row_h = max(row_h, h)
        self.width = used_w + margin - gap
        self.height = y + row_h + margin

    def render(self, sprites_by_id: dict[int, Sprite], sheet: Sheet,
               bg=(0, 0, 0, 0)) -> Image:
        img = Image.blank(max(1, self.width), max(1, self.height), bg)
        for e in self.entries:
            sp = sprites_by_id.get(e.sprite_id)
            if sp is None:
                continue
            img.paste(sp.render(sheet), e.rect[0], e.rect[1])
        return img

    def as_dict(self) -> dict:
        return {"gap": self.gap, "margin": self.margin, "mode": self.mode,
                "width": self.width, "height": self.height,
                "entries": [{"sprite": e.sprite_id, "name": e.name,
                             "rect": list(e.rect)} for e in self.entries]}

    @classmethod
    def from_dict(cls, d: dict) -> Atlas:
        a = cls(gap=int(d.get("gap", 2)), margin=int(d.get("margin", 2)),
                mode=d.get("mode", "auto"), width=int(d.get("width", 0)),
                height=int(d.get("height", 0)))
        a.entries = [AtlasEntry(int(e["sprite"]), e.get("name", ""),
                                tuple(int(v) for v in e["rect"]))
                     for e in d.get("entries", [])]
        return a


# ---------------------------------------------------------------------------
# Journal des mouvements
# ---------------------------------------------------------------------------


@dataclass
class MoveEvent:
    t: str
    type: str                 # place | move | swap | remove | rotate | mirror | validate | ...
    sprite: int
    tile: int | None = None
    frm: tuple[int, int] | None = None
    to: tuple[int, int] | None = None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = {"t": self.t, "type": self.type, "sprite": self.sprite,
             "tile": self.tile,
             "from": list(self.frm) if self.frm else None,
             "to": list(self.to) if self.to else None}
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, d: dict) -> MoveEvent:
        frm = tuple(d["from"]) if d.get("from") else None
        to = tuple(d["to"]) if d.get("to") else None
        return cls(t=d.get("t", now_stamp()), type=d.get("type", "move"),
                   sprite=int(d.get("sprite", 0)), tile=d.get("tile"),
                   frm=frm, to=to, extra=d.get("extra") or {})


class MoveLog:
    """Journal horodaté de toutes les actions sur les placements."""

    def __init__(self) -> None:
        self.events: list[MoveEvent] = []

    def add(self, type_: str, sprite: int, tile: int | None = None,
            frm=None, to=None, **extra) -> MoveEvent:
        ev = MoveEvent(now_stamp(), type_, sprite, tile, frm, to, extra)
        self.events.append(ev)
        return ev

    def __len__(self) -> int:
        return len(self.events)

    def clear(self) -> None:
        self.events.clear()

    def as_list(self) -> list[dict]:
        return [e.as_dict() for e in self.events]

    def load(self, data) -> None:
        self.events = [MoveEvent.from_dict(d) for d in (data or [])]

    def replay_placements(self, sprite_id: int) -> dict[int, int]:
        """Reconstitue les placements d'un sprite en rejouant ses événements."""
        placements: dict[int, int] = {}
        for ev in self.events:
            if ev.sprite != sprite_id or ev.tile is None:
                continue
            slot = (ev.to[1] * 1000 + ev.to[0]) if ev.to else None
            if ev.type in ("place", "move", "swap") and slot is not None:
                for s, t in list(placements.items()):
                    if t == ev.tile:
                        del placements[s]
                placements[slot] = ev.tile
            elif ev.type == "remove" and ev.frm is not None:
                placements.pop(ev.frm[1] * 1000 + ev.frm[0], None)
        return placements


# ---------------------------------------------------------------------------
# Recettes d'ordonnancement
# ---------------------------------------------------------------------------


@dataclass
class Recipe:
    """Correspondance observée entre case de grille et indice de stockage."""

    name: str = "recette"
    cols: int = 3
    rows: int = 4
    mapping: list[int] = field(default_factory=list)   # slot -> offset de stockage
    fit: dict = field(default_factory=dict)            # modèle ajusté
    base: int = 0

    @property
    def count(self) -> int:
        return self.cols * self.rows

    def apply(self, storage_indices: list[int], base: int = 0) -> dict[int, int]:
        """Renvoie slot -> indice de stockage pour un groupe donné."""
        out: dict[int, int] = {}
        n = min(self.count, len(self.mapping))
        for slot in range(n):
            off = self.mapping[slot]
            if off < 0:
                continue
            idx = base + off
            if 0 <= idx < len(storage_indices):
                out[slot] = storage_indices[idx]
        return out

    def as_dict(self) -> dict:
        return {"name": self.name, "cols": self.cols, "rows": self.rows,
                "mapping": list(self.mapping), "fit": self.fit, "base": self.base}

    @classmethod
    def from_dict(cls, d: dict) -> Recipe:
        return cls(name=d.get("name", "recette"), cols=int(d.get("cols", 3)),
                   rows=int(d.get("rows", 4)),
                   mapping=[int(v) for v in d.get("mapping", [])],
                   fit=d.get("fit", {}), base=int(d.get("base", 0)))


# ---------------------------------------------------------------------------
# Projet
# ---------------------------------------------------------------------------


@dataclass
class Project:
    """Document complet : planche, grille, sprites, atlas, journal, recettes."""

    sheet: Sheet | None = None
    grid: Grid = field(default_factory=Grid)
    sprites: list[Sprite] = field(default_factory=list)
    current: Sprite = field(default_factory=lambda: Sprite(0, "pose_00", 3, 4, 24, 21))
    atlas: Atlas = field(default_factory=Atlas)
    moves: MoveLog = field(default_factory=MoveLog)
    recipes: list[Recipe] = field(default_factory=list)
    game: str = ""
    system: dict = field(default_factory=dict)
    detection: dict = field(default_factory=dict)
    resolution: dict = field(default_factory=dict)
    path: str | None = None
    dirty: bool = False
    next_sprite_id: int = 1

    # -- gestion des sprites ------------------------------------------------

    def new_sprite(self, name: str | None = None) -> Sprite:
        self.next_sprite_id += 1
        index = len(self.validated_sprites())
        sp = Sprite(id=self.next_sprite_id, name=name or f"pose_{index:02d}",
                    cols=self.grid.cols, rows=self.grid.rows,
                    tile_w=self.grid.tile_w, tile_h=self.grid.tile_h)
        self.current = sp
        return sp

    def validate_current(self, name: str | None = None) -> Sprite:
        sp = self.current
        if name:
            sp.name = name
        sp.validated = True
        sp.created_at = now_stamp()
        self.sprites = [s for s in self.sprites if s.id != sp.id]
        self.sprites.append(sp)
        self.atlas.compute(self.validated_sprites())
        self.moves.add("validate", sp.id, extra={"name": sp.name})
        self.dirty = True
        return sp

    def validated_sprites(self) -> list[Sprite]:
        return [s for s in self.sprites if s.validated]

    def sprite_by_id(self, sid: int) -> Sprite | None:
        for s in self.sprites:
            if s.id == sid:
                return s
        return None

    def delete_sprite(self, sid: int) -> None:
        self.sprites = [s for s in self.sprites if s.id != sid]
        self.atlas.compute(self.validated_sprites())
        self.dirty = True

    # -- état ---------------------------------------------------------------

    def snapshot(self) -> dict:
        """Instantané minimal pour l'undo/redo."""
        return {
            "tiles": [(t.id, t.rect, t.storage_index, t.label) for t in (self.sheet.tiles if self.sheet else [])],
            "grid": (self.grid.cols, self.grid.rows, self.grid.tile_w, self.grid.tile_h),
            "current": (self.current.id, self.current.name, dict(self.current.placements),
                        dict(self.current.transforms)),
            "sprites": [(s.id, s.name, s.validated, dict(s.placements), dict(s.transforms))
                        for s in self.sprites],
        }

    def restore(self, snap: dict) -> None:
        if self.sheet is not None:
            self.sheet.tiles = [Tile(id=tid, rect=rect, storage_index=si, label=lab)
                                for tid, rect, si, lab in snap["tiles"]]
            self.sheet.invalidate()
            self.sheet._next_id = 1 + max((t.id for t in self.sheet.tiles), default=-1)
        c, r, tw, th = snap["grid"]
        self.grid = Grid(c, r, tw, th)
        cid, cname, cplace, ctrans = snap["current"]
        self.current = Sprite(cid, cname, c, r, tw, th,
                              placements=dict(cplace), transforms=dict(ctrans))
        self.sprites = []
        for sid, name, validated, place, trans in snap["sprites"]:
            self.sprites.append(Sprite(sid, name, c, r, tw, th,
                                       placements=dict(place), transforms=dict(trans),
                                       validated=validated))

    # -- sérialisation ------------------------------------------------------

    def as_dict(self) -> dict:
        d = {
            "format": "tileforge/2",
            "game": self.game,
            "system": self.system,
            "resolution": self.resolution,
            "detection": self.detection,
            "grid": self.grid.as_dict(),
            "sprites": [s.as_dict() for s in self.sprites],
            "current": self.current.as_dict(),
            "atlas": self.atlas.as_dict(),
            "moves": self.moves.as_list(),
            "recipes": [r.as_dict() for r in self.recipes],
            "next_sprite_id": self.next_sprite_id,
        }
        if self.sheet is not None:
            d["sheet"] = {
                "source": self.sheet.source,
                "kind": self.sheet.kind,
                "info": self.sheet.info,
                "width": self.sheet.image.w,
                "height": self.sheet.image.h,
                "tiles": [t.as_dict() for t in self.sheet.tiles],
            }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Project:
        p = cls()
        p.game = d.get("game", "")
        p.system = d.get("system", {}) or {}
        p.resolution = d.get("resolution", {}) or {}
        p.detection = d.get("detection", {}) or {}
        p.grid = Grid.from_dict(d.get("grid", {}))
        p.sprites = [Sprite.from_dict(s) for s in d.get("sprites", [])]
        p.current = Sprite.from_dict(d["current"]) if d.get("current") else \
            Sprite(0, "pose_00", p.grid.cols, p.grid.rows, p.grid.tile_w, p.grid.tile_h)
        p.atlas = Atlas.from_dict(d.get("atlas", {}))
        p.moves.load(d.get("moves"))
        p.recipes = [Recipe.from_dict(r) for r in d.get("recipes", [])]
        p.next_sprite_id = int(d.get("next_sprite_id", 1))
        return p
