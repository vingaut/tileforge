# Fiche de jeu — modèle

> Copier ce fichier sous `docs/cases/<jeu>-<machine>.md`, remplir au fur et à
> mesure, et le mettre à jour à la fin de l'extraction. Une fiche doit suffire
> à refaire le travail sans relire toute la conversation.

## Identité

- **Jeu** :
- **Éditeur / année** :
- **Machine** :
- **Support d'entrée** (ROM, ADF, STX, archive…) :
- **Taille / empreinte** :
- **Statut** : exploration / partiel / validé

## Point de départ

Décrire le fichier tel qu'il arrive : en-tête, archive, membres, protections,
compressions candidates. Commandes utilisées :

```bash
# exemples
.venv/bin/python tools/amiga.py list disque.adf
```

## Chaîne suivie

| Étape | Outil / commande | Résultat |
|---|---|---|
| Inventaire | | |
| Extraction | | |
| Décompression | | |
| Localisation | | |
| Rendu | | |
| Vérification | | |

## Offsets et formats

| Élément | Offset | Taille | Format | Palette | Remarques |
|---|---|---|---|---|---|
| | | | | | |

## Palettes

- Offset(s) :
- Nombre de couleurs :
- Appariement image ↔ palette :
- Tables de fondu écartées :

## Résultats

- Nombre de blocs / tuiles / sprites :
- Fichiers produits :
- Projet `.tileforge.json` :
- Captures / aperçus :

## Vérifications

- [ ] Aperçu visuel reconnaissable.
- [ ] Recoupement avec une table de pointeurs ou le code.
- [ ] Recoupement avec la mémoire d'émulateur (si disponible).
- [ ] Densité des plans cohérente.
- [ ] Palette cohérente (pas de fondu, premier noir).

## Ce qui a résisté

Décrire les fausses pistes, les formats non décodés, les hypothèses rejetées.
C'est la partie la plus utile pour la prochaine extraction.

## Prochaines étapes

- [ ] ...
