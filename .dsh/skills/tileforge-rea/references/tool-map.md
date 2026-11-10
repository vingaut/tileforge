# Carte des outils TileForge et REA

> Référence chargée par la compétence `tileforge-rea`. Les schémas exacts
> vivent dans le code (`tileforge/mcp/server.py`) et dans `rea_describe`.

## 1. TileForge MCP

Le serveur s'appelle `tileforge` ; les outils sont préfixés `tileforge_`.
Les chemins doivent être **absolus** (le `cwd` du client MCP n'est pas celui
du dépôt). Les aperçus sont écrits dans le dossier de travail MCP
(`TILEFORGE_MCP_DIR`, sinon `~/.local/share/tileforge/mcp`).

### Inventaire

| Outil | Usage | Entrées utiles |
|---|---|---|
| `inspect_file` | type de fichier, en-tête, machine, compressions | `path`, `archive_member` |
| `list_archive` | membres d'un zip/7z | `path` |
| `list_tile_formats` | catalogue des formats de tuiles | — |
| `list_systems` | catalogue des machines | `family` |
| `read_palette` | palette brute dans un fichier | `path`, `offset`, `kind`, `count` |

`inspect_file` reconnaît désormais les disques Amiga (ADF/ADZ), les hunks, les
blocs Imploder/RNC, les ROMs SNES/Mega Drive et les projets.

### Recherche et validation

| Outil | Usage | Entrées utiles |
|---|---|---|
| `scan_graphics` | brut + compressé, budget, aperçus | `path`, `start`, `end`, `tile_format`, `compression`, `threshold`, `extended`, `workers` |
| `identify_format` | confirmer un format de tuile | `path`, `offset`, `length`, `formats` |
| `cartography` | zones d'entropie, tables de pointeurs | `path`, `window` |
| `preview_tiles` | rendre une plage d'octets | `offset`, `tile_format`, `compression`, `palette`, `count` |
| `open_bank` | charger une banque dans le projet | `offset`, `tile_format`, `compression`, `count`, `per_row` |

`scan_graphics` renvoie une note, pas une vérité : toujours regarder l'aperçu.

### Assemblage et export

`project_info`, `list_tiles`, `auto_assemble`, `render_sprite`,
`validate_sprite`, `save_project`, `export_atlas`.

### Désassemblage et émulation

| Outil | Usage |
|---|---|
| `disassemble` | 6502, 65816, Z80, 68000 ; `entry` pour tracer depuis une adresse |
| `list_emulator_cores` | cœurs libretro installés |
| `emulator_memory` | exécuter N trames, lire RAM/VRAM/SRAM, snapshot |

`emulator_memory` est la voie de secours quand le jeu décompresse en RAM.

### Chaîne Amiga

| Outil | Usage | Entrées utiles |
|---|---|---|
| `open_disk` | ouvrir ADF/ADZ/HDF, lister l'arborescence | `path`, `archive_member` |
| `extract_disk_file` | extraire un fichier | `path`, `node_path`, `output` |
| `decompress_nested` | Imploder/RNC/hunk récursif | `path`, `offset`, `max_depth`, `key` |
| `amiga_screen` | rendu planaire | `offset`, `width`, `height`, `planes`, `layout`, `stride`, `palette_offset` |
| `amiga_sprites` | composantes, grille, pré-décalage | idem + `min_area`, `close_radius`, `columns` |
| `amiga_analyze` | hunk + copper + imbriqué | `path`, `offset` |

`decompress_nested` écrit chaque bloc décompressé dans le dossier de travail et
renvoie `offset`, `format`, `depth`, `parent`, `warnings`.

## 2. REA

REA est un MCP de rétro-ingénierie. Il est **stateful** : `open_binary` établit
la cible, les appels suivants s'y réfèrent, `close_binary` ferme la session.

### Protocole

1. `rea_search` avec des mots de capacité (`decompile native function`,
   `rizin`, `xrefs`, `search bytes`) — jamais un nom deviné.
2. `rea_describe` sur le nom exact pour obtenir le schéma JSON.
3. `rea_call` avec les arguments validés.

### Outils les plus utiles pour les jeux

| Besoin | Outil | Remarques |
|---|---|---|
| Ouvrir un binaire/ELF/PE/Mach-O | `open_binary` | valide le fichier avant analyse |
| Vue d'ensemble | `binary_overview` | segments, procédures, chaînes |
| Segments | `list_segments` | adresses de début/fin exclusives |
| Procédures | `list_procedures`, `search_procedures` | après analyse |
| Fonction | `analyze_function` | dossier complet (appels, chaînes, CFG) |
| Pseudocode | `decompile_all` | écrit un manifeste, pas tout en contexte |
| Références | `xrefs`, `find_xrefs_to_name` | relier code ↔ données |
| Octets | `search_bytes` | signature masquée |
| Chaînes | `search_strings`, `list_strings` | protection, noms de fichiers |
| Rizin | `execute_rizin_command` | commande unique, profil propre |
| Fermer | `close_binary` | snapshot optionnel |

### Exemple Amiga

```text
open_binary(executable)
execute_rizin_command("aa; afl; iz")       # analyse, fonctions, chaînes
xrefs(0x12cd6)                              # qui pointe vers l'image ?
execute_rizin_command("pd 20 @ 0x1234")    # désassembler autour du loader
close_binary()
```

Rizin reconnaît `arch m68k`, `os AmigaOS` et les sections hunk : `paddr` donne
l'offset fichier, `vaddr` l'adresse de chargement. C'est le pont le plus court
entre une instruction `lea.l $adresse.l,a0` et un offset TileForge.

## 3. Choisir entre TileForge et REA

| Question | TileForge | REA |
|---|---|---|
| Où sont les graphismes ? | scan, cartographie, aperçus | recherche d'octets, xrefs |
| Quel est le format ? | `identify_format`, catalogue | désassemblage, structures |
| Comment le jeu charge-t-il ? | `disassemble`, `amiga_analyze` | `analyze_function`, pseudocode |
| Le jeu décompresse en RAM ? | `emulator_memory` | debugger Rizin si besoin |
| Vérifier une palette ? | `read_palette`, `amiga_screen` | lecture mémoire/constantes |

Les deux se complètent : TileForge pour l'image et les formats, REA pour le
code et les références.
