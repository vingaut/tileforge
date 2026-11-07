"""Widgets communs : canevas zoomable, vignettes de tuiles, barres de coût."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.image import Image
from . import theme

# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


def to_qimage(img: Image) -> QImage:
    """Image interne → QImage (copie, pour ne pas dépendre du tampon numpy)."""
    arr = np.ascontiguousarray(img.px)
    h, w = arr.shape[:2]
    qimg = QImage(arr.data, w, h, w * 4, QImage.Format_RGBA8888)
    return qimg.copy()


def from_qimage(qimg: QImage) -> Image:
    qimg = qimg.convertToFormat(QImage.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    ptr = qimg.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, qimg.bytesPerLine()))
    arr = arr[:, :w * 4].reshape(h, w, 4).copy()
    return Image(arr)


def fit_to_screen(dialog, width: int, height: int, ratio: float = 0.94):
    """Dimensionne une fenêtre pour qu'elle tienne sur l'écran courant."""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        dialog.resize(width, height)
        return
    available = screen.availableGeometry()
    dialog.resize(min(width, int(available.width() * ratio)),
                  min(height, int(available.height() * ratio)))


def panel_width(preferred: int, minimum: int = 230) -> int:
    """Largeur d'un panneau latéral adaptée à la taille de l'écran."""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return preferred
    width = screen.availableGeometry().width()
    if width < 1000:
        # écran étroit : le panneau garde ~60 % de la largeur, le canevas le reste
        return max(minimum, min(preferred, int(width * 0.62)))
    return preferred


def checker_pixmap(cell: int = 8, c1: str = "#2a2c34", c2: str = "#232430") -> QPixmap:
    pm = QPixmap(cell * 2, cell * 2)
    pm.fill(QColor(c1))
    p = QPainter(pm)
    p.fillRect(0, 0, cell, cell, QColor(c2))
    p.fillRect(cell, cell, cell, cell, QColor(c2))
    p.end()
    return pm


def image_to_pixmap(img: Image, max_size: int | None = None,
                    checker: bool = True, cell: int = 6) -> QPixmap:
    """Image → QPixmap opaque sur damier.

    On compose le damier dans le pixmap plutôt que de compter sur la
    transparence de la fenêtre : certains serveurs graphiques (dont la
    plateforme « offscreen ») rendent les pixmaps sans canal alpha.
    """
    qimg = to_qimage(img)
    pm = QPixmap(qimg.width(), qimg.height())
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    if checker:
        p.fillRect(pm.rect(), QBrush(checker_pixmap(cell)))
    p.drawImage(0, 0, qimg)
    p.end()
    if max_size:
        pm = pm.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.FastTransformation)
    return pm


def tile_icon(sheet, tile_id: int, size: int = 48, scale: int = 1) -> QIcon:
    """Vignette d'une tuile sur damier."""
    img = sheet.tile_image(tile_id)
    if scale > 1:
        img = img.scaled(scale)
    qimg = to_qimage(img)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.fillRect(0, 0, size, size, QBrush(checker_pixmap(6)))
    target = QRectF(0, 0, size, size)
    p.drawImage(target, qimg, QRectF(0, 0, qimg.width(), qimg.height()))
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------------------
# Canevas zoomable
# ---------------------------------------------------------------------------


class Canvas(QGraphicsView):
    """Vue zoomable / déplaçable sur une image, avec fond en damier."""

    zoomChanged = Signal(float)
    cursorMoved = Signal(float, float)      # coordonnées image
    cursorLeft = Signal()

    MIN_ZOOM = 0.02
    MAX_ZOOM = 64.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMouseTracking(True)
        self.setFrameShape(QFrame.NoFrame)
        self._checker = checker_pixmap(8)
        self._content = QRectF(0, 0, 1, 1)
        self._panning = False
        self._pan_start = QPointF()
        self._space = False
        self._auto_fit = True
        self._image_rect = QRectF(0, 0, 1, 1)
        self._needs_fit = False
        self.pan_mode = False          # glisser = déplacer la vue (tactile)
        self._pinch_total = None
        self.grabGesture(Qt.PinchGesture)

    # -- géométrie ----------------------------------------------------------

    def set_content_rect(self, rect: QRectF, auto_fit: bool = False) -> None:
        self._content = QRectF(rect)
        self.setSceneRect(rect.adjusted(-8, -8, 8, 8))
        if auto_fit:
            self._needs_fit = True
            self.fit()

    def image_rect(self) -> QRectF:
        return self._image_rect

    def set_image_rect(self, rect: QRectF) -> None:
        self._image_rect = QRectF(rect)

    def zoom(self) -> float:
        return float(self.transform().m11())

    def set_zoom(self, value: float, anchor: QPointF | None = None) -> None:
        value = max(self.MIN_ZOOM, min(self.MAX_ZOOM, value))
        if anchor is None:
            anchor = QPointF(self.viewport().rect().center())
        old_scene = self.mapToScene(anchor.toPoint())
        self.resetTransform()
        self.scale(value, value)
        new_scene = self.mapToScene(anchor.toPoint())
        delta = new_scene - old_scene
        self.translate(delta.x(), delta.y())
        self.zoomChanged.emit(self.zoom())

    def fit(self) -> None:
        rect = self._content
        if rect.width() <= 0 or rect.height() <= 0:
            return
        vp = self.viewport().rect()
        # un onglet encore masqué n'a pas de taille exploitable : on retentera
        # l'ajustement quand il sera affiché
        if vp.width() < 50 or vp.height() < 50:
            self._needs_fit = True
            return
        sx = vp.width() / (rect.width() + 16)
        sy = vp.height() / (rect.height() + 16)
        z = max(self.MIN_ZOOM, min(self.MAX_ZOOM, min(sx, sy)))
        self.resetTransform()
        self.scale(z, z)
        self.centerOn(rect.center())
        self._needs_fit = False
        self.zoomChanged.emit(self.zoom())

    def showEvent(self, event):
        super().showEvent(event)
        if self._needs_fit:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.fit)

    def fit_1to1(self) -> None:
        self.set_zoom(1.0, QPointF(self.viewport().rect().center()))

    # -- événements ---------------------------------------------------------

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.18 ** (delta / 120.0)
        self.set_zoom(self.zoom() * factor, event.position())
        event.accept()

    def mousePressEvent(self, event):
        if (self.pan_mode and event.button() == Qt.LeftButton) or \
                event.button() == Qt.MiddleButton or \
                (self._space and event.button() == Qt.LeftButton):
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        pos = self.mapToScene(event.position().toPoint())
        self.cursorMoved.emit(pos.x(), pos.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() in (Qt.MiddleButton, Qt.LeftButton):
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # -- gestes (écran tactile) --------------------------------------------

    def event(self, ev):
        if ev.type() == QEvent.Gesture:
            return self._handle_gesture(ev)
        return super().event(ev)

    def _handle_gesture(self, ev) -> bool:
        handled = False
        for gesture in ev.gestures():
            if gesture.gestureType() != Qt.PinchGesture:
                continue
            if gesture.state() == Qt.GestureStarted:
                self._pinch_total = 1.0
            total = max(0.05, gesture.totalScaleFactor())
            if self._pinch_total is None:
                self._pinch_total = 1.0
            factor = total / self._pinch_total
            self._pinch_total = total
            center = gesture.centerPoint()
            self.set_zoom(self.zoom() * factor, QPointF(center))
            if gesture.state() == Qt.GestureFinished:
                self._pinch_total = None
            handled = True
        return handled

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self._space = True
            self.setCursor(Qt.OpenHandCursor)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space:
            self._space = False
            self.unsetCursor()
        super().keyReleaseEvent(event)

    def leaveEvent(self, event):
        self.cursorLeft.emit()
        super().leaveEvent(event)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(theme.BG))
        if self._image_rect.isValid():
            painter.save()
            painter.setBrushOrigin(self._image_rect.topLeft())
            painter.fillRect(self._image_rect, QBrush(self._checker))
            painter.restore()


# ---------------------------------------------------------------------------
# Barres de coût
# ---------------------------------------------------------------------------

COST_LABELS = [
    ("C1_silhouette", "Silhouette", theme.ACCENT),
    ("C2_couleur", "Couleur", "#7f6ce0"),
    ("C3_contour", "Contour", "#4cc38a"),
    ("C4_trou", "Trous", "#e8b339"),
    ("C5_palette", "Palette", "#e08a4c"),
    ("C6_doublon", "Doublons", "#e5534b"),
]


class CostBars(QWidget):
    """Petites barres horizontales pour le détail du coût."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self._rows = {}
        for key, label, color in COST_LABELS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            name = QLabel(label)
            name.setFixedWidth(72)
            name.setProperty("hint", True)
            bar = _MiniBar(color)
            value = QLabel("—")
            value.setFixedWidth(48)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value.setProperty("hint", True)
            row.addWidget(name)
            row.addWidget(bar, 1)
            row.addWidget(value)
            layout.addLayout(row)
            self._rows[key] = (bar, value)
        self.clear()

    def clear(self) -> None:
        for bar, value in self._rows.values():
            bar.set_value(0.0)
            value.setText("—")

    def set_values(self, breakdown: dict | None) -> None:
        if not breakdown:
            self.clear()
            return
        for key, (bar, value) in self._rows.items():
            v = float(breakdown.get(key, 0.0))
            bar.set_value(v)
            value.setText(f"{v:.2f}")


class _MiniBar(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._color = QColor(color)
        self.setFixedHeight(8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(0, 1, 0, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.BORDER))
        p.drawRoundedRect(QRectF(r), 3, 3)
        if self._value > 0:
            w = max(2.0, r.width() * self._value)
            p.setBrush(self._color)
            p.drawRoundedRect(QRectF(r.left(), r.top(), w, r.height()), 3, 3)
        p.end()


# ---------------------------------------------------------------------------
# Divers
# ---------------------------------------------------------------------------


def section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    font = QFont()
    font.setPointSize(8)
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
    lbl.setFont(font)
    lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; padding: 6px 0 2px 0;")
    return lbl


def hint_label(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setProperty("hint", True)
    return lbl


def separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"color: {theme.BORDER}; background: {theme.BORDER}; max-height: 1px;")
    return line


class TilePalette(QListWidget):
    """Liste de vignettes de tuiles, source de glisser-déposer."""

    MIME = "application/x-tileforge-tile"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(44, 44))
        self.setGridSize(QSize(54, 58))
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSpacing(1)
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setUniformItemSizes(True)
        self.setWordWrap(False)
        self._sheet = None

    def set_sheet(self, sheet) -> None:
        self._sheet = sheet

    def populate(self, tile_ids, labels: dict | None = None) -> None:
        self.clear()
        if self._sheet is None:
            return
        for tid in tile_ids:
            item = QListWidgetItem(tile_icon(self._sheet, tid, 44), "")
            item.setData(Qt.UserRole, tid)
            if labels and tid in labels:
                item.setToolTip(labels[tid])
            self.addItem(item)

    def mimeTypes(self):
        return [self.MIME]

    def startDrag(self, actions):
        item = self.currentItem()
        if item is None:
            return
        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QDrag
        mime = QMimeData()
        ids = [i.data(Qt.UserRole) for i in self.selectedItems()]
        mime.setData(self.MIME, ",".join(str(i) for i in ids).encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        icon = item.icon()
        if not icon.isNull():
            drag.setPixmap(icon.pixmap(44, 44))
        drag.exec(Qt.CopyAction)
