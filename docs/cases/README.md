# Fiches de cas — mémoire des extractions

Chaque jeu traité a sa fiche : ce qui a été essayé, les offsets, les formats,
les palettes, les vérifications et ce qui a résisté. Le but est simple :
**ne jamais refaire deux fois le même travail d'analyse**.

## Index

| Jeu | Machine | Support | Fiche |
|---|---|---|---|
| The Legend of Zelda (EU) | NES | ROM iNES | [zelda-nes.md](zelda-nes.md) |
| Project-X | Amiga | 4 IPF → ADF | [project-x-amiga.md](project-x-amiga.md) |

Les récits complets, avec les outils et les métriques, sont dans
[`../ETUDES_DE_CAS.md`](../ETUDES_DE_CAS.md).

## Ajouter une fiche

1. Copier [`TEMPLATE.md`](TEMPLATE.md) en `<jeu>-<machine>.md`.
2. Remplir au fil de l'extraction, pas à la fin : les fausses pistes
   s'oublient vite.
3. Ajouter la ligne dans l'index ci-dessus.
4. Si la fiche révèle un manque de l'outil, ouvrir une tâche dans
   [`../../ROADMAP.md`](../../ROADMAP.md) et, si le format est nouveau,
   documenter dans `docs/`.

## Règles

- Aucun contenu de jeu commercial dans une fiche : offsets, formats, métriques
  et captures **synthétiques** uniquement.
- Les commandes doivent être reproductibles avec le dépôt courant.
- Une fiche qui n'a pas été vérifiée l'annonce explicitement.
