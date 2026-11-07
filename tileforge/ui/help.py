"""Aide interactive : fiches affichées après deux secondes de survol.

Le principe est volontairement simple :

* un filtre d'événements global surveille le widget sous le curseur ;
* si le curseur reste **deux secondes** sur le même widget sans clic, une fiche
  apparaît à côté, avec le titre, l'explication et le raccourci ;
* le contrôle survolé est surligné d'un cadre ;
* un clic, un déplacement vers un autre contrôle ou Échap referme la fiche.

Les fiches viennent de :mod:`tileforge.ui.help_content`.  La liaison se fait
par clé (``help.bind(bouton, "sheet.detect")``) ou automatiquement par libellé
pour tout le reste de l'interface.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFrame,
    QGroupBox,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .help_content import GROUP_TO_KEY, HELP, TEXT_TO_KEY, HelpEntry

MAX_WIDTH = 400


# ---------------------------------------------------------------------------
# Liaison des fiches
# ---------------------------------------------------------------------------


def bind(widget: QWidget, key: str) -> QWidget:
    """Associe une fiche d'aide à un widget."""
    if widget is not None and key in HELP:
        widget.setProperty("helpKey", key)
        entry = HELP[key]
        if entry.shortcut:
            widget.setToolTip(f"{entry.title} ({entry.shortcut})")
        else:
            widget.setToolTip(entry.title)
    return widget


def _widget_label(widget: QWidget) -> str:
    for attr in ("text", "title"):
        value = getattr(widget, attr, None)
        if callable(value):
            try:
                text = value()
            except Exception:
                continue
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""


def resolve(widget: QWidget | None) -> tuple[HelpEntry, QWidget] | None:
    """Trouve la fiche correspondant à un widget (en remontant ses parents)."""
    current = widget
    depth = 0
    while current is not None and depth < 12:
        key = current.property("helpKey")
        if key and key in HELP:
            return HELP[key], current
        label = _widget_label(current)
        if label:
            if isinstance(current, (QAbstractButton, QToolButton)):
                mapped = TEXT_TO_KEY.get(label)
                if mapped:
                    return HELP[mapped], current
            if isinstance(current, QGroupBox):
                mapped = GROUP_TO_KEY.get(label)
                if mapped:
                    return HELP[mapped], current
        tip = current.toolTip()
        if tip and len(tip) > 3:
            return HelpEntry(label or tip, tip), current
        current = current.parentWidget()
        depth += 1
    return None


def auto_bind(root: QWidget) -> int:
    """Parcourt l'arbre de widgets et lie les fiches par libellé.

    Renvoie le nombre de contrôles liés.  Les widgets qui ont déjà une clé ne
    sont pas touchés.
    """
    count = 0
    for widget in root.findChildren(QWidget):
        if widget.property("helpKey"):
            continue
        label = _widget_label(widget)
        if not label:
            continue
        key = None
        if isinstance(widget, QAbstractButton):
            key = TEXT_TO_KEY.get(label)
        elif isinstance(widget, QGroupBox):
            key = GROUP_TO_KEY.get(label)
        if key:
            bind(widget, key)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Surbrillance du contrôle survolé
# ---------------------------------------------------------------------------


class _Highlight(QWidget):
    """Cadre lumineux posé sur le contrôle survolé."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._rect = QRect()

    def show_over(self, rect: QRect) -> None:
        self._rect = QRect(rect)
        self.setGeometry(rect.adjusted(-2, -2, 2, 2))
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(theme.ACCENT), 2)
        p.setPen(pen)
        p.setBrush(QColor(76, 154, 255, 26))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 5, 5)
        p.end()


# ---------------------------------------------------------------------------
# Fiche
# ---------------------------------------------------------------------------


class HelpCard(QFrame):
    """Petite fiche flottante."""

    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint)
        self.setObjectName("HelpCard")
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(
            f"#HelpCard {{ background: #1b1c22; border: 1px solid {theme.ACCENT};"
            f" border-radius: 8px; }}"
            "#HelpCard QLabel { background: transparent; border: none; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(6)

        self.title = QLabel()
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self.title.setFont(font)
        self.title.setStyleSheet(f"color: {theme.ACCENT};")
        layout.addWidget(self.title)

        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setFixedWidth(MAX_WIDTH - 28)
        self.body.setStyleSheet(f"color: {theme.TEXT};")
        layout.addWidget(self.body)

        self.shortcut = QLabel()
        self.shortcut.setStyleSheet(
            f"color: {theme.WARN}; font-family: monospace; font-size: 11px;")
        layout.addWidget(self.shortcut)

        self.footer = QLabel("Aide interactive — cliquez ou bougez pour fermer")
        self.footer.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 10px;")
        layout.addWidget(self.footer)

    def set_entry(self, entry: HelpEntry) -> None:
        self.title.setText(entry.title)
        self.body.setText(entry.text)
        self.body.setFixedWidth(MAX_WIDTH - 28)
        self.shortcut.setText(f"Raccourci : {entry.shortcut}" if entry.shortcut else "")
        self.shortcut.setVisible(bool(entry.shortcut))
        self.adjustSize()

    def show_near(self, anchor: QRect) -> None:
        self.adjustSize()
        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        size = self.sizeHint()
        x = anchor.right() + 12
        y = anchor.top()
        if x + size.width() > available.right():
            x = max(available.left() + 4, anchor.left() - size.width() - 12)
        if y + size.height() > available.bottom():
            y = max(available.top() + 4, available.bottom() - size.height() - 4)
        self.move(QPoint(int(x), int(y)))
        self.show()
        self.raise_()


# ---------------------------------------------------------------------------
# Contrôleur
# ---------------------------------------------------------------------------


class HelpController(QObject):
    """Filtre d'événements qui déclenche les fiches d'aide."""

    def __init__(self, window: QWidget, delay_ms: int = 2000):
        super().__init__(window)
        self.window = window
        self.delay_ms = max(300, int(delay_ms))
        self.enabled = False
        self._card = HelpCard()
        self._highlight = _Highlight()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show_current)
        self._current: QWidget | None = None
        self._shown_for: QWidget | None = None
        self._last_entry: HelpEntry | None = None
        QApplication.instance().installEventFilter(self)
        self._enabled_changed = None

    # -- état ---------------------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.hide()
        if self._enabled_changed:
            self._enabled_changed(self.enabled)

    def on_enabled_changed(self, callback) -> None:
        self._enabled_changed = callback

    def hide(self) -> None:
        self._timer.stop()
        self._shown_for = None
        self._current = None
        self._card.hide()
        self._highlight.hide()

    # -- filtrage -----------------------------------------------------------

    def eventFilter(self, obj, event):
        if not self.enabled:
            return False
        etype = event.type()
        if etype in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick,
                     QEvent.Wheel, QEvent.KeyPress):
            if etype == QEvent.KeyPress and event.key() not in (Qt.Key_Escape,):
                return False
            self.hide()
            return False
        if etype in (QEvent.MouseMove, QEvent.Enter, QEvent.HoverMove,
                     QEvent.TabletMove):
            try:
                global_pos = event.globalPosition().toPoint()
            except AttributeError:
                global_pos = QCursor.pos()
            widget = QApplication.widgetAt(global_pos)
            if widget is self._card or widget is self._highlight:
                return False
            if widget is not self._current:
                self._current = widget
                self._shown_for = None
                self._card.hide()
                self._highlight.hide()
                self._timer.stop()
                if widget is not None and self._looks_helpful(widget):
                    self._timer.start(self.delay_ms)
            return False
        if etype == QEvent.Leave and obj is self.window:
            self.hide()
        return False

    @staticmethod
    def _looks_helpful(widget: QWidget) -> bool:
        if widget is None or not widget.isVisible():
            return False
        if widget.window() is widget and widget is not QApplication.activeWindow():
            return False
        return resolve(widget) is not None

    def _show_current(self) -> None:
        if not self.enabled or self._current is None:
            return
        found = resolve(self._current)
        if not found:
            return
        entry, target = found
        if target is None or not target.isVisible():
            return
        self._shown_for = target
        self._last_entry = entry
        rect = QRect(target.mapToGlobal(QPoint(0, 0)), target.size())
        self._highlight.show_over(rect)
        self._card.set_entry(entry)
        self._card.show_near(rect)

    # -- divers -------------------------------------------------------------

    def current_entry(self) -> HelpEntry | None:
        return self._last_entry

    def cleanup(self) -> None:
        self.hide()
        self._card.deleteLater()
        self._highlight.deleteLater()
