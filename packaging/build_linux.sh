#!/usr/bin/env bash
# Construit l'application Linux autonome (dossier dist/TileForge).
#
#   ./packaging/build_linux.sh              paquet « onedir » (recommandé)
#   TILEFORGE_ONEFILE=1 ./packaging/build_linux.sh    exécutable unique
#   TILEFORGE_CONSOLE=1 ./packaging/build_linux.sh    garde une console
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BUILD_VENV="$ROOT/.venv-build"
DIST="$ROOT/dist"

echo "== TileForge — construction Linux =="
echo "projet : $ROOT"

if [ ! -x "$BUILD_VENV/bin/python" ]; then
    echo "-- création de l'environnement de compilation"
    python3 -m venv "$BUILD_VENV"
    "$BUILD_VENV/bin/pip" install --upgrade pip >/dev/null
fi

echo "-- installation des dépendances de compilation"
"$BUILD_VENV/bin/pip" install -q PySide6 numpy Pillow pyinstaller

echo "-- PyInstaller"
cd "$ROOT"
"$BUILD_VENV/bin/pyinstaller" \
    --noconfirm --clean \
    --distpath "$DIST" \
    --workpath "$ROOT/build" \
    "$HERE/tileforge.spec"

TARGET="$DIST/TileForge"
if [ -x "$TARGET/TileForge" ]; then
    echo
    echo "Terminé : $TARGET/TileForge"
    du -sh "$TARGET" 2>/dev/null || true
    echo
    echo "Lancement : $TARGET/TileForge"
    echo "Installeur .desktop : cp packaging/tileforge.desktop ~/.local/share/applications/"
else
    echo "Échec : $TARGET/TileForge est introuvable" >&2
    exit 1
fi
