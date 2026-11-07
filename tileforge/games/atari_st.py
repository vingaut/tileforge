"""Lecture d'images disquette Atari ST et extraction des banques de sprites.

Ce module reprend la chaîne de ``tools/extract_graphismes.py`` (image Pasti
``.stx`` → image brute ``.st`` → FAT12 → fichier), pour que TileForge puisse
ouvrir directement la disquette du jeu sans passer par un script externe.
"""

from __future__ import annotations

import struct

from ..core.formats import format_by_key
from ..core.image import Image
from ..core.model import Sheet

#: Banques de sprites de Barbarian (Palace, 1987), dans BARB.DAT.
BARBARIAN_BANKS = {
    1: {"offset": 0x33A52, "size": 0x07C08, "name": "banque 1 (personnages)"},
    2: {"offset": 0x3B65A, "size": 0x07C08, "name": "banque 2"},
}
BARBARIAN_TILE_FORMAT = "barbarian_st"
BARBARIAN_TILE_COUNT = 252


# ---------------------------------------------------------------------------
# 1. Image Pasti .stx → image brute .st
# ---------------------------------------------------------------------------


def parse_stx(data: bytes) -> list[dict]:
    if data[:4] != b"RSY\0":
        raise ValueError("ce n'est pas une image Pasti (.stx)")
    tracks_count = data[0x0A]
    pos = 0x10
    tracks = []
    for _ in range(tracks_count):
        start = pos
        block_size = struct.unpack_from("<I", data, pos)[0]
        fuzzy_size = struct.unpack_from("<I", data, pos + 4)[0]
        sector_count = struct.unpack_from("<H", data, pos + 8)[0]
        flags = struct.unpack_from("<H", data, pos + 10)[0]
        track_number = data[pos + 14]
        pos += 16
        track = {"track": track_number & 0x7F,
                 "side": 1 if track_number & 0x80 else 0,
                 "flags": flags, "sectors": []}
        blocks = []
        if sector_count:
            if flags & 0x01:
                for _ in range(sector_count):
                    blocks.append({
                        "data_offset": struct.unpack_from("<I", data, pos)[0],
                        "id_sector": data[pos + 10],
                        "id_size": data[pos + 11],
                        "fdc_status": data[pos + 14]})
                    pos += 16
            else:
                for i in range(sector_count):
                    blocks.append({"data_offset": i * 512, "id_sector": i + 1,
                                   "id_size": 2, "fdc_status": 0})
        track_data_start = pos + fuzzy_size
        for sb in blocks:
            size = 128 << (sb["id_size"] & 3)
            off = track_data_start + sb["data_offset"]
            sb["data"] = None if (sb["fdc_status"] & 0x10) else data[off:off + size]
        track["sectors"] = blocks
        tracks.append(track)
        pos = start + block_size if block_size else pos
    return tracks


def stx_to_st(path: str) -> bytes:
    with open(path, "rb") as handle:
        data = handle.read()
    tracks = parse_stx(data)
    boot = None
    for tr in tracks:
        if tr["track"] == 0 and tr["side"] == 0:
            for sb in tr["sectors"]:
                if sb["id_sector"] == 1 and sb["data"]:
                    boot = sb["data"]
    if boot is None:
        raise ValueError("secteur d'amorçage introuvable dans l'image .stx")
    spt = struct.unpack_from("<H", boot, 0x18)[0] or 9
    heads = struct.unpack_from("<H", boot, 0x1A)[0] or 1
    total = struct.unpack_from("<H", boot, 0x13)[0] or 80 * 2 * spt
    ntr = total // (spt * heads)
    img = bytearray(total * 512)
    for tr in tracks:
        t, side = tr["track"], tr["side"]
        for sb in tr["sectors"]:
            sec = sb["id_sector"]
            if not (0 <= t < ntr and 0 <= side < heads and 1 <= sec <= spt and sb["data"]):
                continue
            off = ((t * heads + side) * spt + (sec - 1)) * 512
            img[off:off + 512] = sb["data"][:512]
    return bytes(img)


# ---------------------------------------------------------------------------
# 2. FAT12 Atari ST
# ---------------------------------------------------------------------------


class Fat12:
    def __init__(self, img: bytes):
        b = img[:512]
        (self.bps, self.spc, self.reserved, self.nfats, self.root_entries,
         self.total, self.media, self.spf) = struct.unpack_from("<HBHBHHBH", b, 0x0B)
        self.root_start = (self.reserved + self.nfats * self.spf) * self.bps
        self.root_sectors = (self.root_entries * 32 + self.bps - 1) // self.bps
        self.data_start = self.root_start + self.root_sectors * self.bps
        self.fat = img[self.reserved * self.bps:
                       self.reserved * self.bps + self.spf * self.bps]
        self.img = img

    def next_cluster(self, c: int) -> int:
        off = c * 3 // 2
        v = self.fat[off] | (self.fat[off + 1] << 8)
        return (v >> 4) if (c & 1) else (v & 0xFFF)

    def read_chain(self, c: int, size: int | None = None) -> bytes:
        out = bytearray()
        seen = set()
        while 2 <= c < 0xFF8 and c not in seen:
            seen.add(c)
            off = self.data_start + (c - 2) * self.spc * self.bps
            out += self.img[off:off + self.spc * self.bps]
            c = self.next_cluster(c)
        return bytes(out[:size]) if size else bytes(out)

    def entries(self, raw: bytes) -> list[dict]:
        res = []
        for i in range(0, len(raw), 32):
            e = raw[i:i + 32]
            if len(e) < 32 or e[0] == 0:
                break
            if e[0] == 0xE5:
                continue
            name = e[0:8].decode("latin-1").rstrip()
            ext = e[8:11].decode("latin-1").rstrip()
            if not name and not ext:
                continue
            cluster, size = struct.unpack_from("<HI", e, 26)
            res.append({"name": name, "ext": ext, "attr": e[11],
                        "cluster": cluster, "size": size,
                        "full": name + ("." + ext if ext else "")})
        return res

    def root(self) -> list[dict]:
        return self.entries(self.img[self.root_start:
                                     self.root_start + self.root_entries * 32])

    def listdir(self, cluster: int) -> list[dict]:
        return self.entries(self.read_chain(cluster))

    def files(self) -> dict[str, bytes]:
        out = {}
        for e in self.root():
            if e["attr"] & 0x10:
                for s in self.listdir(e["cluster"]):
                    if not (s["attr"] & 0x10):
                        out[s["full"]] = self.read_chain(s["cluster"], s["size"])
            elif e["size"]:
                out[e["full"]] = self.read_chain(e["cluster"], e["size"])
        return out


def extract_from_disk_image(path: str) -> dict[str, bytes]:
    """Renvoie les fichiers d'une image .stx ou .st (dict nom → contenu)."""
    with open(path, "rb") as handle:
        raw = handle.read()
    if raw[:4] == b"RSY\0":
        raw = stx_to_st(path)
    return Fat12(raw).files()


# ---------------------------------------------------------------------------
# 3. Chargement de Barbarian
# ---------------------------------------------------------------------------


def load_barbarian(path: str, bank: int = 1, per_row: int = 16) -> Sheet:
    """Charge une banque de sprites de Barbarian ST.

    ``path`` peut être la disquette ``.stx``, l'image ``.st`` ou directement
    ``BARB.DAT``.
    """
    info = BARBARIAN_BANKS.get(bank, BARBARIAN_BANKS[1])
    with open(path, "rb") as f:
        head = f.read(4)
    if head == b"RSY\0":
        files = extract_from_disk_image(path)
        data = files.get("BARB.DAT")
        if data is None:
            raise ValueError("BARB.DAT introuvable dans l'image disquette")
        source = path
    else:
        with open(path, "rb") as f:
            data = f.read()
        source = path

    if len(data) < info["offset"] + info["size"]:
        raise ValueError(f"fichier trop court pour la {info['name']}")

    fmt = format_by_key(BARBARIAN_TILE_FORMAT)
    bank_data = data[info["offset"]:info["offset"] + info["size"]]
    tmp = _bank_to_bank(bank_data, fmt, per_row)
    sheet = Sheet(image=tmp.image, source=source, kind="raw",
                  info={"offset": info["offset"], "format": fmt.key,
                        "count": tmp.count, "per_row": per_row, "gap": tmp.gap,
                        "bank": bank, "game": "barbarian_st",
                        "palette": fmt.palette_key})
    for k, rect in enumerate(tmp.tile_rects()):
        sheet.add_tile(rect, storage_index=k, label=str(k))
    return sheet


def _bank_to_bank(bank_data: bytes, fmt, per_row: int):
    """Petite adaptation : :func:`load_raw_bank` lit un fichier, ici on a déjà
    les octets en mémoire."""

    import numpy as np

    from ..core.formats import RawBank

    bpt = fmt.real_bytes
    count = len(bank_data) // bpt
    gap = 1
    rows = max(1, (count + per_row - 1) // per_row)
    W = gap + per_row * (fmt.tile_w + gap)
    H = gap + rows * (fmt.tile_h + gap)
    pal = fmt.palette
    ncolors = max(len(pal), 1 << min(fmt.bpp, 8))
    palette_list = [pal.rgba(i) for i in range(ncolors)]
    pal_rgba = np.asarray(palette_list, dtype=np.uint8)
    px = np.zeros((H, W, 4), dtype=np.uint8)
    index_map = np.full((H, W), -1, dtype=np.int32)
    for k in range(count):
        idx = fmt.decode(bank_data[k * bpt:(k + 1) * bpt])
        gx, gy = k % per_row, k // per_row
        x0 = gap + gx * (fmt.tile_w + gap)
        y0 = gap + gy * (fmt.tile_h + gap)
        safe = np.clip(idx, 0, len(pal_rgba) - 1)
        px[y0:y0 + idx.shape[0], x0:x0 + idx.shape[1]] = pal_rgba[safe]
        index_map[y0:y0 + idx.shape[0], x0:x0 + idx.shape[1]] = safe
    px[index_map < 0] = 0
    return RawBank(image=Image(px, index_map, palette_list), count=count,
                   per_row=per_row, gap=gap, tile_w=fmt.tile_w,
                   tile_h=fmt.tile_h, format=fmt, source="")


def load_barbarian_screens(path: str) -> list[Image]:
    """Décode les 5 écrans RLE de BARB.DAT (bonus : aperçu du jeu)."""

    from ..core.palettes import ST_BARBARIAN

    with open(path, "rb") as f:
        data = f.read()
    screens = [(0x00000, 0x06560), (0x06560, 0x0C867), (0x0C867, 0x12DE0),
               (0x12DE0, 0x19353), (0x19353, 0x1F51B)]
    out = []
    for a, b in screens:
        raw = _rle_unpack(data[a:b], b - a)
        out.append(_st_screen(raw, ST_BARBARIAN))
    return out


def _rle_unpack(src: bytes, comp_len: int) -> bytes:
    out = bytearray()
    i = 0
    while i < comp_len:
        b = src[i]
        i += 1
        if b:
            out.append(b)
        else:
            out.append(0)
            if i >= comp_len:
                break
            n = src[i]
            i += 1
            out.extend(b"\x00" * n)
    return bytes(out)


def _st_screen(data: bytes, palette, w: int = 320, h: int = 200) -> Image:
    import numpy as np
    cols = np.array([palette[i][:3] for i in range(16)], dtype=np.uint8)
    rowbytes = 8 * (w // 16)
    buf = np.zeros((h, w, 4), dtype=np.uint8)
    for y in range(h):
        base = y * rowbytes
        for g in range(w // 16):
            w0 = (data[base + g * 8 + 0] << 8) | data[base + g * 8 + 1]
            w1 = (data[base + g * 8 + 2] << 8) | data[base + g * 8 + 3]
            w2 = (data[base + g * 8 + 4] << 8) | data[base + g * 8 + 5]
            w3 = (data[base + g * 8 + 6] << 8) | data[base + g * 8 + 7]
            for bit in range(16):
                v = (((w0 >> (15 - bit)) & 1) |
                     (((w1 >> (15 - bit)) & 1) << 1) |
                     (((w2 >> (15 - bit)) & 1) << 2) |
                     (((w3 >> (15 - bit)) & 1) << 3))
                buf[y, g * 16 + bit, :3] = cols[v]
                buf[y, g * 16 + bit, 3] = 255
    return Image(buf)
