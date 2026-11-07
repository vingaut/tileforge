#!/usr/bin/env python3
"""Point d'entrée utilisé par PyInstaller et par les paquets figés."""

import multiprocessing
import os
import sys


def _bootstrap() -> None:
    """Ajoute la racine du projet au chemin (mode source uniquement)."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    if root not in sys.path:
        sys.path.insert(0, root)


_bootstrap()

from tileforge.main import main  # noqa: E402

if __name__ == "__main__":
    # Obligatoire pour les exécutables figés : le balayage parallèle crée des
    # processus qui réimportent ce module.
    multiprocessing.freeze_support()
    sys.exit(main())
