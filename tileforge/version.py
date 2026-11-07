"""Version de TileForge et journal des évolutions.

Ce module est la source de vérité pour tout ce qui touche aux versions :
le gestionnaire de mises à jour, l'affichage « À propos » et le manifeste
publié par ``tools/make_update.py``.
"""

from __future__ import annotations

__version__ = "1.4.2"
VERSION_TUPLE = (1, 4, 2)
BUILD_DATE = "2026-11-08"
APP_NAME = "TileForge"
APP_ID = "tileforge"
MIN_PYTHON = (3, 10)


#: Journal des évolutions, du plus récent au plus ancien.
CHANGELOG: list[dict] = [
    {
        "version": "1.4.2",
        "date": "2026-11-08",
        "title": "Décodage des tuiles Mega Drive corrigé",
        "changes": [
            "Le format de tuiles Mega Drive décode désormais 4 plans, un octet "
            "par plan et par ligne (bit 7 = pixel de gauche), au lieu de "
            "2 pixels par octet : les banques Mega Drive ne sortent plus en bruit.",
            "Le préréglage `megadrive` partage la disposition de la Master "
            "System ; aller-retour et non-régression couverts par les tests.",
            "Fixtures de test, outil de calibration, aide intégrée et "
            "documentation alignés sur l'encodage planaire.",
        ],
    },
    {
        "version": "1.4.1",
        "date": "2026-11-08",
        "title": "Import d'une ROM ou d'une archive depuis l'accueil",
        "changes": [
            "Bouton « Ouvrir une ROM / archive… » en tête de l'écran Planche.",
            "Action Fichier ▸ Importer une ROM ou une archive… (Ctrl+Maj+O) et "
            "bouton dans la barre d'outils.",
            "Écran d'accueil : la ROM/archive est proposée en premier, Barbarian "
            "devient un cas d'école secondaire.",
            "Traductions anglaises et allemandes des nouveaux textes.",
        ],
    },
    {
        "version": "1.4.0",
        "date": "2026-11-08",
        "title": "Archives zip/7z et démonstration multi-systèmes",
        "changes": [
            "Lecture directe des ROMs dans les archives zip et 7z, avec choix "
            "du membre ; py7zr ou la commande 7z en secours.",
            "Outil MCP tileforge_list_archive et paramètre archive_member sur "
            "les outils de lecture ; sélection du membre dans les dialogues "
            "Banque brute et Mémoire d'émulateur.",
            "Cœurs libretro validés sur neuf machines : NES, SNES, Mega Drive, "
            "Game Boy, GBA, Master System, PC Engine, ZX Spectrum, CPC.",
            "Démonstration reproductible : tools/build_demo.py et "
            "tools/demo_extract.py produisent capture, planche de tuiles, "
            "proposition de sprites, mémoire brute et rapport JSON.",
            "Dossier ../tileforge-demo : neuf jeux "
            "traités, sans copie de ROM.",
            "Générateur de configuration MCP (tools/mcp_config.py) et guide "
            "des clients LLM (docs/mcp-clients.md).",
            "Configurations de projet .mcp.json, .vscode/mcp.json et "
            ".cursor/mcp.json pour la découverte automatique, plus un point "
            "d'entrée tileforge-mcp.",
            "216 tests, dont les archives zip/7z et le handshake MCP.",
        ],
    },
    {
        "version": "1.3.0",
        "date": "2026-11-08",
        "title": "Mémoire d'émulateur, LZ77/LZ11 et LC_LZ3",
        "changes": [
            "Mémoire d'émulateur : exécute une ROM dans un cœur libretro, "
            "avance de quelques centaines de trames et lit la RAM système, la "
            "VRAM et la SRAM — les graphismes y sont déjà décompressés.",
            "Instantanés reproductibles : une région par fichier .bin, un "
            "fichier concaténé, une capture PNG et un manifeste JSON.",
            "Dialogue Outils ▸ Mémoire d'émulateur…, outils MCP "
            "tileforge_list_emulator_cores et tileforge_emulator_memory, "
            "script tools/emulator_memory.py.",
            "Décompresseurs LZ77/LZ11 (GBA, NDS) d'après GBATEK et LC_LZ3 "
            "(SNES) d'après SnesLab, avec vecteurs de test construits.",
            "Formats de tuiles Game Boy Advance 4 et 8 bits.",
            "Aide : section « Mémoire d'émulateur » (30 sections), traductions "
            "anglaises et allemandes des nouveaux textes.",
            "199 tests, dont un cœur libretro factice compilé à la volée ; "
            "hôte validé avec Snes9x sur Final Fight.",
        ],
    },
    {
        "version": "1.2.0",
        "date": "2026-11-08",
        "title": "Recherche de graphismes, cartographie, désassembleurs, i18n",
        "changes": [
            "Bouton « Chercher des graphismes… » : balaye tout le fichier, données "
            "brutes et blocs compressés, et propose les zones trouvées avec un aperçu.",
            "Note de vraisemblance graphique calibrée sur un corpus étiqueté "
            "(AUC 0,985) ; elle remplace l'ancienne heuristique.",
            "Identification du format d'une banque inconnue : chaque candidat est "
            "comparé à son propre plancher de bruit.",
            "Balayage parallèle, budget de temps, progression et interruption ; "
            "option « zones de données seulement » huit fois plus rapide.",
            "Décompresseurs : Saxman, Enigma, Kosinski modulé, Comper, Sonic RLE, "
            "PackBits et deux variantes de RLE, validés par des vecteurs officiels.",
            "Cartographie de ROM : plateforme à l'en-tête, zones d'entropie, "
            "tables de pointeurs et blocs de données.",
            "Désassembleurs 6502, Z80, SM83 (Game Boy), 68000 et 65816, avec "
            "traçage du fil d'exécution depuis un vecteur.",
            "Interface en français, anglais et allemand, bascule à chaud.",
            "Icônes SVG maison à la place de celles de Qt.",
            "Serveur MCP : 17 outils, même moteur que l'interface.",
            "Publication : licence MIT, pyproject, CI, 155 tests, README bilingue.",
        ],
    },
    {
        "version": "1.1.0",
        "date": "2026-11-06",
        "title": "Aide interactive, tutoriel, mises à jour, multi-plateforme",
        "changes": [
            "Aide interactive : survolez un bouton deux secondes pour lire ce qu'il fait.",
            "Page d'aide et tutoriel pas à pas intégrés (F1).",
            "Gestionnaire de mises à jour avec vérification, notes de version et installation.",
            "Paquets Linux et Windows (PyInstaller) et chaîne Android (pyside6-android-deploy).",
            "Mode tactile : pose des tuiles au doigt, panneaux escamotables, pincement pour zoomer.",
            "Réglages persistants (aide, mises à jour, dernière session).",
        ],
    },
    {
        "version": "1.0.0",
        "date": "2026-11-06",
        "title": "Première version complète",
        "changes": [
            "Chargement PNG, banque brute et disquette Atari ST (Barbarian).",
            "Détection de résolution et catalogue de 76 machines.",
            "Six détecteurs de tuiles, édition manuelle, contrôle qualité.",
            "Assemblage manuel et automatique (M1–M6), coûts C1–C6.",
            "Atlas, journal des mouvements, inférence de règle et recettes.",
            "Exports CSV, JSON et permutations.",
        ],
    },
]


def changelog_text() -> str:
    """Journal des évolutions au format texte simple."""
    lines = []
    for entry in CHANGELOG:
        lines.append(f"v{entry['version']} — {entry['date']} — {entry['title']}")
        for change in entry["changes"]:
            lines.append(f"  • {change}")
        lines.append("")
    return "\n".join(lines)


def version_string() -> str:
    return f"{APP_NAME} {__version__} ({BUILD_DATE})"
