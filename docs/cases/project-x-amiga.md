# Project-X (Amiga, Team17 1992) — fiche de cas

- **Machine** : Amiga OCS
- **Support** : 4 images disque IPF (CAPS/SPS), 1 048 872 octets chacune
- **Statut** : validé (extraction documentée) ; TileForge 1.5.0 couvre la chaîne
- **Récit complet** : [`../ETUDES_DE_CAS.md`](../ETUDES_DE_CAS.md), section 3
- **Feuille de route issue de ce cas** : [`../tileforge_upgrade.md`](../tileforge_upgrade.md)

## Point de départ

Quatre IPF protégés Copylock. Un IPF n'est pas une image de disque : c'est un
flux de cellules magnétiques avec métadonnées de densité variable. Il faut le
convertir en ADF, décoder le MFM, puis le système de fichiers AmigaDOS.

## Chaîne suivie

| Étape | Outil / méthode | Résultat |
|---|---|---|
| Inventaire | `inspect_file`, `list_archive` | archive, 4 IPF, compressions candidates |
| Conversion | bibliothèque SPS (`capsimage`) | 4 ADF de 901 120 octets |
| FS | décodeur OFS maison | 1 749 secteurs utiles sur 1 760 par disquette |
| Extraction | OFS tolérant aux checksums | **28 fichiers** |
| Décompression | Imploder (`ATN!`) | **28/28** fichiers |
| Imbrication | rescan récursif | **31 blocs Imploder** imbriqués |
| Exécutables | hunks | segments, adresses de chargement |
| Écrans | copper + planaire | 6 écrans de chargement |
| Sprites | composantes connexes | **1 043 sprites**, 10 planches |

## Offsets et formats

- Exécutables hunk : `HUNK_HEADER 0x3F3`, `HUNK_CODE 0x3E9`,
  `HUNK_DATA 0x3EA`, `HUNK_RELOC32 0x3EC`.
- Écrans de chargement : **256×256 utiles dans un bitmap de 320**
  (64 colonnes de bourrage), **plane-major**, 10 240 octets par plan.
- Planches de sprites : **640×256, 5 plans**, 102 400 octets.
- Palettes : **six palettes thématiques** (une par niveau) à la fin de chaque
  fichier LPI, six blocs consécutifs de 32 mots `0x0RGB`.
- Code déclarant 6 plans mais **5 utiles** sur 4 images sur 6 (6ᵉ plan vide).

## Extrait de code qui a débloqué la localisation

```text
lea.l   $12cd6.l, a0      ; adresse de l'image
move.l  a0, d0
lea.l   $21d7a.l, a1      ; liste copper
move.l  #6, d2            ; 6 bitplanes
adda.l  #$2800, a0        ; 10 240 octets par plan
```

Trois informations : où, combien de plans, quelle taille de plan.

## Vérifications

- Les six écrans ont été rendus avec la bonne palette après appariement
  image ↔ palette (espace, montagnes, volcan, rivière, lentille, fusée).
- Les offsets des planches ont été recoupés par le code et le rendu.
- Les checksums AmigaDOS étaient tous faux (Copylock) : la lecture a continué
  malgré tout.

## Ce qui a résisté

- L'IPF : aucun décodeur libre ; conversion ADF obligatoire.
- L'Imploder : bloc en fin de fichier, décompression à rebours ; un décodeur
  naïf échoue.
- L'imbrication : sans rescan récursif, 100 % des graphismes sont manqués.
- La palette : elle n'est pas dans l'image ; six candidates, il faut choisir.
- Le 6ᵉ plan vide : le code ment sur le nombre de plans.

## Reproduire avec TileForge 1.5.0

```bash
# 1. Convertir l'IPF en ADF (hors TileForge, licence SPS)
# 2. Ouvrir le disque malgré les checksums faux
.venv/bin/python tools/amiga.py list disque1.adf
.venv/bin/python tools/amiga.py extract disque1.adf CHEMIN/FICHIER -o fichier.bin
# 3. Descendre les blocs imbriqués
.venv/bin/python tools/amiga.py nested fichier.bin -o sortie/
# 4. Analyser un exécutable
.venv/bin/python tools/amiga.py hunk sortie/00_imploder_d0_00000000.bin
# 5. Rendre un écran 256×256 dans un bitmap de 320
.venv/bin/python tools/amiga.py screen ecran.bin --width 256 --height 256 \
    --planes 5 --layout plane --stride 40 --palette-offset 0x... -o ecran.png
```

## Prochaines étapes

- [ ] Décodeur IPF/MFM natif (licence SPS à vérifier).
- [ ] Profil de jeu pour les 10 planches et les 6 écrans.
- [ ] Fiche par niveau (offsets des palettes, planches).
