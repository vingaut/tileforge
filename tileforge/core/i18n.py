"""Internationalisation : catalogues de traduction et langue courante.

Le français est la langue source : les textes de l'interface sont écrits en
français dans le code, et un catalogue JSON associe chaque texte à sa
traduction. Cette méthode a deux avantages sur les marqueurs ``tr()`` de Qt :

* le code reste lisible — on lit du français, pas des clés ;
* une chaîne non traduite s'affiche simplement en français, jamais sous forme
  de clé technique.

Les catalogues vivent dans ``tileforge/i18n/<langue>.json`` et associent le
texte français à sa traduction. Le module ne dépend pas de Qt.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

#: Langues proposées : code ISO → nom affiché dans sa propre langue.
LANGUAGES: dict[str, str] = {
    "fr": "Français",
    "en": "English",
    "de": "Deutsch",
}

#: Langue de référence (celle dans laquelle le code est écrit).
SOURCE_LANGUAGE = "fr"

#: Langue par défaut tant qu'aucun réglage n'a été enregistré.
DEFAULT_LANGUAGE = "fr"

_current: str = DEFAULT_LANGUAGE
_catalog: dict[str, str] = {}


def catalog_dir() -> Path:
    """Dossier des catalogues : ``tileforge/i18n`` (au-dessus du paquet core)."""
    return Path(__file__).resolve().parent.parent / "i18n"


def catalog_path(code: str) -> Path:
    return catalog_dir() / f"{code}.json"


def available_languages() -> dict[str, str]:
    """Langues dont un catalogue existe (la source est toujours disponible)."""
    found = {SOURCE_LANGUAGE: LANGUAGES[SOURCE_LANGUAGE]}
    for code, label in LANGUAGES.items():
        if code != SOURCE_LANGUAGE and catalog_path(code).exists():
            found[code] = label
    return found


def load_catalog(code: str) -> dict[str, str]:
    """Charge le catalogue d'une langue ; renvoie un dictionnaire vide si absent."""
    if code == SOURCE_LANGUAGE:
        return {}
    path = catalog_path(code)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return {str(key): str(value) for key, value in data.items() if value}


def set_language(code: str) -> None:
    """Change la langue courante et recharge le catalogue."""
    global _current, _catalog
    code = (code or DEFAULT_LANGUAGE).lower()
    if code not in LANGUAGES:
        code = DEFAULT_LANGUAGE
    _current = code
    _catalog = load_catalog(code)


def language() -> str:
    """Code de la langue courante."""
    return _current


def language_name(code: str | None = None) -> str:
    """Nom affiché d'une langue."""
    return LANGUAGES.get(code or _current, code or _current)


def t(text: str) -> str:
    """Traduit un texte français ; le renvoie tel quel s'il n'est pas traduit."""
    if not text or _current == SOURCE_LANGUAGE:
        return text
    return _catalog.get(text, text)


def detect_from_environment() -> str:
    """Devine la langue d'après les variables d'environnement du système."""
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "")
        if not value:
            continue
        code = value.split(".")[0].split("_")[0].lower()
        if code in available_languages():
            return code
    return DEFAULT_LANGUAGE


def missing_translations(code: str, texts: list[str]) -> list[str]:
    """Textes non couverts par le catalogue — utile à l'outil d'extraction."""
    catalog = load_catalog(code)
    return sorted({text for text in texts if text and text not in catalog})
