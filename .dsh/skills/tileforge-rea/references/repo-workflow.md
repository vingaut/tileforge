# Ajouter un format, un décompresseur, un outil

> Référence de la compétence `tileforge-rea`. Elle décrit les conventions du
> dépôt pour que chaque ajout reste testé, documenté et publiable.

## 0. Avant de coder

- Vérifier que le format n'existe pas déjà : `list_tile_formats`,
  `DECOMPRESSORS`, `docs/`.
- Chercher une **source de spécification** (Sega Retro, SnesLab, GBATEK, RKM
  Amiga, documentation du jeu). Citer la source dans la docstring.
- Construire un **vecteur de test indépendant** : encodeur de référence,
  fichier produit par l'outil d'origine, ou flux officiel. Ne jamais tester un
  décodeur avec sa propre sortie.
- Vérifier la licence : pas de code GPL recopié dans ce dépôt MIT. Une
  réimplémentation à partir de la spécification est acceptable ; recopier du
  code GPL ne l'est pas.

## 1. Nouveau format de tuiles

1. `tileforge/core/formats.py` : ajouter un `TileFormat` dans `FORMATS`
   (`key`, `name`, `tile_w`, `tile_h`, `bpp`, `layout`, `bytes_per_tile`,
   `system_key`, `palette_key`, `transparent_index`).
2. Vérifier que `layout` existe déjà ; sinon ajouter le décodage dans
   `decode_block`.
3. `tests/test_formats.py` : encoder une tuile de test et vérifier l'égalité
   exacte des indices.
4. `tileforge/core/systems.py` : si la machine manque, ajouter un `SystemSpec`.
5. `docs/` : une ligne dans la doc du système et, si utile, dans `README`.

## 2. Nouveau décompresseur

1. Écrire une fonction `(data, offset) -> bytes` qui lève
   `DecompressionError` sur flux invalide.
2. L'enregistrer dans `DECOMPRESSORS` (`tileforge/core/compression.py`) avec
   `key`, `name`, `machine`, `notes`, `max_size`.
3. Ajouter un vecteur dans `tests/test_compression.py` ou un fichier dédié :
   flux connu → sortie attendue, flux tronqué → erreur, CRC faux → toléré.
4. Si le format est Amiga, vérifier `imploder.py`/`rnc.py` et
   `nested.py` pour la détection imbriquée.
5. Documenter le magic, le sens de lecture, la taille, la source.

## 3. Nouvel outil MCP

1. `tileforge/mcp/tools.py` : fonction sérialisable, chemins absolus, aperçus
   PNG écrits dans `work_dir()`.
2. `tileforge/mcp/server.py` : `Tool(...)` avec description, schéma `_obj`,
   fonction.
3. `tests/test_mcp_config.py` : mettre à jour le nombre d'outils et ajouter le
   nom au handshake.
4. `README.md`/`README.en.md`, `docs/mcp-clients.md` : nombre d'outils et
   description.
5. Si l'outil touche l'interface, ajouter une fiche d'aide et les traductions.

## 4. Nouvelle chaîne / nouveau système

- Créer un module `tileforge/core/<system>.py` sans dépendance Qt.
- Exposer les fonctions dans un outil MCP et, si utile, un script
  `tools/<system>.py`.
- Ajouter une section `docs/<SYSTEM>.md` et une fiche `docs/cases/`.
- Tests synthétiques : disque/image fabriquée par le test, jamais un jeu.
- Mettre à jour `ROADMAP.md` (phase + journal) et `tileforge/version.py`.

## 5. Version, build, publication

```bash
# Qualité
.venv/bin/ruff check tileforge tests tools
.venv/bin/python tests/run_all.py
.venv/bin/python -m tileforge --selftest
.venv/bin/python tools/doctor.py
.venv/bin/python tools/verify_publication.py

# Paquet Python
.venv/bin/python -m build

# Binaire Linux
.venv-build/bin/pyinstaller --noconfirm --clean --distpath dist \
    --workpath build packaging/tileforge.spec

# Commit
git add <fichiers>
git commit -m "feat: ..."   # ou fix:, docs:, chore:
git push origin HEAD
```

`tileforge/version.py` : `__version__`, `VERSION_TUPLE`, `BUILD_DATE`,
`CHANGELOG`. Mettre aussi à jour le nombre de tests dans README/ROADMAP si on
le cite.

## 6. Règles de publication

- Aucun fichier de jeu commercial : ROM, disque, BIOS, capture, sprite.
- Fixtures synthétiques ou produites par un outil libre, avec attribution.
- `.gitignore` couvre les extensions de ROMs/disques ; vérifier
  `git status --ignored` avant un `git add -A`.
- Les images de `docs/` sont régénérables par `tools/make_screenshots.py`.

## 7. Checklist de fin

- [ ] Tests verts, ruff propre.
- [ ] Décodeur validé par un vecteur indépendant.
- [ ] Docstring avec source et limites.
- [ ] Fiche `docs/cases/` ou section de doc mise à jour.
- [ ] Version/changelog si la fonctionnalité est visible.
- [ ] Aucun contenu commercial ajouté.
- [ ] Commit poussé, message clair.
