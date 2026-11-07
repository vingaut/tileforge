# Logiciels tiers

TileForge est distribué sous licence MIT (voir `LICENSE`). Il utilise ou
recommande les composants suivants, **non inclus dans le dépôt** sauf mention
contraire.

## Dépendances Python

| Paquet | Rôle | Licence | Site |
|---|---|---|---|
| numpy | calculs | BSD-3-Clause | https://numpy.org/ |
| Pillow | lecture PNG | HPND | https://python-pillow.org/ |
| PySide6 / Qt | interface | LGPL-3.0 / commercial | https://www.qt.io/ |
| py7zr (optionnel) | archives 7z | LGPL-2.1 | https://github.com/miurahr/py7zr |
| ruff (développement) | style | MIT | https://docs.astral.sh/ruff/ |

## Cœurs libretro

Les cœurs ne sont pas distribués. `tools/fetch_cores.py` les télécharge depuis
le buildbot officiel de libretro et vérifie leur empreinte. Les licences et
les dépôts amont sont indiqués dans `tools/cores_manifest.json` : FCEUmm,
Snes9x, PicoDrive, Genesis Plus GX, SameBoy, Gambatte, mGBA, Mednafen PCE
Fast, Stella 2014, Fuse, CrocoDS, VICE, PUAE et Hatari.

Chaque cœur reste sous sa licence propre. Si vous redistribuez un binaire de
cœur, vous devez respecter cette licence (source, notices, etc.).

## BIOS et firmwares

Aucun BIOS n'est distribué. Voir [BIOS.md](BIOS.md) pour les fichiers libres
(EmuTOS, AROS Kickstart, OpenROMs, C-BIOS) et les fichiers copyrightés à
extraire d'un matériel possédé.

## 7-Zip

La commande `7z` est un logiciel tiers (licence LGPL + unlicense pour certaines
parties). Elle n'est utilisée que si `py7zr` n'est pas installé.

## Contenu de démonstration

`docs/planche_demo.png`, les captures de `docs/` et les fixtures de `tests/`
sont générées par le projet (voir `tools/make_screenshots.py` et
`tools/make_fixture.py`). Aucune image de jeu commercial n'est incluse.
