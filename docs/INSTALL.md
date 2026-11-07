# Installation depuis les sources

## Prérequis

- **Python ≥ 3.10** (testé localement avec 3.14, CI avec 3.10 → 3.13) ;
- `git` ;
- pour l'interface : **PySide6** ;
- pour les archives 7z : `py7zr` **ou** la commande `7z`/`7za` ;
- pour les cœurs libretro : un dossier de cœurs (voir plus bas) ;
- pour les BIOS : voir [BIOS.md](BIOS.md).

## Installation minimale (cœur + MCP + tests)

```bash
git clone https://github.com/<compte>/tileforge.git
cd tileforge
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .
.venv/bin/python -m tileforge --selftest
.venv/bin/python tests/run_all.py
```

Le cœur (`core`, `detect`, `assemble`, `mcp`) ne dépend ni de Qt ni de
l'interface.

## Binaire Linux déjà compilé

Un binaire Linux x86_64 est joint à la release GitHub 1.4.1 :
`tileforge-1.4.1-linux-x86_64.tar.gz` (environ 91 Mo).

```bash
tar xzf tileforge-1.4.1-linux-x86_64.tar.gz
cd tileforge-1.4.1-linux-x86_64
./lancer.sh
```

L'archive contient `NOTICE.txt` (licences Qt/PySide6 et composants tiers),
`LICENSE` et la documentation. Aucun BIOS ni ROM n'est inclus.

## Interface graphique

```bash
.venv/bin/pip install -e ".[gui]"
.venv/bin/python -m tileforge
```

ou, si le venv existe déjà :

```bash
./run.sh
```

## Développement

```bash
.venv/bin/pip install -e ".[gui,dev]"
.venv/bin/python tests/run_all.py
.venv/bin/ruff check tileforge tests tools
```

Les tests sont **synthétiques** : aucune ROM, aucun BIOS, aucune image de jeu
n'est nécessaire.

## Archives zip/7z

Le zip est lu avec la bibliothèque standard. Pour le 7z, installez `py7zr` :

```bash
.venv/bin/pip install py7zr
```

ou installez la commande système `7z` (paquet `p7zip-full` sur Debian/Ubuntu).

## Cœurs libretro

Les cœurs ne sont pas versionnés. Téléchargez ceux dont vous avez besoin :

```bash
python tools/fetch_cores.py --list
python tools/fetch_cores.py --output ~/.local/share/tileforge/cores
python tools/fetch_cores.py --check --output ~/.local/share/tileforge/cores
```

Puis indiquez le dossier :

```bash
export TILEFORGE_CORES="$HOME/.local/share/tileforge/cores"
```

ou passez `--core /chemin/vers/coeur_libretro.so` aux outils.

Le manifeste `tools/cores_manifest.json` contient les URL, tailles, licences et
empreintes SHA-256 des cœurs testés. Les binaires ne sont pas redistribués.

## BIOS

Aucun BIOS copyrighté n'est fourni. Les systèmes de la démonstration qui n'en
ont pas besoin fonctionnent immédiatement ; pour les autres, voir
[BIOS.md](BIOS.md) et vérifiez votre dossier :

```bash
python tools/check_bios.py --system-dir ~/.local/share/tileforge/system
```

## MCP (assistant LLM)

```bash
python tools/mcp_config.py --check
python tools/mcp_config.py                    # Claude Desktop
python tools/mcp_config.py --client cursor    # Cursor
python tools/mcp_config.py --client vscode    # VS Code
python tools/mcp_config.py --client claude-code
```

Guide détaillé : [mcp-clients.md](mcp-clients.md).

## Démonstration multi-systèmes

Nécessite un dossier de ROMs et les cœurs :

```bash
python tools/build_demo.py \
    --roms-root /path/to/roms \
    --cores ~/.local/share/tileforge/cores \
    --output ../tileforge-demo
```

Les ROMs ne sont jamais copiées ; seules les images produites, un extrait de
banque et les rapports JSON sont écrits. Voir [BIOS.md](BIOS.md) pour les
systèmes qui demandent un BIOS.

## Régénérer les captures de la documentation

```bash
QT_QPA_PLATFORM=offscreen python tools/make_screenshots.py
```

Toutes les images de `docs/` sont synthétiques et peuvent être publiées.

## Versions testées

| Paquet | Version locale |
|---|---|
| Python | 3.14.4 |
| numpy | 2.5.4 |
| Pillow | 13.0.0 |
| PySide6 | 6.12.0 |
| ruff | 0.17.4 |
| 7-Zip | 26.00 |

La CI vérifie Python 3.10 à 3.13. Les dépendances déclarées dans
`pyproject.toml` sont volontairement larges ; ces versions sont celles qui ont
servi à valider la démonstration.

## Dépannage

| Symptôme | Solution |
|---|---|
| `ModuleNotFoundError: numpy` | utilisez `.venv/bin/python`, pas le Python système |
| `ModuleNotFoundError: PySide6` | `pip install -e ".[gui]"` |
| 7z non lu | `pip install py7zr` ou installez `7z` |
| aucun cœur trouvé | `tools/fetch_cores.py`, puis `TILEFORGE_CORES` |
| BIOS manquant | `tools/check_bios.py`, voir [BIOS.md](BIOS.md) |
| MCP ne répond pas | `python tools/mcp_config.py --check` |
