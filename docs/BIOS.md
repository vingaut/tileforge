# BIOS et firmwares

TileForge **ne distribue aucun BIOS de console ni firmware de constructeur**.
Le dépôt public ne contient que du code et des ressources synthétiques. Ce
document explique ce qui est nécessaire, ce qui est libre, ce qui ne l'est pas,
et où placer les fichiers.

## Ce qui ne demande aucun BIOS

La plupart des systèmes de la démonstration n'en demandent pas. Le ZX Spectrum
et l'Amstrad CPC sont les exceptions : ils ont besoin d'une ROM système.

| Système | Cœur testé | BIOS |
|---|---|---|
| NES | FCEUmm | aucun |
| Super Nintendo | Snes9x | aucun |
| Mega Drive | PicoDrive | aucun (TMSS optionnel) |
| Game Boy / Color | SameBoy | aucun (boot ROM optionnelle) |
| Game Boy Advance | mGBA | aucun (BIOS HLE) |
| Master System | PicoDrive | aucun pour la plupart des jeux |
| PC Engine (HuCard) | Mednafen PCE Fast | aucun |
| Atari 2600 | Stella 2014 | aucun |
| ZX Spectrum | Fuse | ROM 48K/128K **nécessaire** |
| Amstrad CPC | CrocoDS | ROM CPC **nécessaire** |

## Fichiers copyrightés

Ces fichiers ne peuvent pas être publiés avec TileForge. Vous devez les
extraire d'un matériel que vous possédez, ou utiliser une solution libre quand
elle existe. Vérifiez la législation de votre pays.

| Système | Fichiers attendus | Emplacement | Remplacement libre |
|---|---|---|---|
| ZX Spectrum | `48.rom`, `128-0.rom`, `128-1.rom` | `system/fuse/` | ROM de remplacement compatible Fuse (SE Basic, par exemple) |
| Amstrad CPC | `cpc464.rom`, `cpc6128.rom`, `cpc_amsdos.rom` | `system/` | pas de remplacement complet connu |
| Commodore 64 | `vice/kernal`, `vice/basic`, `vice/chargen` | `system/` | OpenROMs (libre) si VICE l'accepte |
| Amiga | `kick34005.A500`, `kick40068.A1200` | `system/` | AROS Kickstart (libre) pour certains jeux |
| Atari ST | `tos.img`, `st.img`, `etos512fr.img` | `system/` | **EmuTOS** (GPL) |
| Neo Geo | `neogeo.zip` | `system/` | aucun |
| PC Engine CD | `syscard3.pce` | `system/` | aucun |
| Game Boy Advance | `gba_bios.bin` (optionnel) | `system/` | BIOS HLE de mGBA |

## BIOS libres

### EmuTOS (Atari ST)

EmuTOS est un TOS libre sous GPL, compatible avec Hatari. La version utilisée
pour les tests est EmuTOS 1.4, image 512 Ko française :

```bash
curl -L -o emutos.zip \
  "https://sourceforge.net/projects/emutos/files/emutos/1.4/emutos-512k-1.4.zip"
unzip emutos.zip
cp emutos-512k-1.4/etos512fr.img system/
```

Empreinte SHA-256 de `etos512fr.img` :

```
6787ef0b2e5f6e372fb50f24ff6594f70416d9613fa98063ea47109b51b32a3b
```

### AROS Kickstart (Amiga)

AROS fournit un Kickstart libre pour certaines configurations. Vérifiez la
compatibilité du jeu et du cœur PUAE avant de l'utiliser.

### OpenROMs (Commodore 64)

OpenROMs est une réimplémentation libre des ROM du C64. Elle peut remplacer
`kernal`, `basic` et `chargen` selon la compatibilité du logiciel.

### C-BIOS (MSX)

C-BIOS est un BIOS MSX libre, utile pour les cœurs MSX qui l'acceptent.

## Où placer les fichiers

Le dossier système est passé aux cœurs :

- interface : champ **Dossier système** du dialogue *Mémoire d'émulateur* ;
- CLI : `--system-dir /chemin/vers/system` ;
- MCP : paramètre `system_dir` de `tileforge_emulator_memory`.

Arborescence typique :

```
system/
├── cpc464.rom
├── cpc6128.rom
├── cpc_amsdos.rom
├── etos512fr.img
├── kick34005.A500
├── kick40068.A1200
├── neogeo.zip
├── syscard3.pce
├── gba_bios.bin          (optionnel)
├── fuse/
│   ├── 48.rom
│   ├── 128-0.rom
│   └── 128-1.rom
└── vice/
    ├── kernal
    ├── basic
    └── chargen
```

## Vérifier son dossier

```bash
python tools/check_bios.py --system-dir /chemin/vers/system
python tools/check_bios.py --system-dir /chemin/vers/system --strict
```

Le script lit `tools/bios_manifest.json`, vérifie les empreintes connues et
distingue les fichiers obligatoires des optionnels. Il ne télécharge rien.

## Cœurs libretro

Les cœurs ne sont pas non plus dans le dépôt. Ils se téléchargent depuis le
buildbot officiel avec vérification d'empreinte :

```bash
python tools/fetch_cores.py --list
python tools/fetch_cores.py --output ~/.local/share/tileforge/cores
python tools/fetch_cores.py --check --output ~/.local/share/tileforge/cores
```

Le manifeste `tools/cores_manifest.json` donne l'URL, la taille, la licence et
l'empreinte SHA-256 de chaque cœur testé. Une URL `latest` peut évoluer : si
l'empreinte ne correspond plus, le script s'arrête et signale le changement.

## Ce que TileForge ne fera jamais

- publier une ROM, un BIOS ou un firmware copyrighté ;
- publier des graphismes extraits d'un jeu commercial ;
- télécharger automatiquement un BIOS copyrighté ;
- contourner une protection.

La démonstration `tileforge-demo/` est produite localement à partir de ROMs que
vous fournissez ; elle n'est pas versionnée.
