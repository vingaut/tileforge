# Par système — formats, pièges, point d'entrée

> Référence de la compétence `tileforge-rea`. Les valeurs sont celles du
> catalogue TileForge et des cas réels documentés dans `docs/`.

## Amiga (OCS/AGA)

| Élément | Valeur |
|---|---|
| Disque | ADF 901 120 octets (80×2×11×512), ADZ = gzip, HDF = disque dur |
| FS | OFS (blocs de données 488 utiles) ou FFS (512), blocs 512/1024 |
| Racine | bloc 880 (ou milieu du volume), table de hachage 72 entrées |
| Protection | Copylock/Rob Northen ⇒ checksums faux ; **ouvrir quand même** |
| Compression | Imploder (`IMP!`, `ATN!`, `BDPI`, `CHFI`, `Dupa`, `EDAM`, `FLT!`, `M.H.`, `PARA`, `RDC9`), RNC (`RNC\x01`) |
| Imploder | bloc compressé en fin de fichier, pied de page 0x32, décompression à rebours |
| Exécutable | hunk `0x3F3`, segments `0x3E9`/`0x3EA`/`0x3EB`, reloc `0x3EC` |
| Écran | planaire, row-major ou plane-major ; 256 utiles dans 320 est courant |
| Plan | 320 px = 40 octets/ligne ; 1 à 8 plans |
| Palette | `0x0RGB` (4 bits/composante), souvent hors de l'image |
| Copper | `BPLCON0` 0x0100, `COLORxx` 0x0180+, `BPLxPT` 0x00E0+ |
| Sprites | planches 640×256×5 plans, composantes connexes, pré-décalage |

Point d'entrée : `open_disk` → `extract_disk_file` → `decompress_nested` →
`amiga_analyze` → `amiga_screen`/`amiga_sprites`.

## Atari ST

| Élément | Valeur |
|---|---|
| Disquette | `.st` (secteurs bruts), `.stx` (flux de protection), `.msa` |
| FS | FAT12, secteurs 512, 80 pistes × 2 faces × 9/10/11 secteurs |
| Exécutable | PRG GEMDOS, en-tête à 0x1C, texte à 0x1C |
| Tuiles | planaire 2/4 plans, mots big-endian, Barbarian 24×21 (126 octets) |
| Palette | `0x0RGB` 3 bits/composante |
| Émulation | Hatari + EmuTOS/TOS |

Point d'entrée : `games/atari_st.py` pour Barbarian, sinon `inspect_file`,
`scan_graphics` format `st_sprite_4pl`/`barbarian_st`, REA pour le PRG.

## NES / Famicom

| Élément | Valeur |
|---|---|
| ROM | iNES `.nes`, en-tête 16 octets, PRG/CHR, mapper |
| Tuiles | 2bpp séquentiel (8 octets plan 0 puis 8 plan 1) |
| Palettes | 4 couleurs par tuile, tables dans les transfer records |
| Piège | 0 banque CHR : les graphismes sont dans la PRG |

Point d'entrée : `inspect_file`, `cartography`, `scan_graphics` format `nes`,
`disassemble` 6502.

## Super Nintendo

| Élément | Valeur |
|---|---|
| ROM | LoROM (`0x7FC0`) ou HiROM (`0xFFC0`), en-tête 0x20 |
| Tuiles | 2/3/4/8 bpp, paires de plans entrelacées |
| Compression | LC_LZ2, LC_LZ3, LZSS SNES |
| Piège | graphismes copiés en VRAM par DMA ; le code seul ne suffit pas |

Point d'entrée : `inspect_file`, `cartography`, `scan_graphics` format
`snes_4bpp`, `disassemble` 65816.

## Mega Drive / Genesis

| Élément | Valeur |
|---|---|
| ROM | en-tête `SEGA MEGA DRIVE` à 0x100, TMSS |
| Tuiles | 4bpp planaire, 4 octets/ligne (un par plan), bit 7 à gauche |
| Compression | Kosinski, Kosinski modulé, Nemesis, Saxman, Comper, Sonic RLE |
| Piège | ne pas décoder en quartets (2 pixels/octet) |

Point d'entrée : `inspect_file`, `scan_graphics` format `megadrive`,
`disassemble` 68000.

## Game Boy / Game Boy Color / GBA

| Élément | Valeur |
|---|---|
| GB | 2bpp, 8×8, LZ Pokémon Crystal, palettes DMG/CGB |
| GBA | 4bpp/8bpp, LZ77/LZ11 (`0x10`/`0x11`), tuiles 8×8 |
| Piège | LZ sans en-tête de longueur ⇒ faux positifs |

Point d'entrée : `scan_graphics` format `gameboy`/`gba_4bpp`,
`compression="gba_lz77"`, `disassemble` Z80/SM83.

## Master System / Game Gear

4bpp planaire, 4 octets/ligne, comme la Mega Drive ; format `master_system`.

## PC Engine / Neo Geo / arcade

Formats souvent propriétaires. Utiliser `cartography` (entropie), `scan_graphics`
avec `extended`, `emulator_memory` (MAME/Mednafen), puis REA pour le code.
Neo Geo : tuiles 4bpp, palettes 16 couleurs par tuile ; CPS-1/2 : 4bpp
planaires avec masque.

## Format totalement inconnu

1. `inspect_file` : archive, exécutable, image, disque ?
2. `cartography` : carte d'entropie, zéros, tables de pointeurs.
3. `decompress_nested` : magics connus et imbrication.
4. `scan_graphics` : balayage multi-format, aperçus.
5. `identify_format` : confirmer les meilleurs candidats.
6. REA : `open_binary`, `binary_overview`, `search_bytes`, `xrefs`.
7. `emulator_memory` : laisser le jeu décompresser.
8. Documenter l'échec et les pistes dans `docs/cases/`.

## Tableau des palettes

| Système | Format | Bits/composante |
|---|---|---|
| Amiga | `0x0RGB` | 4 |
| Atari ST | `0x0RGB` | 3 |
| SNES | BGR555 | 5 |
| Mega Drive | `0BGR` | 3 |
| NES | 2C02 | 6 bits indexés |
| Game Boy | DMG/CGB | 2/5 |
| CPC | mode 0/1/2 | 1/2/4 |
