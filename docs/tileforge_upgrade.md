# TileForge — retour d'expérience Amiga et feuille de route

> Rédigé après l'extraction complète de **Project-X** (Team17, Amiga 1992) :
> 4 disquettes IPF protégées Copylock → ADF → AmigaDOS OFS → Imploder (imbriqué)
> → planches de sprites et écrans de chargement.
>
> Ce document liste **ce qui a manqué à TileForge** à chaque étape, avec, pour
> chaque manque, le cas réel qui l'a révélé. Il est destiné à servir de base de
> travail pour la reprise du développement.
>
> Il ne contient **aucun graphisme extrait** : uniquement des formats, des
> structures et des métriques. Voir la note juridique de
> [`docs/ETUDES_DE_CAS.md`](ETUDES_DE_CAS.md).

> **État au 10 novembre 2026 (TileForge 1.5.0).** Les itérations 1 à 3 de
> cette feuille de route sont implémentées : disques ADF/ADZ (OFS/FFS,
> checksums tolérés), Imploder et RNC, détection imbriquée, hunks, copper,
> rendu planaire row/plane-major, palettes `0x0RGB`, découpe de sprites. Six
> outils MCP exposent la chaîne. Restent ouverts : le décodeur IPF/MFM natif,
> DMS, et les décompresseurs CrunchMania/Turbo Packer/StoneCracker (signatures
> détectées, blocs signalés). Voir [`AMIGA.md`](AMIGA.md).

---

## 0. Résumé exécutif

Sur cette tâche, TileForge a servi **deux fois** : à l'inventaire d'entrée
(`inspect_file` : archive, 4 IPF, formats/compressions candidats) et à une
tentative de scan (`scan_graphics`). Tout le reste — décodage IPF, MFM,
système de fichiers, décompression, rendu planaire, palettes — a été fait
hors de TileForge, faute de support.

Le constat est simple : **TileForge est un excellent outil de tuiles console,
mais ce n'est pas encore un outil de « rétro-ingénierie graphique ».** L'Amiga
n'est pas un cas périphérique : c'est la plateforme où le travail manuel est le
plus coûteux, donc celle où l'outillage rapporte le plus.

Les manques se répartissent en cinq couches, à ajouter dans cet ordre :

| Priorité | Couche | Ce qui manque | Blocage réel constaté |
|---|---|---|---|
| **P0** | Disque | IPF/CAPS, ADF, OFS/FFS, tolérance aux checksums invalides | Aucun fichier n'était atteignable |
| **P0** | Compression | Imploder (10 magics), RNC, CrunchMania, **détection imbriquée** | 28 fichiers illisibles |
| **P0** | Exécutable | Hunk Amiga, table des segments, adresses de chargement | Impossible de relier code ↔ données |
| **P0** | Graphismes | Rendu planaire libre, **mode écran**, palettes `0x0RGB`, copper | 6 écrans + 10 planches invisibles |
| **P1** | Sprites | Découpe automatique, grille, pré-décalage, animations | 1043 sprites à trier à la main |
| **P1** | Palettes | Scan, scoring, tables de fondu, appariement image↔palette | Couleurs fausses sur 5 images sur 6 |
| **P2** | Émulation | Cœur PUAE + Kickstart, snapshot RAM | Voie de secours absente |
| **P2** | Générique | Pipeline « format inconnu », API de plugins, rapport | Tout a été scripté à la main |

---

## 1. Couche disque — le point d'entrée manquant

### 1.1 Le cas réel

L'utilisateur fournit une archive ZIP contenant **4 fichiers `.ipf`**. TileForge
sait parfaitement ouvrir l'archive et lister les membres (`inspect_file` fait
très bien ce travail), mais aucun outil en aval ne peut lire un IPF.

Un IPF n'est **pas** une image de disque : c'est un flux de cellules magnétiques
(CAPS/SPS) avec des métadonnées de densité variable. Il faut la bibliothèque
SPS pour le relire, puis **décoder le MFM soi-même**.

### 1.2 Ce qu'il faut ajouter

**A. Import disque**
- `.adf` / `.adz` (le plus simple, couvre 90 % des cas)
- `.ipf` : soit un décodeur natif, soit un appel à un convertisseur externe
  documenté (`capsimage` + un `ipf2adf` maison). La licence SPS n'est pas libre,
  donc prévoir un **chemin de repli** : détecter l'IPF, expliquer pourquoi il
  n'est pas lisible, et proposer la conversion.
- `.dms`, `.hdf`, `.lha` (archives Amiga), `.iso` pour les compilations CD32.

**B. Décodage MFM** (si le décodeur IPF est intégré)
Le décodeur doit gérer les trois pièges rencontrés :
1. la synchro `0x4489` n'est **pas alignée sur l'octet** (première synchro
   tombait au bit 1779) → lecteur bit à bit obligatoire ;
2. l'**entrelacement pair/impair** : chaque `long` occupe **4 mots MFM** dans
   l'ordre `w0,w2 / w1,w3` ;
3. les pistes font 82 cylindres (pas 80) et il faut ignorer proprement les
   cylindres hors géométrie.

**C. Système de fichiers AmigaDOS**
- OFS et FFS, blocs de 512 ou 1024 octets.
- Arborescence complète : bloc racine (880), table de hachage (72 entrées),
  chaînage `next_hash` / `parent`, blocs de données (488 octets en OFS).
- **Point critique** : ce disque a **tous ses checksums faux**. Le bloc de
  démarrage somme à `0xFFFFFFF2` au lieu de `0xFFFFFFFF`, le bloc racine
  contient `0x31313131` au lieu de son checksum. C'est **Rob Northen Copylock**,
  et c'est volontaire.
  → TileForge doit **ouvrir quand même**, signaler « checksums invalides —
  probablement une protection », et proposer un mode « lecture brute ».
  Un outil qui refuse le volume est inutilisable sur une bonne partie du
  catalogue Amiga.

**D. Détection de protection**
Reconnaître au passage les chaînes `Copylock Amiga`, `Rob Northen`,
`RNC`, `SPS`, et prévenir : *les checksums ne sont pas fiables, les données
sont peut-être chiffrées*. Cela change la stratégie de tout le reste.

### 1.3 API suggérée

```
DiskSource.open(path) -> Volume
Volume.list() -> [Node]
Volume.extract(node) -> bytes
Volume.warnings -> ["checksums invalides (Copylock probable)", ...]
```

Le reste du pipeline ne doit voir que des `bytes` : c'est le contrat qui permet
d'enchaîner décompression → graphismes sans se soucier de la provenance.

---

## 2. Couche compression — le verrou principal

### 2.1 Le cas réel

Les 28 fichiers extraits commencent tous par `ATN!`. TileForge ne connaît pas
cette signature. Deux jours de travail ont été nécessaires pour identifier
**Imploder** (le manuel WHDLoad le confirme : « ATN!: identical to IMP! only id
is different »), comprendre que le bloc compressé est **en fin de fichier** et
que l'image se reconstruit **à rebours**.

Puis, une fois les exécutables obtenus, on découvre que **des blocs `ATN!` sont
imbriqués à l'intérieur** : c'est là que se trouvent les planches de sprites.
Sans détection récursive, on passe à côté de 100 % des graphismes.

### 2.2 Ce qu'il faut ajouter

**A. Décompresseurs Amiga** (par ordre d'importance)

| Format | Magics à reconnaître | Remarque |
|---|---|---|
| **Imploder** | `IMP!`, `ATN!`, `BDPI`, `CHFI`, `Dupa`, `EDAM`, `FLT!`, `M.H.`, `PARA`, `RDC9` | 10 variantes, même algorithme. Bloc compressé **en fin de fichier**, décompression **à rebours** |
| **RNC ProPack** | `RNC\x01` (PC), `ATN!` ambigu → heuristique | méthodes 1 et 2, chiffrement optionnel (clé 16 bits) |
| **CrunchMania** | `CrM!`, `CrM2` | |
| **Turbo Packer** | `TPWM` | pas de taille dans l'en-tête |
| **Imploder 2 / FImp** | | |
| **Pack-Ice, StoneCracker, Titanics** | | |

**B. Détection imbriquée récursive** — *indispensable*
Après chaque décompression, rescanner le résultat pour de nouveaux magics, et
recommencer (profondeur limitée à ~4). C'est exactement ce qui a débloqué les
sprites : `lv1f` → Imploder → exécutable hunk → **3 blocs Imploder imbriqués**
→ 2 planches de sprites de 102 400 octets.

**C. Décompression « en place »**
L'Imploder écrit **à rebours** dans le même buffer. Un décompresseur naïf qui
alloue `taille_décompressée` et lit depuis l'en-tête échoue. Prévoir une API
qui autorise l'écrasement de la source et documenter le sens d'écriture.

**D. Vérification**
Les CRC de l'en-tête Imploder ne correspondent pas toujours (chiffrement,
protection). Ne pas rejeter sur CRC : **essayer, mesurer, avertir**.

### 2.3 API suggérée

```
decompress(data) -> (bytes, format, warnings)
scan_nested(data) -> [Blob(offset, format, decompressed)]
```

---

## 3. Couche exécutable — relier le code aux données

### 3.1 Le cas réel

Les fichiers décompressés sont des **exécutables hunk Amiga**. Sans parser la
table des segments, impossible de savoir où finit le code et où commencent les
données. Et surtout : les graphismes ne sont pas dans un conteneur, ils sont
**au milieu du code**, référencés par des adresses absolues.

C'est en lisant six instructions que tout s'est débloqué :

```
lea.l   $12cd6.l, a0      ; adresse de l'image
move.l  a0, d0
lea.l   $21d7a.l, a1      ; liste copper
move.l  #6, d2            ; 6 bitplanes
adda.l  #$2800, a0        ; 10 240 octets par plan
```

Trois informations capitales y sont encodées : **où**, **combien de plans**,
**quelle taille de plan**.

### 3.2 Ce qu'il faut ajouter

**A. Parseur hunk**
- `HUNK_HEADER`, `HUNK_CODE` (0x3E9), `HUNK_DATA` (0x3EA), `HUNK_BSS`,
  `HUNK_RELOC32` (0x3EC), `HUNK_SYMBOL`, `HUNK_END`.
- Table des tailles (attention : les tailles peuvent porter des drapeaux dans
  les bits hauts — rencontré sur `lv1f`).
- Calcul de l'**adresse de chargement** : c'est ce qui permet de convertir une
  adresse absolue du code en offset fichier (`offset = vaddr − base`).

> À noter : **rizin fait déjà ce travail** et c'est l'apport le plus utile de
> REA sur cette tâche. Il a reconnu `arch m68k / os AmigaOS` et donné
> `section hunk_0_code paddr 0x20 vaddr 0x8000`. TileForge devrait s'appuyer
> sur la même bibliothèque ou reproduire ce comportement.

**B. Désassembleur m68k + suivi des références**
C'est le cœur du gain de productivité. Détecter les motifs :

```
41F9 <addr>          lea.l <addr>.l, aN
207C <addr>          movea.l #<addr>, aN
23FC <addr> <dst>    move.l #<addr>, <dst>
```

et, pour chaque cible, proposer : « donnée à l'offset X, taille Y, type
probable (bitmap / copper / palette / code) ».

**C. Séparation code / données**
Une carte du fichier (code, données, zéros, haute entropie) avec la même
présentation que la cartographie ROM existante.

---

## 4. Couche graphismes — le mode « écran » qui n'existe pas

### 4.1 Le cas réel

TileForge ne sait rendre que des **tuiles** (8×8, 16×16, 24×21). Or l'Amiga
stocke des **bitmaps pleine page**, et dans deux dispositions différentes :

- **row-major** (plan 0 ligne 0, plan 1 ligne 0, … puis ligne 1) ;
- **plane-major** (tous les plans à la suite, 10 240 octets chacun).

Les écrans de chargement sont en plane-major 256×256, dans un bitmap de 320 de
large (64 colonnes de padding à droite). **Aucun outil ne devine ça.**

### 4.2 Ce qu'il faut ajouter

**A. Mode « écran »** à côté du mode « tuiles »
- largeur / hauteur / nombre de plans **libres** (1 à 8)
- row-major **et** plane-major
- stride indépendant de la largeur (le cas 256-dans-320 est la norme, pas
  l'exception)
- rendu indexé + palette, export PNG, et export « atlas »

**B. Détection automatique de géométrie**
Un score de cohérence (colonnes **et** lignes) permet de trouver les bitmaps
dans un binaire. C'est ce qui a permis de localiser les images :
- score = fraction de pixels adjacents égaux
- un vrai bitmap : 0,8–0,95 ; du code ou du bruit : ~0,03
- balayer les offsets, les largeurs (256/288/320/352/384), les plans (3 à 6)

**C. Détection du padding**
Le cas « image de 256 de large dans un bitmap de 320 » se détecte par un pic
net de la différence inter-colonnes à x = 256. TileForge doit le signaler et
proposer la largeur utile.

**D. Listes copper**
C'est la source d'information la plus fiable sur l'Amiga :
- `BPLCON0` (0x0100) → nombre de plans (bits 12-14) ;
- `COLOR00..31` (0x0180–0x01BE) → **la palette** ;
- `BPL1PT..8PT` (0x00E0–0x00EE) → adresses des plans ;
- `DIWSTRT`/`DIWSTOP` (0x008E/0x0090), `DDFSTRT`/`DDFSTOP` (0x0092/0x0094)
  → fenêtre d'affichage et géométrie ;
- `BPL1MOD`/`BPL2MOD` (0x0108/0x010A) → modulo (padding).
Un parseur de copper list donne **gratuitement** les plans, la palette et la
géométrie. C'est la première chose à implémenter.

---

## 5. Couche palettes — le défaut le plus visible

### 5.1 Le cas réel

Les six écrans de chargement ont d'abord été rendus avec une table trouvée au
hasard : tous violets, avec des couleurs manifestement fausses. La vraie
palette n'était **pas dans le fichier image** : c'était une des **six palettes
thématiques** (une par niveau) stockées à la fin de chaque fichier LPI, en six
blocs consécutifs de 32 mots `0x0RGB`.

Une fois le bon appariement fait, les images sont devenues justes :
espace, montagnes enneigées, volcan, rivière, lentille, fusée.

### 5.2 Ce qu'il faut ajouter

**A. Extraction de palettes `0x0RGB`**
- balayer les suites de mots < 0x1000, de longueur 16/32/64 ;
- critères : premier = 0 (noir), nombre de valeurs distinctes, absence de
  motifs de registres copper.

**B. Appariement image ↔ palette**
Quand plusieurs palettes coexistent (ici six), il faut **choisir la bonne**.
Pistes :
- tester toutes les combinaisons et scorer le rendu (continuité des couleurs
  entre pixels voisins, respect des dégradés) ;
- exploiter le contexte : l'image `LPI2` du niveau 2 utilise la palette du
  niveau 2 ;
- exposer le choix à l'utilisateur (liste déroulante) plutôt que de trancher.

**C. Tables de fondu**
Chaque fichier contenait aussi des **tables de fondu** (suites de palettes
dégradées). Il faut les reconnaître et les exclure des candidates, sinon on
obtient des images « à moitié noires » qui semblent valides.

**D. Détection du nombre de plans réel**
Ici, le code déclarait 6 plans mais **le 6ᵉ plan était vide** sur 4 images sur 6
(densité de bits = 0,000). Un outil doit calculer la densité par plan et
signaler « plan vide — probablement 5 plans utiles ».

---

## 6. Couche sprites — de la planche au sprite

### 6.1 Le cas réel

Les planches font **640×256, 5 plans** (102 400 octets). Elles contiennent des
vaisseaux, des ennemis, des projectiles, des explosions et des items, disposés
en grille irrégulière. 1043 composantes connexes ont été extraites, dont
beaucoup de fragments (un vaisseau avec ses flammes séparées = 3 sprites).

### 6.2 Ce qu'il faut ajouter

**A. Découpe automatique**
- composantes connexes (8-connexité) sur le masque « index ≠ 0 » ;
- seuil de surface, fusion des composantes proches (fermeture morphologique
  avec un rayon de 1-2 px) pour ne pas couper les vaisseaux en morceaux ;
- export RGBA avec transparence sur l'index 0.

**B. Détection de grille**
Les planches sont presque toujours organisées en cellules régulières
(16×16, 32×32, 48×48). Détecter la période par autocorrélation des marges
(colonnes/lignes vides) et proposer un découpage en cellules.

**C. Détection de pré-décalage**
Sur Amiga, les sprites sont souvent stockés **pré-décalés** (16 copies pour un
défilement fluide). Signature : des blocs très similaires à un décalage
horizontal près. Détecter et ne garder qu'une copie + le pas.

> Sur ce jeu, les deux moitiés de chaque planche sont identiques à ~90 % sans
> décalage : ce sont probablement deux variantes de frame. Un outil devrait
> proposer les deux hypothèses (décalage vs variante) au lieu de laisser
> l'utilisateur deviner.

**D. Groupement d'animations**
Une fois les sprites découpés, regrouper par similarité (SSIM ou distance de
Hamming sur le masque) pour reconstituer les séquences (marche, tir, explosion)
et exporter des planches animées.

---

## 7. Couche générique — ce qui manque quel que soit le système

Ces manques ne sont pas spécifiques à l'Amiga ; ils ont coûté du temps ici et
coûteront du temps sur Mega Drive, SNES ou arcade.

**A. Pipeline « format inconnu »**
Un assistant qui enchaîne automatiquement :
1. magics connus (compression, conteneurs, exécutables) ;
2. carte d'entropie par fenêtre de 4 Ko ;
3. carte des zéros ;
4. scan de cohérence bitmap ;
5. propositions classées avec aperçu.

C'est exactement la démarche manuelle suivie ici ; elle est automatisable à
80 %.

**B. Détection imbriquée systématique**
Après *chaque* étape, rescanner. Un fichier peut être : archive → exécutable →
compressé → bitmap. TileForge s'arrête aujourd'hui au premier niveau.

**C. API de plugins**
Les formats Amiga sont nombreux et mal documentés. Il faut pouvoir écrire un
décompresseur en 50 lignes (Python ou WASM) et le brancher sans recompiler
TileForge :

```python
@register_decompressor(magic=b"ATN!")
def imploder(data: bytes) -> bytes: ...
```

**D. Rapport de provenance**
À la fin, produire un `report.md` automatique : ce qui a été ouvert, avec quel
décodeur, quels offsets, quelles palettes, quels avertissements. Indispensable
pour reproduire et pour documenter un rip.

**E. Mode « recette » / régression**
Un corpus de référence (comme celui de ce projet) avec les résultats attendus,
pour éviter les régressions quand on touche au rendu planaire.

---

## 8. Ce que TileForge fait déjà bien (à ne pas casser)

- `inspect_file` : détection d'archive, liste des membres, inventaire des
  compressions candidates. C'est un excellent point d'entrée.
- La cartographie par entropie : le concept est bon, il faut juste l'étendre
  aux conteneurs et aux exécutables.
- Le rendu de tuiles et l'assemblage de sprites : la mécanique existe, il
  manque l'entrée « format Amiga » et la découpe automatique.
- `list_tile_formats` : le catalogue est propre et extensible — il faut
  simplement y ajouter les formats Amiga (4/5/6 plans, pleine page,
  plane-major, sprite 16×16/32×32 avec masque).

---

## 9. Ordre de développement proposé

**Itération 1 — « ouvrir un disque Amiga »**
1. Import ADF + parseur OFS/FFS tolérant aux checksums.
2. Détection de protection + avertissement.
3. Décompresseur Imploder (10 magics) + RNC.
4. Détection imbriquée récursive.

*Résultat attendu : à la fin de cette itération, les 28 fichiers de Project-X
sont accessibles et décompressés depuis l'interface, sans script.*

**Itération 2 — « voir une image Amiga »**
5. Parseur hunk + adresse de chargement.
6. Parseur de copper list (plans, palette, géométrie).
7. Mode écran plan-major / row-major avec stride libre.
8. Extraction de palettes `0x0RGB`.

*Résultat : les 6 écrans de chargement s'affichent avec les bonnes couleurs.*

**Itération 3 — « sortir les sprites »**
9. Scan de cohérence + détection de géométrie.
10. Découpe par composantes connexes + détection de grille.
11. Détection de pré-décalage et groupement d'animations.
12. Export atlas + planches.

*Résultat : les 10 planches de sprites et les 1043 sprites sont exportés
automatiquement.*

**Itération 4 — « généraliser »**
13. Assistant format inconnu.
14. API de plugins.
15. Rapport de provenance.
16. Corpus de régression.

---

## 10. Annexes — faits techniques à retenir

| Fait | Valeur | Pourquoi c'est important |
|---|---|---|
| Synchro MFM | `0x4489 0x4489`, non alignée octet | lecteur bit à bit obligatoire |
| Long MFM | 4 mots, ordre `w0,w2 / w1,w3` | sinon tout est décalé |
| Piste Amiga | 82 cylindres × 2 faces × 11 secteurs | ne pas supposer 80 |
| Secteur | 540 octets utiles = 4 + 16 + 4 + 4 + 512 | |
| Bloc AmigaDOS | 512 octets, données utiles 488 (OFS) | |
| Imploder | bloc compressé **en fin de fichier**, écriture **à rebours** | un décompresseur naïf échoue |
| Imploder magics | 10 variantes dont `ATN!` | `ATN!` ≠ RNC |
| Hunk | `0x3F3` header, `0x3E9` code, `0x3EA` data, `0x3EC` reloc32 | |
| Plan Amiga | 320 px = 40 octets/ligne | |
| Écran chargement | 256×256 utiles dans un bitmap 320 | 64 colonnes de padding |
| Planche sprites | 640×256 × 5 plans = 102 400 octets | |
| Palette | `0x0RGB`, 4 bits par composante | |
| Copper | `BPLCON0` 0x0100, `COLORxx` 0x0180+, `BPLxPT` 0x00E0+ | source de vérité |
| Protection | Copylock → **checksums AmigaDOS invalides** | ne pas rejeter le volume |
