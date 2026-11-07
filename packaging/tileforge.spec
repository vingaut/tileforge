# -*- mode: python ; coding: utf-8 -*-
"""Recette PyInstaller de TileForge (Linux et Windows).

Utilisation :
    pyinstaller --noconfirm --clean packaging/tileforge.spec

Variables d'environnement utiles :
    TILEFORGE_CONSOLE=1   garde une console (utile pour voir les erreurs)
    TILEFORGE_ONEFILE=1   produit un exécutable unique au lieu d'un dossier
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
CONSOLE = os.environ.get("TILEFORGE_CONSOLE") == "1"
ONEFILE = os.environ.get("TILEFORGE_ONEFILE") == "1"
ICON = os.path.join(SPECPATH, "icon.ico" if os.name == "nt" else "icon.png")

# Modules Qt inutiles ici : les exclure divise la taille du paquet par deux.
EXCLUDES = [
    "tkinter", "unittest", "pydoc_data", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtQml", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtHelp",
    "PySide6.QtDesigner", "PySide6.QtUiTools", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSerialPort",
    "PySide6.QtSensors", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio", "PySide6.QtSvgWidgets",
]

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(SPECPATH, "icon.png"), "packaging")],
    hiddenimports=[
        "tileforge.ui.help_content",
        "tileforge.ui.help",
        "tileforge.ui.help_dialog",
        "tileforge.ui.update_dialog",
        "tileforge.core.updates",
        "tileforge.core.settings",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="TileForge",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=CONSOLE,
        icon=ICON,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="TileForge",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=CONSOLE,
        icon=ICON,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="TileForge",
    )
