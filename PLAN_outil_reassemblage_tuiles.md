# TileForge — plan de développement

**Outil graphique de reconstruction des sprites à partir de planches de tuiles**

Version du document : 1.0 — 5 novembre 2026
Cible immédiate : `Barbarian (Palace, 1987)` — Atari ST
Cible suivante : réutilisable pour d'autres jeux (Atari ST, Amiga, CPC…)

---

## 0. Résumé

Le but est de retrouver l'**assemblage d'origine** des tuiles de sprites d'un jeu,
puis d'en déduire la **logique d'ordonnancement** utilisée par les développeurs.

Le programme doit permettre de :

1. charger une planche de tuiles (PNG ou banque binaire brute) ;
2. détecter les tuiles automatiquement (plusieurs algorithmes) ou à la main ;
3. corriger les détections à la souris ;
4. réassembler les sprites, à la main (glisser-déposer) ou automatiquement
   (plusieurs méthodes paramétrables) ;
5. valider un sprite et l'ajouter à une planche finale (atlas) dont la taille
   est calculée ;
6. enregistrer chaque placement et chaque déplacement ;
7. inférer une règle d'ordonnancement et la **réappliquer** à d'autres groupes
   de tuiles ;
8. exporter toutes ces données pour analyse externe.

---

## 1. Objectif détaillé

### 1.1 Ce que l'utilisateur doit pouvoir faire

| # | Besoin | Traduction en fonctionnalité |
|---|--------|------------------------------|
| 1 | Charger une planche | Ouvrir un PNG, ou une banque brute (fichier + offset + taille de tuile) |
| 2 | Détecter les tuiles | Choix d'algorithme + paramètres, aperçu immédiat |
| 3 | Corriger | Outils rectangle : ajouter, déplacer, redimensionner, supprimer, fusionner, scinder |
| 4 | Réassembler | Glisser-déposer des tuiles sur un canevas avec grille magnétique |
| 5 | Aider | Coût de jointure affiché en direct, surbrillance des raccords douteux |
| 6 | Valider | Bouton « Valider le sprite » → ajout à l'atlas |
| 7 | Atlas | Planche finale dont la taille se calcule automatiquement |
| 8 | Tracer | Journal horodaté de tous les placements/déplacements |
| 9 | Deviner | Détection automatique de la grille + classement d'hypothèses d'ordre |
| 10 | Réappliquer | « Appliquer cette recette aux N prochains groupes » / « à toute la banque » |
| 11 | Sauvegarder | Projet JSON + export CSV/JSON pour analyse |

### 1.2 Ce que l'outil n'a pas à faire

- Émuler le jeu.
- Décoder les formats graphiques à notre place : le décodage d'une tuile est un
  **plugin** (une fonction de 10 lignes par jeu).
- Remplacer le travail d'analyse : il doit au contraire **produire les données**
  qui rendent cette analyse possible.

---

## 2. Ce que l'on sait déjà (Barbarian ST)

### 2.1 La disquette

- Image Pasti `.stx`, disquette 360 Ko simple face (80 pistes × 9 secteurs).
- Deux fichiers : `AUTO/A.PRG` (66 262 o) et `BARB.DAT` (275 042 o).
- L'outil `tools/extract_graphismes.py` sait déjà extraire les deux.

### 2.2 Plan de `BARB.DAT`

| Offset | Taille | Contenu |
|---|---|---|
| `0x00000` | `0x06560` | écran 1 (RLE) |
| `0x06560` | `0x06307` | écran 2 (RLE) |
| `0x0C867` | `0x06579` | écran 3 (RLE) |
| `0x12DE0` | `0x06573` | écran 4 (RLE) |
| `0x19353` | `0x061C8` | écran 5 (RLE) |
| `0x1F51B` | `0x00301` | police 8×8 (96 caractères) |
| `0x1F81C` | `0x14236` | 26 blocs audio |
| `0x33A52` | `0x07C08` | **banque de sprites 1** |
| `0x3B65A` | `0x07C08` | **banque de sprites 2** |

### 2.3 Les tuiles

Une tuile = **126 octets** = 24 × 21 pixels, **2 plans**, 6 octets par ligne
(3 colonnes de 8 pixels).

Décodage exact (extrait de la routine de blit à `0x3814` de `A.PRG`) :

```
pour chaque ligne r de 0 à 20 :
    pour chaque colonne c de 0 à 2 :
        b0 = octet (r*6 + c*2)       -> plan 0
        b1 = octet (r*6 + c*2 + 1)   -> plan 1
        pixel = b0_bit | (b1_bit << 1)
```

Le jeu écrit ensuite le plan 0 et le plan 1 à l'écran, et met le **OU** des deux
dans les plans 2 et 3 : les sprites n'utilisent donc que les **couleurs 12 à 15**
de la palette.

Chaque banque = `31752 / 126 = 252` tuiles.

### 2.4 Ce que dit le code de dessin

La routine `0x3970` dessine un « objet » composé de tuiles :

- boucle externe : `y` de 0 à `0x54` par pas de `0x15` → **4 lignes** de 21 px ;
- boucle interne : `x` de 0 à 9 par pas de 3 → **3 colonnes** de 24 px ;
- la tuile suivante est lue séquentiellement (126 octets de plus) ;
- l'ordonnancement en mémoire est donc **ligne par ligne** (row-major).

Cela suggère une grille **3 × 4 = 12 tuiles** par sprite, et
`252 / 12 = 21` sprites par banque — un compte parfaitement rond.

### 2.5 Premières mesures (faites pendant la rédaction de ce plan)

Une métrique de continuité de **silhouette** (masque transparent/opaque de part
et d'autre d'une jointure) a été testée sur la banque 1 : on compare le coût de
l'ordre d'origine à 3 000 permutations aléatoires.

| Grille | Coût ordre d'origine | Médiane aléatoire | Percentile |
|--------|---------------------:|------------------:|-----------:|
| 4 × 3 | 59 | 166 | **0,0 %** |
| 6 × 2 | 42 | 155 | **0,0 %** |
| 2 × 6 | 62 | 162 | 0,1 % |
| 2 × 4 | 35 | 102 | 1,0 % |
| 3 × 4 | 146 | 168 | 23,8 % |

Enseignements :

1. La **continuité de silhouette est un signal fort** — bien plus que la
   comparaison des valeurs de pixels brutes (testée aussi, percentile ~38 %,
   donc inutilisable seule).
2. Les grilles 4×3 et 6×2 « gagnent » parce qu'elles alignent **plusieurs
   sprites côte à côte** : les images voisines sont des poses successives du
   même personnage, donc très ressemblantes. C'est un **piège** : la métrique
   seule confond « tuiles d'un même sprite » et « sprites voisins similaires ».
3. Il faut donc **combiner plusieurs indices** (voir §8.1) et laisser
   l'utilisateur trancher, d'où l'importance de l'interface.

### 2.6 Hypothèses de grille à tester

| # | Grille | Tuiles/sprite | Sprites/banque | Remarque |
|---|--------|--------------:|---------------:|----------|
| H1 | 3 × 4 | 12 | 21 | ce que suggère la routine `0x3970` |
| H2 | 2 × 3 | 6 | 42 | 2 personnages × 21 poses ? |
| H3 | 2 × 4 | 8 | 31,5 | ne tombe pas juste → peu probable |
| H4 | 4 × 3 | 12 | 21 | même compte que H1, transposé |
| H5 | 2 × 2 | 4 | 63 | 63 = 63, curieux |
| H6 | 3 × 3 | 9 | 28 | |

L'outil doit pouvoir **tester toutes ces grilles automatiquement** et présenter
un classement (voir §8.3).

---

## 3. Choix techniques

### 3.1 Langage et interface

**Python 3.14 + PySide6 (Qt 6).**

Justification :

- Python est déjà l'environnement du projet (`tools/extract_graphismes.py`) ;
- PySide6 fournit un `QGraphicsView` : zoom, pan, sélection, glisser-déposer,
  superposition — exactement ce qu'il faut ici ;
- le wheel PySide6 6.12 est en **abi3 (cp310)** : il fonctionne sur Python 3.14 ;
- l'environnement dispose d'un affichage Wayland/X11 et des bibliothèques Qt
  (`libGL`, `libxkbcommon`, `libxcb-cursor`) ;
- `tkinter` **n'est pas installé** sur cette machine, donc écarté.

Installation :

```bash
cd /path/to/tileforge
python3 -m venv .venv
.venv/bin/pip install PySide6
.venv/bin/python tileforge/main.py
```

> Repli si Qt pose problème : la même architecture peut être portée en
> application web locale (FastAPI + `<canvas>`), l'utilisateur ayant déjà un
> navigateur. Le modèle de données et les algorithmes sont indépendants de l'UI.

### 3.2 Dépendances

| Paquet | Usage |
|---|---|
| `PySide6` | interface |
| `numpy` | calcul des coûts, algos (facultatif mais très recommandé) |
| *(optionnel)* `scipy` | affectation (Hungarian), si besoin |

Le reste est la bibliothèque standard (`json`, `zlib`, `struct`, `dataclasses`).

### 3.3 Arborescence proposée

```
atari_st/
├── tileforge/
│   ├── main.py                 # point d'entrée
│   ├── core/
│   │   ├── model.py            # Sheet, Tile, Sprite, Atlas, Project
│   │   ├── project_io.py       # lecture/écriture JSON
│   │   ├── imageio.py          # PNG lecture/écriture (déjà écrit)
│   │   ├── formats.py          # plugins de décodage (Barbarian, génériques)
│   │   └── history.py          # undo/redo + journal des mouvements
│   ├── detect/
│   │   ├── base.py             # interface Detector + ParamSpec
│   │   ├── grid.py             # grille fixe
│   │   ├── projection.py       # profils de projection
│   │   ├── components.py       # composantes connexes
│   │   ├── xycuts.py           # découpe récursive
│   │   └── period.py           # autocorrélation
│   ├── assemble/
│   │   ├── cost.py             # fonction de coût de jointure
│   │   ├── hypotheses.py       # bibliothèque de permutations
│   │   ├── solvers.py          # glouton, beam search, recuit simulé
│   │   └── inference.py        # inférence de règle d'ordre
│   ├── ui/
│   │   ├── main_window.py
│   │   ├── sheet_view.py       # écran « Planche »
│   │   ├── assembly_view.py    # écran « Atelier »
│   │   ├── atlas_view.py       # écran « Atlas »
│   │   └── analysis_view.py    # écran « Analyse »
│   └── games/
│       ├── barbarian_st.py     # plugin Barbarian
│       └── generic.py          # plugin PNG générique
├── projects/                   # projets sauvegardés (.tileforge.json)
└── graphisme/                  # sorties PNG
```

### 3.4 Formats de fichiers

| Extension | Contenu |
|---|---|
| `.tileforge.json` | projet complet (planche, tuiles, sprites, journal, recettes) |
| `.tfrecipe.json` | recette d'ordonnancement réutilisable |
| `.csv` | export tabulaire pour analyse |

---

## 4. Modèle de données

### 4.1 Entités

```
Project
 ├── Sheet          la planche source (image + géométrie)
 │    └── Tile[]    rectangles découpés
 ├── Grid           grille d'assemblage courante (cols, rows, tw, th)
 ├── Sprite[]       sprites validés (placements + image composée)
 ├── Atlas          planche de sortie
 ├── MoveLog        journal horodaté
 └── Recipe[]       recettes d'ordonnancement
```

### 4.2 Format de projet (JSON)

```json
{
  "format": "tileforge/1",
  "game": "barbarian_st",
  "sheet": {
    "kind": "raw",
    "source": "extract/BARB.DAT",
    "offset": 211538,
    "count": 252,
    "tile_w": 24, "tile_h": 21, "bytes_per_tile": 126,
    "decoder": "planar2_24x21",
    "preview_png": "graphisme/sprites_banque1.png"
  },
  "tiles": [
    { "id": 0, "storage_index": 0, "rect": [1, 1, 24, 21], "label": "0" }
  ],
  "grid": { "cols": 3, "rows": 4, "tile_w": 24, "tile_h": 21 },
  "sprites": [
    {
      "id": 0,
      "name": "pose_00",
      "placements": [ { "tile": 0, "gx": 0, "gy": 0 } ],
      "bbox": [0, 0, 72, 84],
      "validated_at": "2026-11-05T23:40:00"
    }
  ],
  "atlas": { "width": 216, "height": 168, "layout": "shelf", "gap": 0 },
  "moves": [
    { "t": "...", "sprite": 0, "tile": 17,
      "from": [0, 0], "to": [2, 1], "action": "drag" }
  ],
  "recipes": [
    {
      "name": "banque1_3x4",
      "grid": { "cols": 3, "rows": 4 },
      "mapping": [ { "storage_index": 0, "slot": 0 }, { "storage_index": 1, "slot": 1 } ],
      "fit": { "type": "identity", "exact": true }
    }
  ]
}
```

### 4.3 Plugins de format (multi-jeux)

Un plugin décrit comment découper et décoder une banque :

```python
@dataclass
class TileFormat:
    name: str
    tile_w: int
    tile_h: int
    bytes_per_tile: int
    decode: Callable[[bytes], list[list[int]]]   # -> grille de valeurs de palette
    palettes: list[list[int]]                    # 0x0RGB Atari ST, ou RGB888
```

Plugins fournis au départ :

- `barbarian_st` : 24×21, 2 plans, palettes des 5 écrans (voir annexe A) ;
- `generic_png` : lecture d'un PNG déjà découpé, fond transparent ;
- `generic_planar` : planaire N plans, largeur/hauteur/plan configurable.

---

## 5. Écran « Planche » — détection des tuiles

### 5.1 Sources acceptées

1. **Banque brute** (recommandé) : fichier + offset + nombre de tuiles + taille.
   Les indices `storage_index` sont alors exacts — indispensable pour inférer la
   logique d'ordre.
2. **PNG** déjà rendu (ex. `graphisme/sprites_banque1.png`, tuiles 24×21
   espacées de 2 px). Pratique pour d'autres jeux, mais il faut alors retrouver
   la correspondance avec les indices de stockage.

### 5.2 Détecteurs

Chaque détecteur implémente :

```python
class Detector(Protocol):
    name: str
    description: str
    params: list[ParamSpec]          # nom, type, min, max, défaut
    def detect(self, image: RGBAImage, params: dict) -> list[Rect]: ...
```

#### D1 — Grille fixe

Paramètres : `tw`, `th`, `offset_x`, `offset_y`, `gap_x`, `gap_y`,
`cols`/`rows` ou `count`.
C'est le détecteur exact pour Barbarian (24×21, sans gap en mode brut).

#### D2 — Profils de projection

Calcule pour chaque colonne (resp. ligne) le nombre de pixels non-fond.
Les plages vides découpent la planche.
Paramètres : `seuil_alpha`, `seuil_vide` (nb de pixels), `taille_min`,
`fusion_gap` (les petits vides internes sont ignorés).

#### D3 — Composantes connexes

Étiquetage 4/8-connexe du masque « non-fond », puis regroupement.
Paramètres : `seuil_alpha`, `dilatation` (px), `aire_min`, `distance_fusion`.
Utile quand les sprites ont des tailles variables.

#### D4 — Découpe récursive (XY-cut)

Découpe récursivement la boîte englobante à l'endroit du plus grand espace vide,
jusqu'à obtenir des cellules ≤ `taille_max`.
Paramètres : `taille_min`, `taille_max`, `gap_min`, `seuil_alpha`.

#### D5 — Détection de période (autocorrélation)

Cherche la période dominante du masque en X et en Y, en déduit le pas de la
grille, puis applique D1.
Paramètres : `periode_min`, `periode_max`, `seuil`.

#### D6 — Manuel

Aucune détection : l'utilisateur trace tout.

> **Mode hybride** (par défaut) : lancer un détecteur, puis corriger.

### 5.3 Édition manuelle

Outils (barre d'outils + raccourcis) :

| Outil | Raccourci | Action |
|---|---|---|
| Sélection | `V` | sélectionner une ou plusieurs tuiles |
| Rectangle | `R` | tracer une nouvelle tuile |
| Déplacer | `M` | déplacer une tuile |
| Redimensionner | poignées | ajuster les bords |
| Supprimer | `Suppr` | retirer la tuile |
| Fusionner | `F` | fusionner 2 tuiles sélectionnées |
| Scinder | `S` | couper en 2 (vertical/horizontal) |
| Dupliquer | `Ctrl+D` | dupliquer le rectangle |
| Aimant | `G` | aimanter à la grille |
| Numéroter | — | renuméroter selon l'ordre de lecture ou le `storage_index` |

Fonctions complémentaires :

- **zoom** molette, **pan** clic-milieu ou `Espace` ;
- **grille de repère** avec pas configurable ;
- **vue loupe** ;
- **undo/redo** illimité (`Ctrl+Z` / `Ctrl+Y`) ;
- **contrôle qualité** : tuiles qui se chevauchent, tuiles vides, tuiles hors
  planche, tailles incohérentes → liste cliquable.

### 5.4 Paramètres persistants

Les paramètres du dernier détecteur sont sauvegardés dans le projet, pour
pouvoir rejouer la même détection sur une autre banque.

---

## 6. Écran « Atelier » — assemblage

### 6.1 Disposition

```
┌──────────────┬────────────────────────────────┬──────────────┐
│  Palette     │        Canevas d'assemblage    │  Inspecteur  │
│  des tuiles  │        (grille magnétique)     │  + coûts     │
│  non placées │                                │              │
└──────────────┴────────────────────────────────┴──────────────┘
```

### 6.2 Interactions

- **Glisser-déposer** une tuile depuis la palette vers le canevas.
- **Déplacer** une tuile déjà placée (aimantation à la grille).
- **Échanger** deux tuiles (`Alt` + glisser).
- **Retirer** une tuile du canevas (`Suppr` ou double-clic).
- **Rotation / miroir** (utile pour d'autres jeux ; désactivé par défaut).
- **Grille** : `cols × rows` paramétrable, pas = taille de tuile ; origine
  déplaçable.
- **Zoom / pan** identiques à l'écran Planche.
- **Annuler / refaire**.
- **Plein écran** du canevas (`F11`).

### 6.3 Aides visuelles

1. **Coût de jointure en direct** : à chaque déplacement, la barre d'état
   affiche le coût total et le coût par jointure ; les jointures les plus
   mauvaises clignotent en rouge.
2. **Superposition** : afficher la tuile survolée en semi-transparence sur la
   case cible avant de déposer.
3. **Fantôme de silhouette** : si l'utilisateur a chargé une capture d'écran de
   référence, afficher la silhouette attendue en surimpression.
4. **Indice de cohérence** par tuile : les tuiles dont le raccord est mauvais
   sont surlignées.
5. **Verrouillage** : verrouiller une tuile validée pour ne plus la bouger.

### 6.4 Validation

Bouton **« Valider le sprite »** (`Entrée`) :

1. vérifie que toutes les cases de la grille sont remplies (ou autorise les
   cases vides avec confirmation) ;
2. calcule l'image composée (rendu à la palette du jeu) ;
3. enregistre un `Sprite` (placements + bbox + horodatage) ;
4. ajoute l'image à l'atlas ;
5. écrit un événement `validate` dans le journal ;
6. propose immédiatement « **Sprite suivant** » : vide le canevas et pré-remplit
   avec les tuiles suivantes dans l'ordre de stockage.

---

## 7. Écran « Atlas »

- Une planche unique qui accumule tous les sprites validés.
- **Taille calculée automatiquement** :

```
si tous les sprites ont la même taille (cas courant) :
    n     = nombre de sprites
    cols  = ceil(sqrt(n * h / w))          # équilibre largeur/hauteur
    rows  = ceil(n / cols)
    atlas = (cols * (w + gap) - gap, rows * (h + gap) - gap)

sinon (tailles variables) :
    rangement en étagères (shelf packing) :
        largeur cible = ceil(sqrt(somme des aires) * 1,1)
        on remplit les lignes tant que ça tient, sinon nouvelle étagère
        hauteur = somme des hauteurs d'étagère
```

- Affichage : chaque sprite avec son nom, sa bbox, son nombre de tuiles.
- Réorganisation automatique (`Ré-optimiser`), ou manuelle (glisser un sprite).
- Export : `atlas.png` + `atlas.json` (rect de chaque sprite).
- Option : export d'un atlas **avec marges** pour éviter le sanglage des
  filtres lors de l'affichage.

---

## 8. Assemblage automatique

### 8.1 Fonction de coût

Le cœur du problème : trouver la permutation des tuiles qui minimise un coût
global. Le coût est une somme pondérée de plusieurs indices.

#### C1 — Continuité de silhouette (poids fort, mesuré comme le plus discriminant)

Pour une jointure horizontale entre la tuile A (gauche) et B (droite) :

```
cout_silhouette = Σ_y  [ masqueA(y, 23) ≠ masqueB(y, 0) ]
```

où `masque = (pixel ≠ transparent)`. Idem verticalement.

Normalisation : diviser par le nombre de pixels comparés (21 ou 24).

#### C2 — Continuité de couleur le long du raccord

Comparaison des valeurs de palette des colonnes adjacentes, mais **uniquement
sur les pixels opaques**, avec une tolérance (les dégradés des sprites
« numérisés » varient lentement) :

```
cout_couleur = Σ |vA - vB|  /  nombre de pixels opaques comparés
```

#### C3 — Continuité de contour (gradient)

Sur les pixels opaques, comparer la dérivée au bord : un contour qui entre d'un
côté doit ressortir de l'autre.

#### C4 — Pénalité de « trou »

Un sprite assemblé ne doit pas avoir de trou intérieur ni de morceau flottant :
```
cout_trou = nb de pixels transparents entourés de pixels opaques
```

#### C5 — Similarité de couleur globale

Deux tuiles voisines d'un même sprite partagent souvent la même dominante
(peau, métal, tissu). Histogramme de palette, distance χ².

#### C6 — Pénalité de doublon

Deux tuiles identiques ou quasi identiques ne doivent pas se retrouver côte à
côte (piège des poses successives).

#### Coût total

```
cout = w1*C1 + w2*C2 + w3*C3 + w4*C4 + w5*C5 + w6*C6
```

Les poids `w1..w6` sont **exposés dans l'interface** (curseurs) et sauvegardés
dans la recette. Valeurs par défaut proposées, d'après les mesures : `w1` fort,
`w2` moyen, `w3` faible, `w4` moyen, `w5` faible, `w6` moyen.

### 8.2 Méthodes de résolution

#### M1 — Hypothèses d'ordre (rapide, cible la « logique »)

On génère un catalogue de permutations candidates et on les classe par coût.
C'est la méthode à essayer **en premier**, car elle répond directement à
l'hypothèse « il y a une logique ».

Catalogue :

| Famille | Exemple |
|---|---|
| ligne / colonne | row-major, column-major |
| sens | lignes inversées, colonnes inversées, les deux |
| serpentin | boustrophédon (ligne paire →, ligne impaire ←) |
| transposition | `slot = col*rows + row` |
| blocs | 2 moitiés, 3 blocs, 4 blocs échangés |
| entrelacement | pairs/impairs, modulo k |
| pas | `slot = (a*i + b) mod N` pour tout `a` premier avec N |
| bits | inversion / permutation des bits de l'indice (N puissance de 2) |
| rotation | décalage circulaire de k |
| plans | tuiles rangées par plan (toutes les colonnes 0, puis 1, …) |

Chaque hypothèse est rendue en vignette + coût, et classée.

#### M2 — Recherche gloutonne + amélioration locale

1. placer la tuile la plus « riche » (le plus de pixels opaques) au centre ;
2. étendre case par case en choisissant la tuile qui minimise le coût local ;
3. améliorer par échanges 2-à-2 (2-opt) jusqu'à convergence.

#### M3 — Beam search

Construction ligne par ligne : on garde les `K` meilleurs assemblages partiels
(`K` = 200 à 5 000), on étend chaque ligne par les permutations restantes
filtrées par un coût de jointure minimal, puis on garde les `K` meilleurs.

Complexité maîtrisée pour 12–30 tuiles.

#### M4 — Recuit simulé

Permutation initiale aléatoire ou issue de M1/M2, puis recuit sur les échanges
de deux tuiles. Paramètres : température initiale/finale, nb d'itérations,
critère d'arrêt.

#### M5 — Recherche exhaustive avec élagage

Pour `N ≤ 9` tuiles : branch & bound avec borne inférieure = somme des coûts
minimaux par jointure. Garantit l'optimum.

#### M6 — Affectation (Hungarian)

Si la grille est 1 × N ou N × 1, le problème est une affectation linéaire :
résolution exacte par l'algorithme hongrois.

#### M7 — Aide par capture d'écran (optionnel, phase ultérieure)

Charger une capture du jeu, détecter le sprite, et scorer chaque assemblage par
corrélation avec l'image de référence.

### 8.3 Interface de l'assemblage automatique

- Panneau « **Assemblage auto** » avec :
  - choix de la méthode (M1…M6) ;
  - curseurs de poids ;
  - paramètres propres à la méthode ;
  - bouton « Lancer » avec barre de progression (thread séparé, UI non figée).
- Résultats présentés en **grille de vignettes classées** avec leur coût.
- Un clic sur une vignette charge l'assemblage dans le canevas, où il reste
  modifiable à la main.
- Bouton « **Appliquer à tous les groupes suivants** » (voir §9.3).

---

## 9. Découverte de la logique d'ordre

C'est la partie « recherche » de l'outil.

### 9.1 Données collectées

Pour chaque sprite validé, on connaît :

- `storage_index` de chaque tuile (indice dans la banque) ;
- `(gx, gy)` de chaque tuile dans le sprite ;
- donc le **slot** `= gy * cols + gx` ;
- et la **permutation locale** `P : slot → storage_index - base`.

On stocke aussi l'historique complet des déplacements (§10).

### 9.2 Modèles testés

Pour une banque et une grille données, on teste si les permutations observées
sont expliquées par une fonction simple.

| Modèle | Formule | Méthode |
|---|---|---|
| Identité | `slot = i` | direct |
| Transposition | `slot = (i % rows) * cols + i // rows` | direct |
| Affine mod N | `slot = (a·i + b) mod N` | force brute sur `a`, `b` |
| Pas | `slot = (i·k) mod N` | force brute sur `k` |
| Bits | `slot = permute_bits(i)` | recherche de la permutation de bits (N = 2^k) |
| Blocs | découpage en B blocs, ordre des blocs à trouver | force brute B ∈ 2..8 |
| Serpentin | `slot = i` pair/impair inversé | direct |
| Par plans | `slot = (i % planes) * (N/planes) + i // planes` | force brute `planes` |
| Par sprite | la permutation dépend de l'indice du sprite | comparaison des `P` entre sprites |

**Score d'un modèle** : nombre de sprites expliqués exactement / total, et
nombre de tuiles correctement placées.

**Rapport** : l'outil affiche le classement et, pour le meilleur modèle, une
visualisation « attendu vs observé » (matrice de correspondance).

### 9.3 Réapplication

Une **recette** (`Recipe`) contient :

```json
{
  "name": "banque1_3x4",
  "grid": { "cols": 3, "rows": 4 },
  "mapping": [ {"storage_index": 0, "slot": 0}, ... ],
  "fit": { "type": "affine", "a": 1, "b": 0, "exact": true }
}
```

Actions proposées :

1. **« Appliquer au groupe suivant »** : prend les `N` tuiles suivantes dans
   l'ordre de stockage et les place selon `mapping`.
2. **« Appliquer à toute la banque »** : génère tous les sprites restants.
3. **« Appliquer à une autre banque »** : même grille, même recette.
4. **« Vérifier »** : calcule le coût de chaque sprite généré et signale les
   anomalies (coût très supérieur à la médiane).

Si le modèle est **affine**, on peut aussi générer les placements sans table,
ce qui permet de traiter des banques plus grandes.

### 9.4 Export pour analyse externe

Bouton « **Exporter pour analyse** » :

- `analyse_placements.csv` :

  ```csv
  sprite,storage_index,gx,gy,slot,grid_cols,grid_rows
  0,0,0,0,0,3,4
  0,1,1,0,1,3,4
  ...
  ```

- `analyse_placements.json` : mêmes données + métadonnées (jeu, banque, grille,
  poids utilisés, coût par sprite).

- `analyse_permutations.txt` : pour chaque sprite, la permutation sous forme
  lisible (`0 1 2 3 … → 0 2 1 3 …`), ce qui permet de repérer visuellement un
  motif.

Ces fichiers sont destinés à être analysés (par l'utilisateur ou par moi) pour
trouver la formule exacte.

---

## 10. Journal des mouvements

### 10.1 Ce qui est enregistré

Chaque action modifiant un placement produit un événement :

```json
{ "t": "2026-11-05T23:45:12.318", "type": "place",
  "sprite": 3, "tile": 17, "from": null, "to": [2, 1] }
```

Types : `place`, `move`, `swap`, `remove`, `rotate`, `mirror`, `validate`,
`unvalidate`, `apply_recipe`.

### 10.2 Rejeu

- **Rejeu complet** : rejoue la séquence pour reconstituer l'état.
- **Rejeu partiel** : à partir d'un point donné.
- **Rejeu sur un autre groupe** : applique la séquence de positions finales aux
  tuiles suivantes.
- **Diff** : compare deux séquences pour voir si elles sont identiques.

### 10.3 Utilité pour l'analyse

Le journal permet de voir **comment** l'utilisateur est arrivé au bon
assemblage : quelles tuiles ont été déplacées, dans quel ordre, quelles
tentatives ont été abandonnées. C'est une donnée précieuse pour inférer une
règle (par exemple : « la tuile 5 va toujours en bas à gauche »).

---

## 11. Interface générale

### 11.1 Fenêtre principale

Onglets : **Planche** · **Atelier** · **Atlas** · **Analyse**

Barre d'état : coordonnées, zoom, tuile survolée, coût de jointure, état de
sauvegarde.

Barre d'outils : ouvrir, sauvegarder, annuler, refaire, zoom, outils de
sélection, lancer la détection, lancer l'assemblage auto, valider le sprite.

### 11.2 Raccourcis

| Touche | Action |
|---|---|
| `Ctrl+O` / `Ctrl+S` | ouvrir / sauvegarder |
| `Ctrl+Z` / `Ctrl+Y` | annuler / refaire |
| `V` `R` `M` | sélection / rectangle / déplacement |
| `G` | aimantation |
| `+` / `-` / `0` | zoom |
| `Espace` | pan |
| `Entrée` | valider le sprite |
| `Échap` | annuler l'action en cours |
| `Suppr` | supprimer la tuile sélectionnée |
| `F11` | plein écran |

### 11.3 Sauvegarde

- Sauvegarde automatique toutes les 60 s dans `projects/*.autosave.json`.
- Sauvegarde manuelle explicite.
- **Undo/redo** en mémoire (pas seulement sur disque).

---

## 12. Plan de développement

| Phase | Contenu | Livrable | Estimation |
|---|---|---|---|
| **P0** | Squelette Qt, ouverture d'image, zoom/pan, chargement de la banque Barbarian | fenêtre affichant la planche | 0,5 j |
| **P1** | Détecteur grille fixe, édition manuelle des rectangles, sauvegarde/chargement projet | écran Planche fonctionnel | 1 j |
| **P2** | Détecteurs D2–D5, contrôle qualité, comparaison de détections | détection automatique complète | 1 j |
| **P3** | Atelier : glisser-déposer, aimant, coût en direct, validation, atlas | assemblage manuel complet | 1,5 j |
| **P4** | Coût C1–C6, hypothèses M1, glouton M2, beam M3, recuit M4 | assemblage auto + classement | 2 j |
| **P5** | Journal, inférence de règle, réapplication, export CSV/JSON | écran Analyse | 1 j |
| **P6** | Finitions : raccourcis, undo/redo, autosave, doc, tests | version 1.0 | 0,5 j |

**Total : ~7,5 jours.**

### Jalons

- **J1 (fin P1)** : on peut charger `sprites_banque1.png`, voir les 252 tuiles
  encadrées, les corriger, sauvegarder.
- **J2 (fin P3)** : on peut reconstruire à la main la pose 0 et l'ajouter à
  l'atlas.
- **J3 (fin P4)** : l'outil propose un classement d'hypothèses et retrouve
  automatiquement au moins une pose.
- **J4 (fin P6)** : la règle est inférée, réappliquée à toute la banque, et
  exportée.

---

## 13. Tests d'acceptation

1. **Chargement** : la banque brute `BARB.DAT` offset `0x33A52` produit
   exactement 252 tuiles de 126 octets, et la tuile 0 est identique au rendu
   actuel (`sprites_banque1.png`).
2. **Détection** : le détecteur D1 avec `tw=24, th=21, gap=2` retrouve les 252
   tuiles du PNG.
3. **Édition** : déplacer/redimensionner/supprimer une tuile met à jour
   l'aperçu et le projet sauvegardé.
4. **Assemblage manuel** : reconstruire la pose qui fonctionnait déjà
   (tuiles 0–7 en 2×4) et la valider ; l'atlas contient 1 sprite de 48×84.
5. **Atlas** : avec 21 sprites de 72×84, la taille calculée est cohérente et
   l'export PNG s'ouvre correctement.
6. **Auto** : lancer M1 sur la banque 1 ; au moins une hypothèse doit produire
   un coût nettement inférieur à la médiane aléatoire.
7. **Règle** : valider 3 sprites, inférer la permutation, l'appliquer aux
   suivants ; vérifier que les sprites générés ont un coût comparable.
8. **Export** : le CSV contient bien `sprite, storage_index, gx, gy, slot`.

---

## 14. Risques et limites

| Risque | Impact | Mitigation |
|---|---|---|
| La métrique de silhouette confond poses voisines | classement biaisé | combiner C1–C6, afficher plusieurs candidats, laisser trancher l'utilisateur |
| Les tuiles ne sont pas toutes de 24×21 | découpage faux | détecteurs D2–D5 + édition manuelle |
| L'ordre dépend de chaque sprite (pas de règle globale) | réapplication impossible | stocker une recette par sprite et le signaler |
| Qt ne se lance pas (Wayland/X11) | blocage | tester `QT_QPA_PLATFORM=xcb` ; repli web |
| Performances sur de grosses banques | lenteur | numpy + cache des bords + calcul incrémental |
| Ambiguïté irréductible (tuiles symétriques) | plusieurs solutions | proposer les N meilleures, laisser choisir |

---

## 15. Annexes

### A. Palettes Barbarian (format 0RGB Atari ST)

```
écran 1 (jungle)        : 000 430 320 542 230 777 047 370 051 500 700 740 760 444 006 777
écran 2 (arène)         : 000 437 416 304 310 210 467 370 051 500 700 740 760 444 006 777
écran 3 (trône)         : 000 555 333 741 530 420 406 370 051 500 700 740 760 444 006 777
écran 4 (cachot)        : 000 056 425 303 774 743 420 370 051 500 700 740 760 444 006 777
écran 5 (hall)          : 000 555 333 222 742 530 320 370 051 500 700 740 760 444 006 777
```

Sprites : couleurs 12 à 15.

### B. Décodage d'une tuile (pseudo-code)

```
def decode_planar2_24x21(blk):        # blk = 126 octets
    px = [[0]*24 for _ in range(21)]
    for r in range(21):
        for c in range(3):
            b0 = blk[r*6 + c*2]
            b1 = blk[r*6 + c*2 + 1]
            for bit in range(8):
                p0 = (b0 >> (7-bit)) & 1
                p1 = (b1 >> (7-bit)) & 1
                px[r][c*8+bit] = p0 | (p1 << 1)
    return px
```

### C. Commandes utiles

```bash
# régénérer les PNG actuels
python3 tools/extract_graphismes.py

# lancer l'outil (une fois développé)
python3 -m venv .venv
.venv/bin/pip install PySide6 numpy
.venv/bin/python tileforge/main.py
```

### D. Références dans le binaire

| Adresse | Rôle |
|---|---|
| `0x3970` | routine de dessin d'un objet composé de tuiles |
| `0x3814` | blit d'une tuile (variante « opacité ») |
| `0x38C2` | blit d'une tuile (variante « transparence ») |
| `0x7194` | table des 5 × 6 couleurs d'écran (`-$bda(a4)`) |
| `0x7014` | table des 26 tailles de blocs audio (`-$af2(a4)`) |
| `0x720C` | table des 5 longueurs d'écrans compressés (`-$c30(a4)`) |
| `0xE5F8` | chargement de `BARB.DAT` et calcul des pointeurs de banques |
| `0xE8A6` | décompresseur RLE |

---

*Fin du plan.*
