# Contribuer à TileForge

Merci de votre intérêt. Ce document décrit comment installer le projet, lancer
les tests et proposer une contribution.

---

## 1. Installation de développement

```bash
git clone <votre-dépôt> tileforge
cd tileforge
python3 -m venv .venv
.venv/bin/pip install -e ".[gui,dev]"
```

Le cœur (`core`, `detect`, `assemble`) et le serveur MCP fonctionnent sans Qt.
Seule l'interface en a besoin : `pip install -e ".[dev]"` suffit pour les tests.

```bash
.venv/bin/python tests/run_all.py      # 220 tests, sans interface
.venv/bin/python -m tileforge          # l'application
.venv/bin/python -m tileforge --selftest
```

---

## 2. Règles de qualité

**Aucun contenu de jeu commercial dans le dépôt.** Pas de ROM, pas de
disquette, pas de graphisme extrait d'un jeu. Les tests fabriquent leurs
données. Le fichier `.gitignore` exclut déjà ces extensions ; vérifiez avec
`git status` avant de proposer une contribution.

**Un décodeur = un test.** Tout décompresseur ou format de tuiles ajouté doit
être accompagné d'un test : vecteur officiel quand il en existe un, aller-retour
sinon. Un décodeur non testé n'est pas accepté.

**Pas de code mort ni de dépendance inutile.** Le cœur ne dépend que de
`numpy` et `Pillow` ; l'interface de `PySide6`.

**Style.** `ruff check tileforge tests tools` doit passer. Lignes de 100
caractères au plus, docstrings en français, commentaires expliquant le
*pourquoi* plutôt que le *comment*.

---

## 3. Ajouter un décompresseur

```python
from tileforge.core.compression import Decompressor, register

def mon_format(data: bytes, offset: int = 0, max_size: int = 1 << 24) -> bytes:
    """Décompresse ... (décrire le format et citer la source)."""
    ...
    return bytes(out)

register("mon_format", mon_format, "Mon format", "Mega Drive",
         "Jeux concernés ; particularités.")
```

Puis, dans `tests/test_compression.py`, un test qui prouve le décodage.

Trois points à respecter :

1. **Signaler la fin.** Si le format n'a pas de marqueur de fin, documentez-le :
   le moteur ne le balayera pas automatiquement (il ne peut jamais échouer).
2. **Respecter `max_size`** et lever `DecompressionError` sur un flux
   incohérent, plutôt que de produire des octets au hasard.
3. **Citer la source** de la spécification dans la docstring.

## 4. Ajouter un format de tuiles

Dans `tileforge/core/formats.py`, ajoutez un `TileFormat` à la liste
`FORMATS`, avec son `layout`, sa profondeur et sa palette. Ajoutez un test
d'aller-retour dans `tests/test_formats.py`.

## 5. Ajouter un jeu ou un compresseur maison

Créez un module dans `tileforge/games/`, exportez un profil JSON
(`tileforge/profile/1`) et documentez l'offset, le format et la palette dans
l'aide. C'est le mécanisme prévu pour rendre un jeu reproductible.

---

## 6. Commits

Messages en français, à l'impératif, avec un préfixe :

| Préfixe | Usage |
|---|---|
| `feat:` | nouvelle fonctionnalité |
| `fix:` | correction |
| `perf:` | performance |
| `docs:` | documentation seule |
| `test:` | tests seuls |
| `refactor:` | réorganisation sans changement de comportement |
| `chore:` | outillage, dépendances, métadonnées |

Le corps du message explique le problème et la mesure qui prouve que c'est
réglé. Un commit = un sujet.

---

## 7. Proposer une contribution

1. Créez une branche (`feat/nom-court`).
2. Vérifiez que `python tests/run_all.py` et `ruff check` passent.
3. Ouvrez une *pull request* en décrivant le problème, la solution et ce qui a
   été vérifié.

Pour les nouveaux décompresseurs, joignez si possible un vecteur de test
officiel ou un fichier libre de droits qui prouve le décodage.
