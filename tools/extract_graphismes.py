#!/usr/bin/env python3
"""Extraction des graphismes de Barbarian (Palace, 1987) - Atari ST.

Chaine complete, sans dependance externe (uniquement la bibliotheque standard) :

  1. Decodage de l'image disquette Pasti  .stx  ->  image brute .st
  2. Lecture du systeme de fichiers FAT12 (Atari ST) et extraction des fichiers
  3. Decompression RLE des ecrans contenus dans BARB.DAT
  4. Rendu des ecrans, de la police et des sprites en PNG

Format du fichier BARB.DAT (275 042 octets) :

  0x00000 - 0x06560  ecran 1 (RLE)
  0x06560 - 0x0C867  ecran 2 (RLE)
  0x0C867 - 0x12DE0  ecran 3 (RLE)
  0x12DE0 - 0x19353  ecran 4 (RLE)
  0x19353 - 0x1F51B  ecran 5 (RLE)
  0x1F51B - 0x1F81C  police 8x8, 96 caracteres (ASCII 0x20-0x7F), brute
  0x1F81C - 0x33A52  26 blocs (donnees audio, non graphiques)
  0x33A52 - 0x3B65A  banque de 252 sprites de 126 octets
  0x3B65A - 0x43262  banque de 252 sprites de 126 octets

RLE : un octet non nul est copie tel quel ; un octet 0x00 est suivi d'un
compteur N et produit 1 + N octets a zero.

Ecran ST : 320x200, 4 plans imbriques, 160 octets par ligne, 8 octets par
groupe de 16 pixels (un mot par plan).

Sprite : 24x21 pixels, 2 plans, 6 octets par ligne (3 colonnes de 8 pixels),
soit 126 octets. Les plans 2 et 3 de l'ecran recoivent le OU des deux plans,
ce qui donne les couleurs 12, 13, 14 et 15 de la palette.
"""

import os
import struct
import sys
import zlib

# --------------------------------------------------------------------------
# Ecriture PNG minimaliste (RGBA 8 bits, filtre 0)
# --------------------------------------------------------------------------

def write_png(path, width, height, pixels):
    """pixels : octets RGBA, width*height*4."""
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        raw += pixels[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    png += chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(png)


# --------------------------------------------------------------------------
# 1. STX -> ST
# --------------------------------------------------------------------------

def parse_stx(path):
    with open(path, 'rb') as handle:
        data = handle.read()
    if data[:4] != b'RSY\0':
        raise ValueError('ce n\'est pas une image Pasti .stx')
    tracks_count = data[0x0A]
    pos = 0x10
    tracks = []
    for _ in range(tracks_count):
        start = pos
        block_size = struct.unpack_from('<I', data, pos)[0]
        fuzzy_size = struct.unpack_from('<I', data, pos + 4)[0]
        sector_count = struct.unpack_from('<H', data, pos + 8)[0]
        flags = struct.unpack_from('<H', data, pos + 10)[0]
        track_number = data[pos + 14]
        pos += 16
        track = {'track': track_number & 0x7F,
                 'side': 1 if track_number & 0x80 else 0,
                 'flags': flags, 'sectors': []}
        blocks = []
        if sector_count:
            if flags & 0x01:
                for _ in range(sector_count):
                    blocks.append({
                        'data_offset': struct.unpack_from('<I', data, pos)[0],
                        'id_sector': data[pos + 10],
                        'id_size': data[pos + 11],
                        'fdc_status': data[pos + 14]})
                    pos += 16
            else:
                for i in range(sector_count):
                    blocks.append({'data_offset': i * 512, 'id_sector': i + 1,
                                   'id_size': 2, 'fdc_status': 0})
        track_data_start = pos + fuzzy_size
        for sb in blocks:
            size = 128 << (sb['id_size'] & 3)
            off = track_data_start + sb['data_offset']
            sb['data'] = None if (sb['fdc_status'] & 0x10) else data[off:off + size]
        track['sectors'] = blocks
        tracks.append(track)
        pos = start + block_size if block_size else pos
    return tracks


def stx_to_st(stx_path):
    tracks = parse_stx(stx_path)
    boot = None
    for tr in tracks:
        if tr['track'] == 0 and tr['side'] == 0:
            for sb in tr['sectors']:
                if sb['id_sector'] == 1 and sb['data']:
                    boot = sb['data']
    spt = struct.unpack_from('<H', boot, 0x18)[0] or 9
    heads = struct.unpack_from('<H', boot, 0x1A)[0] or 1
    total = struct.unpack_from('<H', boot, 0x13)[0] or 80 * 2 * spt
    ntr = total // (spt * heads)
    img = bytearray(total * 512)
    for tr in tracks:
        t, side = tr['track'], tr['side']
        for sb in tr['sectors']:
            sec = sb['id_sector']
            if not (0 <= t < ntr and 0 <= side < heads and 1 <= sec <= spt and sb['data']):
                continue
            off = ((t * heads + side) * spt + (sec - 1)) * 512
            img[off:off + 512] = sb['data'][:512]
    return bytes(img)


# --------------------------------------------------------------------------
# 2. FAT12 Atari ST
# --------------------------------------------------------------------------

class Fat12:
    def __init__(self, img):
        b = img[:512]
        (self.bps, self.spc, self.reserved, self.nfats, self.root_entries,
         self.total, self.media, self.spf) = struct.unpack_from('<HBHBHHBH', b, 0x0B)
        self.root_start = (self.reserved + self.nfats * self.spf) * self.bps
        self.root_sectors = (self.root_entries * 32 + self.bps - 1) // self.bps
        self.data_start = self.root_start + self.root_sectors * self.bps
        self.fat = img[self.reserved * self.bps:self.reserved * self.bps + self.spf * self.bps]
        self.img = img

    def next_cluster(self, c):
        off = c * 3 // 2
        v = self.fat[off] | (self.fat[off + 1] << 8)
        return (v >> 4) if (c & 1) else (v & 0xFFF)

    def read_chain(self, c, size=None):
        out = bytearray()
        seen = set()
        while 2 <= c < 0xFF8 and c not in seen:
            seen.add(c)
            off = self.data_start + (c - 2) * self.spc * self.bps
            out += self.img[off:off + self.spc * self.bps]
            c = self.next_cluster(c)
        return bytes(out[:size]) if size else bytes(out)

    def entries(self, raw):
        res = []
        for i in range(0, len(raw), 32):
            e = raw[i:i + 32]
            if len(e) < 32 or e[0] == 0:
                break
            if e[0] == 0xE5:
                continue
            name = e[0:8].decode('latin-1').rstrip()
            ext = e[8:11].decode('latin-1').rstrip()
            if not name and not ext:
                continue
            cluster, size = struct.unpack_from('<HI', e, 26)
            res.append({'name': name, 'ext': ext, 'attr': e[11],
                        'cluster': cluster, 'size': size,
                        'full': name + ('.' + ext if ext else '')})
        return res

    def root(self):
        return self.entries(self.img[self.root_start:self.root_start + self.root_entries * 32])

    def listdir(self, cluster):
        return self.entries(self.read_chain(cluster))


# --------------------------------------------------------------------------
# 3. Decompression RLE
# --------------------------------------------------------------------------

def rle_unpack(src, comp_len):
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
            out.extend(b'\x00' * n)
    return bytes(out)


# --------------------------------------------------------------------------
# 4. Palettes
# --------------------------------------------------------------------------
# Couleurs 1 a 6 : un jeu de 6 couleurs propre a chaque ecran, defini dans
# A.PRG a l'adresse 0x7194 (table -$bda(a4), 5 enregistrements de 6 mots).
# Couleur 0 : noir. Couleurs 7 a 15 : communes a tous les ecrans.
SCREEN_COLORS = [
    [0x430, 0x320, 0x542, 0x230, 0x777, 0x047],   # jungle
    [0x437, 0x416, 0x304, 0x310, 0x210, 0x467],   # arene rocheuse
    [0x555, 0x333, 0x741, 0x530, 0x420, 0x406],   # salle du trone
    [0x056, 0x425, 0x303, 0x774, 0x743, 0x420],   # cachot
    [0x555, 0x333, 0x222, 0x742, 0x530, 0x320],   # hall of heroes
]
COMMON_COLORS = [0x370, 0x051, 0x500, 0x700, 0x740, 0x760, 0x444, 0x006, 0x777]

README = """Graphismes extraits de Barbarian (Palace Software, 1987) - version Atari ST
=========================================================================

Source : Barbarian (1987)(Palace).stx  (image disquette Pasti)
Disquette 360 Ko, simple face, 80 pistes x 9 secteurs.
Contenu : AUTO\\A.PRG (le programme) et BARB.DAT (275 042 octets de donnees).

Fichiers
--------
ecran_01_titre_jungle.png     ecran-titre / jungle (320x200, 16 couleurs)
ecran_02_arene_rocheuse.png   arene rocheuse
ecran_03_salle_du_trone.png   salle du trone
ecran_04_cachot.png           cachot
ecran_05_hall_of_heroes.png   hall of heroes (tableau des scores)
police_8x8.png                police 8x8, 96 caracteres (ASCII 0x20-0x7F)
sprites_banque1.png           252 tuiles de sprite 24x21 (banque 1)
sprites_banque2.png           252 tuiles de sprite 24x21 (banque 2)
personnages_banque1.png       essai d'assemblage des tuiles en personnages 48x84
personnages_banque2.png       idem pour la banque 2
palettes.txt                  les 16 couleurs de chaque ecran (format 0RGB Atari ST)

Format des donnees
------------------
Les 5 ecrans sont compresses en RLE dans BARB.DAT :
  - octet non nul  : recopie tel quel
  - octet 0x00     : suivi d'un compteur N, produit 1 + N octets a zero

Un ecran ST fait 320x200 en 4 plans imbriques (32 000 octets, 160 octets par
ligne, 8 octets par groupe de 16 pixels).

La palette est construite ainsi :
  couleur 0      : noir
  couleurs 1-6   : 6 couleurs propres a chaque ecran (table a l'adresse 0x7194
                   de A.PRG, 5 enregistrements de 6 mots)
  couleurs 7-15  : communes aux 5 ecrans
                   (370 051 500 700 740 760 444 006 777)

Les tuiles de sprite font 24x21 pixels, 2 plans, 6 octets par ligne (3 colonnes
de 8 pixels), soit 126 octets. Le jeu ecrit les plans 0 et 1 depuis les donnees
et met le OU des deux dans les plans 2 et 3, ce qui n'utilise que les couleurs
12 a 15 de la palette.

Note sur les personnages : le jeu assemble les tuiles 24x21 pour former les
combattants (environ 2 tuiles de large sur 4 de haut). L'assemblage propose ici
est un essai : les premieres poses sont correctes, d'autres sont incompletes car
le jeu utilise en plus des tables d'animation internes.

Reproduire l'extraction
-----------------------
    python3 tools/extract_graphismes.py

Le script n'utilise que la bibliotheque standard de Python.
"""


SCREEN_NAMES = [
    '01_titre_jungle',
    '02_arene_rocheuse',
    '03_salle_du_trone',
    '04_cachot',
    '05_hall_of_heroes',
]


def palette(index):
    return [0x000] + SCREEN_COLORS[index] + COMMON_COLORS


def rgb(color):
    return (((color >> 8) & 7) * 255 // 7,
            ((color >> 4) & 7) * 255 // 7,
            (color & 7) * 255 // 7)


# --------------------------------------------------------------------------
# 5. Rendu
# --------------------------------------------------------------------------

def screen_pixels(data, pal, w=320, h=200):
    """Decode un ecran ST 4 plans et renvoie un buffer RGBA."""
    cols = [rgb(c) for c in pal]
    buf = bytearray(w * h * 4)
    rowbytes = 8 * (w // 16)
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
                r, gg, b = cols[v]
                o = (y * w + g * 16 + bit) * 4
                buf[o] = r
                buf[o + 1] = gg
                buf[o + 2] = b
                buf[o + 3] = 255
    return buf


def sprite_pixels(block, pal):
    """Decode un sprite 24x21 (2 plans, 6 octets par ligne)."""
    cols = [rgb(c) for c in pal]
    buf = bytearray(24 * 21 * 4)
    for r in range(21):
        for c in range(3):
            b0 = block[r * 6 + c * 2]
            b1 = block[r * 6 + c * 2 + 1]
            for bit in range(8):
                p0 = (b0 >> (7 - bit)) & 1
                p1 = (b1 >> (7 - bit)) & 1
                if p0 or p1:
                    v = 12 + (1 if p0 else 0) + (2 if p1 else 0)
                    rr, gg, bb = cols[v]
                    o = (r * 24 + c * 8 + bit) * 4
                    buf[o] = rr
                    buf[o + 1] = gg
                    buf[o + 2] = bb
                    buf[o + 3] = 255
    return buf


def sprite_sheet(chunk, pal, per_row=16, scale=1, bg=(32, 32, 32)):
    n = len(chunk) // 126
    rows = (n + per_row - 1) // per_row
    tw, th = 24 + 2, 21 + 2
    W, H = per_row * tw * scale, rows * th * scale
    buf = bytearray(W * H * 4)
    for i in range(W * H):
        buf[i * 4] = bg[0]
        buf[i * 4 + 1] = bg[1]
        buf[i * 4 + 2] = bg[2]
        buf[i * 4 + 3] = 255
    for idx in range(n):
        sp = sprite_pixels(chunk[idx * 126:(idx + 1) * 126], pal)
        ox = (idx % per_row) * tw
        oy = (idx // per_row) * th
        for y in range(21):
            for x in range(24):
                o = (y * 24 + x) * 4
                if sp[o + 3] == 0:
                    continue
                for sy in range(scale):
                    for sx in range(scale):
                        dx = (ox + x) * scale + sx
                        dy = (oy + y) * scale + sy
                        d = (dy * W + dx) * 4
                        buf[d] = sp[o]
                        buf[d + 1] = sp[o + 1]
                        buf[d + 2] = sp[o + 2]
                        buf[d + 3] = 255
    return W, H, buf


def character_sheet(chunk, pal, per_row=8):
    """Assemble les tuiles par groupes de 8 (2 large x 4 haut = 48x84 px)."""
    n = len(chunk) // (126 * 8)
    rows = (n + per_row - 1) // per_row
    CW, CH = 48 + 2, 84 + 2
    W, H = per_row * CW, rows * CH
    buf = bytearray(W * H * 4)
    for i in range(W * H):
        buf[i * 4] = buf[i * 4 + 1] = buf[i * 4 + 2] = 32
        buf[i * 4 + 3] = 255
    for k in range(n):
        ox = (k % per_row) * CW
        oy = (k // per_row) * CH
        for by in range(4):
            for bx in range(2):
                idx = k * 8 + by * 2 + bx
                sp = sprite_pixels(chunk[idx * 126:(idx + 1) * 126], pal)
                for y in range(21):
                    for x in range(24):
                        o = (y * 24 + x) * 4
                        if sp[o + 3] == 0:
                            continue
                        d = ((oy + by * 21 + y) * W + ox + bx * 24 + x) * 4
                        buf[d] = sp[o]
                        buf[d + 1] = sp[o + 1]
                        buf[d + 2] = sp[o + 2]
                        buf[d + 3] = 255
    return W, H, buf


def font_sheet(font, pal, cols=16):
    n = len(font) // 8
    rows = (n + cols - 1) // cols
    W, H = cols * 10, rows * 10
    buf = bytearray(W * H * 4)
    for i in range(W * H):
        buf[i * 4] = 20
        buf[i * 4 + 1] = 20
        buf[i * 4 + 2] = 20
        buf[i * 4 + 3] = 255
    fg = rgb(pal[15])
    for i in range(n):
        ox = (i % cols) * 10 + 1
        oy = (i // cols) * 10 + 1
        for y in range(8):
            b = font[i * 8 + y]
            for bit in range(8):
                if (b >> (7 - bit)) & 1:
                    d = ((oy + y) * W + ox + bit) * 4
                    buf[d] = fg[0]
                    buf[d + 1] = fg[1]
                    buf[d + 2] = fg[2]
                    buf[d + 3] = 255
    return W, H, buf


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    stx = None
    for f in os.listdir(here):
        if f.lower().endswith('.stx'):
            stx = os.path.join(here, f)
    if not stx:
        sys.exit('aucune image .stx trouvee')

    out = os.path.join(here, 'graphisme')
    os.makedirs(out, exist_ok=True)

    print('1. Decodage de', os.path.basename(stx))
    st = stx_to_st(stx)
    os.makedirs(os.path.join(here, 'extract'), exist_ok=True)
    with open(os.path.join(here, 'extract', 'barbarian.st'), 'wb') as handle:
        handle.write(st)

    print('2. Lecture du systeme de fichiers')
    fs = Fat12(st)
    files = {}
    for e in fs.root():
        if e['attr'] & 0x10:
            for s in fs.listdir(e['cluster']):
                if not (s['attr'] & 0x10):
                    files[s['full']] = fs.read_chain(s['cluster'], s['size'])
        elif e['size']:
            files[e['full']] = fs.read_chain(e['cluster'], e['size'])
    for name, data in files.items():
        print(f'   {name:<12s} {len(data):7d} octets')

    dat = files.get('BARB.DAT')
    if not dat:
        sys.exit('BARB.DAT introuvable')

    print('3. Decompression des 5 ecrans')
    screens = [(0x00000, 0x06560), (0x06560, 0x0C867), (0x0C867, 0x12DE0),
               (0x12DE0, 0x19353), (0x19353, 0x1F51B)]
    for i, (a, b) in enumerate(screens):
        img = rle_unpack(dat[a:b], b - a)
        pal = palette(i)
        w, h, buf = 320, 200, screen_pixels(img, pal)
        write_png(os.path.join(out, f'ecran_{SCREEN_NAMES[i]}.png'), w, h, buf)
        print(f'   ecran_{SCREEN_NAMES[i]}.png  ({len(img)} octets decompresses)')

    print('4. Police 8x8')
    font = dat[0x1F51B:0x1F81C]
    w, h, buf = font_sheet(font, palette(0))
    write_png(os.path.join(out, 'police_8x8.png'), w, h, buf)
    print(f'   police_8x8.png  ({len(font) // 8} caracteres)')

    print('5. Sprites')
    for i, (a, b) in enumerate([(0x33A52, 0x3B65A), (0x3B65A, 0x43262)], 1):
        chunk = dat[a:b]
        w, h, buf = sprite_sheet(chunk, palette(0))
        write_png(os.path.join(out, f'sprites_banque{i}.png'), w, h, buf)
        print(f'   sprites_banque{i}.png  ({len(chunk) // 126} sprites de 24x21)')

    print('6. Personnages assembles (2x4 tuiles)')
    for i, (a, b) in enumerate([(0x33A52, 0x3B65A), (0x3B65A, 0x43262)], 1):
        chunk = dat[a:b]
        w, h, buf = character_sheet(chunk, palette(0))
        write_png(os.path.join(out, f'personnages_banque{i}.png'), w, h, buf)
        print(f'   personnages_banque{i}.png  ({len(chunk) // (126 * 8)} personnages)')

    with open(os.path.join(out, 'palettes.txt'), 'w') as f:
        for i in range(5):
            colors = ' '.join(f'{c:03X}' for c in palette(i))
            f.write(f'{SCREEN_NAMES[i]} : {colors}\n')
    with open(os.path.join(out, 'README.txt'), 'w') as f:
        f.write(README)
    print('\nTermine ->', out)


if __name__ == '__main__':
    main()
