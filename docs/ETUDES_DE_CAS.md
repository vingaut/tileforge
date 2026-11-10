# Études de cas — deux jeux extraits de bout en bout

> **Zéro intervention humaine, hormis le prompt initial.**
>
> Les deux extractions décrites ici ont été menées par un agent à partir d'une
> seule consigne en langage naturel. Aucun réglage à la souris, aucune sélection
> d'offset à la main, aucune palette corrigée manuellement, aucune retouche
> d'image. L'agent a lu les fichiers, écrit ses propres scripts, compilé les
> bibliothèques manquantes et vérifié ses résultats par recoupement.

> **Aucun graphisme extrait n'est publié dans ce dépôt.** Les sprites, décors et
> écrans appartiennent à leurs ayants droit (Nintendo, Team17) et restent hors
> du dépôt. Ce document ne décrit que la **démarche** : formats, chaîne d'outils,
> offsets, métriques. Voir la note juridique en fin de document.

---

## 1. Pourquoi ces deux cas

Les deux jeux ont été choisis parce qu'ils représentent les deux extrémités du
problème :

| | **The Legend of Zelda** (NES, 1986) | **Project-X** (Amiga, 1992) |
|---|---|---|
| Format d'entrée | ROM `.nes` iNES, un seul fichier | Archive de 4 images disque `.ipf` |
| Où sont les graphismes | dans la PRG, copiés en VRAM par le jeu | dans des exécutables hunk, recompressés |
| Compression | aucune (blocs CHR bruts) | Imploder, **imbriqué sur deux niveaux** |
| Difficulté principale | retrouver les offsets et les règles d'assemblage | traverser disque → FS → décompression → hunk |
| Ce que TileForge a apporté | l'essentiel (scan, banques, atlas) | le point d'entrée et la reconnaissance de format |

Le premier cas montre TileForge **dans son domaine** ; le second montre **où il
s'arrête aujourd'hui**, et c'est tout aussi utile.

---

## 2. Cas 1 — The Legend of Zelda (NES, EU)

### 2.1 Point de départ

ROM `Legend of Zelda, The (1987-11-15)(Nintendo)(EU).nes`, 131 088 octets,
iNES, mapper MMC1, 8 banques PRG de 16 Kio, **0 banque CHR**. C'est le cas
intéressant : les graphismes ne sont pas dans une banque CHR dédiée, ils sont
dans la PRG et le jeu les copie en VRAM au chargement.

### 2.2 Chaîne suivie

1. **En-tête et cartographie** — `inspect_file` puis `cartography` : mapper 1,
   8 banques PRG, 0 CHR, zones classées par entropie, tables de pointeurs
   probables.
2. **Recherche de graphismes** — `scan_graphics` en format `nes` : 582 candidats
   testés, 103 notés, aperçus PNG générés pour chaque candidat.
3. **Confirmation du format** — `identify_format` : 8×8, 2 plans, plans
   séquentiels (8 octets plan 0 puis 8 octets plan 1).
4. **Recoupement des offsets par trois sources indépendantes** :
   * le désassemblage 6502 (REA + rizin) ;
   * la table de pointeurs du loader de CHR, lue directement dans la banque 3 ;
   * le rendu visuel (l'alphabet et Link sont immédiatement reconnaissables).
   Les blocs se suivent exactement, ce qui valide la chaîne.
5. **Validation dans TileForge** — `open_bank` puis `validate_sprite` sur
   19 sprites Link/objets, `export_atlas` pour l'atlas, `save_project` pour le
   projet `.tileforge.json`.
6. **Rendu des planches** — script Python (Pillow) qui applique les palettes
   lues dans les *transfer records* du jeu, et compose les sprites selon les
   trois règles d'assemblage découvertes.

### 2.3 Résultats

* **15 blocs graphiques** identifiés et localisés (offsets PRG *et* offsets
  fichier), dont 6 blocs de sprites, 3 blocs de boss, 3 blocs de décor,
  2 blocs de police et 1 bloc de splash.
* **3 règles d'assemblage** reconstituées et vérifiées :
  * `wide` — 16×16 = 4 tuiles (Link, armes, objets) ;
  * `mirror` — 16×16 = 2 tuiles (8×16) + leur miroir horizontal (ennemis) ;
  * `boss` — 32×32 = 8 tuiles + miroir (boss).
  La règle `mirror` n'est pas une hypothèse : elle est confirmée par la routine
  `Anim_WriteMirroredSpritePair` du désassemblage.
* **10 palettes de niveau** (Overworld + donjons 1→9) extraites des blocs
  `LevelInfo`, plus les palettes spéciales (menu, écran-titre, splash) et les
  palettes de boss injectées en `$3F1C`.
* **65 fichiers produits** : planches de palettes, planches de sprites par
  variante de couleur, décors par palette de fond, versions 1× en RGBA
  transparent, projet TileForge, atlas et manifeste JSON.

### 2.4 Outils utilisés

**TileForge (MCP)** — analyse et validation structurelle :

| Outil | Usage |
|---|---|
| `inspect_file` | en-tête iNES, taille, mapper |
| `cartography` | zones, entropie, tables de pointeurs |
| `scan_graphics` | 582 candidats, 103 notés |
| `identify_format` | confirmation 2 plans / plans séquentiels |
| `open_bank` | ouverture des banques dans le projet |
| `validate_sprite` | 19 sprites validés |
| `export_atlas` | atlas de sortie |
| `save_project` | projet `.tileforge.json` |

**REA** — désassemblage et cross-check :

| Outil | Usage |
|---|---|
| `execute_rizin_command` | désassemblage 6502, lecture de la table de pointeurs du loader de CHR |
| provider Ghidra 6502 | import de la banque 7, 15 procédures, xrefs |

**Hors outils** — Python/Pillow : décodage NES, composition des sprites, rendu
des planches avec les palettes du ROM.

---

## 3. Cas 2 — Project-X (Amiga, Team17 1992)

### 3.1 Point de départ

Une archive ZIP contenant **4 images disque IPF** (CAPS/SPS) de 1 048 872 octets
chacune. Un IPF n'est pas une image de disque : c'est un flux de cellules
magnétiques avec des métadonnées de densité variable.

### 3.2 Chaîne suivie

1. **Détection du conteneur** — `inspect_file` : archive reconnue, 4 membres IPF
   listés, inventaire des compressions candidates.
2. **Décodage IPF → ADF** — bibliothèque SPS (`capsimage`) compilée à la main
   (pas de CMake sur la machine), puis décodeur MFM écrit de zéro. Trois pièges :
   la synchro `0x4489` n'est pas alignée sur l'octet (première synchro au bit
   1 779), chaque `long` occupe **4 mots MFM** dans l'ordre `w0,w2 / w1,w3`, et
   les pistes font 82 cylindres et non 80.
   *Validation :* les 11 secteurs d'une piste donnent `FF 00 08 0B`,
   `FF 00 09 0A`… soit une permutation parfaite des numéros de secteur.
   *Contrôle indépendant :* la règle MFM (horloge à 1 seulement entre deux
   données à 0) est respectée sur 50 144 cellules sur 50 145.
3. **Système de fichiers** — AmigaDOS OFS. **Tous les checksums sont faux**
   (bloc de démarrage à `0xFFFFFFF2` au lieu de `0xFFFFFFFF`) : c'est
   **Rob Northen Copylock**, et c'est volontaire. Les données sont intactes, un
   parseur OFS maison suffit. **28 fichiers** extraits.
4. **Décompression** — les 28 fichiers commencent par `ATN!`, signature de
   l'**Imploder**. Particularité : le bloc compressé est **en fin de fichier** et
   l'image se reconstruit **à rebours**. Code de référence compilé, 28/28
   décompressés.
5. **Décompression imbriquée** — le scan des fichiers décompressés révèle
   **31 blocs `ATN!` cachés à l'intérieur des exécutables**. C'est là que sont
   les graphismes : le premier passage s'arrêtait un niveau trop tôt.
6. **Graphismes** — les blocs de 102 400 octets sont des planches **640×256 en
   5 plans** (640 × 256 × 5 / 8 = 102 400). Rendu en plane-major, palette du
   niveau, puis découpe par composantes connexes.
7. **Palettes** — le premier rendu utilisait une **table de fondu** et donnait
   des images fausses. La vraie palette est constituée de **6 palettes
   thématiques de 32 mots `0x0RGB`** stockées à la suite en fin de chaque
   fichier `LPI`, une par niveau. Une fois l'appariement corrigé, les images
   sont justes.

### 3.3 Résultats

* **4 ADF** de 901 120 octets, 1 749 secteurs utiles sur 1 760 par disquette.
* **28 fichiers** extraits et **28/28** décompressés.
* **31 blocs Imploder imbriqués** décompressés.
* **10 planches de sprites** (640×256, 5 plans), deux par niveau.
* **1 043 sprites** découpés (composantes connexes, export RGBA transparent).
* **6 écrans de chargement** 256×256 restitués avec les bonnes palettes, après
  correction de deux défauts : 256 pixels utiles dans un bitmap de 320 (64
  colonnes de padding) et 4 images sur 6 qui n'utilisent que **5 plans** alors
  que le code en déclare 6 (le 6ᵉ plan a une densité de bits nulle).

### 3.4 Outils utilisés

**TileForge (MCP)** — point d'entrée et inventaire :

| Outil | Usage |
|---|---|
| `inspect_file` | archive, 4 membres IPF, compressions candidates |
| `list_tile_formats` | inventaire du catalogue, constat des manques Amiga |
| `scan_graphics` | tentative de scan (non concluante : format `chunky8` choisi automatiquement, inadapté aux bitplanes) |
| `list_emulator_cores` | vérification de la voie « émulation » (aucun cœur installé) |

**REA** — reconnaissance de format :

| Outil | Usage |
|---|---|
| `rea_search` | écarter deux fausses pistes (aucun décodeur IPF, aucun FS Amiga au catalogue) |
| `execute_rizin_command` | rizin reconnaît nativement le **hunk Amiga** : `arch m68k`, `os AmigaOS`, section `hunk_0_code` avec `paddr` et `vaddr` — c'est ce qui permet de relier les adresses absolues du code aux offsets fichier |

**Hors outils** — bibliothèque SPS (`capsimage`) pour l'IPF, `explode.c`
(`lab313ru/AmigaImploder`) pour l'Imploder, capstone pour le m68k,
Python/Pillow/numpy/scipy pour le rendu et la découpe.

---

## 4. Ce que « zéro intervention humaine » veut dire exactement

Il ne faut pas se raconter d'histoires : **l'agent a écrit beaucoup de code**
(décodeur MFM, parseur OFS, rendu planaire, découpe de sprites, pilote de
décompression). Ce qui est nul, c'est l'intervention *humaine* :

| Intervention humaine | Statut |
|---|---|
| Prompt initial | **seule intervention** |
| Choisir un offset à la souris | aucune |
| Corriger une palette à l'œil | aucune |
| Découper un sprite manuellement | aucun |
| Réencoder une image | aucun |
| Relancer un script après ajustement | aucun |

Toutes les décisions techniques (quel offset, quel format, quelle palette,
quelle géométrie) ont été prises par l'agent, puis **vérifiées par recoupement**
plutôt que par validation humaine :

* la permutation des numéros de secteur valide le décodage MFM ;
* la règle MFM (50 144 cellules sur 50 145) valide l'assignation horloge/donnée ;
* la table de pointeurs du loader de CHR recoupe les offsets Zelda ;
* la continuité des blocs (`0xC11B + 0x820 = 0xC93B`) valide la chaîne Zelda ;
* la cohérence visuelle des 6 écrans valide l'appariement des palettes.

C'est ce dernier point qui compte : **un résultat non vérifié n'est pas un
résultat**. L'agent a systématiquement cherché un oracle indépendant.

---

## 5. Récapitulatif des outils

| Catégorie | Outil | Rôle dans ces deux cas |
|---|---|---|
| MCP | `inspect_file` | point d'entrée, détection conteneur/format |
| MCP | `cartography` | zones, entropie, pointeurs (Zelda) |
| MCP | `scan_graphics` | 582 candidats (Zelda), tentative Amiga |
| MCP | `identify_format` | confirmation du format de tuiles |
| MCP | `open_bank` / `validate_sprite` / `export_atlas` / `save_project` | projet et atlas Zelda |
| MCP | `list_tile_formats` / `list_emulator_cores` | inventaire des capacités |
| REA | `rea_search` | cadrage du catalogue disponible |
| REA | `execute_rizin_command` | 6502 (Zelda), hunk Amiga (Project-X) |
| REA | provider Ghidra 6502 | xrefs et procédures (Zelda) |
| Hors outils | SPS `capsimage` | IPF → flux MFM |
| Hors outils | `AmigaImploder` (`explode.c`) | décompression Imploder |
| Hors outils | capstone | désassemblage m68k de travail |
| Hors outils | Python / Pillow / numpy / scipy | rendu planaire, palettes, découpe |

---

## 6. Ce que ces deux cas prouvent — et ce qu'ils ne prouvent pas

**Ils prouvent** que la chaîne « fichier inconnu → graphismes exploitables »
est réalisable sans intervention humaine, et que le **recoupement par oracle**
est une méthode fiable pour valider chaque étape sans humain dans la boucle.

**Ils ne prouvent pas** que TileForge couvre ces cas. Sur Zelda, TileForge a fait
l'essentiel (scan, banques, atlas) mais le rendu coloré a dû être fait à côté,
TileForge ignorant alors le paramètre `palette`. Sur Project-X, TileForge n'a
servi qu'à l'inventaire d'entrée : ni IPF, ni AmigaDOS, ni Imploder, ni rendu
planaire, ni palettes `0x0RGB` n'étaient disponibles.

C'est exactement ce que la feuille de route
[`docs/tileforge_upgrade.md`](tileforge_upgrade.md) propose
de combler : disque Amiga, décompresseurs (dont la **détection imbriquée
récursive**, qui est ce qui a débloqué les sprites), parseur hunk, **mode
« écran » plan-major** à côté du mode « tuiles », extraction et appariement de
palettes, découpe automatique de sprites.

---

## 7. Reproduire

Les deux chaînes ne dépendent que de fichiers fournis par l'utilisateur :

* **Zelda** : le ROM `.nes` et un script Python (Pillow). Les offsets et les
  palettes sont dans un manifeste JSON, donc rejouables.
* **Project-X** : les 4 IPF, la bibliothèque SPS, le décompresseur Imploder, et
  les scripts de décodage. Aucun état caché : tout est déterministe à partir des
  images disque.

Dans les deux cas, le résultat est **reproductible** : relancer la chaîne sur les
mêmes fichiers redonne exactement les mêmes offsets et les mêmes palettes.

---

## 8. Note juridique

Les graphismes extraits (sprites, décors, écrans, palettes appliquées) sont des
œuvres protégées. Ils **ne sont pas publiés** dans ce dépôt et ne doivent pas
l'être : ni en documentation, ni en exemple, ni en « petite vignette ».

Ce qui est publiable, et qui l'est ici :

* les **formats** et les **algorithmes** (MFM, Imploder, hunk, planar, copper) ;
* les **offsets** et les **structures** de données ;
* les **méthodes de vérification** (oracles, recoupements) ;
* les **métriques** (nombre de blocs, de sprites, de palettes).

Les captures présentes dans `docs/` sont celles de l'**interface de TileForge**
sur sa planche de démonstration synthétique : aucune ne contient d'asset de jeu.

Cette règle est celle du dépôt, rappelée en fin de `README.md` (« Repository
policy ») et dans [`CONTRIBUTING.md`](../CONTRIBUTING.md) : les ROMs, disquettes
et graphismes extraits de jeux sont exclus par `.gitignore`.
