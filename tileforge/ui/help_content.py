"""Textes de l'aide interactive et documentation intégrée.

Deux choses vivent ici :

* ``HELP`` — la fiche affichée quand on survole un bouton deux secondes en mode
  aide interactive (titre, explication, raccourci) ;
* ``DOC_SECTIONS`` — le contenu de la page d'aide et du tutoriel.

Les clés d'aide sont posées sur les widgets par ``help.bind(widget, clé)``.
À défaut, ``TEXT_TO_KEY`` permet de retrouver une fiche à partir du libellé
d'un bouton, ce qui couvre automatiquement l'interface.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpEntry:
    title: str
    text: str
    shortcut: str = ""
    section: str = ""

    @property
    def html(self) -> str:
        return self.text.replace("\n", "<br>")


# ---------------------------------------------------------------------------
# Fiches d'aide
# ---------------------------------------------------------------------------

HELP: dict[str, HelpEntry] = {
    # -- fenêtre principale -------------------------------------------------
    "app.new": HelpEntry(
        "Nouveau projet", "Ferme le projet courant (après confirmation) et repart "
        "d'une planche vide.", "Ctrl+N", "demarrage"),
    "app.open": HelpEntry(
        "Ouvrir un projet", "Recharge un fichier .tileforge.json : planche, tuiles, "
        "sprites, atlas, journal et recettes.", "Ctrl+O", "demarrage"),
    "app.import_rom": HelpEntry(
        "Importer une ROM ou une archive", "Ouvre une ROM, un fichier zip/7z ou "
        "une banque brute. Le dialogue permet de choisir l'offset, le format de "
        "tuile et la compression ; c'est le point d'entrée pour un jeu autre que "
        "Barbarian.", "Ctrl+Maj+O", "demarrage"),
    "app.save": HelpEntry(
        "Enregistrer", "Écrit le projet sur disque. La planche est embarquée dans le "
        "fichier, il reste donc lisible sans la ROM d'origine.", "Ctrl+S", "demarrage"),
    "app.save_as": HelpEntry(
        "Enregistrer sous", "Enregistre le projet sous un autre nom.", "Ctrl+Maj+S",
        "demarrage"),
    "app.undo": HelpEntry(
        "Annuler", "Revient à l'état précédent : tuiles, placements, validations.",
        "Ctrl+Z", "raccourcis"),
    "app.redo": HelpEntry(
        "Refaire", "Rétablit l'action annulée.", "Ctrl+Y", "raccourcis"),
    "app.machines": HelpEntry(
        "Résolutions des machines", "Ouvre le catalogue des 76 consoles, ordinateurs "
        "et bornes d'arcade avec leurs résolutions natives, palettes et tailles de "
        "tuile.", "", "machines"),
    "app.help_mode": HelpEntry(
        "Aide interactive", "Active le mode aide : survolez un bouton deux secondes "
        "sans cliquer pour lire ce qu'il fait.", "F1", "aide"),
    "app.help": HelpEntry(
        "Aide et tutoriel", "Ouvre la page d'aide complète : démarrage, concepts, "
        "tutoriel Barbarian, référence des écrans et dépannage.", "Ctrl+F1", "aide"),
    "app.updates": HelpEntry(
        "Mises à jour", "Vérifie s'il existe une version plus récente, affiche les "
        "notes de version et l'installe.", "", "mises_a_jour"),
    "app.fullscreen": HelpEntry(
        "Plein écran", "Bascule la fenêtre en plein écran.", "F11", "raccourcis"),
    "app.weights": HelpEntry(
        "Poids du coût", "Règle l'importance relative des six indices de coût utilisés "
        "par l'assemblage automatique.", "", "cout"),

    # -- écran Planche ------------------------------------------------------
    "sheet.open_png": HelpEntry(
        "Ouvrir une image PNG", "Charge une planche déjà rendue (PNG, GIF, BMP). La "
        "couleur de fond du bord est rendue transparente automatiquement.", "", "planche"),
    "sheet.open_raw": HelpEntry(
        "Ouvrir une banque brute", "Ouvre un fichier binaire de ROM : on choisit "
        "l'offset, le format de tuile, la palette et l'on voit un aperçu immédiat.",
        "", "formats"),
    "sheet.open_barbarian": HelpEntry(
        "Barbarian ST", "Lit directement la disquette .stx (Pasti), y extrait "
        "BARB.DAT et décode la banque de 252 tuiles de 24 × 21 px.", "", "barbarian"),
    "sheet.palette": HelpEntry(
        "Éditeur de palette", "Modifie les couleurs de la banque, charge une palette "
        ".pal ou .gpl, et choisit l'index transparent.", "", "palette"),
    "sheet.transparent": HelpEntry(
        "Fond transparent", "Rend transparente la couleur de fond détectée sur le "
        "bord de la planche.", "", "palette"),
    "sheet.analyse": HelpEntry(
        "Analyser la résolution", "Détecte l'agrandissement éventuel, la résolution "
        "native, le nombre de couleurs, la profondeur et le pas de grille, puis "
        "propose les machines compatibles.", "", "resolution"),
    "sheet.systems": HelpEntry(
        "Choisir une machine", "Parcourt le catalogue complet des machines et de "
        "leurs résolutions, filtrable et trié par famille.", "", "machines"),
    "sheet.apply_system": HelpEntry(
        "Appliquer la machine", "Reprend la taille de tuile et la palette de la "
        "machine choisie pour les prochaines détections.", "", "machines"),
    "sheet.detector": HelpEntry(
        "Détecteur de tuiles", "Choisit l'algorithme de découpage : grille fixe, "
        "période, projections, XY-cut, composantes connexes ou manuel.", "", "detection"),
    "sheet.detect": HelpEntry(
        "Détecter", "Lance le détecteur choisi avec les paramètres affichés et "
        "remplace (ou ajoute) les tuiles de la planche.", "", "detection"),
    "sheet.compare": HelpEntry(
        "Comparer les méthodes", "Essaie tous les détecteurs et garde celui qui "
        "produit le plus de tuiles.", "", "detection"),
    "sheet.replace": HelpEntry(
        "Remplacer les tuiles", "Coché : la détection efface le découpage existant. "
        "Décoché : elle l'ajoute.", "", "detection"),
    "sheet.quality": HelpEntry(
        "Contrôle qualité", "Signale les chevauchements, tuiles vides, tailles "
        "incohérentes et débordements. Cliquez sur une ligne pour sélectionner la "
        "tuile concernée.", "", "planche"),
    "sheet.tool_select": HelpEntry(
        "Outil sélection", "Sélectionne, déplace et redimensionne les tuiles. "
        "Ctrl+clic ajoute à la sélection, glisser dans le vide fait un lasso.", "V",
        "edition"),
    "sheet.tool_create": HelpEntry(
        "Nouvelle tuile", "Trace un nouveau rectangle de tuile à la souris.", "R",
        "edition"),
    "sheet.snap": HelpEntry(
        "Aimant", "Aligne les déplacements et redimensionnements sur le pas de la "
        "grille.", "G", "edition"),
    "sheet.grid": HelpEntry(
        "Grille de repère", "Affiche la grille de pas de tuile par-dessus l'image "
        "(visible au-delà de 150 % de zoom).", "", "edition"),
    "sheet.fit": HelpEntry(
        "Ajuster", "Met l'image entière dans la fenêtre.", "0", "raccourcis"),
    "sheet.canvas": HelpEntry(
        "Planche", "Molette pour zoomer, clic du milieu (ou Espace + glisser) pour "
        "déplacer, clic droit pour fusionner, scinder, dupliquer ou supprimer. "
        "Les poignées du rectangle sélectionné permettent de le redimensionner.",
        "", "edition"),

    # -- écran Atelier ------------------------------------------------------
    "asm.palette": HelpEntry(
        "Tuiles disponibles", "Vignettes des tuiles du groupe courant qui ne sont pas "
        "encore placées. Glissez-en une sur le canevas, ou cliquez puis cliquez sur "
        "une case (mode tactile).", "", "atelier"),
    "asm.canvas": HelpEntry(
        "Canevas d'assemblage", "Glissez une tuile pour la déplacer (elle échange sa "
        "place si la case est occupée). Double-clic ou Suppr pour la retirer.", "",
        "atelier"),
    "asm.grid": HelpEntry(
        "Dimensions de la grille", "Nombre de colonnes et de lignes du sprite. Le "
        "produit donne le nombre de tuiles par sprite.", "", "grilles"),
    "asm.cost": HelpEntry(
        "Coût de l'assemblage", "Somme pondérée des six indices : plus bas = raccords "
        "plus cohérents. Les barres montrent la contribution de chacun.", "", "cout"),
    "asm.auto": HelpEntry(
        "Assemblage automatique", "Classe des assemblages candidats avec six méthodes "
        "et affiche un aperçu de chacun ; double-cliquez pour en charger un.", "",
        "auto"),
    "asm.grids": HelpEntry(
        "Tester les grilles", "Essaie toutes les grilles plausibles sur le même paquet "
        "de tuiles et les classe (aperçu, coût, nombre de sprites par banque).", "",
        "grilles"),
    "asm.recipe": HelpEntry(
        "Appliquer la recette", "Place les tuiles du groupe courant selon la "
        "correspondance apprise dans l'onglet Analyse.", "", "regle"),
    "asm.validate": HelpEntry(
        "Valider le sprite", "Enregistre le sprite, l'ajoute à l'atlas et journalise "
        "l'événement. Demande confirmation si des cases sont vides.", "Entrée",
        "atelier"),
    "asm.next": HelpEntry(
        "Sprite suivant", "Passe au groupe de tuiles suivant dans l'ordre de stockage "
        "et vide le canevas.", "", "atelier"),
    "asm.clear": HelpEntry(
        "Vider", "Retire toutes les tuiles du canevas sans valider.", "", "atelier"),
    "asm.fill_storage": HelpEntry(
        "Ordre de stockage", "Remplit la grille dans l'ordre des indices de la banque, "
        "pour partir d'une base à corriger.", "", "atelier"),
    "asm.fill_reverse": HelpEntry(
        "Inversé", "Remplit la grille dans l'ordre inverse du stockage.", "", "atelier"),
    "asm.group_nav": HelpEntry(
        "Navigation par groupe", "Passe au groupe de tuiles précédent ou suivant "
        "(flèches). Le compteur indique le groupe courant sur le total.", "", "atelier"),

    # -- dialogue d'assemblage automatique ----------------------------------
    "auto.method": HelpEntry(
        "Méthode", "M1 hypothèses d'ordre, M2 glouton + 2-opt, M3 faisceau, M4 recuit "
        "simulé, M5 exhaustif (≤ 10 tuiles), M6 chemin optimal (1 × N), ou tout "
        "essayer.", "", "auto"),
    "auto.weights": HelpEntry(
        "Poids des indices", "Ajuste l'influence de chaque indice de coût. Le poids de "
        "la silhouette est le plus déterminant.", "", "cout"),
    "auto.run": HelpEntry(
        "Lancer", "Relance le calcul avec les paramètres courants.", "", "auto"),
    "auto.results": HelpEntry(
        "Résultats", "Classés du coût le plus bas au plus haut. Double-clic pour "
        "charger un assemblage dans le canevas.", "", "auto"),

    # -- écran Atlas --------------------------------------------------------
    "atlas.mode": HelpEntry(
        "Mode de disposition", "Automatique : grille équilibrée quand tous les sprites "
        "ont la même taille. Étagères : rangement ligne par ligne pour des tailles "
        "variables.", "", "atlas"),
    "atlas.gap": HelpEntry(
        "Espacement", "Pixels laissés entre deux sprites dans l'atlas.", "", "atlas"),
    "atlas.margin": HelpEntry(
        "Marge", "Pixels laissés autour de la planche, utile pour éviter le sanglage "
        "des filtres à l'affichage.", "", "atlas"),
    "atlas.export_png": HelpEntry(
        "Exporter l'atlas", "Écrit la planche PNG finale avec tous les sprites "
        "validés.", "", "atlas"),
    "atlas.export_json": HelpEntry(
        "Exporter les positions", "Écrit un JSON avec le rectangle de chaque sprite "
        "dans l'atlas.", "", "atlas"),
    "atlas.export_sheet": HelpEntry(
        "Exporter la planche", "Écrit la planche source telle quelle (tuiles non "
        "assemblées).", "", "atlas"),

    # -- écran Analyse ------------------------------------------------------
    "an.hypotheses": HelpEntry(
        "Hypothèses d'ordre", "Classe un catalogue de permutations plausibles "
        "(identité, serpentin, blocs, entrelacement, affine mod N, bits…) par coût "
        "des raccords.", "", "hypotheses"),
    "an.apply_hyp": HelpEntry(
        "Appliquer au canevas", "Charge l'hypothèse sélectionnée dans l'atelier pour "
        "la retoucher ou la valider.", "", "hypotheses"),
    "an.infer": HelpEntry(
        "Inférer la règle", "Cherche, à partir des sprites validés, la fonction qui "
        "relie l'indice de stockage des tuiles à leur case dans la grille.", "",
        "regle"),
    "an.recipe": HelpEntry(
        "Créer la recette", "Transforme le modèle retenu en recette réapplicable aux "
        "groupes suivants.", "", "regle"),
    "an.apply_next": HelpEntry(
        "Appliquer au groupe suivant", "Place les tuiles du groupe courant selon la "
        "recette choisie.", "", "regle"),
    "an.apply_all": HelpEntry(
        "Appliquer à toute la banque", "Génère et valide tous les sprites de la "
        "banque avec la recette choisie.", "", "regle"),
    "an.log": HelpEntry(
        "Journal des mouvements", "Historique horodaté de tous les placements, "
        "déplacements et validations.", "", "journal"),
    "an.export_csv": HelpEntry(
        "CSV des placements", "Une ligne par tuile placée : sprite, indice de "
        "stockage, coordonnées de grille, case.", "", "exports"),
    "an.export_json": HelpEntry(
        "JSON des placements", "Mêmes données que le CSV avec les métadonnées du "
        "projet.", "", "exports"),
    "an.export_perm": HelpEntry(
        "Permutations", "Un fichier texte lisible : pour chaque sprite, la suite des "
        "cases dans l'ordre des indices de stockage.", "", "exports"),

    # -- dialogues ----------------------------------------------------------
    "raw.path": HelpEntry(
        "Fichier", "Chemin de la banque binaire ou de la ROM à décoder.", "",
        "formats"),
    "raw.format": HelpEntry(
        "Préréglage", "Format de tuile d'une machine connue. « Personnalisé » expose "
        "tous les paramètres à la main.", "", "formats"),
    "raw.offset": HelpEntry(
        "Offset", "Position de la banque dans le fichier, en hexadécimal.", "",
        "formats"),
    "raw.count": HelpEntry(
        "Nombre de tuiles", "Nombre de tuiles à décoder à partir de l'offset.", "",
        "formats"),
    "raw.tile": HelpEntry(
        "Taille de tuile", "Largeur et hauteur d'une tuile en pixels.", "", "formats"),
    "raw.bpp": HelpEntry(
        "Bits par pixel", "Profondeur : 1 bit = 2 couleurs, 4 bits = 16 couleurs, "
        "8 bits = 256.", "", "formats"),
    "raw.layout": HelpEntry(
        "Disposition", "Organisation des plans en mémoire : par ligne, séquentielle, "
        "quartets, chunky ou entrelacement CPC.", "", "formats"),
    "raw.bytes": HelpEntry(
        "Octets par tuile", "Taille d'une tuile dans le fichier. « auto » la déduit de "
        "la taille et de la profondeur.", "", "formats"),
    "raw.per_row": HelpEntry(
        "Tuiles par ligne", "Disposition de l'aperçu et de la planche générée.", "",
        "formats"),
    "raw.palette": HelpEntry(
        "Palette", "Palette utilisée pour convertir les indices en couleurs.", "",
        "palette"),
    "raw.scan": HelpEntry(
        "Analyser le fichier", "Cherche les tailles de tuile qui divisent exactement "
        "la taille du fichier et propose les meilleurs candidats.", "", "formats"),
    "sheet.profiles": HelpEntry(
        "Profils de jeu", "Rejoue les réglages d'un jeu déjà identifié (offset, "
        "format, compression, palette) et retrouve ses tuiles en un clic.", "",
        "profils"),
    "raw.compression": HelpEntry(
        "Compression", "Format de compression des graphismes dans la ROM : "
        "Kosinski, Nemesis, Saxman et Enigma pour la Mega Drive, LC_LZ2 pour la "
        "Super Nintendo, PackBits et deux variantes de RLE pour le reste. "
        "« Aucune » pour des données brutes.", "", "compression"),
    "raw.detect": HelpEntry(
        "Chercher des graphismes", "Balaye tout le fichier, données brutes et "
        "blocs compressés, note chaque zone et affiche les résultats avec un "
        "aperçu. La recherche tourne en arrière-plan et s'interrompt d'un clic. "
        "Choisissez ensuite le bloc à charger.", "", "compression"),
    "tools.cartography": HelpEntry(
        "Cartographier une ROM", "Reconnaît la plateforme à partir de l'en-tête "
        "(signature NES, « SEGA » sur Mega Drive, somme de contrôle SNES…), découpe "
        "la ROM en zones classées par entropie — vide, données structurées, code "
        "probable, compressé — et repère les suites de pointeurs croissants qui "
        "trahissent une table de données.", "", "compression"),
    "tools.emulator": HelpEntry(
        "Mémoire d'émulateur", "Exécute la ROM dans un cœur libretro, avance de "
        "quelques centaines de trames, puis lit la RAM système et la VRAM. Les "
        "graphismes y sont déjà décompressés par le jeu : c'est la voie de "
        "secours quand le compresseur de la ROM est inconnu. Choisissez un cœur "
        "(.so), la ROM, le nombre de trames et, si besoin, un script d'entrée "
        "comme « start@120-140 » pour atteindre le jeu.", "", "emulation"),
    "raw.identify": HelpEntry(
        "Identifier le format", "Compare le bloc affiché à chaque format connu "
        "et propose celui qui l'explique le mieux. Chaque format est jugé par "
        "rapport à ce qu'il donnerait sur du bruit : un format à 1 bit "
        "« explique » n'importe quoi et ne doit pas gagner. La profondeur et la "
        "disposition sont fiables ; la taille de tuile reste à vérifier.", "",
        "compression"),
    "raw.rom_palette": HelpEntry(
        "Palette depuis la ROM", "Lit la palette du jeu directement dans le "
        "fichier : BGR555 sur SNES, 0BGR sur Mega Drive, 0RGB sur Atari ST. "
        "Indispensable pour retrouver les vraies couleurs.", "", "palette"),
    "raw.save_profile": HelpEntry(
        "Enregistrer le profil", "Mémorise l'offset, le format, la compression et "
        "la palette courants dans un fichier JSON réutilisable.", "", "profils"),
    "raw.preview": HelpEntry(
        "Aperçu", "Rendu des premières tuiles avec les paramètres courants : on voit "
        "tout de suite si le format est le bon.", "", "formats"),
    "sys.filter": HelpEntry(
        "Filtrer", "Filtre la liste par nom de machine, famille, année ou résolution.",
        "", "machines"),
    "sys.only_compat": HelpEntry(
        "Machines proches", "N'affiche que les machines dont la résolution est proche "
        "de celle détectée.", "", "machines"),
    "pal.swatch": HelpEntry(
        "Pastille de couleur", "Cliquez pour modifier la couleur de cet index.", "",
        "palette"),
    "pal.transparent": HelpEntry(
        "Couleur transparente", "Index considéré comme transparent à l'affichage.", "",
        "palette"),
}

#: Libellés de boutons → clé d'aide (liaison automatique).
TEXT_TO_KEY: dict[str, str] = {
    "Nouveau projet": "app.new",
    "Ouvrir un projet": "app.open",
    "Importer une ROM ou une archive…": "app.import_rom",
    "Ouvrir une ROM / archive…": "app.import_rom",
    "Enregistrer": "app.save",
    "Enregistrer sous…": "app.save_as",
    "Annuler": "app.undo",
    "Refaire": "app.redo",
    "Résolutions des machines": "app.machines",
    "Plein écran": "app.fullscreen",
    "Aide interactive": "app.help_mode",
    "Aide et tutoriel": "app.help",
    "Mises à jour": "app.updates",
    "Image PNG…": "sheet.open_png",
    "Banque brute…": "sheet.open_raw",
    "Barbarian ST (disquette .stx)": "sheet.open_barbarian",
    "Palette…": "sheet.palette",
    "Profil de jeu…": "sheet.profiles",
    "Enregistrer le profil…": "raw.save_profile",
    "Fond transparent": "sheet.transparent",
    "Analyser": "sheet.analyse",
    "Machines…": "sheet.systems",
    "Appliquer la machine (tuile + palette)": "sheet.apply_system",
    "Détecter": "sheet.detect",
    "Comparer les méthodes": "sheet.compare",
    "Vérifier": "sheet.quality",
    "Sélection": "sheet.tool_select",
    "Nouvelle tuile": "sheet.tool_create",
    "Aimant": "sheet.snap",
    "Grille": "sheet.grid",
    "Ajuster": "sheet.fit",
    "Assemblage automatique…": "asm.auto",
    "Tester les grilles…": "asm.grids",
    "Appliquer la recette": "asm.recipe",
    "Valider le sprite  (Entrée)": "asm.validate",
    "Sprite suivant": "asm.next",
    "Vider": "asm.clear",
    "Ordre de stockage": "asm.fill_storage",
    "Inversé": "asm.fill_reverse",
    "Lancer": "auto.run",
    "Exporter l'atlas (PNG)…": "atlas.export_png",
    "Exporter les positions (JSON)…": "atlas.export_json",
    "Exporter en planche de tuiles (PNG)…": "atlas.export_sheet",
    "Analyser le groupe": "an.hypotheses",
    "Appliquer au canevas": "an.apply_hyp",
    "Inférer": "an.infer",
    "Créer la recette": "an.recipe",
    "Appliquer au groupe suivant": "an.apply_next",
    "Appliquer à toute la banque": "an.apply_all",
    "CSV des placements…": "an.export_csv",
    "JSON des placements…": "an.export_json",
    "Permutations (.txt)…": "an.export_perm",
    "Parcourir…": "raw.path",
    "Analyser le fichier (tailles probables)": "raw.scan",
    "Chercher un bloc…": "raw.detect",
    "Chercher des graphismes…": "raw.detect",
    "Identifier le format…": "raw.identify",
    "Cartographier une ROM…": "tools.cartography",
    "Mémoire d'émulateur…": "tools.emulator",
    "Lire la palette dans la ROM": "raw.rom_palette",
}

#: Titres de groupes → clé d'aide.
GROUP_TO_KEY: dict[str, str] = {
    "Paramètres": "sheet.detector",
    "Disposition": "atlas.mode",
    "Grille": "asm.grid",
    "Méthode": "auto.method",
    "Poids des indices": "auto.weights",
    "Palette": "raw.palette",
    "Format": "raw.format",
    "Découpage": "raw.tile",
}


# ---------------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------------

DOC_SECTIONS: list[tuple[str, str, str]] = [
    ("demarrage", "Démarrage rapide", """
<p>TileForge sert à retrouver l'assemblage d'origine des tuiles de sprites d'un
jeu 8 ou 16 bits, puis à en déduire la logique d'ordonnancement des développeurs.</p>
<h3>Trois minutes pour voir un résultat</h3>
<ol>
<li>Onglet <b>Planche</b> → bouton <b>Barbarian ST (disquette .stx)</b>.</li>
<li>Choisissez la disquette, puis <b>Banque 1</b>. 252 tuiles de 24 × 21 apparaissent.</li>
<li>Onglet <b>Atelier</b> : réglez la grille sur <b>2 × 4</b> (ou 3 × 4).</li>
<li>Bouton <b>Assemblage automatique…</b>, méthode <b>Tout essayer</b>, puis
double-cliquez sur un aperçu : il se charge dans le canevas.</li>
<li>Corrigez si besoin, puis <b>Valider le sprite</b> (Entrée).</li>
<li>Onglet <b>Analyse</b> : après quelques sprites, <b>Inférer</b> révèle la règle,
et <b>Appliquer à toute la banque</b> la rejoue partout.</li>
</ol>
<h3>Avec un autre jeu</h3>
<p>Pour une planche déjà rendue : <b>Image PNG…</b>. Pour une banque de ROM :
<b>Banque brute…</b> avec l'offset et le format. En cas de doute sur le format,
le bouton <b>Analyser le fichier</b> propose les tailles de tuile plausibles.</p>
"""),

    ("concepts", "Concepts", """
<h3>Planche, tuile, sprite</h3>
<ul>
<li><b>Planche</b> : l'image source, qu'elle vienne d'un PNG ou d'une banque
binaire décodée.</li>
<li><b>Tuile</b> : un rectangle de la planche. Dans une banque de ROM, chaque
tuile a un <b>indice de stockage</b> : sa position d'origine dans le fichier.
C'est cette information qui permet de retrouver la logique du jeu.</li>
<li><b>Sprite</b> : un assemblage de tuiles sur une grille (par exemple 2 × 4),
validé par vous et ajouté à l'atlas.</li>
<li><b>Atlas</b> : la planche finale qui accumule les sprites validés.</li>
<li><b>Recette</b> : la correspondance apprise entre l'indice de stockage et la
case de la grille, réapplicable aux groupes suivants.</li>
</ul>
<h3>Pourquoi le coût ?</h3>
<p>Deux tuiles qui se touchent dans le jeu ont des bords qui se prolongent :
la silhouette se poursuit, les couleurs se ressemblent, le contour s'aligne.
Le <b>coût</b> mesure à quel point ces raccords sont cohérents. Plus il est bas,
plus l'assemblage est vraisemblable.</p>
<h3>Pourquoi plusieurs méthodes ?</h3>
<p>Aucune métrique n'est parfaite : deux poses successives se ressemblent
beaucoup, une tuile symétrique peut aller des deux côtés, et un décalage
cyclique d'une ligne ne change presque aucun raccord. L'outil propose donc
toujours <b>plusieurs candidats</b> et vous laisse trancher.</p>
"""),

    ("planche", "Écran Planche", """
<p>Il sert à charger une source et à découper les tuiles.</p>
<h3>Source</h3>
<ul>
<li><b>Image PNG…</b> : planche déjà rendue. La couleur de fond du bord devient
transparente ; le bouton <b>Fond transparent</b> permet de recommencer.</li>
<li><b>Banque brute…</b> : fichier binaire, offset, format, palette, aperçu
immédiat.</li>
<li><b>Barbarian ST</b> : lit la disquette Pasti, en extrait BARB.DAT et décode
les deux banques de 252 tuiles.</li>
</ul>
<h3>Édition</h3>
<ul>
<li><b>V</b> sélection, <b>R</b> nouvelle tuile, <b>G</b> aimant, <b>0</b> ajuster,
<b>1</b> taille réelle.</li>
<li>Molette : zoom. Clic du milieu ou Espace + glisser : déplacer.</li>
<li>Poignées du rectangle sélectionné : redimensionner.</li>
<li>Clic droit : fusionner, scinder, dupliquer, supprimer.</li>
<li>Flèches : décaler d'un pixel (Maj : d'un pas de grille).</li>
</ul>
<h3>Contrôle qualité</h3>
<p>La liste signale chevauchements, tuiles vides, tailles incohérentes et
débordements ; un clic sélectionne la tuile fautive.</p>
"""),

    ("detection", "Détecteurs de tuiles", """
<table border="1" cellspacing="0" cellpadding="4">
<tr><th>Détecteur</th><th>Principe</th><th>Quand l'utiliser</th></tr>
<tr><td>Grille fixe</td><td>taille et espacement constants</td>
<td>banque de ROM : c'est le cas exact</td></tr>
<tr><td>Période</td><td>autocorrélation des profils de projection</td>
<td>taille de tuile inconnue</td></tr>
<tr><td>Profils de projection</td><td>colonnes et lignes vides</td>
<td>planche avec gouttières</td></tr>
<tr><td>XY-cut</td><td>coupe récursive au plus grand vide</td>
<td>sprites collés, tailles variées</td></tr>
<tr><td>Composantes connexes</td><td>étiquetage puis fusion des boîtes</td>
<td>objets isolés de tailles variables</td></tr>
<tr><td>Manuel</td><td>rien</td><td>tout à la main</td></tr>
</table>
<p>Le bouton <b>Comparer les méthodes</b> lance tous les détecteurs et garde
celui qui produit le plus de tuiles. <b>Remplacer les tuiles</b> décide si le
résultat remplace ou complète le découpage existant.</p>
"""),

    ("resolution", "Résolution et machines", """
<p>Sur une <b>image d'écran</b>, l'analyse :</p>
<ol>
<li>détecte un agrandissement ×2, ×3, ×4 (capture d'émulateur) ;</li>
<li>en déduit la résolution native ;</li>
<li>compte les couleurs et estime la profondeur ;</li>
<li>cherche le pas de grille par autocorrélation ;</li>
<li>identifie les machines compatibles.</li>
</ol>
<p>Sur une <b>banque brute</b>, la taille de l'image n'a pas de sens : l'analyse
porte sur le profil des tuiles (profondeur, taille, plans) et met en avant la
machine du format choisi.</p>
<h3>Le catalogue</h3>
<p>76 machines : 22 consoles, 29 ordinateurs, 25 bornes d'arcade, avec leurs
résolutions natives, le nombre de couleurs simultanées, la profondeur des
tuiles, les tailles de tuile usuelles et une note technique.</p>
<p><b>Appliquer la machine</b> reprend sa taille de tuile et sa palette pour la
suite du travail.</p>
"""),

    ("machines", "Catalogue des machines", """
<p>Le dialogue <b>Résolutions des machines</b> liste toutes les machines par
famille, avec un filtre (nom, famille, résolution) et une option « seulement les
machines proches de la résolution détectée ». Les machines compatibles avec
l'analyse en cours apparaissent en vert.</p>
<h3>Familles</h3>
<ul>
<li><b>Consoles</b> : Atari 2600, Intellivision, ColecoVision, NES, Master
System, PC Engine, Mega Drive, Game Boy, SNES, Neo Geo, Game Gear, Saturn,
PlayStation, Game Boy Advance…</li>
<li><b>Ordinateurs</b> : Atari 8-bit et ST, Amiga, Amstrad CPC, ZX Spectrum,
C64, MSX, Apple II, CGA/EGA/VGA, BBC Micro, Thomson, X68000, PC-88/98…</li>
<li><b>Bornes</b> : Pac-Man, Galaga, System 16, CPS-1/2/3, Neo Geo MVS, Namco
System 1/2, Irem M72/M92, Taito F2, Toaplan, Psikyo, CV-1000, Naomi…</li>
</ul>
<p>Les valeurs sont des références documentaires : beaucoup de machines
partagent la même résolution, l'identification reste donc indicative.</p>
"""),

    ("formats", "Formats de banque brute", """
<p>Une banque brute est une suite d'octets : <i>N</i> tuiles de <i>T</i> octets.
Le décodage dépend de la machine.</p>
<table border="1" cellspacing="0" cellpadding="4">
<tr><th>Préréglage</th><th>Tuile</th><th>Plans</th><th>Disposition</th></tr>
<tr><td>barbarian_st</td><td>24×21</td><td>2</td><td>plans entrelacés par ligne</td></tr>
<tr><td>nes / gameboy</td><td>8×8</td><td>2</td><td>plans séquentiels</td></tr>
<tr><td>snes_2bpp / 4bpp / 8bpp</td><td>8×8</td><td>2/4/8</td><td>plans par ligne</td></tr>
<tr><td>master_system</td><td>8×8</td><td>4</td><td>plans par ligne</td></tr>
<tr><td>megadrive</td><td>8×8</td><td>4</td><td>plans par ligne</td></tr>
<tr><td>pc_engine</td><td>8×8</td><td>4</td><td>paires de plans</td></tr>
<tr><td>neo_geo / cps1</td><td>16×16</td><td>4</td><td>plans par ligne</td></tr>
<tr><td>zx_spectrum / c64</td><td>8×8</td><td>1</td><td>plans séquentiels</td></tr>
<tr><td>cpc_mode0/1/2</td><td>8×8</td><td>4/2/1</td><td>entrelacement CPC</td></tr>
<tr><td>chunky4 / chunky8</td><td>8×8</td><td>4/8</td><td>pixels indexés</td></tr>
</table>
<p>Le mode <b>Personnalisé</b> expose largeur, hauteur, profondeur,
disposition, ordre des bits, octets par tuile et remplissage de ligne : presque
toute banque régulière peut être décodée sans écrire de code.</p>
"""),

    ("profils", "Profils de jeu — rendre le travail reproductible", """
<p>Quand vous avez trouvé comment lire les graphismes d'un jeu (offset, format,
compression, palette), enregistrez-le en <b>profil</b> : c'est un fichier JSON
qui rejoue tout en un clic.</p>

<h3>Enregistrer</h3>
<ol>
<li><b>Banque brute…</b> → réglez tout jusqu'à ce que l'aperçu montre du
graphisme.</li>
<li><b>Enregistrer le profil…</b> → choisissez un nom.</li>
</ol>

<h3>Rejouer</h3>
<p><b>Fichier ▸ Profils de jeu…</b> (ou le bouton <b>Profil de jeu…</b> de
l'écran Planche) : la liste montre les profils fournis et les vôtres. Un clic
charge la banque ; la ROM est cherchée automatiquement dans le dossier du projet
et ses sous-dossiers.</p>

<h3>Partager</h3>
<p>Les profils personnels sont dans <code>~/.config/tileforge/profiles/</code>.
Copier un fichier suffit à le transmettre : votre correspondant ouvre le même
jeu avec les mêmes réglages, sans rien connaître de la ROM.</p>

<pre>{
  "format": "tileforge/profile/1",
  "key": "mon_jeu",
  "name": "Mon jeu (1993)",
  "rom_name": "Mon Jeu.md",
  "offset": 123456,
  "tile_format": "megadrive",
  "compression": "nemesis",
  "palette": {"kind": "megadrive", "offset": 512, "count": 16},
  "grid": [2, 4]
}</pre>

<p>C'est le chaînon qui rend le processus reproductible : la recherche se fait
une fois, le résultat se rejoue indéfiniment.</p>
"""),

    ("compression", "Planches compressées (SNES, Mega Drive)", """
<p>La plupart des jeux SNES et Mega Drive ne stockent pas leurs tuiles en clair :
elles sont compressées dans la ROM. TileForge sait décompresser les formats les
plus courants, et en ajouter d'autres en quelques lignes.</p>

<h3>Formats fournis</h3>
<table border="1" cellspacing="0" cellpadding="4">
<tr><th>Format</th><th>Machine</th><th>Jeux typiques</th></tr>
<tr><td>Kosinski</td><td>Mega Drive</td><td>Sonic 2/3, QuackShot,
Phantasy Star IV</td></tr>
<tr><td>Nemesis</td><td>Mega Drive</td><td>Sonic, Golden Axe, Streets of Rage,
Castle of Illusion</td></tr>
<tr><td>LC_LZ2</td><td>Super Nintendo</td><td>Super Mario World, Yoshi's
Island, A Link to the Past</td></tr>
<tr><td>zlib / gzip</td><td>—</td><td>homebrews et romhacks</td></tr>
</table>

<h3>Marche à suivre</h3>
<ol>
<li><b>Banque brute…</b> → choisir la ROM.</li>
<li>Choisir le <b>format de tuile</b> de la machine (SNES 4bpp, Mega Drive,
etc.) : c'est ce qui décide de la façon de relire les octets.</li>
<li>Régler la <b>compression</b>. Si vous ne connaissez pas l'offset, cliquez sur
<b>Chercher des graphismes…</b> : l'outil balaye tout le fichier, essaie chaque
décompresseur, note les zones trouvées et les classe avec un aperçu.</li>
<li>Cocher <b>Lire la palette dans la ROM</b> et indiquer l'offset de la palette
(BGR555 sur SNES, 0BGR sur Mega Drive). Sans elle, les couleurs sont fausses.</li>
<li>L'aperçu montre immédiatement si le résultat est du graphisme. Sinon, changez
d'offset ou de format : un mauvais décodage donne du bruit.</li>
</ol>

<h3>Pourquoi ça ne tombe pas toujours juste</h3>
<p>Beaucoup de jeux utilisent un compresseur <b>maison</b>. Les formats fournis
couvrent les plus répandus, pas tous. Dans ce cas, deux solutions :</p>
<ul>
<li>extraire les graphismes avec un outil dédié (Tile Molester, YY-CHR,
SonED2, Lunar Magic) puis ouvrir le fichier obtenu en données brutes ;</li>
<li>ajouter le décompresseur du jeu : une fonction de quelques dizaines de
lignes, enregistrée par <code>compression.register()</code>, apparaît
automatiquement dans le dialogue.</li>
</ul>

<h3>Ajouter un décompresseur</h3>
<pre>from tileforge.core.compression import register

def mon_jeu(data, offset=0):
    ...          # renvoie les octets décompressés
    return bytes(sortie)

register("mon_jeu", mon_jeu, "Mon jeu (1993)", "Mega Drive")</pre>
<p>Le format apparaît alors dans la liste « Compression » et dans le balayage.</p>

<h3>Vérification</h3>
<p>Le décodage Kosinski est validé par les trois exemples officiels de Sega
Retro ; les dispositions de tuiles SNES (2, 3, 4 et 8 bits par pixel) et Mega
Drive sont validées par encodage/décodage aller-retour
(<code>python tests/run_all.py</code>).</p>
"""),

    ("palette", "Palettes", """
<p>Une banque brute ne contient que des indices : c'est la palette qui donne
l'image. L'éditeur permet de corriger les couleurs, de charger une palette
JASC (<code>.pal</code>) ou GIMP (<code>.gpl</code>) et de choisir l'index
transparent.</p>
<p>Des palettes sont fournies pour Atari ST (dont celle de Barbarian), Amiga,
NES, Game Boy, Master System, Mega Drive, CPC, C64, ZX Spectrum et EGA/CGA.</p>
"""),

    ("atelier", "Écran Atelier", """
<p>La palette des tuiles libres est à gauche, le canevas au centre, l'inspecteur
à droite.</p>
<h3>Placer une tuile</h3>
<ul>
<li><b>Glisser-déposer</b> depuis la palette vers une case.</li>
<li><b>Mode tactile</b> : touchez une tuile dans la palette, puis une case.</li>
<li>Glissez une tuile déjà placée pour la déplacer ; elle échange sa place si
la case est occupée.</li>
<li>Double-clic ou Suppr pour retirer une tuile.</li>
</ul>
<h3>Valider</h3>
<p><b>Valider le sprite</b> (Entrée) enregistre l'assemblage, l'ajoute à l'atlas
et journalise l'événement. <b>Sprite suivant</b> passe au groupe suivant.</p>
"""),

    ("grilles", "Choisir la grille", """
<p>La grille (colonnes × lignes) définit le nombre de tuiles par sprite. C'est
une hypothèse de travail : l'outil aide à la trancher.</p>
<ul>
<li>Si le nombre de tuiles de la banque est divisible par la taille de la
grille, c'est un indice fort (21 sprites de 12 tuiles, 42 de 6…).</li>
<li>Le bouton <b>Tester les grilles</b> essaie toutes les grilles plausibles sur
le même paquet de tuiles et les classe : les grilles dont le compte tombe juste
passent devant, puis le coût des raccords tranche.</li>
</ul>
<p>Attention : une grille plus petite a mécaniquement moins de raccords à
rater, elle paraît donc souvent meilleure.</p>
"""),

    ("cout", "Le coût d'assemblage", """
<p>Six indices, pondérés :</p>
<ul>
<li><b>C1 Silhouette</b> — le masque opaque se poursuit-il de part et d'autre
du raccord ? C'est le signal le plus discriminant.</li>
<li><b>C2 Couleur</b> — les pixels opaques voisins se ressemblent-ils ?</li>
<li><b>C3 Contour</b> — la dérivée au bord se poursuit-elle ?</li>
<li><b>C4 Trous</b> — le sprite assemblé a-t-il des trous intérieurs ?</li>
<li><b>C5 Palette</b> — deux tuiles voisines partagent-elles la même
dominante de couleurs ?</li>
<li><b>C6 Doublons</b> — deux tuiles quasi identiques sont-elles collées ?</li>
</ul>
<p>Une jointure dont les deux bords sont vides n'apporte aucune information :
elle reçoit un coût neutre, sans quoi les solveurs adorent les assemblages
fragmentés.</p>
"""),

    ("auto", "Assemblage automatique", """
<table border="1" cellspacing="0" cellpadding="4">
<tr><th>Méthode</th><th>Principe</th></tr>
<tr><td>M1</td><td>catalogue de permutations plausibles (identité, serpentin,
blocs, entrelacement, affine mod N, bits, plans…)</td></tr>
<tr><td>M2</td><td>glouton case par case puis amélioration 2-opt</td></tr>
<tr><td>M3</td><td>faisceau : garde les K meilleurs assemblages partiels</td></tr>
<tr><td>M4</td><td>recuit simulé sur les échanges de deux tuiles</td></tr>
<tr><td>M5</td><td>exhaustif avec élagage (≤ 10 tuiles)</td></tr>
<tr><td>M6</td><td>chemin optimal par programmation dynamique (grille 1 × N)</td></tr>
</table>
<p>« Tout essayer » enchaîne les méthodes et fusionne les classements. Les
aperçus sont triés par coût ; double-cliquez pour en charger un.</p>
"""),

    ("regle", "Retrouver la logique d'ordre", """
<p>Une fois quelques sprites validés, l'onglet <b>Analyse</b> compare les
modèles : identité, transposition, serpentin, affine mod N, pas multiplicatif,
permutation de bits, blocs, par plans, ou simple correspondance majoritaire
case par case.</p>
<p>Chaque modèle est noté par le nombre de sprites expliqués exactement et la
part de tuiles correctement placées. Le meilleur modèle devient une
<b>recette</b>, applicable au groupe suivant ou à toute la banque.</p>
<p>Le fichier <b>Permutations</b> exporté permet de repérer un motif à l'œil :
chaque sprite y apparaît comme une suite de cases dans l'ordre des indices de
stockage.</p>
"""),

    ("hypotheses", "Hypothèses d'ordre", """
<p>Sur le groupe courant, l'outil classe un catalogue de permutations : lecture
ligne par ligne, colonne par colonne, inversions, serpentin, blocs échangés,
entrelacement modulo k, pas multiplicatif, fonction affine mod N, inversion de
bits, décalage circulaire, rangement par plans.</p>
<p>Chaque hypothèse affiche son coût. Un clic sur <b>Appliquer au canevas</b>
charge la permutation dans l'atelier, où vous pouvez la retoucher.</p>
"""),

    ("journal", "Journal des mouvements", """
<p>Chaque placement, déplacement, échange, suppression, rotation et validation
produit un événement horodaté. Ce journal documente <i>comment</i> vous êtes
arrivé à un assemblage : quelles tuiles ont bougé, dans quel ordre, quelles
tentatives ont été abandonnées. C'est une matière première pour l'inférence de
règle.</p>
"""),

    ("atlas", "Écran Atlas", """
<p>L'atlas accumule les sprites validés.</p>
<ul>
<li><b>Automatique</b> : grille équilibrée quand tous les sprites ont la même
taille.</li>
<li><b>Étagères</b> : rangement ligne par ligne pour des tailles variables.</li>
<li><b>Espacement</b> et <b>marge</b> réglables (utiles pour éviter le sanglage
des filtres à l'affichage).</li>
</ul>
<p>Export PNG de l'atlas et JSON des positions de chaque sprite.</p>
"""),

    ("exports", "Exports pour analyse", """
<ul>
<li><code>analyse_placements.csv</code> : sprite, indice de stockage, gx, gy,
case, colonnes, lignes.</li>
<li><code>analyse_placements.json</code> : mêmes données plus les métadonnées du
projet.</li>
<li><code>analyse_permutations.txt</code> : pour chaque sprite, la suite des
cases dans l'ordre des indices de stockage — la forme la plus lisible pour
repérer un motif.</li>
</ul>
<p>Ces fichiers sont faits pour être analysés ailleurs (tableur, script) afin de
retrouver la formule exacte du jeu.</p>
"""),

    ("raccourcis", "Raccourcis clavier", """
<table border="1" cellspacing="0" cellpadding="4">
<tr><th>Touche</th><th>Action</th></tr>
<tr><td>Ctrl+O / Ctrl+S</td><td>ouvrir / enregistrer</td></tr>
<tr><td>Ctrl+Z / Ctrl+Y</td><td>annuler / refaire</td></tr>
<tr><td>Ctrl+1..4</td><td>onglets Planche, Atelier, Atlas, Analyse</td></tr>
<tr><td>V / R</td><td>sélection / nouvelle tuile</td></tr>
<tr><td>G</td><td>aimant</td></tr>
<tr><td>0 / 1</td><td>ajuster / taille réelle</td></tr>
<tr><td>Molette</td><td>zoom</td></tr>
<tr><td>Espace + glisser</td><td>déplacer la vue</td></tr>
<tr><td>Suppr</td><td>supprimer la tuile</td></tr>
<tr><td>Entrée</td><td>valider le sprite</td></tr>
<tr><td>F1</td><td>aide interactive (survol 2 s)</td></tr>
<tr><td>Ctrl+F1</td><td>page d'aide et tutoriel</td></tr>
<tr><td>F11</td><td>plein écran</td></tr>
</table>
"""),

    ("aide", "L'aide dans TileForge", """
<h3>Aide interactive</h3>
<p>Activez le bouton <b>Aide interactive</b> (F1) dans la barre d'outils :
survolez ensuite n'importe quel bouton <b>deux secondes sans cliquer</b> et une
fiche apparaît, avec le raccourci s'il y en a un. Le cadre du contrôle est
surligné.</p>
<p>Un clic, un déplacement de souris ou Échap referme la fiche. Le mode reste
actif jusqu'à ce que vous le désactiviez, et votre choix est mémorisé.</p>
<h3>Page d'aide</h3>
<p><b>Aide et tutoriel</b> (Ctrl+F1) ouvre cette
documentation : démarrage, concepts, tutoriel, référence des écrans, formats,
raccourcis et dépannage.</p>
"""),

    ("mises_a_jour", "Mises à jour", """
<p>TileForge peut se mettre à jour tout seul à partir d'un manifeste JSON
publié sur un serveur web ou un dossier partagé.</p>
<ul>
<li><b>Vérifier maintenant</b> compare la version installée à celle du
manifeste.</li>
<li>Les <b>notes de version</b> s'affichent avant toute installation.</li>
<li>Le paquet est téléchargé, son empreinte <b>SHA-256</b> vérifiée, puis il
remplace les fichiers de l'application. Une sauvegarde de la version précédente
est conservée : <b>Revenir à la version précédente</b> restaure l'état d'avant.</li>
<li>La vérification au démarrage peut être désactivée dans le dialogue.</li>
</ul>
<p>Pour publier une version : <code>python tools/make_update.py</code> construit
l'archive et le manifeste à partir du dossier courant.</p>
"""),

    ("mcp", "Connecter le MCP", """
<p>TileForge embarque un serveur <b>MCP</b> (Model Context Protocol) : un
assistant peut piloter l'outil avec les mêmes fonctions que l'interface —
inspecter une ROM, chercher des graphismes, identifier un format, assembler un
sprite, exporter un atlas.</p>

<h3>Ce que fait le serveur</h3>
<p>Il parle JSON-RPC 2.0 sur l'entrée et la sortie standard. Il ne dépend ni de
Qt ni de l'interface : il peut tourner sans écran, sur un serveur ou dans un
conteneur. Chaque outil renvoie du JSON <b>et le chemin d'un aperçu PNG</b>, que
le modèle peut regarder avant de décider.</p>

<h3>Lancer le serveur à la main</h3>
<pre>python -m tileforge --mcp</pre>
<p>Le serveur attend alors des messages JSON-RPC sur l'entrée standard. C'est ce
que fait un client MCP à votre place : vous n'avez normalement rien à taper.</p>

<h3>Claude Desktop</h3>
<p>Éditez le fichier de configuration
(<code>claude_desktop_config.json</code>, dans le dossier de configuration de
Claude) et ajoutez :</p>
<pre>{
  "mcpServers": {
    "tileforge": {
      "command": "/chemin/vers/tileforge/.venv/bin/python",
      "args": ["-m", "tileforge", "--mcp"]
    }
  }
}</pre>
<p>Redémarrez Claude Desktop : l'icône d'outils doit proposer les vingt
outils <code>tileforge_*</code>. Le plus sûr est de générer la configuration
avec l'interpréteur du projet :</p>
<pre>python tools/mcp_config.py --check
python tools/mcp_config.py --write ~/.config/Claude/claude_desktop_config.json</pre>
<p>Le guide complet (Claude Code, Cursor, VS Code, Cline, Continue) est dans
<code>docs/mcp-clients.md</code>.</p>

<h3>Cursor et VS Code</h3>
<p>Dans <code>~/.cursor/mcp.json</code> (Cursor) ou le fichier
<code>mcp.json</code> du projet (VS Code avec l'extension MCP), la même
déclaration fonctionne :</p>
<pre>{
  "mcpServers": {
    "tileforge": {
      "command": "/chemin/vers/tileforge/.venv/bin/python",
      "args": ["-m", "tileforge", "--mcp"],
      "cwd": "/chemin/vers/tileforge"
    }
  }
}</pre>

<h3>Les outils exposés</h3>
<ul>
<li><code>tileforge_inspect_file</code> — en-tête, taille, format probable ;</li>
<li><code>tileforge_list_archive</code> — membres d'une archive zip/7z, puis
<code>archive_member</code> pour lire la ROM choisie ;</li>
<li><code>tileforge_scan_graphics</code> — cherche les graphismes (bruts et
compressés) et écrit un aperçu par candidat ;</li>
<li><code>tileforge_identify_format</code> — devine la profondeur et la
disposition d'une banque ;</li>
<li><code>tileforge_open_bank</code>, <code>tileforge_list_tiles</code>,
<code>tileforge_auto_assemble</code>, <code>tileforge_render_sprite</code>,
<code>tileforge_validate_sprite</code> — le parcours d'assemblage ;</li>
<li><code>tileforge_read_palette</code>, <code>tileforge_preview_tiles</code>,
<code>tileforge_list_systems</code>, <code>tileforge_list_tile_formats</code>,
<code>tileforge_cartography</code>, <code>tileforge_disassemble</code> ;</li>
<li><code>tileforge_list_emulator_cores</code>,
<code>tileforge_emulator_memory</code> — exécute une ROM dans un cœur libretro
et lit la mémoire décodée ;</li>
<li><code>tileforge_save_project</code>, <code>tileforge_export_atlas</code>.</li>
</ul>

<h3>En cas de problème</h3>
<ul>
<li><b>Rien ne démarre</b> : vérifiez que le chemin du Python pointe bien vers
l'environnement virtuel du projet, et que <code>python -m tileforge --mcp</code>
répond à la main.</li>
<li><b>Le client ne voit pas les outils</b> : le serveur écrit ses journaux sur
l'erreur standard ; un message au démarrage confirme le nombre d'outils
chargés.</li>
<li><b>Recherche interminable</b> : donnez un <code>budget</code> en secondes à
<code>tileforge_scan_graphics</code> ; le serveur s'arrête proprement et signale
la troncature.</li>
</ul>
<p>Le MCP est une commodité : tout est faisable dans l'interface, sans modèle.</p>
"""),

    ("cartographie", "Cartographier une ROM", """
<p><b>Outils ▸ Cartographier une ROM…</b> répond à trois questions avant
d'attaquer un jeu inconnu.</p>

<h3>Quelle machine ?</h3>
<p>L'en-tête d'une cartouche contient presque toujours une signature : la
chaîne <code>NES\x1A</code> au début d'un fichier iNES, <code>SEGA</code> à
l'offset 0x100 sur Mega Drive, le logo Nintendo sur Game Boy, ou la somme de
contrôle complémentaire de la Super Nintendo. La confiance affichée dit si la
signature est complète (95-99 %) ou seulement plausible.</p>

<h3>Où sont les zones homogènes ?</h3>
<p>L'entropie locale, calculée par fenêtres puis fusionnée, sépare le vide, les
données structurées, le code probable et les blocs compressés. Une bande
colorée montre la carte de la cartouche ; un clic sur la légende rappelle la
couleur de chaque nature de zone.</p>

<h3>Où sont les tables ?</h3>
<p>Une suite de pointeurs croissants vers la ROM trahit une table de données.
TileForge les détecte, les liste avec leur offset, leur nombre d'entrées et leur
ordre d'octets, et en déduit les <b>blocs de données</b> qu'elles délimitent :
chaque pointeur ouvre un bloc qui va jusqu'au suivant. C'est souvent là que se
trouvent les banques de tuiles.</p>

<h3>Et ensuite ?</h3>
<p>Le bouton <b>Chercher des graphismes…</b> accepte une option « zones de
données seulement » qui restreint le balayage aux plages structurées : sur une
ROM de 1 Mo, cela divise le terrain par huit et le bruit d'autant.</p>
"""),

    ("desassemblage", "Désassembler", """
<p><b>Outils ▸ Désassembler…</b> décode du code machine quand les formats
résistent. Cinq processeurs sont reconnus : <b>6502</b> (NES, Commodore 64,
Apple II, Atari 8 bits), <b>Z80</b> (ZX Spectrum, Amstrad CPC, MSX),
<b>SM83</b> (Game Boy), <b>68000</b> (Mega Drive, Amiga, Atari ST) et
<b>65816</b> (Super Nintendo).</p>

<h3>Deux modes</h3>
<ul>
<li><b>linéaire</b> : on décode à partir d'un offset de fichier, comme un
hexdump lisible ;</li>
<li><b>traçage</b> : on part d'une adresse processeur — le vecteur de reset
d'une ROM LoROM est à <code>0x8000</code>, celui d'une cartouche Mega Drive se
lit aux quatre premiers octets du fichier — et l'outil suit les sauts, les
branches et les sous-programmes avec une pile de retours.</li>
</ul>
<p>Le traçage ne décode que le code réellement atteignable : c'est ce qui
distingue le code des données. Les tables de sauts (<code>jmp (table,x)</code>)
sont explorées entrée par entrée, faute de connaître la valeur de l'index.</p>

<h3>À quoi ça sert</h3>
<p>À retrouver les adresses que le code charge : quand un jeu utilise un
compresseur maison, c'est le seul chemin qui reste vers ses graphismes. Sur
Aero Blasters, le traçage depuis le vecteur de reset fait apparaître le code
d'amorçage TMSS et son écriture de « SEGA » dans le registre vidéo.</p>

<h3>Limites</h3>
<p>Le traçage ne modélise pas la pile d'appels indirects : un retour de
sous-programme arrête la branche au lieu de revenir à l'appelant. La couverture
est donc partielle, et certaines instructions sortent en <code>.dc.w</code>
plutôt que d'être inventées.</p>
"""),

    ("emulation", "Mémoire d'émulateur", """
<p><b>Outils ▸ Mémoire d'émulateur…</b> répond à une impasse : un jeu qui
décompresse ses graphismes à l'exécution, ou qui les fabrique en mémoire, ne
laisse rien à lire dans la ROM. Plutôt que d'inverser son compresseur, on
laisse le jeu faire le travail.</p>

<h3>Comment ça marche</h3>
<p>TileForge charge un <b>cœur libretro</b> — le format de greffon utilisé par
RetroArch, mGBA, Snes9x, Genesis Plus GX, Hatari… —, exécute la ROM sans
fenêtre pendant le nombre de trames demandé, puis copie la <b>RAM système</b>,
la <b>VRAM</b> et la <b>SRAM</b>. Les données sont déjà dans le format natif de
la machine.</p>

<h3>Utilisation</h3>
<ul>
<li><b>Cœur</b> : choisissez un cœur détecté dans les dossiers habituels
(<code>~/.config/retroarch/cores</code>, <code>/usr/lib/libretro</code>), ou
pointez un fichier <code>.so</code>.</li>
<li><b>Trames</b> : 600 trames représentent environ dix secondes de jeu. Un
logo puis un écran-titre suffisent souvent ; augmentez pour atteindre un
niveau.</li>
<li><b>Script d'entrée</b> : <code>start@120-140</code> maintient Start de la
trame 120 à 140 ; <code>a@200</code> presse A à partir de la trame 200. Les
noms sont ceux de la manette libretro (<code>a</code>, <code>b</code>,
<code>start</code>, <code>up</code>…).</li>
<li><b>Balayer la mémoire</b> : cherche les tuiles dans les régions extraites,
avec le format choisi. La mémoire étant déjà décompressée, le balayage brut
suffit.</li>
</ul>

<h3>Fichiers produits</h3>
<p>Un dossier contient une région par fichier (<code>*.system_ram.bin</code>,
<code>*.video_ram.bin</code>, <code>*.save_ram.bin</code>), un fichier
concaténé, une capture PNG et un manifeste JSON avec les adresses de base
indicatives. Ouvrez un <code>.bin</code> comme <b>banque brute</b> dans
TileForge, ou utilisez <code>--scan</code> en ligne de commande.</p>

<h3>Sans cœur installé</h3>
<p>TileForge n'embarque aucun émulateur ni contenu de jeu. Le cœur et la ROM
restent à la charge de l'utilisateur. Si aucun cœur n'est trouvé, installez
RetroArch ou un paquet <code>libretro-*</code>, puis rouvrez le dialogue.</p>
"""),

    ("langues", "Choisir la langue", """
<p>L'interface existe en <b>français</b>, <b>anglais</b> et <b>allemand</b>.
<b>Aide ▸ Langue</b> bascule à chaud, sans redémarrer ; le choix est mémorisé.
Au premier lancement, la langue du système est détectée.</p>
<p>Le français est la langue source : les textes sont écrits en français dans le
code, et les catalogues associent chaque texte à sa traduction. Une chaîne non
traduite s'affiche donc en français, jamais sous forme de clé technique.</p>
<p>Pour compléter une traduction :
<code>python tools/extract_strings.py --missing en</code> liste ce qui
reste à faire.</p>
"""),

    ("barbarian", "Tutoriel : Barbarian (Atari ST)", """
<p>Objectif : retrouver comment Palace a rangé ses tuiles de personnages.</p>
<h3>1. Charger</h3>
<p><b>Planche</b> → <b>Barbarian ST</b> → la disquette → <b>Banque 1</b>.
L'outil affiche 252 tuiles de 24 × 21 px, en 2 plans, avec la palette du jeu
(couleurs 12 à 15).</p>
<h3>2. Comprendre les tuiles</h3>
<p>Chaque tuile est un morceau de personnage. La banque contient 252 tuiles ;
si un sprite fait 2 × 4 = 8 tuiles, il y en a 31 et demi — si la routine de
dessin du jeu suggère 3 × 4 = 12, on tombe sur 21 sprites exactement.</p>
<h3>3. Chercher</h3>
<p><b>Atelier</b> → grille 2 × 4 → <b>Assemblage automatique…</b> →
<i>Tout essayer</i>. Pour le premier groupe, une solution ressort : un chevalier
avec son épée, dans un ordre qui n'est pas l'ordre de stockage.</p>
<h3>4. Valider et répéter</h3>
<p><b>Valider le sprite</b>, puis <b>Sprite suivant</b>. Au bout de quelques
sprites, allez dans <b>Analyse</b> → <b>Inférer</b> : l'outil compare les
permutations et propose le modèle le plus simple qui les explique.</p>
<h3>5. Réappliquer</h3>
<p><b>Créer la recette</b>, puis <b>Appliquer à toute la banque</b> : les 21
sprites sont générés d'un coup et rangés dans l'atlas.</p>
"""),

    ("depannage", "Dépannage", """
<h3>L'image est noire ou illisible</h3>
<p>Le format ou la palette ne correspondent pas. Essayez <b>Analyser le
fichier</b>, changez de préréglage, ou vérifiez l'offset.</p>
<h3>La détection ne trouve rien</h3>
<p>La planche n'a peut-être pas de gouttières : utilisez la <b>grille fixe</b>
avec la taille de tuile attendue, ou le <b>XY-cut</b>.</p>
<h3>L'assemblage automatique propose n'importe quoi</h3>
<p>Vérifiez d'abord la grille. Ensuite, montez le poids de la silhouette et
baissez ceux de la palette et des doublons. Regardez plusieurs candidats : les
premiers sont souvent des variantes (décalage d'une ligne, miroir).</p>
<h3>L'inférence ne trouve aucune observation</h3>
<p>Elle a besoin de sprites validés dont les tuiles portent un indice de
stockage : cela suppose une banque brute, pas un PNG déjà découpé.</p>
<h3>Le programme ne démarre pas</h3>
<p>Vérifiez <code>python -m tileforge --selftest</code>, puis réinstallez les
dépendances : <code>pip install PySide6 numpy Pillow</code>.</p>
"""),

    ("apropos", "À propos", """
<p><b>TileForge</b> — reconstruction de sprites à partir de planches de tuiles.</p>
<p>Interface PySide6, calculs numpy, lecture PNG par Pillow (avec décodeur de
secours intégré). Le cœur (modèle, détection, coûts, solveurs) ne dépend pas de
Qt et s'utilise en script.</p>
<p>Version {version}. Licence libre, code source fourni.</p>
"""),
]


def doc_html(version: str) -> str:
    """Assemble la documentation complète en HTML."""
    toc = "".join(f'<li><a href="#{anchor}">{title}</a></li>'
                  for anchor, title, _ in DOC_SECTIONS)
    body = []
    for anchor, title, html in DOC_SECTIONS:
        body.append(f'<h2><a name="{anchor}"></a>{title}</h2>\n{html}')
    return f"""<html><head><style>
body {{ font-family: sans-serif; font-size: 13px; color: #d7dae2; }}
h2 {{ color: #4c9aff; margin-top: 28px; font-size: 19px; }}
h3 {{ color: #e8b339; font-size: 15px; margin-top: 18px; }}
a {{ color: #4c9aff; }}
code {{ background: #25262e; padding: 1px 4px; }}
li {{ margin-bottom: 4px; }}
table {{ border-collapse: collapse; margin: 8px 0; }}
th {{ background: #25262e; color: #8b90a0; padding: 5px; }}
td {{ padding: 4px; }}
</style></head><body>
<h1>TileForge — aide et tutoriel</h1>
<p>Version {version}</p>
<ul>{toc}</ul>
{''.join(body)}
</body></html>"""
