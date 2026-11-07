"""Jeu d'icônes maison, dessinées en SVG et rendues par Qt.

Les icônes standard de Qt datent des années 1990 : cercles colorés et
pictogrammes de bureau. Elles jurent dans une interface sombre. Ce module
fournit un jeu cohérent, en trait fin, qui reprend la couleur d'accent.

Chaque icône est un SVG minimal (18 × 18) rendu à la taille demandée ; Qt sait
lire le SVG grâce au greffon `qsvg` livré avec PySide6.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

#: Couleur du trait, alignée sur le thème.
STROKE = "#c8d0e0"
ACCENT = "#4f8cff"

_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18" '
    'fill="none" stroke="{color}" stroke-width="1.4" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)

#: Corps SVG de chaque icône.
SHAPES: dict[str, str] = {
    "new": '<path d="M4 2h7l3 3v11H4z"/><path d="M11 2v3h3"/><path d="M9 8v5M6.5 10.5h5"/>',
    "open": '<path d="M2 5h5l1.5 2H16v8H2z"/><path d="M2 7h14"/>',
    "save": '<path d="M3 2h9l3 3v11H3z"/><path d="M6 2v4h6V2"/><path d="M6 11h6v5H6z"/>',
    "undo": '<path d="M6 5L2 9l4 4"/><path d="M2 9h8a5 5 0 0 1 0 10H7"/>',
    "redo": '<path d="M12 5l4 4-4 4"/><path d="M16 9H8a5 5 0 0 0 0 10h3"/>',
    "help": '<circle cx="9" cy="9" r="7"/><path d="M6.8 6.6a2.3 2.3 0 1 1 3.2 2.1c-.7.3-1 .9-1 1.6v.4"/>'
            '<circle cx="9" cy="13.4" r=".8" fill="{color}" stroke="none"/>',
    "updates": '<path d="M15 9a6 6 0 1 1-2-4.5"/><path d="M15 2v4h-4"/>',
    "fullscreen": '<path d="M3 7V3h4"/><path d="M15 7V3h-4"/><path d="M3 11v4h4"/><path d="M15 11v4h-4"/>',
    "machines": '<rect x="2" y="3" width="14" height="9" rx="1"/><path d="M6 15h6"/><path d="M9 12v3"/>',
    "cartography": '<rect x="2" y="3" width="14" height="12" rx="1"/>'
                   '<path d="M2 7h14M2 11h14M6 3v12M11 3v12"/>',
    "disassemble": '<path d="M6 5L2 9l4 4"/><path d="M12 5l4 4-4 4"/><path d="M10 3l-2 12"/>',
    "scan": '<circle cx="8" cy="8" r="5"/><path d="M12 12l4 4"/>',
    "identify": '<circle cx="9" cy="9" r="7"/><path d="M9 12v.6"/><path d="M6.5 6.5a2.5 2.5 0 1 1 3.4 2.4c-.6.2-.9.7-.9 1.2"/>',
    "profile": '<path d="M3 3h12v12H3z"/><path d="M3 7h12"/><circle cx="6" cy="10" r="1.3"/>'
               '<path d="M10 9.5h3M10 11.5h3"/>',
    "palette": '<circle cx="9" cy="9" r="7"/><circle cx="6" cy="7" r="1" fill="{color}" stroke="none"/>'
               '<circle cx="11" cy="6.5" r="1" fill="{color}" stroke="none"/>'
               '<circle cx="12" cy="11" r="1" fill="{color}" stroke="none"/>',
    "weights": '<path d="M2 13h3V7H2zM7 13h3V4H7zM12 13h3V9h-3z"/>',
}

_cache: dict[tuple[str, int], QIcon] = {}


def svg(name: str, color: str = STROKE) -> str:
    """Source SVG d'une icône, ou une chaîne vide si le nom est inconnu."""
    body = SHAPES.get(name)
    if body is None:
        return ""
    return _TEMPLATE.format(color=color, body=body.replace("{color}", color))


def pixmap(name: str, size: int = 18, color: str = STROKE) -> QPixmap:
    """Rend l'icône en pixmap, avec transparence."""
    source = svg(name, color)
    result = QPixmap(size, size)
    result.fill()
    if not source:
        return result
    renderer = QSvgRenderer(QByteArray(source.encode("utf-8")))
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return result


def icon(name: str, size: int = 18, color: str = STROKE) -> QIcon:
    """Icône prête à l'emploi, mise en cache."""
    key = (name, size)
    if key not in _cache:
        _cache[key] = QIcon(pixmap(name, size, color))
    return _cache[key]


def available() -> list[str]:
    """Noms d'icônes connus."""
    return sorted(SHAPES)


def clear_cache() -> None:
    """Vide le cache (utile quand le thème change)."""
    _cache.clear()
