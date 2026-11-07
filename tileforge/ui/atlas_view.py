"""Écran « Atlas » : planche finale des sprites validés."""

from __future__ import annotations

import json
import os

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.image import save_image
from ..core.settings import default_dir
from . import theme
from .widgets import Canvas, hint_label, panel_width, section_label, to_qimage


class AtlasCanvas(Canvas):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._qimage = None
        self._entries = []

    def set_atlas(self, image, entries) -> None:
        self._entries = entries
        self._qimage = to_qimage(image) if image is not None else None
        if image is not None:
            rect = QRectF(0, 0, image.w, image.h)
            self.set_image_rect(rect)
            self.set_content_rect(rect, auto_fit=True)
        else:
            self.set_content_rect(QRectF(0, 0, 1, 1))
        self.viewport().update()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        if self._qimage is None:
            return
        painter.setRenderHint(QPainter.SmoothPixmapTransform, self.zoom() < 1.0)
        painter.drawImage(QRectF(0, 0, self._qimage.width(), self._qimage.height()),
                          self._qimage)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        if not self._entries:
            return
        painter.setPen(Qt.NoPen)
        for _name, (x, y, w, h) in self._entries:
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(Qt.lightGray)
            painter.drawRect(QRectF(x, y, w, h))


class AtlasView(QWidget):
    """Onglet « Atlas »."""

    statusMessage = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window_ref = window

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        panel = QWidget()
        panel.setFixedWidth(panel_width(300, 220))
        panel.setStyleSheet(f"background: {theme.PANEL};")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(10, 10, 10, 10)

        pv.addWidget(section_label("Planche de sortie"))
        self.info = hint_label("Aucun sprite validé.")
        pv.addWidget(self.info)

        gb = QGroupBox("Disposition")
        form = QFormLayout(gb)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Automatique (équilibré)", "auto")
        self.mode_combo.addItem("Étagères (tailles variables)", "shelf")
        self.mode_combo.currentIndexChanged.connect(self.recompute)
        form.addRow("Mode", self.mode_combo)
        self.gap_spin = QSpinBox()
        self.gap_spin.setRange(0, 32)
        self.gap_spin.setValue(2)
        self.gap_spin.valueChanged.connect(self.recompute)
        form.addRow("Espacement", self.gap_spin)
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(0, 32)
        self.margin_spin.setValue(2)
        self.margin_spin.valueChanged.connect(self.recompute)
        form.addRow("Marge", self.margin_spin)
        pv.addWidget(gb)

        self.size_label = hint_label("")
        pv.addWidget(self.size_label)

        b1 = QPushButton("Exporter l'atlas (PNG)…")
        b1.clicked.connect(self.export_png)
        pv.addWidget(b1)
        b2 = QPushButton("Exporter les positions (JSON)…")
        b2.clicked.connect(self.export_json)
        pv.addWidget(b2)
        b3 = QPushButton("Exporter en planche de tuiles (PNG)…")
        b3.clicked.connect(self.export_tiles)
        pv.addWidget(b3)
        pv.addStretch(1)

        self.sprites_info = QLabel("")
        self.sprites_info.setWordWrap(True)
        self.sprites_info.setProperty("hint", True)
        pv.addWidget(self.sprites_info)

        root.addWidget(panel)

        self.canvas = AtlasCanvas()
        root.addWidget(self.canvas, 1)

    # -- calcul -------------------------------------------------------------

    def recompute(self) -> None:
        project = self.window_ref.project
        sprites = project.validated_sprites()
        atlas = project.atlas
        atlas.gap = self.gap_spin.value()
        atlas.margin = self.margin_spin.value()
        atlas.mode = self.mode_combo.currentData()
        atlas.compute(sprites)
        if not sprites or project.sheet is None:
            self.canvas.set_atlas(None, [])
            self.info.setText("Aucun sprite validé. Validez un sprite dans l'atelier.")
            self.size_label.setText("")
            self.sprites_info.setText("")
            return
        img = atlas.render({s.id: s for s in sprites}, project.sheet)
        entries = [(e.name, e.rect) for e in atlas.entries]
        self.canvas.set_atlas(img, entries)
        self.info.setText(f"{len(sprites)} sprites")
        self.size_label.setText(f"Atlas : {atlas.width} × {atlas.height} px")
        sizes = sorted({(s.width, s.height) for s in sprites})
        detail = " · ".join(f"{w}×{h}" for w, h in sizes[:4])
        self.sprites_info.setText(f"Tailles : {detail}\n"
                                  f"Surface utile : "
                                  f"{sum(s.width * s.height for s in sprites)} px²")

    def refresh(self) -> None:
        self.recompute()

    # -- exports ------------------------------------------------------------

    def export_png(self) -> None:
        project = self.window_ref.project
        sprites = project.validated_sprites()
        if not sprites:
            QMessageBox.information(self, "Atlas", "Aucun sprite à exporter.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exporter l'atlas",
                                              os.path.join(default_dir("graphisme"), "atlas.png"),
                                              "PNG (*.png)")
        if not path:
            return
        img = project.atlas.render({s.id: s for s in sprites}, project.sheet)
        save_image(path, img)
        self.statusMessage.emit(f"Atlas exporté : {path}")

    def export_json(self) -> None:
        project = self.window_ref.project
        path, _ = QFileDialog.getSaveFileName(self, "Exporter les positions",
                                              os.path.join(default_dir("graphisme"), "atlas.json"),
                                              "JSON (*.json)")
        if not path:
            return
        data = project.atlas.as_dict()
        data["sprites"] = [{"id": s.id, "name": s.name, "cols": s.cols,
                            "rows": s.rows, "cost": s.cost} for s in project.validated_sprites()]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        self.statusMessage.emit(f"Positions exportées : {path}")

    def export_tiles(self) -> None:
        """Exporte la planche source telle quelle (utile pour la retravailler ailleurs)."""
        project = self.window_ref.project
        if project.sheet is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exporter la planche",
                                              os.path.join(default_dir("graphisme"), "planche.png"),
                                              "PNG (*.png)")
        if path:
            save_image(path, project.sheet.image)
            self.statusMessage.emit(f"Planche exportée : {path}")
