# The Legend of Zelda (NES, EU) — fiche de cas

- **Machine** : NES / Famicom
- **Support** : ROM iNES, 131 088 octets, mapper MMC1
- **Statut** : validé (extraction documentée)
- **Récit complet** : [`../ETUDES_DE_CAS.md`](../ETUDES_DE_CAS.md), section 2

## Point de départ

ROM `.nes` iNES : 8 banques PRG de 16 Kio, **0 banque CHR**. C'est le cas
intéressant : les graphismes ne sont pas dans une banque CHR dédiée, ils sont
dans la PRG et le jeu les copie en VRAM au chargement.

## Chaîne suivie

| Étape | Outil | Résultat |
|---|---|---|
| En-tête | `inspect_file` | iNES, mapper 1, 8 banques PRG, 0 CHR |
| Cartographie | `cartography` | zones, entropie, tables de pointeurs |
| Recherche | `scan_graphics` format `nes` | 582 candidats testés, 103 notés |
| Format | `identify_format` | 8×8, 2 plans, plans séquentiels |
| Recoupement | désassemblage 6502 (REA/rizin), table du loader CHR | offsets confirmés |
| Validation | `open_bank`, `validate_sprite`, `export_atlas`, `save_project` | 19 sprites Link/objets |
| Rendu | script Pillow | planches avec les palettes du jeu |

## Formats et règles

- Tuiles 8×8, 2 plans, 8 octets plan 0 puis 8 octets plan 1.
- **15 blocs graphiques** : 6 blocs de sprites, 3 de boss, 3 de décor,
  2 de police, 1 de splash.
- **3 règles d'assemblage** :
  - `wide` : 16×16 = 4 tuiles (Link, armes, objets) ;
  - `mirror` : 16×16 = 2 tuiles (8×16) + miroir horizontal (ennemis) ;
  - `boss` : 32×32 = 8 tuiles + miroir (boss).
- **10 palettes de niveau** (Overworld + donjons 1→9) lues dans les blocs
  `LevelInfo`, plus les palettes spéciales (menu, titre, splash) et les
  palettes de boss injectées en `$3F1C`.

## Vérifications

- Trois sources indépendantes pour les offsets : désassemblage 6502, table de
  pointeurs du loader CHR, rendu visuel.
- La règle `mirror` est confirmée par la routine
  `Anim_WriteMirroredSpritePair`, pas par intuition.

## Ce qui a résisté

- L'absence de banque CHR : il faut suivre le code qui copie vers la VRAM.
- Les palettes ne sont pas dans les blocs graphiques : il faut les lire dans
  les structures de niveau.

## Reproduire

```bash
.venv/bin/python -m tileforge --selftest
# puis via MCP : inspect_file → cartography → scan_graphics → identify_format
# → open_bank → validate_sprite → export_atlas → save_project
```

## Prochaines étapes

- [ ] Ajouter un profil de jeu pour rejouer les 15 offsets sans scan.
- [ ] Vérifier la règle `boss` sur les autres boss.
