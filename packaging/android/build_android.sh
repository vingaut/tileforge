#!/usr/bin/env bash
# Construit l'APK Android de TileForge avec pyside6-android-deploy.
#
# Prérequis (voir packaging/README.md) :
#   * JDK 17
#   * Android SDK + NDK r28c  (ANDROID_SDK_ROOT / ANDROID_NDK_ROOT)
#   * les roues PySide6 et shiboken6 pour Android
#
# Usage :
#   ./packaging/android/build_android.sh \
#       --pyside-wheel ~/wheels/PySide6-6.12.0-cp39-abi3-android_aarch64.whl \
#       --shiboken-wheel ~/wheels/shiboken6-6.12.0-cp39-abi3-android_aarch64.whl
#
# Les roues peuvent aussi être déposées dans packaging/android/wheels/.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
STAGE="$HERE/.stage"
WHEEL_DIR="$HERE/wheels"

PYSIDE_WHEEL=""
SHIBOKEN_WHEEL=""
NDK_PATH="${ANDROID_NDK_ROOT:-}"
SDK_PATH="${ANDROID_SDK_ROOT:-}"
NAME="TileForge"

while [ $# -gt 0 ]; do
    case "$1" in
        --pyside-wheel)   PYSIDE_WHEEL="$2"; shift 2 ;;
        --shiboken-wheel) SHIBOKEN_WHEEL="$2"; shift 2 ;;
        --ndk-path)       NDK_PATH="$2"; shift 2 ;;
        --sdk-path)       SDK_PATH="$2"; shift 2 ;;
        --name)           NAME="$2"; shift 2 ;;
        -h|--help)        sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "option inconnue : $1" >&2; exit 2 ;;
    esac
done

# -- détection automatique des roues ---------------------------------------
if [ -z "$PYSIDE_WHEEL" ] && [ -d "$WHEEL_DIR" ]; then
    PYSIDE_WHEEL="$(ls -1 "$WHEEL_DIR"/PySide6-*android*.whl 2>/dev/null | head -1 || true)"
fi
if [ -z "$SHIBOKEN_WHEEL" ] && [ -d "$WHEEL_DIR" ]; then
    SHIBOKEN_WHEEL="$(ls -1 "$WHEEL_DIR"/shiboken6-*android*.whl 2>/dev/null | head -1 || true)"
fi

fail() { echo; echo "ERREUR : $*" >&2; echo; exit 1; }

echo "== TileForge — construction Android =="

# -- vérifications ---------------------------------------------------------
command -v java >/dev/null 2>&1 || fail "Java introuvable. Installez un JDK 17."
JAVA_MAJOR="$(java -version 2>&1 | head -1 | sed -E 's/.*version "([0-9]+).*/\1/')"
if [ -n "$JAVA_MAJOR" ] && [ "$JAVA_MAJOR" -lt 17 ] 2>/dev/null; then
    fail "JDK $JAVA_MAJOR détecté : il faut au moins Java 17."
fi
echo "  java      : $(java -version 2>&1 | head -1)"

[ -n "$SDK_PATH" ] || fail "Android SDK introuvable (définissez ANDROID_SDK_ROOT ou --sdk-path)."
[ -d "$SDK_PATH" ] || fail "Android SDK inexistant : $SDK_PATH"
echo "  sdk       : $SDK_PATH"

[ -n "$NDK_PATH" ] || fail "Android NDK introuvable (ANDROID_NDK_ROOT ou --ndk-path). Version r28c attendue."
[ -d "$NDK_PATH" ] || fail "Android NDK inexistant : $NDK_PATH"
echo "  ndk       : $NDK_PATH"

[ -n "$PYSIDE_WHEEL" ] && [ -f "$PYSIDE_WHEEL" ] || \
    fail "roue PySide6 Android introuvable (--pyside-wheel ou packaging/android/wheels/)."
[ -n "$SHIBOKEN_WHEEL" ] && [ -f "$SHIBOKEN_WHEEL" ] || \
    fail "roue shiboken6 Android introuvable (--shiboken-wheel ou packaging/android/wheels/)."
echo "  pyside    : $(basename "$PYSIDE_WHEEL")"
echo "  shiboken  : $(basename "$SHIBOKEN_WHEEL")"

VENV="$ROOT/.venv"
if [ ! -x "$VENV/bin/python" ]; then
    echo "-- création de l'environnement (pyside6-android-deploy)"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q --upgrade pip
fi
if ! "$VENV/bin/python" -c "import PySide6, jinja2, pkginfo, tqdm" >/dev/null 2>&1; then
    echo "-- installation de PySide6 et des outils de déploiement"
    "$VENV/bin/pip" install -q PySide6 numpy Pillow jinja2 pkginfo tqdm "packaging==24.1"
fi

# -- préparation du projet -------------------------------------------------
echo "-- préparation de $STAGE"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -r "$ROOT/tileforge" "$STAGE/tileforge"
rm -rf "$STAGE/tileforge/__pycache__" "$STAGE"/tileforge/*/__pycache__
cp "$HERE/main.py" "$STAGE/main.py"

cat > "$STAGE/README.txt" <<'TXT'
TileForge — paquet Android
Généré par packaging/android/build_android.sh
TXT

# -- déploiement -----------------------------------------------------------
echo "-- pyside6-android-deploy"
cd "$STAGE"
"$VENV/bin/pyside6-android-deploy" \
    --name "$NAME" \
    --wheel-pyside "$PYSIDE_WHEEL" \
    --wheel-shiboken "$SHIBOKEN_WHEEL" \
    --ndk-path "$NDK_PATH" \
    --sdk-path "$SDK_PATH" \
    --force

echo
echo "Terminé. L'APK se trouve dans : $STAGE/dist/"
find "$STAGE" -maxdepth 3 -name "*.apk" -print 2>/dev/null || true
echo
echo "Installation sur un appareil connecté :"
echo "  adb install -r <chemin>.apk"
