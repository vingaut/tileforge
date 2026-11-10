---
name: tileforge-rea
description: "Méthode de travail pour décompiler et extraire les graphismes de jeux 8/16 bits avec TileForge (MCP + CLI) et REA (rizin, Ghidra, capstone) : disques Amiga, ROMs consoles, exécutables, compressions imbriquées, palettes, sprites, et mise à jour du dépôt TileForge."
whenToUse: "Dès qu'on demande d'extraire, décompiler, désassembler ou analyser les graphismes/données d'un jeu rétro, d'ajouter un système ou un format à TileForge, de reprendre une extraction existante, ou de documenter/committer le résultat. À charger avant de commencer, pour ne pas repartir de zéro."
---

# TileForge + REA — extraction de graphismes 8/16 bits

Cette compétence est le **playbook** des extractions rétro du projet TileForge.
Elle suppose le dépôt `/home/vincent/Partage/codage/tileforge` (adapter le
chemin si le dépôt a bougé) et le serveur MCP `tileforge` déclaré.

## 0. Règle d'or : ne pas repartir de zéro

Avant toute chose, lire dans cet ordre :

1. `docs/ETUDES_DE_CAS.md` — les deux extractions de référence (Zelda NES,
   Project-X Amiga) et les outils qui ont débloqué chaque étape.
2. `docs/AMIGA.md` — la chaîne Amiga complète (ADF, Imploder, hunk, copper,
   planaire, palettes, sprites).
3. `docs/cases/` — les fiches des jeux déjà traités (une fiche par jeu).
4. `ROADMAP.md` — ce qui est fait, ce qui reste, les critères d'acceptation.
5. `docs/tileforge_upgrade.md` — la feuille de route issue de Project-X.

Puis vérifier l'état réel du dépôt :

```bash
cd /home/vincent/Partage/codage/tileforge
git status --short
git log --oneline -5
.venv/bin/python tests/run_all.py          # 283 tests attendus
.venv/bin/python tools/doctor.py
.venv/bin/python tools/mcp_config.py --check
```

Si les tests échouent, **réparer d'abord** : une extraction sur un outil cassé
produit de faux résultats.

## 1. Boucle de travail en cinq étapes

### 1.1 Inventaire — quel est le fichier ?

| Situation | Outils |
|---|---|
| Fichier inconnu | `tileforge_inspect_file` |
| Archive zip/7z | `tileforge_list_archive`, puis `archive_member` |
| ROM console | `inspect_file`, `cartography`, `list_tile_formats` |
| Disque Amiga | `tileforge_open_disk` |
| Exécutable / binaire | `tileforge_amiga_analyze`, REA `open_binary` + `binary_overview` |
| Image disque protégée | `open_disk` (lire les avertissements) |

Noter dès l'inventaire : taille, en-tête, machine probable, compressions
candidates, checksums, chaînes de protection.

### 1.2 Localiser — où sont les données ?

1. `tileforge_scan_graphics` : brut + compressé, budget de temps, aperçus PNG.
2. `tileforge_identify_format` : confirmer taille/profondeur/disposition.
3. `tileforge_cartography` : zones par entropie, tables de pointeurs.
4. `tileforge_decompress_nested` : Imploder, RNC, hunk, magics imbriqués.
5. `tileforge_emulator_memory` : voie de secours quand le jeu décompresse en
   RAM (aucun cœur fourni : vérifier `list_emulator_cores`).
6. REA : `search_bytes` pour un magic, `execute_rizin_command` pour les
   références, `xrefs`/`analyze_function` pour relier code et données.

**Ne jamais conclure sur un seul offset.** Croiser au moins deux sources :
aperçu visuel, table de pointeurs, désassemblage, mémoire d'émulateur.

### 1.3 Décoder — choisir le bon chemin

#### Amiga

```text
open_disk → extract_disk_file → decompress_nested
          → amiga_analyze (hunk + copper + imbriqué)
          → amiga_screen / amiga_sprites
```

- `decompress_nested` descend Imploder (`IMP!`, `ATN!`, …) et RNC.
- `amiga_analyze` donne les segments hunk, l'adresse de chargement, les listes
  copper (plans, palette, géométrie) et les blocs restants.
- `amiga_screen` : `layout="row"` ou `"plane"`, `stride` libre. Le cas
  « 256 utiles dans un bitmap de 320 » est la norme.
- `amiga_sprites` : composantes 8-connexité, fermeture morphologique, grille,
  pré-décalage, groupes d'animation.

#### Console (NES, SNES, Mega Drive, GB/GBA, Master System…)

- Choisir le format dans `list_tile_formats` (`snes_4bpp`, `megadrive`,
  `nes`, `gameboy`, `gba_4bpp`, `master_system`, `amiga_*`…).
- `open_bank` puis `preview_tiles` pour valider.
- Compression : `scan_graphics` avec `compression="auto"` ou une clé précise
  (`lz2`, `lz3`, `kosinski`, `nemesis`, `gba_lz77`, `imploder`, `rnc`…).
- Désassemblage : `tileforge_disassemble` (6502, 65816, Z80, 68000) ; REA pour
  les xrefs et le pseudocode.

#### Exécutable / format inconnu

- REA : `open_binary`, `binary_overview`, `list_segments`, `list_procedures`,
  `analyze_function`, `xrefs`, `search_bytes`, `execute_rizin_command`,
  `decompile_all`, puis `close_binary`.
- TileForge : `amiga_analyze` (hunk/copper), `decompress_nested`,
  `cartography`, `disassemble`.
- Convertir une adresse absolue en offset : `hunk.address_to_offset(addr)` avec
  la bonne base (0x8000 par défaut, mais vérifier le linker).

### 1.4 Vérifier — l'image est-elle juste ?

- Ouvrir l'aperçu PNG : reconnaît-on le vaisseau, le décor, la police ?
- Vérifier les palettes : `0x0RGB`, premier mot noir, pas de table de fondu,
  continuité des couleurs entre voisins.
- Vérifier les plans : densité par plan ; un plan vide signale un plan en trop.
- Vérifier le bourrage : `content_width` < largeur du bitmap.
- Recouper avec le code : une instruction `lea.l $adresse.l,aN` ou une table de
  pointeurs doit pointer vers l'offset trouvé.
- En cas de doute, `emulator_memory` : le jeu a déjà décompressé.

### 1.5 Capitaliser — pour la prochaine fois

1. **Écrire une fiche** dans `docs/cases/<jeu>-<machine>.md` avec le modèle
   `docs/cases/TEMPLATE.md` : entrée, chaîne suivie, offsets, formats,
   palettes, commandes, résultats, ce qui a résisté.
2. **Enregistrer le profil** : `tileforge_save_project` (`.tileforge.json`) ou
   un profil JSON dans `tileforge/games/` si le jeu mérite un plugin.
3. **Mettre à jour** `docs/ETUDES_DE_CAS.md` (résumé), `ROADMAP.md` (journal)
   et, si le format est nouveau, `docs/AMIGA.md` ou la doc du système.
4. **Tester** : ajouter un test avec une fixture synthétique, jamais un fichier
   de jeu commercial.
5. **Committer** : `feat:`/`fix:`/`docs:`, tests et ruff verts, puis push.

## 2. Carte des outils

### TileForge MCP (26 outils)

| Catégorie | Outils |
|---|---|
| Inventaire | `inspect_file`, `list_archive`, `list_tile_formats`, `list_systems`, `read_palette` |
| Recherche | `scan_graphics`, `identify_format`, `cartography` |
| Banques / rendu | `preview_tiles`, `open_bank`, `project_info`, `list_tiles` |
| Assemblage | `auto_assemble`, `render_sprite`, `validate_sprite`, `save_project`, `export_atlas` |
| Désassemblage | `disassemble` |
| Émulation | `list_emulator_cores`, `emulator_memory` |
| Amiga | `open_disk`, `extract_disk_file`, `decompress_nested`, `amiga_screen`, `amiga_sprites`, `amiga_analyze` |

Détail et schémas : `references/tool-map.md`.

### REA

REA est **stateful** : `open_binary` d'abord, `close_binary` à la fin. Toujours
`rea_search` → `rea_describe` → `rea_call` ; ne jamais deviner un schéma.

| Besoin | Outil REA |
|---|---|
| Ouvrir un binaire | `open_binary` |
| Vue d'ensemble | `binary_overview`, `list_segments`, `list_procedures` |
| Chercher des octets | `search_bytes` (signature masquée) |
| Chaînes | `search_strings`, `list_strings` |
| Références | `xrefs`, `find_xrefs_to_name` |
| Fonction | `analyze_function`, `decompile_all` |
| Rizin brut | `execute_rizin_command` |
| Fermer | `close_binary` (snapshot éventuel) |

Pour l'Amiga, rizin reconnaît nativement `arch m68k`, `os AmigaOS` et les
sections hunk (`paddr`, `vaddr`) : c'est souvent le raccourci le plus rapide
pour relier une adresse absolue à un offset.

## 3. Par système — pièges connus

Voir `references/platforms.md` pour les tableaux détaillés. En résumé :

| Système | Pièges |
|---|---|
| Amiga | plans row/plane-major, stride 320 pour 256 utiles, 6ᵉ plan vide, palette hors image, Imploder en fin de fichier, hunk à drapeaux |
| Atari ST | STX/FAT12, PRG GEMDOS, sprites 2/4 plans, banques Barbarian, TOS/EmuTOS |
| NES | iNES, mapper MMC1, 0 banque CHR, 2bpp séquentiel, palettes dans les transfer records |
| SNES | LoROM/HiROM, LC_LZ2/LZ3, 4bpp paires de plans, DMA |
| Mega Drive | 4bpp planaire (4 octets/ligne), Kosinski/Nemesis/Saxman, TMSS |
| Game Boy/GBA | 2bpp/4bpp, LZ Pokémon, LZ77/LZ11, tuiles 8×8 |
| Arcade | formats propriétaires, entropy map, mémoire d'émulateur, MAME |

## 4. Pièges transverses

- **Boutisme** : Amiga/ST/SNES big-endian ; Mega Drive big-endian ; PC little.
- **Planaire vs chunky** : un bitmap Amiga/ST n'est pas une suite d'octets par
  pixel. Vérifier la disposition avant de conclure au bruit.
- **Stride** : la largeur du bitmap n'est pas la largeur utile.
- **Plans vides** : un plan à densité nulle est un plan en trop.
- **Palettes** : la palette n'est pas toujours dans l'image ; chercher les
  suites `0x0RGB`, écarter les fondus, apparier par continuité.
- **Protections** : Copylock/Rob Northen ⇒ checksums faux ; lire quand même.
- **Compression imbriquée** : toujours rescanner le résultat.
- **CRC faux** : avertir, ne pas rejeter.
- **Faux positifs** : une note de scan n'est pas une preuve ; l'aperçu décide.

## 5. Conventions du dépôt

- Le cœur (`tileforge/core`) ne dépend pas de Qt.
- Documentation et commentaires en français ; noms d'outils en anglais.
- Aucun contenu de jeu commercial : fixtures synthétiques uniquement.
- Toute nouvelle chaîne d'interface passe par `t()` et les catalogues
  `tileforge/i18n/en.json` et `de.json`.
- Nouveau format de tuile : `formats.py` + test dans `tests/test_formats.py`.
- Nouveau décompresseur : `compression.py` + vecteur de test + docstring citant
  la source.
- Nouvel outil MCP : `mcp/server.py` + `mcp/tools.py` + test de handshake +
  mise à jour du nombre d'outils dans README/docs.
- Avant commit : `ruff check`, `tests/run_all.py`, `--selftest`, éventuellement
  `python -m build` et PyInstaller.
- Version : `tileforge/version.py` (version, date, CHANGELOG) + README/ROADMAP.

Détail : `references/repo-workflow.md`.

## 6. Commandes utiles

```bash
# Tests et qualité
.venv/bin/python tests/run_all.py
.venv/bin/ruff check tileforge tests tools
.venv/bin/python -m tileforge --selftest
.venv/bin/python tools/mcp_config.py --check
.venv/bin/python tools/doctor.py
.venv/bin/python tools/verify_publication.py

# Chaîne Amiga
.venv/bin/python tools/amiga.py list disque.adf
.venv/bin/python tools/amiga.py nested fichier -o sortie/
.venv/bin/python tools/amiga.py screen ecran.bin --width 256 --height 256 \
    --planes 5 --layout plane --stride 40 -o ecran.png
.venv/bin/python tools/amiga.py sprites planche.bin --width 640 --height 256 \
    --planes 5 --layout plane --stride 80 -o planche.png

# Paquet et binaire
.venv/bin/python -m build
.venv-build/bin/pyinstaller --noconfirm --clean --distpath dist \
    --workpath build packaging/tileforge.spec
```

## 7. Ressources de cette compétence

- `references/tool-map.md` — schémas et usages des outils TileForge/REA.
- `references/platforms.md` — tableau par machine, formats et pièges.
- `references/repo-workflow.md` — ajouter un format, un décompresseur, un outil.
- `docs/cases/TEMPLATE.md` — modèle de fiche de jeu.
- `docs/AMIGA.md` — la chaîne Amiga en détail.

## 8. Ce qu'il ne faut pas faire

- Ne pas écrire un décodeur sans vecteur de test indépendant.
- Ne pas copier un décompresseur GPL dans le dépôt MIT (écrire une
  réimplémentation à partir de la spécification).
- Ne pas publier de ROM, disque, BIOS, capture ou sprite de jeu commercial.
- Ne pas annoncer un résultat non vérifié : le dépôt assume ses limites.
