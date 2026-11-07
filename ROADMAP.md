# Feuille de route — TileForge, outil universel d'extraction

> Ce document est la référence du chantier « outil universel ». Il fixe la
> cible, l'ordre des travaux et les critères d'acceptation. Il est mis à jour
> à chaque jalon.

---

## 1. Vision

TileForge doit permettre d'extraire les graphismes de **n'importe quel jeu
8 ou 16 bits des années 1977–1995**, sans connaissance préalable du format :
consoles, ordinateurs personnels, bornes d'arcade.

Quand le format, la compression ou l'organisation résistent à l'analyse
automatique, l'outil doit permettre de **descendre jusqu'au code** — cartographie
de la ROM puis désassemblage — pour retrouver comment les développeurs
chargeaient leurs graphismes.

Le résultat est un outil libre, publié, traduit, documenté, testé, reproductible.

---

## 2. Principes directeurs

1. **Universalité.** Couvrir tous les systèmes de la période, pas seulement les
   plus courants. Un format absent est un bug.
2. **Pas de compromis.** Chaque décodeur est validé par un aller-retour
   encode/décode *et* par au moins un cas réel documenté. Pas de « ça a l'air
   de marcher ».
3. **Reproductibilité.** Toute trouvaille se mémorise en profil JSON : offset,
   format, compression, palette, grille. Un profil rejoué doit redonner la même
   image.
4. **Honnêteté.** Ce qui n'est pas validé est annoncé comme tel, dans l'aide et
   dans la documentation.
5. **Publication.** Le dépôt ne contient **aucun contenu de jeu commercial**.
   Les jeux de données de test sont fabriqués par les tests.
6. **Internationalisation dès la conception.** Aucune chaîne codée en dur dans
   une nouvelle fonctionnalité : tout passe par le catalogue de traduction.
7. **Le cœur sans interface.** `core`, `detect`, `assemble`, `scan`, `compress`
   ne dépendent ni de Qt ni de l'interface : ils s'utilisent en script, en CLI
   et via MCP.

---

## 3. Périmètre matériel visé

| Famille | Systèmes |
|---|---|
| Consoles 8 bits | Atari 2600, Intellivision, ColecoVision, NES/Famicom, SG-1000, Master System, Atari 7800, PC Engine, Game Boy, Game Boy Color, Lynx, Vectrex, PV-1000 |
| Consoles 16 bits | Mega Drive/Genesis, SNES/Super Famicom, Neo Geo, Game Gear, 32X, Saturn (2D), PC Engine CD |
| Ordinateurs 8 bits | Apple II, Atari 8-bit, VIC-20, C64, ZX81, ZX Spectrum, MSX1, Amstrad CPC, Thomson MO5/TO7, Oric, BBC Micro, TI-99/4A, PC-88, Dragon 32, Sam Coupé |
| Ordinateurs 16 bits | Atari ST, Amiga (OCS/AGA), MSX2/2+, PC-98, X68000, Archimedes, Amstrad PCW, C128, Enterprise 128, CoCo 3, EGA/VGA |
| Arcade | Pac-Man, Galaga, Donkey Kong, System 1/2/16/24, CPS-1/2/3, M72/M92, Model 1/2, Neo Geo MVS, Taito F2, Toaplan, Psikyo, Naomi |

---

## 4. Phases

### Phase 0 — Fondations (en cours)

| # | Tâche | État |
|---|---|---|
| 0.1 | Dépôt git, `.gitignore` de publication, commit de référence | ✅ |
| 0.2 | `LICENSE` MIT, `pyproject.toml`, point d'entrée console | ✅ |
| 0.3 | `ROADMAP.md` | ✅ |
| 0.4 | `README.md` réécrit : chemins corrects, MCP, universel, publication | à faire |
| 0.5 | `CONTRIBUTING.md`, modèles d'issues, politique de contenu | à faire |
| 0.6 | CI GitHub Actions (tests 3.10 → 3.13, ruff, build) | à faire |
| 0.7 | Jeu de données de test 100 % synthétique (`tests/fixtures/`) | à faire |

**Critère d'acceptation** : `git clone` + `pip install -e .[gui,dev]` +
`pytest` fonctionne sur une machine vierge, sans aucun fichier de jeu.

---

### Phase A — Moteur de recherche fiable (priorité 1)

Aujourd'hui le balayage est lent (jusqu'à 56 s pour 256 Ko), faux positif
fréquent (LC_LZ2 noté 0,71 sur du bruit) et bloquant pour l'interface.

| # | Tâche |
|---|---|
| A.1 | Nouveau module `tileforge/core/scan.py`, indépendant de l'interface | ✅ |
| A.2 | Score de vraisemblance calibré (silhouette, entropie, cohérence, palette, unicité) mesuré sur jeu étiqueté |
| A.3 | Budget temps par décompresseur + abandon des offsets pathologiques |
| A.4 | Regroupement des candidats voisins (un bloc = un résultat) |
| A.5 | Essai multi-format : un candidat est noté sur les 23 formats, le meilleur gagne — **fait : `core/identify.py`, marge au-dessus du plancher de bruit** |
| A.6 | Parallélisme (`multiprocessing`) avec repli séquentiel | ✅ |
| A.7 | Interface : scan en arrière-plan, progression, annulation, résultats avec vignettes |
| A.8 | MCP : mêmes paramètres et budget, résultat identique |
| A.9 | Tests : vrais positifs retrouvés, bruit rejeté, temps borné |

**Critère d'acceptation** : sur les 4 ROMs de travail, aucun candidat noté
> 0,5 ne doit être du bruit ; un scan complet de 1 Mo tient en moins de 60 s
sur un cœur ; l'interface reste réactive.

---

### Phase B — Compression universelle (priorité 2)

| # | Tâche |
|---|---|
| B.1 | Formats génériques : RLE (3 variantes), PackBits, LZSS (SNES/GB), LZ77, Huffman 8 bits, ZX0/ZX1/ZX2, Exomizer, Enigma (Z80), MTE (Mega Drive), Sega RLE, Comper, Saxman, Kosinski modulé, LC_LZ3 — **fait : Saxman, Enigma, Comper, Sonic RLE, Kosinski modulé, LZSS SNES, LZ77/LZ11 GBA-NDS, LC_LZ3, PackBits, RLE ×2, LZ Pokémon Crystal** |
| B.2 | Décompresseur générique « deviné » : heuristique pour les formats maison (recherche de motifs copie/littéral) |
| B.3 | Détection automatique du type de compression d'un bloc |
| B.4 | Plugins par jeu : dossier `tileforge/games/`, profil associé, chargement dynamique |
| B.5 | Validation croisée : chaque format validé sur au moins un cas réel documenté — **fait : encodeur Kosinski de test, chaîne complète vérifiée** |
| B.6 | Outil CLI `tileforge scan` et `tileforge extract` |
| B.7 | Archives zip/7z : lecture directe, choix du membre, MCP `list_archive` | ✅ `core/archives.py` |

**Critère d'acceptation** : au moins un décompresseur fonctionnel sur chacune
des 4 ROMs de travail, avec offset et profil enregistrés.

---

### Phase C — Consolidation et publication (priorité 3, en continu)

| # | Tâche |
|---|---|
| C.1 | Tests étendus : `model`, `solvers`, `inference`, `detect`, `project_io`, `mcp`, `scan` — **fait sauf `mcp` et `solvers` (couverts indirectement par le banc)** |
| C.2 | Couverture mesurée, objectif ≥ 70 % sur le cœur |
| C.3 | `ruff` propre sur tout le dépôt |
| C.4 | Version 1.2.0 : journal des évolutions, notes de version |
| C.5 | README bilingue (FR/EN), captures refaites avec des données libres |
| C.6 | Empaquetage Linux/Windows vérifié, release automatique — **Linux vérifié** (autotest, greffon SVG, balayage parallèle) |
| C.7 | Documentation en ligne (MkDocs) |

---

### Phase D — Moteur d'assemblage (priorité 4)

| # | Tâche |
|---|---|
| D.1 | Banc d'essai des solveurs M1–M6 sur des sprites connus — **fait : `tools/bench_solvers.py`** |
| D.2 | Amélioration du coût : poids appris sur les sprites validés. **Constat du banc :** l'ordre vrai bat 95 % des arrangements aléatoires, mais 5 % restent meilleurs — le coût est informatif sans être décisif. **Vérification faite :** l'ordre de stockage Barbarian n'est PAS l'assemblage d'origine (aucune grille simple ne reconstitue un sprite), le jeu compose donc par table. Sans sprites validés par l'utilisateur, il n'existe aucune vérité terrain : D.2 est bloquée jusqu'à ce qu'un projet réel soit enregistré. **Piste nouvelle :** la mémoire d'émulateur (phase G) peut fournir cette vérité terrain — lancer Barbarian dans un cœur Atari ST, avancer jusqu'à l'arène, lire la RAM où le jeu a décodé ses sprites. |
| D.3 | Inférence de règle plus robuste (plusieurs modèles concurrents, validation croisée) |
| D.4 | Assemblage guidé : l'outil propose, l'utilisateur confirme, la règle s'affine |

---

### Phase E — Finitions, i18n, documentation (priorité 5)

| # | Tâche |
|---|---|
| E.1 | Socle i18n : `t()`, catalogues JSON, extraction automatique des chaînes | ✅ |
| E.2 | Traductions FR, EN, DE | ✅ (172 textes d'interface) |
| E.3 | Icônes maison (remplacement des icônes standard Qt) | ✅ |
| E.4 | Aide : section « Connecter le MCP » (Claude Desktop, Cursor, VS Code) | ✅ |
| E.5 | Aide : section « Formats universels » et « Cartographie » |
| E.6 | Ergonomie tactile revue |

---

### Phase F — Cartographie de ROM et désassemblage (priorité 6, objectif ultime)

| # | Tâche |
|---|---|
| F.1 | Cartographie : en-tête, banques, tables de pointeurs, carte d'entropie, zones de code/données — **fait : `core/cartography.py`, dialogue, outil MCP** |
| F.2 | Désassembleurs : 6502, 65C02, 65816, SM83 (Game Boy), Z80, 68000, HuC6280, 6809 — **fait : 6502, Z80, SM83, 68000 et 65816** (traçage, choix du processeur dans l'interface et le MCP) |
| F.3 | Analyse de références : retrouver le code qui pointe vers les données graphiques |
| F.4 | Explorateur de ROM dans l'interface : carte, suivi des références, aperçu graphique au clic |
| F.5 | Export des annotations (format IDA/radare2 compatible si possible) |

**Critère d'acceptation** : sur une ROM sans profil connu, l'outil propose une
carte des zones graphiques avec un taux de vraisemblance mesuré, et permet de
naviguer du code vers les données.

---

## 4 bis. Sources de spécifications

Recensement des références fiables trouvées, à réutiliser au lieu de
réinventer un format :

| Format | Source | État |
|---|---|---|
| Kosinski, Nemesis, Enigma, Saxman, Moduled, RNC | [Sega Retro](https://segaretro.org/Category:Data_compression) | intégrés sauf RNC |
| Comper, Sonic RLE, Kosinski+, LZKN1, Rocket, Artc42, ComperX | [mdcomp (flamewing)](https://github.com/flamewing/mdcomp) — code source des décodeurs | Comper et Sonic RLE intégrés |
| ZX0 | [einar-saukas/ZX0](https://github.com/einar-saukas/ZX0), `src/dzx0.c` — décodeur de référence | non intégré (format des années 2020) |
| Compresseur 2bpp de Pokémon | [pret/pokered](https://github.com/pret/pokered), `tools/pkmncompress.c` | non intégré (format propre au jeu) |
| LC_LZ2 | implémentation existante, validée sur flux construits | intégré |
| LZ77/LZ11 GBA-NDS | [GBATEK, « LZSS Decompression »](https://mgba-emu.github.io/gbatek/) — types `0x10` et `0x11` | intégré, vecteurs construits |
| LC_LZ3 SNES | [SnesLab, LZ3](https://sneslab.net/wiki/LZ3) et décompresseur `SMW-Editor/snes-squish` — attribué à Pokémon Or/Argent par SnesLab, utilisé par les hacks SMW | intégré, vecteurs construits |
| MTE/DTE | [GB2Text](https://github.com/Far-g-Us/GB2Text), format de table `.tbl` | documenté ; encodage de texte, hors périmètre graphique immédiat |

Deux règles pour la suite : **ne pas écrire un décodeur sans vecteur de test**
(les sources ci-dessus en fournissent parfois, sinon on en construit un à la
main et on le documente), et **citer la source dans la docstring**.

---

## 4 ter. Barbarian : où sont les assemblages de sprites

Piste ouverte pour débloquer la phase D (vérité terrain). Relevée au
désassembleur, sur `extract/A.PRG` (exécutable GEMDOS, texte à 0x1C).

| Adresse | Rôle |
|---|---|
| 0x1C | table de sauts de 24 entrées (`jmp $xxxx.l`) |
| 0x398C | routine de dessin d'un objet composé : `link a6`, lit un octet via `$000A(a6)`, `0` termine la liste |
| 0xC46, 0xC7C | ses deux appelants |
| 0xC26 | calcul du pointeur : `move.w $000A(a3),d0` puis `lsl.w #1,d0`, indexation dans une table de **mots** à `-$2F22(a4)`, `muls #12`, puis `lea.l -$2F22(a4)` — chaque enregistrement fait donc **12 octets** |

Autrement dit : une table d'index (un mot par entrée) mène à une table
d'enregistrements de 12 octets, et l'adresse de l'enregistrement est passée à la
routine de dessin, qui lit une suite d'octets terminée par zéro — très
vraisemblablement les indices de tuiles du sprite.

La séquence se lit désormais proprement (les décalages et `muls` ont été
ajoutés au désassembleur) :

```
move.w $000A(a3),d0     ; index de l'objet
asl.l  #1,d0            ; × 2 (table de mots)
lea.l  -$2F22(a4),a0
adda.w d0,a0
move.w (a0),d0          ; décalage dans la table B
muls.w #$000C,d0        ; × 12 (taille d'un enregistrement)
lea.l  -$0722(a4),a0
adda.w d0,a0            ; adresse de l'enregistrement
```

**A4 retrouvé.** Deux initialisations existent : à `0x016C`,
`movea.l $0010(a5),a4` puis `adda.l $001C(a5),a4` — la base du segment de
données du PRG ; à `0x1FF8` et `0x2548`, un chargement depuis une adresse
relogée, dont la valeur dans le fichier est un zéro de remplissage.

Avec `A4 = 0x1C + 65742 = 0x100EA`, les deux tables tombent à `0xD1C8` et
`0xF9C8`. La seconde ressemble à des enregistrements, mais la première contient
des valeurs qui ressemblent à des **adresses** (`0x32FC`, `0x79FE`…) et non à
des décalages : l'interprétation du code à `0xC26` n'est donc pas encore la
bonne, ou les tables sont relogées au chargement.

**Le format du flux est décodé.** Le corps de la routine (0x39A6) ne laisse
aucun doute :

```
movea.l $000A(a6),a0     ; pointeur sur la liste
move.b  (a0),d7          ; un octet = indice de tuile, 1-based
cmpi.w  #0,d7
ble     fin              ; 0 termine la liste
subq.w  #1,d7            ; indice 0-based
move.w  #$7E,d0          ; 126 = taille d'une tuile Barbarian
muls.w  d7,d0
movea.l $000E(a6),a0     ; base de la banque de tuiles
adda.w  d0,a0            ; adresse de la tuile
```

Autrement dit : **une liste d'indices de tuiles sur un octet, 1-based, terminée
par zéro**, et la taille de tuile de 126 octets est confirmée par le code
lui-même (0x7E). C'est exactement ce que le modèle « recette » de TileForge
représente.

Les deux occurrences de `0x398C` trouvées dans le binaire à 0xF53E et 0xF542
sont des **données** (des octets de composition), pas des références : fausse
piste.

Prochaine étape : retrouver où sont stockées ces listes. Le calcul de pointeur
à 0xC26 indexe une table de mots à `A4-0x2F22` puis multiplie par 12 — mais les
valeurs lues ressemblent à des adresses, donc soit A4 est faux, soit cette
séquence sert à autre chose. Chercher les appelants qui passent un pointeur
**littéral** à `0x398C` (LEA PC-relatif suivi du JSR) serait plus direct.

**Piste émulateur (essayée).** Hatari 2.6.1 avec EmuTOS 1.4 charge
`extract/barbarian.st` et lance `A.PRG` : le programme place `BARB.DAT` à
`0x36E5C` en RAM, donc la banque 1 se retrouve à `0x6A8AE` (vérifié par
recherche d'octets). Le jeu s'arrête ensuite sur un bus error à `PC=0` —
vraisemblablement parce que la disquette de démarrage ou le TOS d'origine
manque. La chaîne « dump mémoire → balayage » fonctionne néanmoins :

```bash
python tools/emulator_memory.py --import-memory barb_ram.bin \
    --base 0 --system atarist --tile-format barbarian_st --scan
```

Prochaine étape : obtenir une exécution complète (TOS d'origine ou disquette de
démarrage), puis chercher dans la RAM les listes d'indices que la routine
`0x398C` consomme.

---

### Phase G — Mémoire d'émulateur (priorité 2 bis)

Quand un jeu décompresse ses graphismes à l'exécution, ou les fabrique en
mémoire, l'analyse statique de la ROM ne peut pas aboutir. La voie de secours
est de **laisser le jeu faire le travail** : exécuter la ROM dans un émulateur,
puis lire la mémoire décodée. Cette phase est née de la piste Barbarian : la
mémoire d'un émulateur Atari ST peut fournir la vérité terrain qui manque à la
phase D.

| # | Tâche | État |
|---|---|---|
| G.1 | Hôte libretro minimal en `ctypes` : découverte des cœurs, chargement, exécution sans fenêtre, rappels vidéo/audio/entrée | ✅ `core/emulation.py` |
| G.2 | Instantané mémoire : RAM système, VRAM, SRAM, RTC, capture PNG, manifeste JSON, fichier concaténé | ✅ |
| G.3 | Interface : **Outils ▸ Mémoire d'émulateur…**, choix du cœur, de la ROM, des trames et du script d'entrée | ✅ `ui/emulator_dialog.py` |
| G.4 | MCP (`list_emulator_cores`, `emulator_memory`) et CLI (`tools/emulator_memory.py`) | ✅ |
| G.5 | Tests avec un cœur factice compilé à la volée : chargement, trames, entrées, régions, capture, aller-retour d'instantané | ✅ |
| G.6 | Confronter l'hôte à de vrais cœurs (mGBA, Snes9x, Genesis Plus GX, Hatari) sur les ROMs de travail | ✅ Snes9x sur Final Fight : 300 trames, 128 Ko de WRAM, 64 Ko de VRAM, capture du plan de Metro City ; candidats graphiques dans la VRAM (note 0,73). mGBA, Genesis Plus GX et Hatari restent à essayer. |
| G.7 | Enregistrer un instantané comme **profil** reproductible : région, offset, format, palette | à faire |
| G.8 | Lire directement les sauvegardes d'état des émulateurs (mGBA, Snes9x, Hatari), sans exécution | à faire |
| G.9 | Barbarian : extraire la RAM après chargement d'un niveau et retrouver les sprites décodés (vérité terrain de la phase D) | à faire |
| G.10 | Importer un dump mémoire brut d'un émulateur non libretro (`--import-memory`, base, machine) | ✅ |
| G.11 | Démonstration multi-systèmes : neuf jeux, capture, tuiles, sprites, mémoire, rapports | ✅ `tools/build_demo.py`, `tileforge-demo/` |
| G.12 | Cœurs réels validés : FceUmm, Snes9x, Picodrive, SameBoy, mGBA, Mednafen PCE, Fuse, Crocods | ✅ (VICE et PUAE à revoir) |

**Critère d'acceptation** : avec un cœur installé, une ROM est exécutée, la
mémoire est écrite avec ses métadonnées, puis rouverte et balayée dans
TileForge ; sans cœur, le reste de l'outil fonctionne et le dialogue explique
comment en installer un.

---

### Phase H — Publication (priorité 6)

Le dépôt doit être publiable tel quel : aucun contenu de jeu commercial, des
dépendances externes retrouvables, des captures synthétiques et une installation
reproductible.

| # | Tâche | État |
|---|---|---|
| H.1 | Audit du contenu : ROMs, BIOS, captures et autosaves hors du dépôt ; `.gitignore` renforcé | ✅ |
| H.2 | Captures de documentation synthétiques (`tools/make_screenshots.py`) et planche de démonstration | ✅ |
| H.3 | Manifeste des cœurs + `tools/fetch_cores.py` avec vérification SHA-256 | ✅ |
| H.4 | Manifeste BIOS + `tools/check_bios.py` + `docs/BIOS.md` (libre vs copyrighté) | ✅ |
| H.5 | `docs/INSTALL.md`, `docs/PUBLISHING.md`, `docs/THIRD_PARTY.md`, `MANIFEST.in` | ✅ |
| H.6 | Branche publique orpheline et envoi sur GitHub | à faire (dépôt distant à créer) |
| H.7 | CI : tests, ruff, handshake MCP, manifestes, paquet | ✅ |
| H.8 | Release GitHub et notes de version | à faire |

**Critère d'acceptation** : un `git clone` du dépôt public, suivi de
`pip install -e ".[gui]"`, `tests/run_all.py`, `tools/fetch_cores.py` et
`tools/mcp_config.py --check`, donne une installation opérationnelle sans
aucun fichier de jeu.

---

## 5. Qualité

- Chaque module du cœur a ses tests.
- Chaque décodeur de compression a un test d'aller-retour et un test de non-régression.
- Chaque fonctionnalité nouvelle arrive avec sa fiche d'aide et sa traduction.
- Aucun contenu commercial dans le dépôt ; vérification avant chaque release.

## 6. Journal

| Date | Jalon |
|---|---|
| 2026-11-06 | Dépôt git initialisé, licence MIT, `pyproject.toml`, feuille de route. |
| 2026-11-06 | Phase A : notation calibrée (AUC 0,985, validation croisée 0,981) et moteur de balayage ; interface et MCP branchés sur le moteur. |
| 2026-11-07 | Phase B.1 : Saxman et Enigma validés par les vecteurs officiels Sega Retro, PackBits et deux variantes RLE ; garde-fou contre les décompressions en roue libre. |
| 2026-11-07 | Phase A.6 : balayage parallèle (2× sur 4 formats), sonde de 4 Ko, plafond de notation et jeu de formats par défaut resserré. |
| 2026-11-07 | Phase A.5 : identification du format de tuiles (marge au-dessus du plancher de bruit), bouton dans l'interface et outil MCP. |
| 2026-11-07 | Phase E.4 : section « Connecter le MCP » dans l'aide (Claude Desktop, Cursor, VS Code, dépannage). |
| 2026-11-07 | Phase E.1–E.2 : interface traduite en anglais et en allemand (172 textes), bascule à chaud dans Aide ▸ Langue, outil d'extraction et contrôle de couverture. |
| 2026-11-08 | Phase B.1 : Comper et Sonic RLE, portés depuis l'implémentation de référence mdcomp (flamewing), avec vecteurs de test construits à la main. |
| 2026-11-08 | Phase F.1 : cartographie de ROM (plateforme, entropie, tables de pointeurs), dialogue avec bande de zones et outil MCP. |
| 2026-11-08 | Phase D.1 : banc d'essai des solveurs — l'ordre vrai bat 95 % des arrangements aléatoires, M3/M4/M5 le retrouvent exactement 11 à 17 % du temps. |
| 2026-11-08 | Phase C.1 : tests du modèle, de la persistance, des exports, des détecteurs et de l'inférence — 96 tests au total. |
| 2026-11-08 | Phase F.2 (65816) : table des 256 opcodes reprise d'andlabs/65816disasm, décodage, références, traçage depuis le vecteur de reset, outil MCP et fenêtre dédiée. |
| 2026-11-08 | F.2 (suite) : pile de retours dans le traçage — 589 instructions couvertes sur Final Fight, toute l'initialisation et les routines DMA. |
| 2026-11-08 | F.2 (suite) : suivi des tables de sauts (`jmp (table,x)`) — 1 417 instructions couvertes. Le code atteint reste de l'initialisation : le jeu charge ses graphismes par des chemins plus indirects. |
| 2026-11-08 | A (suite) : balayage restreint aux zones de données de la cartographie — 8× plus rapide sur Final Fight, mêmes candidats. |
| 2026-11-08 | F.2 (suite) : désassembleur 6502 — table complète (179 opcodes utiles, 77 invalides rendus en .byte), traçage avec pile de retours, adresse de chargement pour les cartouches. |
| 2026-11-08 | E.3 et C.5 : jeu d'icônes SVG maison (16 icônes), README anglais. |
| 2026-11-08 | F.2 (suite) : désassembleur Z80 — table reconstruite par algorithme à partir des champs xx/yyy/zzz, préfixes CB, ED, DD et FD. |
| 2026-11-08 | F.2 (suite) : désassembleur 68000 — modes d'adressage complets, MOVE/arithmétique/contrôle/MOVEM, traçage. Validé sur le code d'amorçage TMSS d'Aero Blasters (« SEGA » dans $A14000). |
| 2026-11-08 | F.2 (fin) : variante SM83 (Game Boy) du désassembleur Z80 — opcodes réaffectés, swap, dix codes invalides. |
| 2026-11-08 | C.6 : paquet Linux reconstruit et vérifié — autotest, greffon SVG des icônes présent, balayage parallèle fonctionnel dans l'exécutable figé. |
| 2026-11-08 | B.5 : encodeur Kosinski de test (`tools/make_fixture.py`) et test d'intégration — banque compressée retrouvée par le balayage, décompressée à l'octet près. |
| 2026-11-08 | B.1 (suite) : décompresseur du LZ de Pokémon Crystal (Game Boy), porté depuis `pret/pokecrystal` — littéraux, répétitions, alternances, zéros et trois copies arrière. |
| 2026-11-08 | B.1 (suite) : LZSS SNES (0x100), d'après `gingerbeardman/snes-lzss` — drapeaux par huit, distance 12 bits, longueur étendue. |
| 2026-11-08 | Confrontation aux ROMs réelles : le LZSS SNES ne produit **aucun faux positif** sur Final Fight et ActRaiser (ces jeux ne l'utilisent pas) ; le LZ Pokémon Crystal, sans en-tête de longueur, en produit 52 et 34 — il reste hors du balayage automatique. Limite connue de la note : des données très répétitives à deux couleurs obtiennent 0,80, comme un dessin à deux couleurs. |
| 2026-11-08 | D.1 (correction) : vérification visuelle — l'ordre de stockage Barbarian ne reconstitue pas les sprites, le banc mesurait contre une fausse référence. Documentation corrigée ; D.2 est bloquée faute de vérité terrain. |
| 2026-11-08 | A (suite) : balayage brut parallèle par tranches — 1 Mo passe de 31,7 s à 10,9 s sur quatre cœurs, résultat identique. |
| 2026-11-08 | D (piste) : la routine de dessin d'objets composés de Barbarian est localisée à 0x398C, avec ses appelants et la structure de la table (mots d'index → enregistrements de 12 octets). Reste à retrouver A4 et à décoder MULS. |
| 2026-11-08 | D (piste, suite) : format du flux décodé — indices de tuiles sur un octet, 1-based, terminés par zéro, adresse calculée par `indice × 126`. Tables localisées mais pas encore identifiées. |
| 2026-11-08 | E (suite) : trois sections d'aide ajoutées (cartographie, désassemblage, langues) et un doublon de section MCP supprimé — 29 sections, aucune clé répétée. |
| 2026-11-08 | B.1 (suite) : LZ77/LZ11 GBA-NDS (GBATEK) et LC_LZ3 SNES (SnesLab), avec vecteurs construits ; formats de tuiles `gba_4bpp` et `gba_8bpp`. Les deux décompresseurs sont disponibles dans la liste et le MCP, mais restent hors du balayage par défaut (`extended=true` pour les essayer). |
| 2026-11-08 | G.1–G.5 : hôte libretro en `ctypes`, instantanés de mémoire (RAM, VRAM, SRAM, capture, manifeste), dialogue **Mémoire d'émulateur**, outils MCP et CLI, tests avec un cœur factice compilé à la volée. Aucun cœur ni ROM n'est embarqué. |
| 2026-11-08 | Documentation : README bilingue (décodeurs, mémoire d'émulateur, 20 outils MCP), aide (30 sections), traductions EN/DE des nouveaux textes, 216 tests. |
| 2026-11-08 | B.7 : archives zip/7z (`core/archives.py`), outil MCP `list_archive`, paramètre `archive_member`, sélection du membre dans les dialogues, `--member`/`--archive-member` dans les scripts. |
| 2026-11-08 | G.11–G.12 : neuf systèmes traités à partir du pack SMB (NES, SNES, Mega Drive, GB, GBA, Master System, PC Engine, ZX Spectrum, CPC). Démo dans `../tileforge-demo`, outils `build_demo.py` et `demo_extract.py`, aucun contenu de jeu copié. |
| 2026-11-08 | H.1–H.5 : captures synthétiques, planche de démonstration, manifestes cœurs/BIOS, guides d'installation/publication, `MANIFEST.in`, audit des contenus commerciaux. |
| 2026-11-08 | H.7 : CI complétée (handshake MCP, manifestes, paquet) et `tools/doctor.py` pour vérifier une installation. |
| 2026-11-08 | 1.4.1 : import d'une ROM ou d'une archive depuis l'accueil, le menu Fichier et la barre d'outils ; l'écran Planche ne met plus Barbarian en avant. |
| 2026-11-08 | 1.4.2 : correction du format de tuiles Mega Drive — 4 plans, un octet par plan et par ligne (comme la Master System) au lieu de 2 pixels par octet. Les banques Mega Drive ne sortent plus en bruit ; fixtures, calibration et aide alignées. |
| 2026-11-08 | G.10 : import de dumps mémoire bruts (`--import-memory`). Essai réel avec Hatari 2.6.1 + EmuTOS 1.4 : `A.PRG` charge `BARB.DAT` à 0x36E5C, la banque 1 se retrouve à 0x6A8AE dans la RAM ; le jeu s'arrête ensuite sur un bus error (disquette de démarrage absente), mais le chemin dump → balayage fonctionne. |
| 2026-11-08 | G.6 : premier cœur réel — Snes9x sur Final Fight, 300 trames. L'hôte lit 128 Ko de WRAM et 64 Ko de VRAM, écrit une capture du plan de Metro City, et le balayage trouve des tuiles 4bpp dans la VRAM (note 0,73 à 0x2C40). |
