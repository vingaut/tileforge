#!/usr/bin/env python3
"""Extrait les chaînes traduisibles de l'interface.

Le français est la langue source : ce script liste les textes écrits en dur
dans les modules Qt et produit un squelette de catalogue JSON, à compléter
puis à enregistrer dans ``tileforge/i18n/<langue>.json``.

    python tools/extract_strings.py                 # squelette pour l'anglais
    python tools/extract_strings.py --lang de       # squelette pour l'allemand
    python tools/extract_strings.py --missing en    # ce qui reste à traduire

Le script ne modifie rien : il écrit sur la sortie standard.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tileforge.core.i18n import available_languages, load_catalog  # noqa: E402

#: Méthodes et constructeurs dont les arguments textuels sont affichés.
TEXT_CALLS = {
    "setText", "setTitle", "setWindowTitle", "setToolTip", "setStatusTip",
    "setPlaceholderText", "addAction", "addMenu", "addTab", "addItem",
    "setTabText", "setItemText", "QLabel", "QPushButton", "QCheckBox",
    "QRadioButton", "QGroupBox", "QAction", "QMenu", "QToolTip",
}

#: Textes trop courts ou techniques pour valoir une traduction.
IGNORED = {"", "—", "-", "…", "OK", "0", "1", "×"}


def iter_strings(path: Path):
    """Renvoie les chaînes littérales passées aux appels d'interface."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = ""
        if isinstance(node.func, ast.Attribute):
            name = node.func.attr
        elif isinstance(node.func, ast.Name):
            name = node.func.id
        if name not in TEXT_CALLS:
            continue
        for argument in node.args[:2]:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                yield argument.value


def collect(folders: list[Path]) -> list[str]:
    seen: dict[str, None] = {}
    for folder in folders:
        for path in sorted(folder.rglob("*.py")):
            for text in iter_strings(path):
                cleaned = text.strip()
                if cleaned in IGNORED or len(cleaned) < 2:
                    continue
                if cleaned.startswith(("http", "file:", "~", "/")) and " " not in cleaned:
                    continue
                seen.setdefault(cleaned, None)
    return sorted(seen, key=str.lower)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", default="en", help="langue du catalogue à produire")
    parser.add_argument("--missing", metavar="LANGUE",
                        help="affiche les textes absents du catalogue de cette langue")
    args = parser.parse_args(argv)

    folders = [ROOT / "tileforge" / "ui", ROOT / "tileforge"]
    texts = collect(folders)

    if args.missing:
        catalog = load_catalog(args.missing)
        missing = [text for text in texts if text not in catalog]
        for text in missing:
            print(text)
        print(f"\n{len(missing)} texte(s) non traduits sur {len(texts)}.",
              file=sys.stderr)
        return 0

    if args.lang == "fr":
        print("Le français est la langue source : aucun catalogue à produire.",
              file=sys.stderr)
        return 0
    catalog = load_catalog(args.lang)
    skeleton = {text: catalog.get(text, "") for text in texts}
    print(json.dumps(skeleton, ensure_ascii=False, indent=1))
    languages = ", ".join(available_languages())
    print(f"\n{len(texts)} texte(s) · langues disponibles : {languages}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
