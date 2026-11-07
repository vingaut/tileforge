# Publier TileForge sur GitHub

## Principe

Le dépôt public ne contient **que du code, de la documentation et des
ressources synthétiques**. Les ROMs, BIOS, firmwares, captures de jeux
commerciaux et projets personnels restent hors du dépôt.

Le `.gitignore` couvre déjà les extensions de ROMs, les archives, les dossiers
`extract/`, `graphisme/`, `megadrive/`, `snes/`, `projects/*.json` et les
sauvegardes. Vérifiez quand même avant chaque publication.

## Audit avant publication

```bash
# Fichiers suivis
git ls-files

# Recherche de chemins personnels
git grep -n -E "/home/|/Users/|freebox|Partage/codage" -- . ':!docs/mcp-clients.md'

# Gros fichiers
git ls-files -z | xargs -0 du -h | sort -hr | head -30

# Fichiers ignorés mais présents dans le dossier
git status --ignored --short | head -40
```

Aucun fichier de jeu ne doit apparaître dans `git ls-files`. Les images de
`docs/` sont toutes régénérables avec :

```bash
QT_QPA_PLATFORM=offscreen python tools/make_screenshots.py
```

## Branche publique propre

Si l'historique contient déjà des captures ou des fichiers commerciaux, ne
poussez pas `main` tel quel. Créez une branche orpheline qui ne contient que
l'arbre courant :

```bash
# Sauvegarde de l'historique local
git branch archive-avant-publication

# Branche sans historique
git checkout --orphan publication
git rm -rf --cached .
git add -A
git status --short
git commit -m "Publication initiale de TileForge"
```

Avant `git add -A`, vérifiez que les fichiers personnels non ignorés (notes de
recherche, autosaves) sont déplacés hors du dossier ou ajoutés à
`.git/info/exclude` (fichier local, non publié) :

```bash
echo "Décodeurs Compression Retro ROMs.md" >> .git/info/exclude
```

Le dépôt distant :

```bash
git remote add origin https://github.com/vingaut/tileforge.git
git push -u origin publication:main
```

Si le dépôt distant existe déjà avec un historique contaminé, le plus simple
est de le supprimer et de le recréer, ou d'utiliser `git filter-repo` pour
retirer les chemins concernés de tout l'historique.

## Réglages GitHub

- **Description** : « Extraction et reconstruction de graphismes de jeux 8/16
  bits — tuiles, sprites, cartographie, désassembleurs, mémoire d'émulateur,
  MCP. »
- **Topics** : `retrocomputing`, `rom-hacking`, `tiles`, `sprites`, `snes`,
  `megadrive`, `atari-st`, `mcp`, `python`, `pyside6`.
- **License** : MIT (fichier `LICENSE`).
- **Actions** : activer le workflow `.github/workflows/tests.yml`.
- **Branche protégée** : `main`, tests obligatoires avant fusion.
- **Releases** : version issue de `tileforge/version.py`, notes reprises du
  `CHANGELOG` intégré.

## Checklist de release

```bash
.venv/bin/python tests/run_all.py
.venv/bin/ruff check tileforge tests tools
.venv/bin/python -m tileforge --selftest
.venv/bin/python tools/mcp_config.py --check
.venv/bin/python tools/fetch_cores.py --check --output ./cores
.venv/bin/python tools/check_bios.py --system-dir ./system
python -m build --wheel
```

Vérifiez ensuite :

- aucune ROM/BIOS/image de jeu dans `git status` ;
- les captures de `docs/` sont synthétiques ;
- le README et le README anglais pointent vers les bons chemins ;
- la version et la date sont cohérentes dans `tileforge/version.py` ;
- le paquet installé expose bien `tileforge` et `tileforge-mcp`.

## Cœurs et BIOS

Les cœurs libretro et les BIOS ne sont pas versionnés :

- `tools/cores_manifest.json` + `tools/fetch_cores.py` téléchargent les cœurs
  depuis le buildbot officiel avec vérification SHA-256 ;
- `tools/bios_manifest.json` + `tools/check_bios.py` décrivent les BIOS
  attendus, leur statut légal et leur emplacement ;
- `docs/BIOS.md` explique ce qui est libre (EmuTOS, AROS, OpenROMs, C-BIOS) et
  ce qui doit être extrait d'un matériel possédé.

Ne publiez jamais un BIOS copyrighté, même dans une release ou une archive de
démonstration.

## Démonstration

`tileforge-demo/` est produit localement à partir de ROMs fournies par
l'utilisateur. Il n'est pas versionné. La documentation peut citer les jeux
testés, mais pas inclure leurs graphismes.

## Sécurité et vie privée

- aucun secret, token ou mot de passe dans le dépôt ;
- pas de chemin `/home/...` dans les fichiers publiés ;
- le serveur MCP lit et écrit des fichiers avec les droits de l'utilisateur :
  ne connectez que des clients de confiance ;
- les archives et ROMs téléchargées restent sous la responsabilité de
  l'utilisateur.
