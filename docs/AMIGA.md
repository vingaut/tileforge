# Chaîne Amiga — disques, Imploder, hunks, écrans et sprites

> Cette page décrit la chaîne ajoutée en 1.5.0 pour traiter un jeu Amiga de
> bout en bout : image disque → système de fichiers → décompression →
> exécutable → bitmap planaire → palette → sprites.
>
> Aucun fichier de jeu n'est inclus dans le dépôt. Les exemples ci-dessous
> utilisent des images et des données fabriquées par les tests.

---

## 1. Ce qui est couvert

| Couche | Module | État |
|---|---|---|
| Disque ADF / ADZ / HDF | `core/amigadisk.py` | ✅ OFS et FFS, blocs 512/1024 |
| Checksums invalides (Copylock) | `core/amigadisk.py` | ✅ ouverture poursuivie, avertissements |
| IPF (CAPS/SPS) | `core/amigadisk.py` | détecté, conversion ADF expliquée |
| DMS | `core/amigadisk.py` | détecté, conversion `xdms` expliquée |
| Imploder (10 signatures) | `core/imploder.py` | ✅ décompression à rebours |
| RNC ProPack méthodes 1 et 2 | `core/rnc.py` | ✅ clé de déchiffrement optionnelle |
| Formats imbriqués | `core/nested.py` | ✅ profondeur 4, récursif |
| Exécutables hunk | `core/hunk.py` | ✅ segments, relogements, adresses |
| Listes copper | `core/copper.py` | ✅ plans, palette, géométrie |
| Écrans planaires | `core/planar.py` | ✅ row/plane-major, 1–8 plans, stride libre |
| Palettes `0x0RGB` | `core/planar.py` | ✅ recherche, score, rejet des fondus |
| Sprites | `core/amigasprites.py` | ✅ composantes, grille, pré-décalage |
| Tuiles Amiga 3–6 plans | `core/formats.py` | ✅ `amiga_3bpp` à `amiga_6bpp`, sprite 5 plans |
| CrunchMania, Turbo Packer | `core/nested.py` | détectés, décompression pas encore faite |

Les formats **non décodés** sont signalés avec un avertissement explicite :
l'outil ne fait jamais croire qu'un bloc reconnu est vide.

---

## 2. Parcours type

### 2.1 Ouvrir une disquette

```python
from tileforge.core import amigadisk

volume = amigadisk.open_disk("project-x-disk1.adf")
print(volume.name, volume.ffs, volume.warnings)
for node in volume.files():
    print(node.path, node.size)
data = volume.extract("NIVEAU1/SPRITES.BIN")
```

Une image protégée s'ouvre quand même :

```python
volume = amigadisk.open_disk("disque-protege.adf")
print(volume.warnings)
# ['bloc de démarrage : checksum invalide — protection probable (Copylock…)', …]
```

Les chaînes `Copylock`, `Rob Northen`, `RNC` et `SPS` sont recherchées dans le
bloc de démarrage et la racine. Un checksum faux n'est jamais fatal : c'est le
signal d'une protection, pas d'un fichier illisible.

### 2.2 Décompresser en cascade

```python
from tileforge.core import nested

blobs = nested.scan_nested(open("lv1f", "rb").read())
for blob in blobs:
    print(blob.offset, blob.format, blob.depth, blob.decompressed_size)
    if blob.data:
        open(f"{blob.format}_{blob.offset:x}.bin", "wb").write(blob.data)
```

L'ordre est celui de la découverte : `imploder` en profondeur 0, `hunk` ou
`rnc` en profondeur 1, etc. Les blocs `CrM!`/`TPWM` sont listés avec un
avertissement au lieu d'être ignorés.

### 2.3 Lire un exécutable hunk

```python
from tileforge.core import hunk

exe = hunk.parse(open("executable", "rb").read(), base=0x8000)
for segment in exe.segments:
    print(segment.index, segment.kind, hex(segment.vaddr), segment.size)
offset = exe.address_to_offset(0x12CD6)
```

`base` est l'adresse de chargement conventionnelle (0x8000 par défaut, comme
rizin). Les tailles à drapeaux dans les bits hauts sont masquées et signalées.

### 2.4 Trouver une liste copper

```python
from tileforge.core import copper

for candidate in copper.find_lists(data, limit=4):
    print(candidate.summary())
```

Une liste donne gratuitement le nombre de plans (`BPLCON0`), les adresses des
plans (`BPLxPT`), la palette (`COLORxx`), la fenêtre d'affichage et le modulo.

### 2.5 Rendre un écran

```python
from tileforge.core import planar
from tileforge.core.image import save_image

image = planar.render_screen(
    data, offset=0x12CD6, width=256, height=256, planes=5,
    layout="plane", stride=40,           # 256 utiles dans un bitmap de 320
    palette=planar.read_palette(data, 0x21D7A, 32))
save_image("ecran.png", image)
```

Sans géométrie connue :

```python
for candidate in planar.detect_geometry(data, height=256, limit=4):
    print(candidate.as_dict())
```

Le détecteur note la cohérence des voisins (un vrai bitmap : 0,8–0,95 ; du
code : ~0,03), pénalise les zones presque vides et signale le bourrage de fin
de ligne (`content_width`).

### 2.6 Extraire les sprites

```python
from tileforge.core import amigasprites, planar

index = planar.decode_indices(data, 0x40000, 640, 256, 5, "plane", 80)
sprites = amigasprites.components(index, min_area=8, close_radius=1)
grid = amigasprites.detect_grid(index)
shifts = amigasprites.detect_preshift(sprites)
groups = amigasprites.group_animations(sprites)
amigasprites.export_sheet(sprites, palette, "planche.png")
```

La fermeture morphologique (`close_radius=1` ou `2`) évite de couper un
vaisseau et ses flammes en trois sprites. `detect_preshift` repère les copies
décalées horizontalement (défilement Amiga) et ignore les simples doublons.

---

## 3. Ligne de commande

```bash
python tools/amiga.py list disque.adf
python tools/amiga.py extract disque.adf NIVEAU1/SPRITES.BIN -o sprites.bin
python tools/amiga.py nested lv1f -o sortie/
python tools/amiga.py screen ecran.bin --width 256 --height 256 \
    --planes 5 --layout plane --stride 40 -o ecran.png
python tools/amiga.py sprites planche.bin --width 640 --height 256 \
    --planes 5 --layout plane --stride 80 -o planche.png
python tools/amiga.py hunk executable
python tools/amiga.py copper binaire
```

`screen` et `sprites` acceptent `--offset`, `--palette-offset` et
`--palette-count` en hexadécimal (`0x...`). Sans `--width`/`--planes`, la
géométrie est détectée et affichée avant le rendu.

---

## 4. Outils MCP

| Outil | Usage |
|---|---|
| `tileforge_open_disk` | ouvre un ADF/ADZ/HDF et liste l'arborescence |
| `tileforge_extract_disk_file` | extrait un fichier vers le dossier de travail |
| `tileforge_decompress_nested` | descend Imploder/RNC/hunk et écrit chaque bloc |
| `tileforge_amiga_screen` | rend un écran planaire, détecte la géométrie |
| `tileforge_amiga_sprites` | découpe une planche et écrit une planche RGBA |
| `tileforge_amiga_analyze` | hunks, listes copper et blocs imbriqués |

`tileforge_inspect_file` reconnaît désormais les disques Amiga, les exécutables
hunk et les blocs Imploder/RNC, et renvoie les avertissements utiles.

---

## 5. Limites assumées

* **IPF** : le format CAPS/SPS décrit un flux de cellules magnétiques, pas des
  secteurs. La bibliothèque SPS n'est pas libre ; l'outil détecte le fichier et
  explique la conversion en ADF. Aucun décodeur MFM/IPF n'est embarqué.
* **DMS** : détecté, pas décodé. `xdms` fait le travail.
* **CrunchMania / Turbo Packer / StoneCracker** : signatures reconnues,
  décompression pas encore implémentée ; le bloc est signalé, jamais ignoré.
* **Hunks overlays et HUNK_EXT complexes** : les blocs connus sont sautés
  proprement, mais les formats d'overlay ne sont pas interprétés.
* **Détection de géométrie** : elle classe des candidats, elle ne devine pas
  une image unique. Sur un motif très répétitif, plusieurs offsets peuvent
  obtenir la même note ; l'outil renvoie le meilleur et l'utilisateur vérifie
  l'aperçu.
* **Copper** : les listes sont lues instruction par instruction ; les listes
  construites dynamiquement par le code ne sont pas suivies.

---

## 6. Vérification

Les tests couvrent chaque couche avec des données synthétiques :

```bash
python tests/run_all.py
```

* `test_imploder.py` : aller-retour sur un flux produit par `im-tools`, dix
  signatures, checksum faux toléré, flux tronqué refusé.
* `test_rnc.py` : méthodes 1 et 2 sur les vecteurs de `bitplane/propack`,
  CRC faux toléré, CRC vérifié sur demande.
* `test_amigadisk.py` : volumes OFS/FFS, répertoires, checksums invalides,
  protection, ADZ, IPF et DMS.
* `test_hunk.py`, `test_copper.py`, `test_planar.py`,
  `test_amigasprites.py`, `test_nested.py`, `test_amiga_tools.py`.

Les fixtures sont dans `tests/fixtures/` :

| Fichier | Origine |
|---|---|
| `imploder_data.imp` / `.raw` | produit par `im-tools` de Franck Charlet (BSD 2-Clause) |
| `nested_imploder_rnc.imp` / `.raw` | Imploder autour du flux RNC de test |
| `pack1.rnc1`, `pack1.rnc2` et `.expected` | `bitplane/propack` (WTFPL) |

Aucun contenu de jeu commercial n'est présent.

---

## 7. Attributions

* Imploder : algorithme reversé par Vladimir Kononovich (lab313ru),
  décompresseur `im-data` de Franck Charlet (BSD 2-Clause), structure du pied
  de page confirmée par le client XAD `DImp` de Stuart Caie (GPL, non copié).
* RNC ProPack : Rob Northen Computing, manuel ProPack (février 1992) et
  sources d'assembleur ; implémentation Python de `bitplane/propack` (WTFPL).
* AmigaDOS : RKM « AmigaDOS » et « Devices ».
* Copper et plans : RKM « Graphics Library ».
