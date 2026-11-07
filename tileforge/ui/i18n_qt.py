"""Application des traductions à une interface Qt.

Plutôt que d'envelopper chaque chaîne dans un appel de traduction — ce qui
demanderait de réécrire toute l'interface et rendrait le code illisible — on
parcourt l'arbre des widgets après construction et on remplace les libellés
statiques par leur traduction.

Le texte d'origine est mémorisé sur chaque objet la première fois : changer de
langue deux fois de suite repart toujours du français, jamais d'une traduction
déjà appliquée.
"""

from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QMenu,
    QTabWidget,
    QWidget,
)

from ..core.i18n import t

_SOURCE_PROPERTY = "tileforge_source"
_ITEMS_PROPERTY = "tileforge_items"
_TABS_PROPERTY = "tileforge_tabs"


def _remember(obj, text: str) -> str:
    """Retient le texte d'origine et renvoie la traduction."""
    source = obj.property(_SOURCE_PROPERTY)
    if source is None:
        source = text
        obj.setProperty(_SOURCE_PROPERTY, source)
    return t(source)


def _remember_list(obj, texts: list[str], property_name: str) -> list[str]:
    """Mémorise une liste de textes (onglets, entrées d'une liste) une seule fois."""
    sources = obj.property(property_name)
    if sources is None or len(sources) != len(texts):
        sources = list(texts)
        obj.setProperty(property_name, sources)
    return [t(source) for source in sources]


def apply_to(root: QWidget) -> int:
    """Traduit tous les libellés statiques sous ``root``.

    Renvoie le nombre d'éléments traités (utile aux tests et au diagnostic).
    """
    if root is None:
        return 0
    touched = 0

    for action in root.findChildren(QAction):
        text = action.text()
        if text:
            translated = _remember(action, text)
            if translated != text:
                action.setText(translated)
            touched += 1

    for widget in root.findChildren(QWidget):
        if isinstance(widget, QMenu):
            title = widget.title()
            if title:
                widget.setTitle(_remember(widget, title))
                touched += 1
        if isinstance(widget, QGroupBox):
            title = widget.title()
            if title:
                widget.setTitle(_remember(widget, title))
                touched += 1
        if isinstance(widget, (QLabel, QAbstractButton)) and not isinstance(widget, QMenu):
            text = widget.text()
            if text:
                translated = _remember(widget, text)
                if translated != text:
                    widget.setText(translated)
                touched += 1
        if isinstance(widget, QComboBox):
            items = [widget.itemText(index) for index in range(widget.count())]
            translated = _remember_list(widget, items, _ITEMS_PROPERTY)
            for index, text in enumerate(translated):
                if text:
                    widget.setItemText(index, text)
                    touched += 1
        if isinstance(widget, QTabWidget):
            tabs = [widget.tabText(index) for index in range(widget.count())]
            translated = _remember_list(widget, tabs, _TABS_PROPERTY)
            for index, text in enumerate(translated):
                if text:
                    widget.setTabText(index, text)
                    touched += 1

    window_title = root.windowTitle()
    if window_title:
        root.setWindowTitle(_remember(root, window_title))
        touched += 1
    return touched
