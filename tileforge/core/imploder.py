"""Décompression des fichiers de données Imploder (Amiga).

Imploder est un compresseur Amiga très répandu dans les jeux des années 1990
(Team17, Psygnosis…).  Le bloc compressé est écrit **à rebours** : les
derniers octets du fichier décrivent l'état initial (longueur du premier
passage littéral, buffer de bits, tables de Huffman), puis les données se
reconstruisent en remontant vers le début.  Un décompresseur naïf qui lit
depuis l'en-tête échoue donc systématiquement.

Le format reconnaît dix signatures, toutes décodées par le même algorithme :
``IMP!``, ``ATN!``, ``BDPI``, ``CHFI``, ``Dupa``, ``EDAM``, ``FLT!``,
``M.H.``, ``PARA`` et ``RDC9``.  ``ATN!`` est la variante utilisée par
Project-X et de nombreux jeux Team17 ; il ne faut pas la confondre avec RNC.

Structure d'un fichier
----------------------

::

    +0x00  signature (4 octets)
    +0x04  taille décompressée (32 bits, gros-boutiste)
    +0x08  offset du pied de page = taille des données compressées
    ...    données compressées
    +pied  0x32 octets :
           +0x00  trois premiers longs du fichier d'origine (restaurés)
           +0x0C  longueur du premier passage littéral
           +0x10  drapeau (bit 7) et buffer de bits initial
           +0x12  huit offsets de base (mots)
           +0x22  douze largeurs de bits
           +0x2E  somme de contrôle (facultative, souvent fausse)

La somme de contrôle n'est **pas** utilisée pour rejeter le fichier : les
protections Copylock et les variantes de compresseur la rendent souvent
invalide alors que les données sont parfaitement décodables.

Références
----------
L'algorithme est celui du décompresseur ``im-data`` de Franck Charlet
(BSD 2-Clause, https://aminet.net/package/util/pack/im-tools), lui-même
reversé par Vladimir Kononovich (lab313ru).  La variante « Disk Imploder »
de Stuart Caie (xad_DImp, GPL) confirme la structure du pied de page.
"""

from __future__ import annotations

from .compression import DecompressionError

#: Les dix signatures reconnues par Imploder et ses clones.
IMPLODER_MAGICS: tuple[bytes, ...] = (
    b"IMP!", b"ATN!", b"BDPI", b"CHFI", b"Dupa",
    b"EDAM", b"FLT!", b"M.H.", b"PARA", b"RDC9",
)

#: Taille du pied de page (état initial + tables + somme).
FOOTER_SIZE = 0x32

#: Taille minimale lue dans le pied de page (sans la somme).
FOOTER_STATE = 0x2E

#: Taille de sortie maximale acceptée (garde-fou mémoire).
MAX_OUTPUT = 64 << 20

#: Base des longueurs littérales pour les quatre sélecteurs.
_TOKEN_BASE = (6, 10, 10, 18)

#: Largeurs de bits des longueurs littérales (trois niveaux de sélecteurs).
_STATIC_EXTRA = (1, 1, 1, 1, 2, 3, 3, 4, 4, 5, 7, 14)


class ImploderError(DecompressionError):
    """Fichier Imploder invalide ou tronqué."""


def _u16(data: bytes | bytearray, offset: int) -> int:
    return (data[offset] << 8) | data[offset + 1]


def _u32(data: bytes | bytearray, offset: int) -> int:
    return ((data[offset] << 24) | (data[offset + 1] << 16)
            | (data[offset + 2] << 8) | data[offset + 3])


def magic_at(data: bytes | bytearray, offset: int = 0) -> bytes:
    """Signature Imploder à ``offset``, ou ``b""``."""
    if offset < 0 or offset + 4 > len(data):
        return b""
    magic = bytes(data[offset:offset + 4])
    return magic if magic in IMPLODER_MAGICS else b""


def is_imploder(data: bytes | bytearray, offset: int = 0) -> bool:
    """Vrai si les octets à ``offset`` ressemblent à un fichier Imploder."""
    if not magic_at(data, offset):
        return False
    if offset + 12 > len(data):
        return False
    out_len = _u32(data, offset + 4)
    end_off = _u32(data, offset + 8)
    if out_len == 0 or out_len > MAX_OUTPUT:
        return False
    # Le pied de page doit tenir dans le fichier.
    if end_off < 12 or end_off % 2 or offset + end_off + FOOTER_STATE > len(data):
        return False
    # Le bloc compressé est toujours plus petit que l'original.
    return out_len >= end_off + 0x26


def exploded_size(data: bytes | bytearray, offset: int = 0) -> int:
    """Taille décompressée annoncée par l'en-tête (0 si ce n'est pas Imploder)."""
    if not is_imploder(data, offset):
        return 0
    return _u32(data, offset + 4)


def _checksum(data: bytes | bytearray, size: int) -> int:
    total = 7
    for i in range(0, size - 1, 2):
        total += (data[i] << 8) | data[i + 1]
    if size & 1:
        total += data[size - 1] << 8
    return total & 0xFFFFFFFF


def explode(data: bytes | bytearray, offset: int = 0,
            verify_checksum: bool = False) -> tuple[bytes, list[str]]:
    """Décompresse un fichier Imploder.

    Renvoie ``(données, avertissements)``.  Une somme de contrôle fausse
    produit un avertissement, jamais une exception : c'est le cas normal sur
    les fichiers protégés.
    """
    if not magic_at(data, offset):
        raise ImploderError("signature Imploder absente")
    if offset + 12 > len(data):
        raise ImploderError("en-tête Imploder tronqué")

    out_len = _u32(data, offset + 4)
    end_off = _u32(data, offset + 8)

    if out_len == 0 or out_len > MAX_OUTPUT:
        raise ImploderError(f"taille décompressée invalide : {out_len}")
    if end_off < 12 or end_off % 2:
        raise ImploderError(f"offset de données compressées invalide : {end_off}")
    if offset + end_off + FOOTER_STATE > len(data):
        raise ImploderError("pied de page Imploder tronqué")
    if out_len < end_off + 0x26:
        raise ImploderError("taille décompressée incohérente avec l'en-tête")

    warnings: list[str] = []

    # Le décodeur écrit à rebours dans le même tampon que les données
    # compressées : c'est le comportement d'origine, et cela évite une
    # allocation intermédiaire.
    work = bytearray(out_len)
    packed = bytes(data[offset:offset + end_off + FOOTER_SIZE])
    work[:len(packed)] = packed

    footer = work[end_off:end_off + FOOTER_SIZE]
    if len(footer) < FOOTER_SIZE:
        raise ImploderError("pied de page Imploder tronqué")

    # Les trois premiers longs du fichier d'origine ont été déplacés dans le
    # pied de page parce que la décompression écrase l'en-tête.
    work[8:12] = footer[0:4]
    work[4:8] = footer[4:8]
    work[0:4] = footer[8:12]

    has_checksum = offset + end_off + FOOTER_SIZE <= len(data)
    stored_checksum = _u32(footer, FOOTER_STATE) if has_checksum else 0
    # La somme a été calculée sur le fichier compressé *avec* son en-tête,
    # avant que le décodeur ne restaure les douze premiers octets.
    actual_checksum = _checksum(packed, end_off + FOOTER_STATE)
    if not has_checksum:
        warnings.append("somme de contrôle Imploder absente — fichier "
                        "peut-être tronqué ; décompression tentée quand même")
    elif actual_checksum != stored_checksum:
        warnings.append(
            f"somme de contrôle Imploder invalide (0x{stored_checksum:08X} "
            f"attendu, 0x{actual_checksum:08X} calculé) — données peut-être "
            "protégées ; décompression tentée quand même")

    token_run_len = _u32(footer, 0x0C)
    flag = footer[0x10]
    token = footer[0x11]
    base_offs = [_u16(footer, 0x12 + 2 * i) for i in range(8)]
    extra_bits = list(footer[0x22:0x2E])

    cmpr_pos = 0 if (flag & 0x80) else -1
    src_end = out_len

    def compressed_byte(pos: int) -> int:
        """Octet du flux compressé, lu à rebours depuis le pied de page."""
        index = end_off + pos
        if index < 0:
            raise ImploderError("flux Imploder épuisé")
        return work[index]

    # -- lecteur de bits -----------------------------------------------------
    def read_bits(count: int) -> int:
        nonlocal token, cmpr_pos
        value = 0
        for _ in range(count):
            bit = token >> 7
            token = (token << 1) & 0xFF
            if token == 0:
                token = ((compressed_byte(cmpr_pos - 1) << 1) | bit) & 0xFF
                cmpr_pos -= 1
                bit = compressed_byte(cmpr_pos) >> 7
            value = (value << 1) | bit
        return value

    # -- boucle principale ---------------------------------------------------
    while True:
        while token_run_len > 0 and src_end > 0:
            cmpr_pos -= 1
            src_end -= 1
            work[src_end] = compressed_byte(cmpr_pos)
            token_run_len -= 1

        if src_end == 0:
            break

        # longueur et sélecteur du match
        if read_bits(1):
            if read_bits(1):
                if read_bits(1):
                    if read_bits(1):
                        if read_bits(1):
                            cmpr_pos -= 1
                            match_len = compressed_byte(cmpr_pos)
                            selector = 3
                        else:
                            match_len = read_bits(3) + 6
                            selector = 3
                    else:
                        match_len = 5
                        selector = 3
                else:
                    match_len = 4
                    selector = 2
            else:
                match_len = 3
                selector = 1
        else:
            match_len = 2
            selector = 0

        # longueur du prochain passage littéral : tables fixes d'Imploder
        if read_bits(1):
            if read_bits(1):
                token_run_len = (read_bits(_STATIC_EXTRA[selector + 8])
                                 + _TOKEN_BASE[selector])
            else:
                token_run_len = read_bits(_STATIC_EXTRA[selector + 4]) + 2
        else:
            token_run_len = read_bits(_STATIC_EXTRA[selector])

        # pointeur du match
        if read_bits(1):
            if read_bits(1):
                match = (src_end + read_bits(extra_bits[8 + selector])
                         + base_offs[4 + selector] + 1)
            else:
                match = (src_end + read_bits(extra_bits[4 + selector])
                         + base_offs[selector] + 1)
        else:
            match = src_end + read_bits(extra_bits[selector]) + 1

        for _ in range(match_len):
            if src_end <= 0:
                break
            match -= 1
            if match < 0 or match >= out_len:
                raise ImploderError("pointeur de match hors limites")
            src_end -= 1
            work[src_end] = work[match]

    if verify_checksum and has_checksum and actual_checksum != stored_checksum:
        raise ImploderError("somme de contrôle Imploder invalide")
    return bytes(work[:out_len]), warnings


def decompress(data: bytes | bytearray, offset: int = 0) -> bytes:
    """Décompresseur au contrat du registre : ``(data, offset) -> bytes``."""
    return explode(data, offset)[0]


def inspect(data: bytes | bytearray, offset: int = 0) -> dict:
    """Décrit un bloc Imploder sans le décompresser."""
    if not is_imploder(data, offset):
        return {}
    return {
        "format": "imploder",
        "magic": magic_at(data, offset).decode("latin-1"),
        "offset": offset,
        "compressed_size": _u32(data, offset + 8),
        "uncompressed_size": _u32(data, offset + 4),
        "file_size": len(data) - offset,
    }
