"""Tests de l'internationalisation.

Les catalogues sont du JSON livré avec le paquet : on vérifie qu'ils existent,
qu'ils couvrent l'interface et que le repli sur le français ne casse jamais.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tileforge.core import i18n


def test_langues_disponibles():
    languages = i18n.available_languages()
    assert "fr" in languages
    assert "en" in languages
    assert "de" in languages
    assert languages["fr"] == "Français"


def test_catalogues_charges_et_complets():
    """Chaque catalogue est un JSON valide, non vide et sans trou."""
    for code in ("en", "de"):
        path = i18n.catalog_path(code)
        assert path.exists(), path
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        assert len(data) > 100, (code, len(data))
        for key, value in data.items():
            assert key.strip(), code
            assert isinstance(value, str) and value.strip(), (code, key)


def test_traductions_attendues():
    i18n.set_language("en")
    assert i18n.t("Planche") == "Sheet"
    assert i18n.t("Aide interactive") == "Interactive help"
    i18n.set_language("de")
    assert i18n.t("Planche") == "Vorlage"
    i18n.set_language("fr")


def test_repli_sur_le_francais():
    i18n.set_language("en")
    assert i18n.t("texte qui n'existe pas") == "texte qui n'existe pas"
    i18n.set_language("fr")
    assert i18n.t("Planche") == "Planche"


def test_langue_inconnue_retombe_sur_le_francais():
    i18n.set_language("xx")
    assert i18n.language() == "fr"
    i18n.set_language("fr")


def test_detection_par_environnement():
    previous = {name: os.environ.get(name) for name in ("LC_ALL", "LC_MESSAGES", "LANG")}
    try:
        os.environ.pop("LC_ALL", None)
        os.environ.pop("LC_MESSAGES", None)
        os.environ["LANG"] = "de_DE.UTF-8"
        assert i18n.detect_from_environment() == "de"
        os.environ["LANG"] = "en_US.UTF-8"
        assert i18n.detect_from_environment() == "en"
        os.environ["LANG"] = "ja_JP.UTF-8"
        assert i18n.detect_from_environment() == "fr"
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_textes_manquants():
    """L'outil de contrôle doit signaler ce qui reste à traduire."""
    missing = i18n.missing_translations("en", ["Planche", "Texte inédit"])
    assert missing == ["Texte inédit"]
