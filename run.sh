#!/usr/bin/env bash
# Lancement de TileForge (crée l'environnement virtuel au premier lancement).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"

if [ ! -x "$VENV/bin/python" ]; then
    echo "Création de l'environnement virtuel…"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip >/dev/null
    echo "Installation de TileForge et de l'interface (patience, ~200 Mo)…"
    "$VENV/bin/pip" install -e ".[gui]"
fi

export PYTHONPATH="$HERE:${PYTHONPATH:-}"
cd "$HERE"
exec "$VENV/bin/python" -m tileforge "$@"
