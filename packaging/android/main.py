#!/usr/bin/env python3
"""Point d'entrée Android (pyside6-android-deploy attend un ``main.py``)."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from tileforge.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
