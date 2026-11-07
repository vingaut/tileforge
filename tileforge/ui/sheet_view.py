"""Écran « Planche » : chargement, analyse de résolution et découpage en tuiles."""

from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..core import detectres
from ..core.formats import FORMATS_BY_KEY, load_raw_bank
from ..core.model import Sheet
from ..core.settings import default_dir
from ..core.systems import SYSTEMS_BY_KEY
from ..detect.base import all_detectors, detector_by_key, quality_report
from ..games import generic
from ..games.atari_st import load_barbarian
from . import theme
from .dialogs import PaletteEditorDialog, RawBankDialog, SystemPickerDialog
from .widgets import Canvas, hint_label, panel_width, section_label, to_qimage

HANDLE = 7.0


# ---------------------------------------------------------------------------
# Canevas de la planche
# ---------------------------------------------------------------------------


class SheetCanvas(Canvas):
    """Vue de la planche avec édition directe des rectangles de tuiles."""

    tilesChanged = Signal()
    selectionChanged = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sheet: Sheet | None = None
        self._qimage = None
        self.selection: set[int] = set()
        self.hovered: int | None = None
        self.mode = "select"          # "select" | "create"
        self.snap = True
        self.snap_step = (24, 21)
        self.show_grid = False
        self._drag = None             # dict
        self._rubber = None
        self._preview_rect = None
        self._history = None
        self._on_edit = None
        self.setMouseTracking(True)

    # -- données ------------------------------------------------------------

    def set_sheet(self, sheet: Sheet | None) -> None:
        self.sheet = sheet
        self.selection.clear()
        self._qimage = to_qimage(sheet.image) if sheet is not None else None
        if sheet is not None:
            rect = QRectF(0, 0, sheet.image.w, sheet.image.h)
            self.set_image_rect(rect)
            self.set_content_rect(rect, auto_fit=True)
        self.selectionChanged.emit([])
        self.viewport().update()

    def refresh(self) -> None:
        if self.sheet is not None:
            self._qimage = to_qimage(self.sheet.image)
        self.viewport().update()

    def set_edit_callbacks(self, begin, end) -> None:
        self._on_edit = (begin, end)

    def set_selection(self, ids) -> None:
        self.selection = set(ids)
        self.selectionChanged.emit(sorted(self.selection))
        self.viewport().update()

    # -- géométrie ----------------------------------------------------------

    def _snap_value(self, v: float, step: int) -> float:
        if not self.snap or step <= 0:
            return v
        return round(v / step) * step

    def _hit_handle(self, pos: QPointF) -> int | None:
        if len(self.selection) != 1 or self.sheet is None:
            return None
        t = self.sheet.tile(next(iter(self.selection)))
        if t is None:
            return None
        hs = HANDLE / max(0.05, self.zoom())
        r = QRectF(t.x, t.y, t.w, t.h)
        points = [(r.left(), r.top()), (r.center().x(), r.top()), (r.right(), r.top()),
                  (r.right(), r.center().y()), (r.right(), r.bottom()),
                  (r.center().x(), r.bottom()), (r.left(), r.bottom()),
                  (r.left(), r.center().y())]
        for i, (px, py) in enumerate(points):
            if abs(pos.x() - px) <= hs and abs(pos.y() - py) <= hs:
                return i
        return None

    def _hit_tile(self, pos: QPointF) -> int | None:
        if self.sheet is None:
            return None
        for t in reversed(self.sheet.tiles):
            if t.contains(pos.x(), pos.y()):
                return t.id
        return None

    # -- souris -------------------------------------------------------------

    def mousePressEvent(self, event):
        if self.pan_mode and event.button() == Qt.LeftButton:
            super().mousePressEvent(event)
            return
        if self._panning:
            super().mousePressEvent(event)
            return
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        pos = self.mapToScene(event.position().toPoint())
        self.setFocus()

        if self.mode == "create":
            x = self._snap_value(pos.x(), self.snap_step[0])
            y = self._snap_value(pos.y(), self.snap_step[1])
            self._drag = {"kind": "create", "x0": x, "y0": y, "rect": QRectF(x, y, 1, 1)}
            self.viewport().update()
            return

        handle = self._hit_handle(pos)
        if handle is not None:
            t = self.sheet.tile(next(iter(self.selection)))
            self._begin_edit()
            self._drag = {"kind": "resize", "handle": handle, "tile": t.id,
                          "start": pos, "rect": QRectF(t.rect)}
            return

        tile_id = self._hit_tile(pos)
        mods = event.modifiers()
        if tile_id is None:
            if not (mods & (Qt.ControlModifier | Qt.ShiftModifier)):
                self.set_selection([])
            self._rubber = {"start": pos, "end": pos, "base": set(self.selection)}
            self.viewport().update()
            return

        if mods & Qt.ControlModifier:
            sel = set(self.selection)
            sel.symmetric_difference_update({tile_id})
            self.set_selection(sel)
            return
        if tile_id not in self.selection:
            self.set_selection([tile_id])
        self._begin_edit()
        self._drag = {"kind": "move", "start": pos, "tiles": list(self.selection),
                      "orig": {tid: self.sheet.tile(tid).rect for tid in self.selection
                               if self.sheet.tile(tid) is not None}}
        self.viewport().update()

    def mouseMoveEvent(self, event):
        pos = self.mapToScene(event.position().toPoint())
        if self._panning:
            super().mouseMoveEvent(event)
            return
        if self._drag:
            kind = self._drag["kind"]
            if kind == "move":
                dx = pos.x() - self._drag["start"].x()
                dy = pos.y() - self._drag["start"].y()
                for tid, rect in self._drag["orig"].items():
                    t = self.sheet.tile(tid)
                    if t is None or t.locked:
                        continue
                    nx = self._snap_value(rect[0] + dx, self.snap_step[0])
                    ny = self._snap_value(rect[1] + dy, self.snap_step[1])
                    t.rect = (int(nx), int(ny), rect[2], rect[3])
                self.sheet.invalidate()
                self.viewport().update()
            elif kind == "resize":
                self._do_resize(pos)
            elif kind == "create":
                x1 = self._snap_value(pos.x(), self.snap_step[0])
                y1 = self._snap_value(pos.y(), self.snap_step[1])
                self._drag["rect"] = QRectF(QPointF(min(x1, self._drag["x0"]),
                                                    min(y1, self._drag["y0"])),
                                            QPointF(max(x1, self._drag["x0"]),
                                                    max(y1, self._drag["y0"]))).normalized()
                self.viewport().update()
            event.accept()
            return
        if self._rubber is not None:
            self._rubber["end"] = pos
            self.viewport().update()
            return

        hover = self._hit_tile(pos)
        if hover != self.hovered:
            self.hovered = hover
            self.viewport().update()
        if self._hit_handle(pos) is not None:
            self.setCursor(Qt.SizeAllCursor)
        elif hover is not None:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning:
            super().mouseReleaseEvent(event)
            return
        if self._rubber is not None:
            r = QRectF(self._rubber["start"], self._rubber["end"]).normalized()
            base = set(self._rubber["base"])
            for t in self.sheet.tiles:
                if r.intersects(QRectF(t.x, t.y, t.w, t.h)):
                    base.add(t.id)
            self._rubber = None
            self.set_selection(base)
            return
        if self._drag:
            kind = self._drag["kind"]
            if kind == "create":
                rect = self._drag["rect"].toRect()
                if rect.width() >= 1 and rect.height() >= 1:
                    self._end_edit()
                    tid = self.sheet.add_tile((rect.x(), rect.y(), rect.width(), rect.height()))
                    self.set_selection([tid])
                    self.tilesChanged.emit()
            else:
                self._end_edit()
                self.tilesChanged.emit()
            self._drag = None
            self.viewport().update()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        pos = self.mapToScene(event.position().toPoint())
        tid = self._hit_tile(pos)
        if tid is not None:
            self.set_selection([tid])
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.selection:
            self._begin_edit()
            self.sheet.remove_tiles(self.selection)
            self.set_selection([])
            self._end_edit()
            self.tilesChanged.emit()
            return
        if event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down) and self.selection:
            step = 1
            if event.modifiers() & Qt.ShiftModifier:
                step = self.snap_step[0] if event.key() in (Qt.Key_Left, Qt.Key_Right) else self.snap_step[1]
            dx = -step if event.key() == Qt.Key_Left else step if event.key() == Qt.Key_Right else 0
            dy = -step if event.key() == Qt.Key_Up else step if event.key() == Qt.Key_Down else 0
            self._begin_edit()
            for tid in self.selection:
                t = self.sheet.tile(tid)
                if t is not None:
                    t.rect = (t.x + dx, t.y + dy, t.w, t.h)
            self.sheet.invalidate()
            self.viewport().update()
            self.tilesChanged.emit()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        pos = self.mapToScene(event.pos())
        tid = self._hit_tile(pos)
        menu = QMenu(self)
        if tid is not None and tid not in self.selection:
            self.set_selection([tid])
        if self.selection:
            act_del = menu.addAction("Supprimer")
            act_dup = menu.addAction("Dupliquer")
            menu.addSeparator()
            act_merge = menu.addAction("Fusionner la sélection")
            act_split = menu.addAction("Scinder verticalement")
            act_split_h = menu.addAction("Scinder horizontalement")
            chosen = menu.exec(event.globalPos())
            if chosen == act_del:
                self._begin_edit()
                self.sheet.remove_tiles(self.selection)
                self.set_selection([])
                self._end_edit()
                self.tilesChanged.emit()
            elif chosen == act_dup:
                self._begin_edit()
                new_ids = []
                for tid in sorted(self.selection):
                    t = self.sheet.tile(tid)
                    if t:
                        nt = self.sheet.add_tile((t.x + t.w, t.y, t.w, t.h))
                        new_ids.append(nt.id)
                self.set_selection(new_ids)
                self._end_edit()
                self.tilesChanged.emit()
            elif chosen == act_merge:
                self._merge_selection()
            elif chosen in (act_split, act_split_h):
                self._split_selection(chosen == act_split)
            return
        menu.addAction("Ajouter une tuile ici").triggered.connect(lambda: self._add_at(pos))
        menu.exec(event.globalPos())

    # -- opérations ---------------------------------------------------------

    def _add_at(self, pos: QPointF) -> None:
        w, h = self.snap_step
        x = self._snap_value(pos.x(), w)
        y = self._snap_value(pos.y(), h)
        self._begin_edit()
        tid = self.sheet.add_tile((int(x), int(y), w, h))
        self.set_selection([tid])
        self._end_edit()
        self.tilesChanged.emit()

    def _merge_selection(self) -> None:
        if len(self.selection) < 2:
            return
        self._begin_edit()
        rects = [self.sheet.tile(t).rect for t in self.selection if self.sheet.tile(t)]
        x0 = min(r[0] for r in rects)
        y0 = min(r[1] for r in rects)
        x1 = max(r[0] + r[2] for r in rects)
        y1 = max(r[1] + r[3] for r in rects)
        self.sheet.remove_tiles(self.selection)
        tid = self.sheet.add_tile((x0, y0, x1 - x0, y1 - y0))
        self.set_selection([tid])
        self._end_edit()
        self.tilesChanged.emit()

    def _split_selection(self, vertical: bool) -> None:
        if len(self.selection) != 1:
            return
        t = self.sheet.tile(next(iter(self.selection)))
        if t is None:
            return
        self._begin_edit()
        if vertical:
            w1 = t.w // 2
            r1 = (t.x, t.y, w1, t.h)
            r2 = (t.x + w1, t.y, t.w - w1, t.h)
        else:
            h1 = t.h // 2
            r1 = (t.x, t.y, t.w, h1)
            r2 = (t.x, t.y + h1, t.w, t.h - h1)
        if r1[2] < 1 or r1[3] < 1 or r2[2] < 1 or r2[3] < 1:
            return
        self.sheet.remove_tiles([t.id])
        a = self.sheet.add_tile(r1)
        b = self.sheet.add_tile(r2)
        self.set_selection([a.id, b.id])
        self._end_edit()
        self.tilesChanged.emit()

    def _do_resize(self, pos: QPointF) -> None:
        t = self.sheet.tile(self._drag["tile"])
        if t is None:
            return
        r = self._drag["rect"]
        x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
        h = self._drag["handle"]
        px = self._snap_value(pos.x(), self.snap_step[0])
        py = self._snap_value(pos.y(), self.snap_step[1])
        if h in (0, 6, 7):
            x0 = min(px, x1 - 1)
        if h in (2, 3, 4):
            x1 = max(px, x0 + 1)
        if h in (0, 1, 2):
            y0 = min(py, y1 - 1)
        if h in (4, 5, 6):
            y1 = max(py, y0 + 1)
        t.rect = (int(x0), int(y0), int(x1 - x0), int(y1 - y0))
        self.sheet.invalidate()
        self.viewport().update()

    def _begin_edit(self) -> None:
        if self._on_edit:
            self._on_edit[0]()

    def _end_edit(self) -> None:
        if self._on_edit:
            self._on_edit[1]()

    # -- dessin -------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        if self._qimage is None:
            return
        painter.setRenderHint(QPainter.SmoothPixmapTransform, self.zoom() < 1.0)
        target = QRectF(0, 0, self._qimage.width(), self._qimage.height())
        painter.drawImage(target, self._qimage)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        if self.sheet is None:
            return
        z = self.zoom()
        painter.setRenderHint(QPainter.Antialiasing, False)

        if self.show_grid and z > 1.5:
            step = self.snap_step
            pen = QPen(QColor(theme.GRID))
            pen.setWidthF(0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            w, h = self.sheet.image.w, self.sheet.image.h
            for x in range(0, w, max(1, step[0])):
                painter.drawLine(QPointF(x, 0), QPointF(x, h))
            for y in range(0, h, max(1, step[1])):
                painter.drawLine(QPointF(0, y), QPointF(w, y))

        font = QFont()
        font.setPixelSize(max(6, int(min(11, 9 / max(z, 0.2)))))
        painter.setFont(font)

        for t in self.sheet.tiles:
            r = QRectF(t.x + 0.5, t.y + 0.5, t.w, t.h)
            selected = t.id in self.selection
            hovered = t.id == self.hovered
            if selected:
                pen = QPen(QColor(theme.ACCENT), 2.0 / z)
            elif hovered:
                pen = QPen(QColor("#9bb8e0"), 1.5 / z)
            else:
                pen = QPen(QColor(90, 200, 255, 140), 1.0 / z)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(r)
            if z > 0.55:
                label = t.label or str(t.id)
                painter.setPen(QColor(255, 255, 255, 190))
                painter.drawText(r.adjusted(2, 1, 0, 0), Qt.AlignLeft | Qt.AlignTop, label)

        if len(self.selection) == 1:
            t = self.sheet.tile(next(iter(self.selection)))
            if t is not None:
                self._draw_handles(painter, QRectF(t.x, t.y, t.w, t.h), z)

        if self._drag and self._drag.get("kind") == "create":
            r = self._drag["rect"]
            painter.setPen(QPen(QColor(theme.ACCENT), 0))
            painter.setBrush(QColor(76, 154, 255, 60))
            painter.drawRect(r)

        if self._rubber is not None:
            r = QRectF(self._rubber["start"], self._rubber["end"]).normalized()
            painter.setPen(QPen(QColor(theme.ACCENT), 0))
            painter.setBrush(QColor(76, 154, 255, 40))
            painter.drawRect(r)

    def _draw_handles(self, painter: QPainter, r: QRectF, z: float) -> None:
        hs = HANDLE / max(0.05, z)
        pts = [(r.left(), r.top()), (r.center().x(), r.top()), (r.right(), r.top()),
               (r.right(), r.center().y()), (r.right(), r.bottom()),
               (r.center().x(), r.bottom()), (r.left(), r.bottom()),
               (r.left(), r.center().y())]
        painter.setBrush(QColor(theme.ACCENT))
        painter.setPen(QPen(QColor("#0d0e12"), 0))
        for (x, y) in pts:
            painter.drawRect(QRectF(x - hs / 2, y - hs / 2, hs, hs))


# ---------------------------------------------------------------------------
# Écran Planche
# ---------------------------------------------------------------------------


class SheetView(QWidget):
    """Onglet « Planche »."""

    projectChanged = Signal()
    statusMessage = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window_ref = window
        self._param_widgets: dict[str, QWidget] = {}
        self._last_report = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- panneau gauche
        self.panel = QWidget()
        self.panel.setFixedWidth(panel_width(330))
        self.panel.setStyleSheet(f"background: {theme.PANEL};")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.form = QVBoxLayout(inner)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(8)
        scroll.setWidget(inner)
        panel_layout.addWidget(scroll, 1)

        self._build_source_group()
        self._build_resolution_group()
        self._build_detect_group()
        self._build_quality_group()
        self.form.addStretch(1)
        root.addWidget(self.panel)

        # -- centre
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(self.toolbar.iconSize())
        self._build_toolbar()
        cl.addWidget(self.toolbar)
        self.canvas = SheetCanvas()
        self.canvas.tilesChanged.connect(self._on_tiles_changed)
        self.canvas.selectionChanged.connect(self._on_selection_changed)
        self.canvas.zoomChanged.connect(lambda z: self.zoom_label.setText(f"{z * 100:.0f} %"))
        self.canvas.cursorMoved.connect(self._on_cursor)
        cl.addWidget(self.canvas, 1)
        root.addWidget(center, 1)

        self.canvas.set_edit_callbacks(self._begin_undo, self._end_undo)

    # -- construction de l'interface ---------------------------------------

    def _build_source_group(self) -> None:
        self.form.addWidget(section_label("Source"))
        self.source_label = hint_label("Aucune planche chargée.")
        self.form.addWidget(self.source_label)

        btn_rom = QPushButton("Ouvrir une ROM / archive…")
        btn_rom.setProperty("accent", True)
        btn_rom.setToolTip(
            "Ouvre une ROM, une archive zip/7z, ou une banque brute : "
            "choisissez ensuite l'offset, le format et la compression.")
        btn_rom.clicked.connect(self.open_raw)
        self.form.addWidget(btn_rom)
        self.form.addWidget(hint_label(
            "ROM, archive zip/7z, PNG ou disquette ST : choisissez le fichier, "
            "puis l'offset et le format."))

        row = QHBoxLayout()
        btn_png = QPushButton("Image PNG…")
        btn_png.clicked.connect(self.open_png)
        btn_raw = QPushButton("Banque brute (offset)…")
        btn_raw.setToolTip("Même dialogue que ci-dessus, pour régler l'offset à la main.")
        btn_raw.clicked.connect(self.open_raw)
        row.addWidget(btn_png)
        row.addWidget(btn_raw)
        self.form.addLayout(row)

        btn_profile = QPushButton("Profil de jeu…")
        btn_profile.setToolTip("Rejouer les réglages d'un jeu déjà identifié")
        btn_profile.clicked.connect(self.open_profiles)
        self.form.addWidget(btn_profile)

        btn_barb = QPushButton("Barbarian ST (disquette .stx)")
        btn_barb.setProperty("accent", True)
        btn_barb.clicked.connect(self.open_barbarian)
        self.form.addWidget(btn_barb)

        row2 = QHBoxLayout()
        self.palette_btn = QPushButton("Palette…")
        self.palette_btn.clicked.connect(self.edit_palette)
        self.palette_btn.setEnabled(False)
        row2.addWidget(self.palette_btn)
        self.transparent_btn = QPushButton("Fond transparent")
        self.transparent_btn.clicked.connect(self.make_background_transparent)
        row2.addWidget(self.transparent_btn)
        self.form.addLayout(row2)

    def _build_resolution_group(self) -> None:
        self.form.addWidget(section_label("Résolution"))
        self.res_label = hint_label("Chargez une planche puis lancez l'analyse.")
        self.form.addWidget(self.res_label)

        row = QHBoxLayout()
        self.analyse_btn = QPushButton("Analyser")
        self.analyse_btn.clicked.connect(self.analyse_resolution)
        self.system_btn = QPushButton("Machines…")
        self.system_btn.clicked.connect(self.choose_system)
        row.addWidget(self.analyse_btn)
        row.addWidget(self.system_btn)
        self.form.addLayout(row)

        self.system_combo = QComboBox()
        self.system_combo.addItem("— machine détectée —", "")
        self.system_combo.currentIndexChanged.connect(self._on_system_combo)
        self.form.addWidget(self.system_combo)

        self.apply_system_btn = QPushButton("Appliquer la machine (tuile + palette)")
        self.apply_system_btn.clicked.connect(self.apply_system)
        self.form.addWidget(self.apply_system_btn)

    def _build_detect_group(self) -> None:
        self.form.addWidget(section_label("Détection des tuiles"))
        self.detector_combo = QComboBox()
        for d in all_detectors():
            self.detector_combo.addItem(d.name, d.key)
        self.detector_combo.setToolTip("Algorithme de découpage")
        self.detector_combo.currentIndexChanged.connect(self._rebuild_params)
        self.form.addWidget(self.detector_combo)

        self.detector_help = hint_label("")
        self.form.addWidget(self.detector_help)

        self.params_box = QGroupBox("Paramètres")
        self.params_form = QFormLayout(self.params_box)
        self.params_form.setLabelAlignment(Qt.AlignRight)
        self.params_form.setContentsMargins(8, 12, 8, 8)
        self.form.addWidget(self.params_box)

        row = QHBoxLayout()
        self.detect_btn = QPushButton("Détecter")
        self.detect_btn.setProperty("accent", True)
        self.detect_btn.clicked.connect(self.run_detection)
        self.detect_all_btn = QPushButton("Comparer les méthodes")
        self.detect_all_btn.clicked.connect(self.compare_detectors)
        row.addWidget(self.detect_btn)
        row.addWidget(self.detect_all_btn)
        self.form.addLayout(row)

        row2 = QHBoxLayout()
        self.replace_check = QCheckBox("Remplacer les tuiles")
        self.replace_check.setChecked(True)
        row2.addWidget(self.replace_check)
        self.form.addLayout(row2)

        self.detect_info = hint_label("")
        self.form.addWidget(self.detect_info)

        self._rebuild_params()

    def _build_quality_group(self) -> None:
        self.form.addWidget(section_label("Contrôle qualité"))
        self.quality_list = QListWidget()
        self.quality_list.setMaximumHeight(140)
        self.quality_list.setAlternatingRowColors(True)
        self.quality_list.itemClicked.connect(self._on_issue_clicked)
        self.form.addWidget(self.quality_list)
        btn = QPushButton("Vérifier")
        btn.clicked.connect(self.check_quality)
        self.form.addWidget(btn)

    def _build_toolbar(self) -> None:
        self.tb = self.toolbar
        self.act_select = QAction("Sélection", self)
        self.act_select.setCheckable(True)
        self.act_select.setChecked(True)
        self.act_select.setShortcut("V")
        self.act_create = QAction("Nouvelle tuile", self)
        self.act_create.setCheckable(True)
        self.act_create.setShortcut("R")
        self.act_pan = QAction("Déplacer la vue", self)
        self.act_pan.setCheckable(True)
        self.act_pan.setShortcut("H")
        group = QActionGroup(self)
        group.setExclusive(True)
        for a in (self.act_select, self.act_create, self.act_pan):
            self.tb.addAction(a)
            group.addAction(a)
        self.act_select.triggered.connect(lambda: self._set_mode("select"))
        self.act_create.triggered.connect(lambda: self._set_mode("create"))
        self.act_pan.triggered.connect(lambda: self._set_mode("pan"))

        self.act_panel = QAction("Panneau", self)
        self.act_panel.setCheckable(True)
        self.act_panel.setChecked(True)
        self.act_panel.toggled.connect(self.toggle_panel)
        self.tb.addSeparator()
        self.tb.addAction(self.act_panel)

        self.tb.addSeparator()
        self.act_snap = QAction("Aimant", self)
        self.act_snap.setCheckable(True)
        self.act_snap.setChecked(True)
        self.act_snap.setShortcut("G")
        self.act_snap.toggled.connect(self._toggle_snap)
        self.tb.addAction(self.act_snap)

        self.act_grid = QAction("Grille", self)
        self.act_grid.setCheckable(True)
        self.act_grid.toggled.connect(self._toggle_grid)
        self.tb.addAction(self.act_grid)

        self.tb.addSeparator()
        self.act_fit = QAction("Ajuster", self)
        self.act_fit.setShortcut("0")
        self.act_fit.triggered.connect(lambda: self.canvas.fit())
        self.tb.addAction(self.act_fit)
        act_100 = QAction("100 %", self)
        act_100.setShortcut("1")
        act_100.triggered.connect(lambda: self.canvas.fit_1to1())
        self.tb.addAction(act_100)

        self.tb.addSeparator()
        self.tb.addWidget(QLabel("  "))
        self.sel_label = QLabel("aucune tuile sélectionnée")
        self.sel_label.setProperty("hint", True)
        self.tb.addWidget(self.sel_label)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.tb.addWidget(spacer)
        self.zoom_label = QLabel("100 %")
        self.zoom_label.setProperty("hint", True)
        self.tb.addWidget(self.zoom_label)
        self.tb.addWidget(QLabel("  "))

    # -- paramètres de détection -------------------------------------------

    def _rebuild_params(self) -> None:
        while self.params_form.rowCount():
            self.params_form.removeRow(0)
        self._param_widgets = {}
        key = self.detector_combo.currentData()
        det = detector_by_key(key)
        if det is None:
            return
        self.detector_help.setText(det.description)
        if not det.params:
            self.params_form.addRow(QLabel("Aucun paramètre."))
            return
        for spec in det.params:
            widget = self._make_param_widget(spec)
            self._param_widgets[spec.key] = widget
            self.params_form.addRow(spec.label, widget)
        self._sync_detect_defaults()

    def _make_param_widget(self, spec):
        if spec.kind == "int":
            w = QSpinBox()
            w.setRange(spec.minimum, spec.maximum)
            w.setValue(int(spec.default))
            w.setSingleStep(max(1, spec.step))
        elif spec.kind == "float":
            w = QDoubleSpinBox()
            w.setRange(spec.minimum, spec.maximum)
            w.setValue(float(spec.default))
            w.setSingleStep(spec.step)
        elif spec.kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(spec.default))
        else:
            w = QComboBox()
            for value, label in spec.choices:
                w.addItem(label, value)
            idx = w.findData(spec.default)
            if idx >= 0:
                w.setCurrentIndex(idx)
        if spec.help:
            w.setToolTip(spec.help)
        return w

    def _param_values(self) -> dict:
        out = {}
        key = self.detector_combo.currentData()
        det = detector_by_key(key)
        if det is None:
            return out
        for spec in det.params:
            w = self._param_widgets.get(spec.key)
            if w is None:
                continue
            if isinstance(w, (QSpinBox, QDoubleSpinBox)):
                out[spec.key] = w.value()
            elif isinstance(w, QCheckBox):
                out[spec.key] = w.isChecked()
            elif isinstance(w, QComboBox):
                out[spec.key] = w.currentData()
        return out

    def _set_param(self, key: str, value) -> None:
        w = self._param_widgets.get(key)
        if w is None:
            return
        if isinstance(w, QSpinBox):
            w.setValue(int(value))
        elif isinstance(w, QCheckBox):
            w.setChecked(bool(value))
        elif isinstance(w, QComboBox):
            idx = w.findData(value)
            if idx >= 0:
                w.setCurrentIndex(idx)

    def _sync_detect_defaults(self) -> None:
        """Pré-remplit les paramètres avec la planche courante."""
        sheet = self.window_ref.project.sheet
        if sheet is None:
            return
        tw, th = sheet.dominant_tile_size()
        info = sheet.info or {}
        key = self.detector_combo.currentData()
        if key == "grid":
            self._set_param("tile_w", tw)
            self._set_param("tile_h", th)
            self._set_param("gap_x", info.get("gap", 0))
            self._set_param("gap_y", info.get("gap", 0))
            self._set_param("count", info.get("count", 0) or 0)
            self._set_param("cols", 0)
            self._set_param("rows", 0)
        elif key == "period":
            self._set_param("tile_w", tw)
            self._set_param("tile_h", th)
        self.canvas.snap_step = (max(1, tw), max(1, th))

    # -- actions de fichier -------------------------------------------------

    def _require_project(self):
        return self.window_ref.project

    def open_png(self) -> None:
        start = default_dir("graphisme")
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir une planche", start,
                                              "Images (*.png *.gif *.bmp);;Tous (*)")
        if not path:
            return
        try:
            sheet = generic.load_png_sheet(path)
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Lecture impossible : {exc}")
            return
        self._set_sheet(sheet, analyse=True)

    def open_raw(self) -> None:
        dlg = RawBankDialog(self, path="")
        if dlg.exec() != QDialog.Accepted:
            return
        cfg = dlg.result_config()
        if not cfg:
            return
        try:
            data = None
            offset = cfg["offset"]
            if cfg.get("compression"):
                from ..core.compression import decompress
                with open(cfg["path"], "rb") as f:
                    raw = f.read()
                data = decompress(cfg["compression"], raw, cfg["offset"])
                offset = 0
            bank = load_raw_bank(cfg["path"], offset, cfg["count"],
                                 cfg["format"], per_row=cfg["per_row"], gap=1,
                                 palette=cfg["palette"], data=data)
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Décodage impossible : {exc}")
            return
        sheet = generic.sheet_from_bank(bank, cfg["path"])
        if cfg["system"]:
            sheet.info["system"] = cfg["system"]
        if cfg.get("compression"):
            sheet.info["compression"] = cfg["compression"]
            sheet.info["compression_offset"] = cfg["compression_offset"]
        self._set_sheet(sheet, analyse=True)

    # -- profils de jeu -----------------------------------------------------

    def open_profiles(self) -> None:
        from .dialogs import ProfileDialog
        dlg = ProfileDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.selected is not None:
            self.apply_profile(dlg.selected)

    def _locate_rom(self, profile) -> str:
        from ..core.profiles import guess_rom_for
        folders = []
        if self.window_ref.project.path:
            folders.append(os.path.dirname(self.window_ref.project.path))
        folders += [default_dir(""), os.getcwd(), os.path.expanduser("~")]
        path = guess_rom_for(profile, [f for f in folders if f])
        if path:
            return path
        if not profile.rom_name:
            return ""
        path, _ = QFileDialog.getOpenFileName(
            self, f"Fichier de {profile.name}", default_dir(""), "Tous les fichiers (*)")
        return path

    def apply_profile(self, profile) -> None:
        """Charge une banque en rejouant les réglages d'un profil."""
        path = self._locate_rom(profile)
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            offset = profile.offset
            if profile.compression:
                from ..core.compression import decompress
                data = decompress(profile.compression, data, offset)
                offset = 0
            palette = None
            if profile.palette_enabled:
                from ..core.palettes import read_rom_palette
                palette = read_rom_palette(data, profile.palette_offset,
                                           profile.palette_count, profile.palette_kind)
            fmt = FORMATS_BY_KEY.get(profile.tile_format)
            if fmt is None:
                raise ValueError(f"format inconnu : {profile.tile_format}")
            bank = load_raw_bank(None, offset, profile.count or 0, fmt,
                                 per_row=profile.per_row, gap=1, palette=palette,
                                 data=data)
            sheet = generic.sheet_from_bank(bank, path)
            sheet.info.update({"profile": profile.key,
                               "compression": profile.compression})
            self._set_sheet(sheet, analyse=True)
            project = self.window_ref.project
            project.grid.cols, project.grid.rows = profile.grid
            project.current.cols, project.current.rows = profile.grid
            project.current.tile_w = fmt.tile_w
            project.current.tile_h = fmt.tile_h
            self.window_ref.assembly.refresh()
            self.statusMessage.emit(
                f"Profil « {profile.name} » : {bank.count} tuiles de "
                f"{fmt.tile_w}×{fmt.tile_h}")
        except Exception as exc:
            QMessageBox.critical(self, "Profil", f"Chargement impossible : {exc}")

    def open_path_direct(self, path: str) -> None:
        """Ouvre un fichier en devinant son type (utilisé en ligne de commande)."""
        ext = os.path.splitext(path)[1].lower()
        if ext in (".png", ".gif", ".bmp"):
            try:
                self._set_sheet(generic.load_png_sheet(path), analyse=True)
            except Exception as exc:
                QMessageBox.critical(self, "Erreur", f"Lecture impossible : {exc}")
            return
        if ext in (".stx", ".st"):
            try:
                self._set_sheet(load_barbarian(path, 1), analyse=True)
                return
            except Exception:
                pass
        dlg = RawBankDialog(self, path=path)
        if dlg.exec() == QDialog.Accepted:
            cfg = dlg.result_config()
            if cfg:
                data = None
                offset = cfg["offset"]
                if cfg.get("compression"):
                    from ..core.compression import decompress
                    with open(cfg["path"], "rb") as f:
                        data = decompress(cfg["compression"], f.read(), cfg["offset"])
                    offset = 0
                bank = load_raw_bank(cfg["path"], offset, cfg["count"],
                                     cfg["format"], per_row=cfg["per_row"], gap=1,
                                     palette=cfg["palette"], data=data)
                self._set_sheet(generic.sheet_from_bank(bank, cfg["path"]), analyse=True)

    def open_barbarian(self) -> None:
        start = default_dir("")
        path, _ = QFileDialog.getOpenFileName(
            self, "Disquette ou BARB.DAT", start,
            "Disquettes et données (*.stx *.st *.dat);;Tous (*)")
        if not path:
            return
        from PySide6.QtWidgets import QInputDialog
        bank, ok = QInputDialog.getItem(self, "Banque", "Quelle banque de sprites ?",
                                        ["Banque 1 — personnages", "Banque 2"], 0, False)
        if not ok:
            return
        try:
            sheet = load_barbarian(path, 1 if bank.startswith("Banque 1") else 2)
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Extraction impossible : {exc}")
            return
        self._set_sheet(sheet, analyse=True)

    def _set_sheet(self, sheet: Sheet, analyse: bool = False) -> None:
        project = self.window_ref.project
        project.sheet = sheet
        project.game = sheet.info.get("game", "")
        project.dirty = True
        tw, th = sheet.dominant_tile_size()
        project.grid.tile_w, project.grid.tile_h = tw, th
        self.canvas.set_sheet(sheet)
        self.canvas.snap_step = (tw, th)
        self.palette_btn.setEnabled(bool(sheet.image.palette))
        self.source_label.setText(generic.describe_source(sheet))
        self._sync_detect_defaults()
        self.check_quality()
        if analyse:
            self.analyse_resolution()
        self.projectChanged.emit()
        self.window_ref.refresh_all()

    # -- résolution ---------------------------------------------------------

    def analyse_resolution(self) -> None:
        sheet = self.window_ref.project.sheet
        if sheet is None:
            return
        if sheet.kind == "raw":
            self._analyse_raw_bank(sheet)
            return
        rep = detectres.analyse(sheet.image, sheet.dominant_tile_size())
        self._last_report = rep
        lines = rep.summary_lines()
        self.res_label.setText("<br>".join(lines[:6]))
        self.window_ref.project.resolution = rep.as_dict()

        self.system_combo.blockSignals(True)
        self.system_combo.clear()
        self.system_combo.addItem("— choisir une machine —", "")
        for g in rep.guesses:
            self.system_combo.addItem(f"{g.spec.name} · {g.score:.0f} pts", g.spec.key)
        self.system_combo.blockSignals(False)
        if rep.guesses:
            self.system_combo.setCurrentIndex(1)

        info = sheet.info or {}
        info["resolution"] = rep.as_dict()
        self.statusMessage.emit(
            f"Résolution : {rep.width}×{rep.height}"
            + (f" (×{rep.scale} → {rep.native_size[0]}×{rep.native_size[1]})" if rep.scale > 1 else "")
            + f" — {rep.color_count} couleurs — pas {rep.pitch[0]}×{rep.pitch[1]}")

    def _analyse_raw_bank(self, sheet: Sheet) -> None:
        """Analyse d'une banque brute : le profil des tuiles, pas la résolution."""
        info = sheet.info or {}
        fmt = FORMATS_BY_KEY.get(info.get("format", ""))
        tw, th = sheet.dominant_tile_size()
        count = len(sheet.tiles)
        bpp = fmt.bpp if fmt else 4
        guesses = detectres.guess_systems_by_profile(bpp, (tw, th), 1 << bpp)
        preferred = fmt.system_key if fmt and fmt.system_key else ""

        lines = [f"Banque brute : {count} tuiles de {tw}×{th} px"]
        if fmt is not None:
            lines.append(f"Format : {fmt.name}")
            lines.append(f"{fmt.planes} plans · {fmt.real_bytes} octets/tuile · "
                         f"offset 0x{info.get('offset', 0):X}")
        lines.append("La résolution d'écran ne se déduit pas d'une banque de tuiles : "
                     "choisissez la machine ci-dessous.")
        self.res_label.setText("<br>".join(lines))

        self.system_combo.blockSignals(True)
        self.system_combo.clear()
        ordered = []
        if preferred and preferred in SYSTEMS_BY_KEY:
            spec = SYSTEMS_BY_KEY[preferred]
            ordered.append((spec, 999.0))
        for g in guesses:
            if g.spec.key != preferred:
                ordered.append((g.spec, g.score))
        for spec, score in ordered:
            label = spec.name if score == 999.0 else f"{spec.name} · {score:.0f} pts"
            self.system_combo.addItem(label, spec.key)
        self.system_combo.blockSignals(False)
        if ordered:
            self.system_combo.setCurrentIndex(0)

        self.window_ref.project.resolution = {
            "kind": "raw_bank", "tile_w": tw, "tile_h": th, "count": count,
            "bpp": bpp, "format": info.get("format"),
            "systems": [s.key for s, _ in ordered[:6]],
        }
        if ordered:
            spec = ordered[0][0]
            res = ", ".join(f"{w}×{h}" for w, h in spec.resolutions)
            self.statusMessage.emit(
                f"Banque brute {tw}×{th} — machine probable : {spec.name} ({res})")

    def choose_system(self) -> None:
        detected = []
        if self._last_report:
            detected = [g.spec.key for g in self._last_report.guesses]
        current = self.system_combo.currentData() or ""
        dlg = SystemPickerDialog(self, current, detected)
        if dlg.exec() == QDialog.Accepted:
            spec = dlg.selected_system()
            if spec is not None:
                self.system_combo.blockSignals(True)
                self.system_combo.clear()
                self.system_combo.addItem(spec.name, spec.key)
                self.system_combo.blockSignals(False)
                self.window_ref.project.system = {"key": spec.key, "name": spec.name,
                                                  "resolutions": [list(r) for r in spec.resolutions]}
                self.apply_system()

    def _on_system_combo(self, index: int) -> None:
        key = self.system_combo.currentData()
        if not key:
            return
        spec = SYSTEMS_BY_KEY.get(key)
        if spec is None:
            return
        self.window_ref.project.system = {"key": spec.key, "name": spec.name,
                                          "resolutions": [list(r) for r in spec.resolutions]}

    def apply_system(self) -> None:
        key = self.system_combo.currentData()
        spec = SYSTEMS_BY_KEY.get(key) if key else None
        if spec is None:
            QMessageBox.information(self, "Machine", "Choisissez d'abord une machine.")
            return
        tw, th = spec.tile_sizes[0]
        self.canvas.snap_step = (tw, th)
        project = self.window_ref.project
        project.grid.tile_w, project.grid.tile_h = tw, th
        project.system = {"key": spec.key, "name": spec.name,
                          "resolutions": [list(r) for r in spec.resolutions]}
        info = project.sheet.info if project.sheet else {}
        info["system"] = spec.key
        self._sync_detect_defaults()
        self.statusMessage.emit(f"Machine appliquée : {spec.name} — tuiles {tw}×{th}, "
                                f"{spec.bpp} bpp, {spec.colors} couleurs")
        self.projectChanged.emit()

    # -- détection ----------------------------------------------------------

    def run_detection(self) -> None:
        sheet = self.window_ref.project.sheet
        if sheet is None:
            QMessageBox.information(self, "Planche", "Chargez d'abord une planche.")
            return
        key = self.detector_combo.currentData()
        det = detector_by_key(key)
        params = self._param_values()
        self.statusMessage.emit(f"Détection « {det.name} » en cours…")
        try:
            rects = det.run(sheet.image, params)
        except Exception as exc:
            QMessageBox.critical(self, "Détection", f"Échec : {exc}")
            return
        self._apply_rects(rects, det.name)
        self.window_ref.project.detection = {"detector": key, "params": params,
                                             "count": len(rects)}
        self.detect_info.setText(f"{len(rects)} tuiles détectées par « {det.name} ».")

    def compare_detectors(self) -> None:
        sheet = self.window_ref.project.sheet
        if sheet is None:
            return
        results = []
        for det in all_detectors():
            if det.key == "manual":
                continue
            try:
                rects = det.run(sheet.image, self._param_values() if det.key == self.detector_combo.currentData() else {})
            except Exception:
                rects = []
            results.append((det.name, len(rects), rects))
        text = " · ".join(f"{n} : {c}" for n, c, _ in results)
        self.detect_info.setText(text)
        best = max(results, key=lambda r: r[1])
        if best[1]:
            self._apply_rects(best[2], best[0])
            self.detect_info.setText(f"Méthode la plus productive : {best[0]} ({best[1]} tuiles). " + text)

    def _apply_rects(self, rects, name: str) -> None:
        sheet = self.window_ref.project.sheet
        if self.replace_check.isChecked():
            sheet.tiles.clear()
        # une banque brute a un ordre de stockage connu : on le conserve quand
        # la détection retrouve exactement le même nombre de tuiles
        expected = (sheet.info or {}).get("count")
        keep_storage = bool(expected) and len(rects) == expected
        for k, r in enumerate(rects):
            sheet.add_tile(r, storage_index=k if keep_storage else None, label=str(k))
        sheet.invalidate()
        self.canvas.set_selection([])
        self.canvas.refresh()
        self.check_quality()
        self.projectChanged.emit()

    def _on_tiles_changed(self) -> None:
        self.check_quality()
        self.projectChanged.emit()

    def _on_selection_changed(self, ids) -> None:
        if not ids:
            self.sel_label.setText("aucune tuile sélectionnée")
        elif len(ids) == 1:
            t = self.window_ref.project.sheet.tile(ids[0])
            if t:
                self.sel_label.setText(f"tuile {t.id} — {t.w}×{t.h} en ({t.x}, {t.y})")
        else:
            self.sel_label.setText(f"{len(ids)} tuiles sélectionnées")

    def _on_cursor(self, x: float, y: float) -> None:
        self.window_ref.show_coords(x, y)

    def _set_mode(self, mode: str) -> None:
        self.canvas.mode = mode
        self.canvas.pan_mode = (mode == "pan")
        self.act_select.setChecked(mode == "select")
        self.act_create.setChecked(mode == "create")
        self.act_pan.setChecked(mode == "pan")
        if mode == "create":
            self.canvas.setCursor(Qt.CrossCursor)
        elif mode == "pan":
            self.canvas.setCursor(Qt.OpenHandCursor)
        else:
            self.canvas.setCursor(Qt.ArrowCursor)

    def toggle_panel(self, visible: bool) -> None:
        self.panel.setVisible(visible)
        if self.act_panel.isChecked() != visible:
            self.act_panel.blockSignals(True)
            self.act_panel.setChecked(visible)
            self.act_panel.blockSignals(False)

    def _toggle_snap(self, on: bool) -> None:
        self.canvas.snap = on

    def _toggle_grid(self, on: bool) -> None:
        self.canvas.show_grid = on
        self.canvas.viewport().update()

    # -- qualité ------------------------------------------------------------

    def check_quality(self) -> None:
        sheet = self.window_ref.project.sheet
        self.quality_list.clear()
        if sheet is None:
            return
        issues = quality_report(sheet)
        if not issues:
            item = QListWidgetItem("Aucune anomalie détectée.")
            item.setForeground(QColor(theme.OK))
            self.quality_list.addItem(item)
            return
        for issue in issues[:200]:
            item = QListWidgetItem(f"• {issue.message}")
            item.setData(Qt.UserRole, issue.tile_ids)
            if issue.kind in ("overlap", "bounds"):
                item.setForeground(QColor(theme.ERR))
            elif issue.kind == "empty":
                item.setForeground(QColor(theme.WARN))
            self.quality_list.addItem(item)

    def _on_issue_clicked(self, item) -> None:
        ids = item.data(Qt.UserRole)
        if ids:
            self.canvas.set_selection(ids)
            if ids:
                t = self.window_ref.project.sheet.tile(ids[0])
                if t:
                    self.canvas.centerOn(t.x + t.w / 2, t.y + t.h / 2)

    # -- palette ------------------------------------------------------------

    def edit_palette(self) -> None:
        sheet = self.window_ref.project.sheet
        if sheet is None or not sheet.image.palette:
            return
        pal = generic.palette_from_sheet(sheet)
        dlg = PaletteEditorDialog(pal, self, size=max(16, len(pal)))
        if dlg.exec() != QDialog.Accepted:
            return
        new_pal = dlg.result_palette()
        self._apply_palette(new_pal)
        self.canvas.refresh()
        self.projectChanged.emit()

    def _apply_palette(self, pal) -> None:
        import numpy as np
        sheet = self.window_ref.project.sheet
        img = sheet.image
        if img.index is None:
            return
        rgba = np.array([pal.rgba(i) for i in range(max(len(pal), int(img.index.max()) + 1))],
                        dtype=np.uint8)
        safe = np.clip(img.index, 0, len(rgba) - 1)
        img.px = rgba[safe]
        img.palette = [pal.rgba(i) for i in range(len(pal))]
        sheet.invalidate()
        if sheet.info is not None:
            sheet.info["palette"] = pal.name

    def make_background_transparent(self) -> None:
        sheet = self.window_ref.project.sheet
        if sheet is None:
            return
        sheet.image = sheet.image.auto_transparent(0)
        sheet.invalidate()
        self.canvas.refresh()
        self.projectChanged.emit()
        self.statusMessage.emit("Couleur de fond rendue transparente.")

    def _begin_undo(self) -> None:
        self.window_ref.history.begin()

    def _end_undo(self) -> None:
        self.window_ref.history.commit("édition de tuiles")

    # -- rafraîchissement ---------------------------------------------------

    def refresh(self) -> None:
        sheet = self.window_ref.project.sheet
        if sheet is None:
            self.source_label.setText("Aucune planche chargée.")
            self.palette_btn.setEnabled(False)
            self.canvas.set_sheet(None)
            return
        self.source_label.setText(generic.describe_source(sheet))
        self.palette_btn.setEnabled(bool(sheet.image.palette))
        if self.canvas.sheet is not sheet:
            self.canvas.set_sheet(sheet)
        else:
            self.canvas.refresh()
        self._sync_detect_defaults()
