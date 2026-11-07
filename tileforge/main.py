#!/usr/bin/env python3
"""Point d'entrée de TileForge.

Usage :
    python -m tileforge [fichier]           ouvre un projet, une image ou une ROM
    python -m tileforge --mobile            force la présentation tactile
    python -m tileforge --help              options
    python -m tileforge --selftest          vérifie l'installation sans interface
    python -m tileforge --check-updates     vérifie les mises à jour en console
"""

from __future__ import annotations

import argparse
import os
import sys


def _ensure_path() -> None:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)


# ---------------------------------------------------------------------------
# Auto-test sans interface
# ---------------------------------------------------------------------------


def selftest() -> int:
    """Vérifie que le cœur et les dépendances fonctionnent."""
    import importlib
    failures = 0
    print("TileForge — auto-test")
    for module in ("PySide6", "numpy", "PIL"):
        try:
            mod = importlib.import_module(module)
            version = getattr(mod, "__version__", "?")
            print(f"  [ok] {module} {version}")
        except Exception as exc:
            failures += 1
            print(f"  [!!] {module} introuvable : {exc}")

    from tileforge.version import version_string
    print(f"  [ok] {version_string()}")

    try:
        from tileforge.core import formats
        from tileforge.core.systems import SYSTEMS
        from tileforge.detect.base import all_detectors
        from tileforge.games import atari_st, generic  # noqa: F401
        print(f"  [ok] modules cœur chargés · {len(SYSTEMS)} machines · "
              f"{len(all_detectors())} détecteurs · {len(formats.FORMATS)} formats")
    except Exception as exc:
        failures += 1
        print(f"  [!!] chargement des modules : {exc}")

    try:

        from tileforge.core.image import Image
        img = Image.blank(8, 8, (255, 0, 0, 255))
        assert img.px.shape == (8, 8, 4)
        print("  [ok] image et numpy")
    except Exception as exc:
        failures += 1
        print(f"  [!!] image : {exc}")

    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from tileforge.ui import theme
        from tileforge.ui.main_window import MainWindow
        app = QApplication.instance() or QApplication([])
        app.setStyleSheet(theme.STYLESHEET)
        window = MainWindow()
        window.resize(1200, 800)
        window.show()
        app.processEvents()
        print(f"  [ok] interface Qt ({app.platformName()}) · aide interactive : "
              f"{'active' if window.help.enabled else 'inactive'}")
        window.close()
    except Exception as exc:
        failures += 1
        print(f"  [!!] interface Qt : {exc}")

    print("Résultat :", "OK" if failures == 0 else f"{failures} problème(s)")
    return 0 if failures == 0 else 1


# ---------------------------------------------------------------------------
# Vérification de mise à jour en console
# ---------------------------------------------------------------------------


def check_updates_console(url: str, channel: str) -> int:
    from tileforge.core.settings import Settings
    from tileforge.core.updates import UpdateError, UpdateManager
    from tileforge.version import __version__

    settings = Settings()
    url = url or settings.get("update_url", "")
    if not url:
        print("Aucune adresse de manifeste configurée. Utilisez --update-url.")
        return 2
    manager = UpdateManager(url, channel)
    print(f"Version installée : {__version__}")
    try:
        release = manager.check()
    except UpdateError as exc:
        print(f"Échec : {exc}")
        return 1
    if release is None:
        print("À jour.")
        return 0
    print(f"Nouvelle version : {release.version} ({release.date})")
    if release.notes:
        print()
        print(release.notes)
    print()
    print("Installez-la depuis le menu Aide ▸ Mises à jour.")
    return 0


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tileforge",
        description="Reconstruction de sprites à partir de planches de tuiles.")
    parser.add_argument("file", nargs="?", help="projet .json, image ou banque à ouvrir")
    parser.add_argument("--mobile", action="store_true",
                        help="présentation tactile (grandes cibles, panneaux repliés)")
    parser.add_argument("--selftest", action="store_true",
                        help="vérifie l'installation sans ouvrir de fenêtre")
    parser.add_argument("--check-updates", action="store_true",
                        help="vérifie les mises à jour en console")
    parser.add_argument("--update-url", default="",
                        help="adresse du manifeste de mise à jour")
    parser.add_argument("--channel", default="stable", choices=["stable", "beta"],
                        help="canal de mise à jour")
    parser.add_argument("--reset-settings", action="store_true",
                        help="efface les réglages enregistrés")
    parser.add_argument("--mcp", action="store_true",
                        help="lance le serveur MCP (JSON-RPC sur l'entrée standard)")
    return parser


def main(argv: list[str] | None = None) -> int:
    _ensure_path()
    raw_args = list(sys.argv[1:] if argv is None else argv[1:])
    args = _parser().parse_args(raw_args)

    if args.reset_settings:
        from tileforge.core.settings import settings_path
        try:
            os.unlink(settings_path())
            print(f"Réglages effacés : {settings_path()}")
        except FileNotFoundError:
            print("Aucun réglage à effacer.")
        return 0

    if args.selftest:
        return selftest()

    if args.check_updates:
        return check_updates_console(args.update_url, args.channel)

    if args.mcp:
        from tileforge.mcp.server import McpServer
        return McpServer().serve_forever()

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QPalette
    from PySide6.QtWidgets import QApplication

    from tileforge.core import i18n
    from tileforge.core.settings import Settings, is_android
    from tileforge.ui import theme
    from tileforge.ui.main_window import MainWindow
    from tileforge.version import APP_NAME

    if args.mobile or is_android():
        os.environ["TILEFORGE_MOBILE"] = "1"

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication([sys.argv[0]] + raw_args)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("TileForge")
    app.setApplicationVersion(__import__("tileforge.version", fromlist=["__version__"]).__version__)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(theme.BG))
    palette.setColor(QPalette.WindowText, QColor(theme.TEXT))
    palette.setColor(QPalette.Base, QColor(theme.PANEL))
    palette.setColor(QPalette.AlternateBase, QColor(theme.PANEL_ALT))
    palette.setColor(QPalette.Text, QColor(theme.TEXT))
    palette.setColor(QPalette.Button, QColor(theme.PANEL_ALT))
    palette.setColor(QPalette.ButtonText, QColor(theme.TEXT))
    palette.setColor(QPalette.Highlight, QColor(theme.ACCENT_DARK))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor(theme.PANEL_ALT))
    palette.setColor(QPalette.ToolTipText, QColor(theme.TEXT))
    app.setPalette(palette)
    app.setStyleSheet(theme.STYLESHEET)

    font_name = "DejaVu Sans"
    if is_android():
        font_name = "Roboto"
    app.setFont(QFont(font_name, 10))

    settings = Settings()
    language = settings.get("language", "auto")
    if language in ("", "auto", None):
        language = i18n.detect_from_environment()
    i18n.set_language(language)
    if args.update_url:
        settings.set("update_url", args.update_url)
    if args.channel:
        settings.set("update_channel", args.channel, save=False)
        settings.save()

    window = MainWindow(settings)
    window.show()

    if args.file:
        path = args.file
        if path.lower().endswith(".json"):
            window.open_path(path)
        else:
            window.sheet_view.open_path_direct(path)

    return app.exec()


if __name__ == "__main__":
    # Le balayage parallèle lance des processus qui réimportent ce module ;
    # sans cet appel, un exécutable figé (PyInstaller) boucle.
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
