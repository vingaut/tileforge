"""Images RGBA en mémoire, lecture et écriture PNG.

Ce module ne dépend pas de Qt : le cœur de TileForge doit rester utilisable
en ligne de commande (tests, scripts d'extraction).

Représentation : ``Image.px`` est un tableau numpy ``(h, w, 4)`` de uint8
(rouge, vert, bleu, alpha).  Un pixel d'alpha 0 est transparent.

Deux modes de stockage cohabitent :

* image « vraie couleur » : seule ``px`` est renseignée ;
* image « indexée » (cas des banques de ROM) : ``index`` donne l'indice de
  palette de chaque pixel et ``palette`` la table des couleurs.  Les fonctions
  de coût d'assemblage s'appuient sur ces indices, qui sont la vérité du jeu
  d'origine (deux pixels de même couleur ont le même indice).

Pillow est utilisé s'il est disponible (rapide et tolérant), sinon un
décodeur PNG en numpy prend le relais.
"""

from __future__ import annotations

import os
import struct
import zlib

import numpy as np

try:  # Pillow est optionnel
    from PIL import Image as _PILImage

    _HAS_PIL = True
except Exception:  # pragma: no cover - dépend de l'installation
    _PILImage = None
    _HAS_PIL = False


# ---------------------------------------------------------------------------
# Classe Image
# ---------------------------------------------------------------------------


class Image:
    """Image RGBA 8 bits, éventuellement indexée.

    Attributes
    ----------
    px : numpy.ndarray
        Tableau ``(h, w, 4)`` de uint8.
    index : numpy.ndarray | None
        Tableau ``(h, w)`` d'entiers : indice de palette de chaque pixel.
    palette : list[tuple[int, int, int, int]] | None
        Table des couleurs associée à ``index``.
    """

    __slots__ = ("px", "index", "palette")

    def __init__(self, px, index=None, palette=None):
        px = np.ascontiguousarray(px, dtype=np.uint8)
        if px.ndim != 3 or px.shape[2] != 4:
            raise ValueError("px doit être de forme (h, w, 4)")
        self.px = px
        if index is not None:
            index = np.ascontiguousarray(index, dtype=np.int32)
            if index.shape != px.shape[:2]:
                raise ValueError("index et px n'ont pas la même taille")
        self.index = index
        self.palette = list(palette) if palette is not None else None

    # -- constructeurs ------------------------------------------------------

    @classmethod
    def blank(cls, w: int, h: int, color=(0, 0, 0, 0)) -> Image:
        px = np.empty((h, w, 4), dtype=np.uint8)
        px[:, :] = np.asarray(color, dtype=np.uint8)
        return cls(px)

    @classmethod
    def from_rgb(cls, rgb, alpha=None) -> Image:
        """Construit une image depuis un tableau (h, w, 3) et un alpha optionnel."""
        rgb = np.asarray(rgb, dtype=np.uint8)
        px = np.empty((rgb.shape[0], rgb.shape[1], 4), dtype=np.uint8)
        px[..., :3] = rgb
        px[..., 3] = 255 if alpha is None else np.asarray(alpha, dtype=np.uint8)
        return cls(px)

    @classmethod
    def from_indexed(cls, index, palette) -> Image:
        """Construit une image depuis une grille d'indices et une palette."""
        index = np.ascontiguousarray(index, dtype=np.int32)
        pal = np.zeros((max(len(palette), int(index.max(initial=0)) + 1), 4), dtype=np.uint8)
        for i, c in enumerate(palette):
            pal[i] = _rgba(c)
        safe = np.clip(index, 0, len(pal) - 1)
        return cls(pal[safe], index=index, palette=list(palette))

    def copy(self) -> Image:
        return Image(self.px.copy(),
                     None if self.index is None else self.index.copy(),
                     None if self.palette is None else list(self.palette))

    # -- géométrie ----------------------------------------------------------

    @property
    def w(self) -> int:
        return int(self.px.shape[1])

    @property
    def h(self) -> int:
        return int(self.px.shape[0])

    @property
    def size(self) -> tuple[int, int]:
        return (self.w, self.h)

    def cropped(self, x: int, y: int, w: int, h: int) -> Image:
        """Découpe un rectangle ; les zones hors image deviennent transparentes."""
        out = np.zeros((h, w, 4), dtype=np.uint8)
        idx = None
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 > x0 and y1 > y0:
            out[y0 - y:y1 - y, x0 - x:x1 - x] = self.px[y0:y1, x0:x1]
            if self.index is not None:
                idx = np.zeros((h, w), dtype=np.int32)
                idx[y0 - y:y1 - y, x0 - x:x1 - x] = self.index[y0:y1, x0:x1]
        return Image(out, idx, self.palette)

    def paste(self, src: Image, x: int, y: int, skip_transparent: bool = True) -> None:
        """Copie ``src`` dans l'image à la position (x, y), sans déborder."""
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + src.w), min(self.h, y + src.h)
        if x1 <= x0 or y1 <= y0:
            return
        sx, sy = x0 - x, y0 - y
        block = src.px[sy:sy + (y1 - y0), sx:sx + (x1 - x0)]
        dst = self.px[y0:y1, x0:x1]
        if skip_transparent:
            m = block[..., 3] > 0
            dst[m] = block[m]
        else:
            dst[:] = block
        if self.index is not None and src.index is not None:
            self.index[y0:y1, x0:x1][m if skip_transparent else ...] = \
                src.index[sy:sy + (y1 - y0), sx:sx + (x1 - x0)][m if skip_transparent else ...]

    def flipped(self, horizontal: bool = False, vertical: bool = False) -> Image:
        sl = (slice(None, None, -1) if vertical else slice(None),
              slice(None, None, -1) if horizontal else slice(None))
        return Image(self.px[sl].copy(),
                     None if self.index is None else self.index[sl].copy(),
                     self.palette)

    def rotated_quarter(self, turns: int = 1) -> Image:
        turns %= 4
        if not turns:
            return self.copy()
        return Image(np.ascontiguousarray(np.rot90(self.px, turns)),
                     None if self.index is None else np.ascontiguousarray(np.rot90(self.index, turns)),
                     self.palette)

    def scaled(self, factor: int) -> Image:
        """Agrandissement au plus proche voisin (facteur entier >= 1)."""
        factor = max(1, int(factor))
        if factor == 1:
            return self.copy()
        px = np.repeat(np.repeat(self.px, factor, axis=0), factor, axis=1)
        idx = None
        if self.index is not None:
            idx = np.repeat(np.repeat(self.index, factor, axis=0), factor, axis=1)
        return Image(px, idx, self.palette)

    # -- couleurs -----------------------------------------------------------

    def alpha_mask(self) -> np.ndarray:
        """Masque booléen (h, w) des pixels opaques."""
        return self.px[..., 3] > 0

    def color_count(self) -> int:
        """Nombre de couleurs distinctes parmi les pixels opaques."""
        m = self.alpha_mask()
        if not m.any():
            return 0
        rgb = self.px[m][:, :3]
        return int(np.unique(rgb.view([('r', 'u1'), ('g', 'u1'), ('b', 'u1')])).size)

    def make_color_transparent(self, rgb, tolerance: int = 0) -> Image:
        """Rend transparents les pixels proches d'une couleur donnée."""
        out = self.copy()
        rgb = np.asarray(rgb[:3], dtype=np.int16)
        d = np.abs(out.px[..., :3].astype(np.int16) - rgb).max(axis=2)
        out.px[d <= tolerance, 3] = 0
        return out

    def auto_transparent(self, tolerance: int = 0) -> Image:
        """Rend transparente la couleur de fond détectée sur le bord de l'image."""
        bg = detect_background(self)
        return self.make_color_transparent(bg, tolerance)

    def to_indexed(self) -> Image:
        """Convertit une image vraie couleur en image indexée (couleurs triées)."""
        if self.index is not None and self.palette is not None:
            return self
        m = self.alpha_mask()
        rgb = self.px[m][:, :3]
        if rgb.size == 0:
            return Image(self.px.copy(), np.zeros((self.h, self.w), np.int32), [(0, 0, 0, 0)])
        uniq = np.unique(rgb.view([('r', 'u1'), ('g', 'u1'), ('b', 'u1')]))
        uniq = np.sort(uniq)
        table = uniq.view(np.uint8).reshape(-1, 3)
        palette = [(0, 0, 0, 0)] + [tuple(int(v) for v in c) + (255,) for c in table]
        index = np.zeros((self.h, self.w), dtype=np.int32)
        view = self.px[..., :3].view([('r', 'u1'), ('g', 'u1'), ('b', 'u1')]).reshape(-1)
        pos = np.searchsorted(uniq, view)
        pos = np.clip(pos, 0, len(uniq) - 1)
        index = (pos.reshape(self.h, self.w) + 1)
        index[~m] = 0
        return Image(self.px.copy(), index, palette)

    def palette_of(self, index_value: int):
        if self.palette and 0 <= index_value < len(self.palette):
            return self.palette[index_value]
        return (0, 0, 0, 255)

    # -- conversion ---------------------------------------------------------

    def to_rgba_array(self) -> np.ndarray:
        return self.px

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        mode = "indexed" if self.index is not None else "rgba"
        return f"<Image {self.w}x{self.h} {mode}>"


def _rgba(color) -> tuple[int, int, int, int]:
    if len(color) == 3:
        return (int(color[0]), int(color[1]), int(color[2]), 255)
    return (int(color[0]), int(color[1]), int(color[2]), int(color[3]))


# ---------------------------------------------------------------------------
# Détection de la couleur de fond
# ---------------------------------------------------------------------------


def detect_background(img: Image) -> tuple[int, int, int]:
    """Couleur de fond probable : couleur la plus fréquente sur le bord."""
    border = np.concatenate([
        img.px[0, :, :3], img.px[-1, :, :3],
        img.px[:, 0, :3], img.px[:, -1, :3],
    ])
    if border.size == 0:
        return (0, 0, 0)
    packed = border.view([('r', 'u1'), ('g', 'u1'), ('b', 'u1')])
    uniq, counts = np.unique(packed, return_counts=True)
    best = uniq[int(np.argmax(counts))]
    return (int(best['r']), int(best['g']), int(best['b']))


def image_has_alpha(img: Image) -> bool:
    return bool((img.px[..., 3] < 255).any())


# ---------------------------------------------------------------------------
# Lecture / écriture PNG
# ---------------------------------------------------------------------------


def load_image(path: str) -> Image:
    """Charge un PNG (ou tout format géré par Pillow) en Image RGBA."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".png":
        if _HAS_PIL:
            return _load_with_pillow(path)
        return _load_png_builtin(path)
    if _HAS_PIL:
        return _load_with_pillow(path)
    raise ValueError(f"format non géré sans Pillow : {ext}")


def save_image(path: str, img: Image) -> None:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".png":
        if _HAS_PIL:
            _save_with_pillow(path, img)
        else:
            _save_png_builtin(path, img)
        return
    if _HAS_PIL:
        _save_with_pillow(path, img)
        return
    raise ValueError(f"format non géré sans Pillow : {ext}")


def _load_with_pillow(path: str) -> Image:
    im = _PILImage.open(path)
    im.load()
    if im.mode == "P":
        pal = im.getpalette() or []
        palette = [(pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2], 255)
                   for i in range(len(pal) // 3)]
        alpha = im.convert("RGBA")
        arr = np.array(alpha, dtype=np.uint8)
        index = np.array(im, dtype=np.int32)
        for i in range(min(len(palette), 256)):
            palette[i] = (palette[i][0], palette[i][1], palette[i][2], 255)
        return Image(arr, index, palette)
    if im.mode == "RGBA":
        arr = np.array(im, dtype=np.uint8)
        return Image(arr)
    if im.mode == "LA":
        arr = np.array(im.convert("RGBA"), dtype=np.uint8)
        return Image(arr)
    if im.mode in ("L", "I;16", "I", "F"):
        arr = np.array(im.convert("RGBA"), dtype=np.uint8)
        return Image(arr)
    arr = np.array(im.convert("RGBA"), dtype=np.uint8)
    return Image(arr)


def _save_with_pillow(path: str, img: Image) -> None:
    _PILImage.fromarray(np.ascontiguousarray(img.px), "RGBA").save(path)


# -- décodeur PNG autonome --------------------------------------------------

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _load_png_builtin(path: str) -> Image:
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:8] != _PNG_SIG:
        raise ValueError("ce fichier n'est pas un PNG")
    pos = 8
    width = height = bit_depth = color_type = interlace = 0
    idat = bytearray()
    plte = b""
    trns = b""
    while pos < len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif tag == b"PLTE":
            plte = chunk
        elif tag == b"tRNS":
            trns = chunk
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
    if interlace:
        raise ValueError("PNG entrelacé (Adam7) non géré par le décodeur interne ; "
                         "installez Pillow")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    raw = zlib.decompress(bytes(idat))
    bpp = max(1, channels * bit_depth // 8)
    stride = (width * channels * bit_depth + 7) // 8
    rows = _unfilter(raw, width, height, stride, bpp)
    arr = _expand_to_rgba(rows, width, height, bit_depth, color_type, plte, trns)
    return Image(arr)


def _unfilter(raw: bytes, width: int, height: int, stride: int, bpp: int) -> np.ndarray:
    """Défiltre les scanlines PNG (filtres 0 à 4)."""
    buf = np.frombuffer(raw, dtype=np.uint8)
    if buf.size < height * (stride + 1):
        raise ValueError("données PNG tronquées")
    buf = buf[:height * (stride + 1)].reshape(height, stride + 1)
    out = np.zeros((height, stride), dtype=np.uint8)
    prev = np.zeros(stride, dtype=np.uint8)
    for y in range(height):
        ftype = int(buf[y, 0])
        line = buf[y, 1:]
        if ftype == 0:
            cur = line.copy()
        elif ftype == 1:
            cur = _unsub(line, bpp)
        elif ftype == 2:
            cur = line + prev
        elif ftype == 3:
            cur = _unaverage(line, prev, bpp)
        elif ftype == 4:
            cur = _unpaeth(line, prev, bpp)
        else:
            raise ValueError(f"filtre PNG inconnu : {ftype}")
        out[y] = cur
        prev = cur
    return out


def _unsub(line: np.ndarray, bpp: int) -> np.ndarray:
    out = line.copy()
    if bpp == 1:
        return np.cumsum(out, dtype=np.uint8)
    lanes = out.reshape(-1, bpp)
    return np.cumsum(lanes, axis=0, dtype=np.uint8).reshape(-1)


def _unaverage(line: np.ndarray, prev: np.ndarray, bpp: int) -> np.ndarray:
    out = np.zeros(len(line), dtype=np.uint8)
    for i in range(len(line)):
        left = int(out[i - bpp]) if i >= bpp else 0
        out[i] = (int(line[i]) + ((left + int(prev[i])) >> 1)) & 0xFF
    return out


def _unpaeth(line: np.ndarray, prev: np.ndarray, bpp: int) -> np.ndarray:
    out = np.zeros(len(line), dtype=np.uint8)
    for i in range(len(line)):
        a = int(out[i - bpp]) if i >= bpp else 0
        b = int(prev[i])
        c = int(prev[i - bpp]) if i >= bpp else 0
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            pred = a
        elif pb <= pc:
            pred = b
        else:
            pred = c
        out[i] = (int(line[i]) + pred) & 0xFF
    return out


def _expand_to_rgba(rows, width, height, bit_depth, color_type, plte, trns) -> np.ndarray:
    if bit_depth == 16:
        rows = rows.reshape(height, width, -1)[:, :, ::2]
        bit_depth = 8
    if bit_depth < 8:
        # déplie les bits de poids fort
        per_byte = 8 // bit_depth
        bits = np.unpackbits(rows.reshape(-1, 1), axis=1)
        bits = bits.reshape(height, -1, per_byte, bit_depth)
        weights = (1 << np.arange(bit_depth - 1, -1, -1)).astype(np.uint8)
        vals = (bits * weights).sum(axis=3).astype(np.uint8)
        rows = vals[:, :width]
        bit_depth = 8
        if color_type == 3:
            idx = rows.astype(np.int32)
            return _palette_to_rgba(idx, plte, trns)
        channels = 1
    else:
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
        rows = rows.reshape(height, width, channels) if channels > 1 else rows.reshape(height, width, 1)

    if color_type == 3:
        return _palette_to_rgba(rows[:, :, 0].astype(np.int32), plte, trns)
    out = np.empty((height, width, 4), dtype=np.uint8)
    if color_type == 0:
        out[..., 0] = out[..., 1] = out[..., 2] = rows[:, :, 0]
        out[..., 3] = 255
    elif color_type == 4:
        out[..., 0] = out[..., 1] = out[..., 2] = rows[:, :, 0]
        out[..., 3] = rows[:, :, 1]
    elif color_type == 2:
        out[..., :3] = rows[:, :, :3]
        out[..., 3] = 255
    else:  # 6
        out[:] = rows[:, :, :4]
    return out


def _palette_to_rgba(index: np.ndarray, plte: bytes, trns: bytes) -> np.ndarray:
    n = len(plte) // 3
    pal = np.zeros((max(n, 256), 4), dtype=np.uint8)
    for i in range(n):
        pal[i, 0:3] = plte[i * 3:i * 3 + 3]
        pal[i, 3] = 255
    for i, a in enumerate(trns):
        pal[i, 3] = a
    return pal[np.clip(index, 0, len(pal) - 1)]


def _save_png_builtin(path: str, img: Image) -> None:
    h, w = img.h, img.w
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += img.px[y].tobytes()

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = _PNG_SIG
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


# ---------------------------------------------------------------------------
# Fabriques d'images utilitaires
# ---------------------------------------------------------------------------


def checkerboard(w: int, h: int, cell: int = 8,
                 c1=(48, 48, 54, 255), c2=(64, 64, 72, 255)) -> Image:
    """Damier de fond, pour visualiser la transparence."""
    yy, xx = np.mgrid[0:h, 0:w]
    m = ((xx // cell) + (yy // cell)) % 2 == 0
    px = np.empty((h, w, 4), dtype=np.uint8)
    px[m] = np.asarray(c1, dtype=np.uint8)
    px[~m] = np.asarray(c2, dtype=np.uint8)
    return Image(px)


def contact_sheet(images, cols: int = 8, gap: int = 2,
                  bg=(32, 32, 38, 255), labels=None) -> Image:
    """Assemble une liste d'images de tailles variables en planche."""
    if not images:
        return Image.blank(1, 1)
    n = len(images)
    cols = max(1, min(cols, n))
    rows = (n + cols - 1) // cols
    cell_w = max(i.w for i in images)
    cell_h = max(i.h for i in images)
    W = cols * (cell_w + gap) + gap
    H = rows * (cell_h + gap) + gap
    out = Image.blank(W, H, bg)
    for k, im in enumerate(images):
        cx = gap + (k % cols) * (cell_w + gap)
        cy = gap + (k // cols) * (cell_h + gap)
        out.paste(im, cx, cy)
    return out


# ---------------------------------------------------------------------------
# Encodage / décodage PNG en mémoire
# ---------------------------------------------------------------------------


def encode_png(img: Image) -> bytes:
    """Encode une image en PNG (octets)."""
    if _HAS_PIL:
        import io
        buf = io.BytesIO()
        _PILImage.fromarray(np.ascontiguousarray(img.px), "RGBA").save(buf, format="PNG")
        return buf.getvalue()
    import os as _os
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".png")
    _os.close(fd)
    try:
        _save_png_builtin(tmp, img)
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        _os.unlink(tmp)


def decode_png(data: bytes) -> Image:
    """Décode un PNG depuis des octets."""
    if _HAS_PIL:
        import io
        im = _PILImage.open(io.BytesIO(data))
        im.load()
        return _load_with_pillow_object(im)
    import os as _os
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".png")
    _os.close(fd)
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        return _load_png_builtin(tmp)
    finally:
        _os.unlink(tmp)


def _load_with_pillow_object(im) -> Image:
    if im.mode == "P":
        arr = np.array(im.convert("RGBA"), dtype=np.uint8)
        index = np.array(im, dtype=np.int32)
        pal = im.getpalette() or []
        palette = [(pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2], 255)
                   for i in range(len(pal) // 3)]
        return Image(arr, index, palette)
    return Image(np.array(im.convert("RGBA"), dtype=np.uint8))
