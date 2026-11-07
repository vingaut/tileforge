"""Test d'intégration : de la ROM compressée aux tuiles.

Les autres tests vérifient chaque pièce isolément. Celui-ci vérifie la chaîne
complète, telle que l'utilisateur la vit :

1. on fabrique une banque de tuiles ;
2. on l'encode en Kosinski (avec l'encodeur de ``tools/make_fixture.py``) ;
3. on la place dans une ROM de bruit ;
4. on lance le balayage, qui doit la trouver et la décompresser ;
5. on vérifie que les octets retrouvés sont exactement ceux du départ.

C'est la seule preuve que le balayage, la décompression et le découpage
s'enchaînent correctement sur une banque réellement compressée.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from make_fixture import kosinski_encode, sprite_tiles, synthetic_rom  # noqa: E402

from tileforge.core import compression as C  # noqa: E402
from tileforge.core.scan import scan_bytes  # noqa: E402


def test_encodeur_kosinski_aller_retour():
    """L'encodeur de test doit produire un flux que le décodeur relit."""
    for count in (1, 4, 16, 64):
        tiles = sprite_tiles(count)
        assert C.kosinski(kosinski_encode(tiles)) == tiles


def test_encodeur_compresse_vraiment():
    """Sur une banque de sprites, le gain doit être réel."""
    tiles = sprite_tiles(64)
    encoded = kosinski_encode(tiles)
    assert len(encoded) < len(tiles) * 0.8, (len(encoded), len(tiles))


def test_chaine_complete_sur_banque_compressee():
    """Balayage, décompression et comparaison, de bout en bout."""
    tiles = sprite_tiles(64)
    offset = 0x8000
    rom, compressed = synthetic_rom(tiles, offset=offset)
    assert compressed < len(tiles)

    report = scan_bytes(rom, "megadrive", compressions=("kosinski",),
                        budget=60, threshold=0.5, raw=False, compressed=True)
    assert report.candidates, "le balayage n'a rien trouvé"

    best = report.candidates[0]
    assert abs(best.offset - offset) <= 8, (best.offset, offset)
    assert best.compression == "kosinski"
    # la taille rapportée est celle des données décompressées
    assert best.size == len(tiles)
    assert best.score > 0.6, best.score

    recovered = C.kosinski(rom, best.offset)
    assert len(recovered) == len(tiles)
    assert recovered == tiles


def test_la_rom_sans_banque_ne_produit_rien():
    """Le même balayage sur du bruit seul ne doit rien proposer."""
    import random

    rng = random.Random(3)
    noise = bytes(rng.randrange(256) for _ in range(0x10000))
    report = scan_bytes(noise, "megadrive", compressions=("kosinski",),
                        budget=30, threshold=0.6, raw=False, compressed=True)
    assert all(candidate.score < 0.8 for candidate in report.candidates)
