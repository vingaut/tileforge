"""Écran « Atelier » : assemblage manuel et automatique des tuiles."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..assemble import solvers
from ..assemble.cost import CostModel, CostWeights, build_cost_model
from ..core.image import Image
from ..core.model import Sprite
from . import theme
from .widgets import (
    Canvas,
    CostBars,
    TilePalette,
    fit_to_screen,
    hint_label,
    image_to_pixmap,
    panel_width,
    section_label,
    to_qimage,
)

TILE_MIME = TilePalette.MIME


# ---------------------------------------------------------------------------
# Canevas d'assemblage
# ---------------------------------------------------------------------------


class AssemblyCanvas(Canvas):
    """Grille d'assemblage avec glisser-déposer."""

    placementsChanged = Signal()
    cellHovered = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.sheet = None
        self.sprite: Sprite | None = None
        self.grid = None
        self.selected_slot: int | None = None
        self._drag_slot: int | None = None
        self._ghost_slot: int | None = None
        self._qcache: dict[int, object] = {}
        self._on_edit = None
        self.show_numbers = True
        self.pending_tile: int | None = None

    # -- données ------------------------------------------------------------

    def set_context(self, sheet, sprite: Sprite) -> None:
        self.sheet = sheet
        self.sprite = sprite
        self.grid = sprite.grid if sprite else None
        self._qcache.clear()
        if self.grid is not None:
            rect = QRectF(0, 0, self.grid.width, self.grid.height)
            changed = (self.image_rect().size() != rect.size())
            self.set_image_rect(rect)
            self.set_content_rect(rect, auto_fit=changed)
        self.viewport().update()

    def set_edit_callbacks(self, begin, end) -> None:
        self._on_edit = (begin, end)

    def _qimage_for(self, tile_id: int):
        img = self._qcache.get(tile_id)
        if img is None:
            img = to_qimage(self.sheet.tile_image(tile_id))
            self._qcache[tile_id] = img
        return img

    def invalidate(self) -> None:
        self._qcache.clear()
        self.viewport().update()

    def _slot_at(self, pos: QPointF) -> int | None:
        if self.grid is None:
            return None
        if pos.x() < 0 or pos.y() < 0:
            return None
        gx = int(pos.x() // self.grid.tile_w)
        gy = int(pos.y() // self.grid.tile_h)
        if gx >= self.grid.cols or gy >= self.grid.rows:
            return None
        return gy * self.grid.cols + gx

    # -- souris -------------------------------------------------------------

    def mousePressEvent(self, event):
        if self.pan_mode and event.button() == Qt.LeftButton:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.LeftButton and not self._panning:
            pos = self.mapToScene(event.position().toPoint())
            slot = self._slot_at(pos)
            if slot is not None:
                # mode tactile : une tuile choisie dans la palette se pose d'un clic
                if self.pending_tile is not None and slot not in self.sprite.placements:
                    self._begin()
                    self.sprite.placements[slot] = self.pending_tile
                    self.pending_tile = None
                    self.selected_slot = slot
                    self._end()
                    self.viewport().update()
                    event.accept()
                    return
                self.selected_slot = slot
                if slot in self.sprite.placements:
                    self._drag_slot = slot
                self.viewport().update()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = self.mapToScene(event.position().toPoint())
        slot = self._slot_at(pos)
        self.cellHovered.emit(slot if slot is not None else -1)
        if self._drag_slot is not None:
            self._ghost_slot = slot
            self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_slot is not None:
            pos = self.mapToScene(event.position().toPoint())
            target = self._slot_at(pos)
            if target is not None and target != self._drag_slot:
                self._move(self._drag_slot, target)
            self._drag_slot = None
            self._ghost_slot = None
            self.viewport().update()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        pos = self.mapToScene(event.position().toPoint())
        slot = self._slot_at(pos)
        if slot is not None and slot in self.sprite.placements:
            self._remove(slot)
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.selected_slot is not None:
            self._remove(self.selected_slot)
            return
        super().keyPressEvent(event)

    # -- glisser-déposer ----------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(TILE_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(TILE_MIME):
            pos = self.mapToScene(event.position().toPoint())
            self._ghost_slot = self._slot_at(pos)
            self.viewport().update()
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._ghost_slot = None
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(TILE_MIME):
            super().dropEvent(event)
            return
        pos = self.mapToScene(event.position().toPoint())
        slot = self._slot_at(pos)
        raw = bytes(event.mimeData().data(TILE_MIME)).decode("ascii")
        ids = [int(v) for v in raw.split(",") if v.strip()]
        if slot is None or not ids:
            return
        self._begin()
        for k, tid in enumerate(ids):
            target = slot + k
            if target >= self.sprite.cols * self.sprite.rows:
                break
            self.sprite.place(target, tid)
        self.selected_slot = slot
        self._end()
        self.viewport().update()
        event.acceptProposedAction()

    # -- opérations ---------------------------------------------------------

    def _begin(self) -> None:
        if self._on_edit:
            self._on_edit[0]()

    def _end(self) -> None:
        if self._on_edit:
            self._on_edit[1]()
        self.placementsChanged.emit()

    def _move(self, src: int, dst: int) -> None:
        self._begin()
        tid = self.sprite.placements.get(src)
        if tid is None:
            self._end()
            return
        other = self.sprite.placements.get(dst)
        del self.sprite.placements[src]
        if other is not None:
            self.sprite.placements[src] = other
        self.sprite.placements[dst] = tid
        self.selected_slot = dst
        self._end()

    def _remove(self, slot: int) -> None:
        if slot not in self.sprite.placements:
            return
        self._begin()
        del self.sprite.placements[slot]
        self.selected_slot = None
        self._end()
        self.viewport().update()

    def place_ids(self, order: list[int], tile_ids: list[int]) -> None:
        """Applique un ordre (index dans tile_ids) au sprite."""
        self._begin()
        self.sprite.placements.clear()
        for slot, idx in enumerate(order):
            if 0 <= idx < len(tile_ids):
                self.sprite.placements[slot] = tile_ids[idx]
        self._end()
        self.viewport().update()

    # -- dessin -------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        if self.grid is None:
            return
        g = self.grid
        painter.setRenderHint(QPainter.Antialiasing, False)
        cell_pen = QPen(QColor(theme.GRID))
        cell_pen.setCosmetic(True)
        painter.setPen(cell_pen)
        painter.setBrush(Qt.NoBrush)
        for gy in range(g.rows):
            for gx in range(g.cols):
                painter.drawRect(QRectF(gx * g.tile_w, gy * g.tile_h, g.tile_w, g.tile_h))

        painter.setRenderHint(QPainter.SmoothPixmapTransform, self.zoom() < 1.0)
        for slot, tid in self.sprite.placements.items():
            gx, gy = slot % g.cols, slot // g.cols
            target = QRectF(gx * g.tile_w, gy * g.tile_h, g.tile_w, g.tile_h)
            painter.drawImage(target, self._qimage_for(tid))

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        if self.grid is None:
            return
        g = self.grid
        z = self.zoom()
        painter.setRenderHint(QPainter.Antialiasing, False)

        if self.selected_slot is not None:
            gx, gy = self.selected_slot % g.cols, self.selected_slot // g.cols
            pen = QPen(QColor(theme.ACCENT), 0)
            pen.setCosmetic(True)
            pen.setWidthF(2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(gx * g.tile_w, gy * g.tile_h, g.tile_w, g.tile_h))

        if self._ghost_slot is not None and self._drag_slot is not None:
            gx, gy = self._ghost_slot % g.cols, self._ghost_slot // g.cols
            tid = self.sprite.placements.get(self._drag_slot)
            if tid is not None:
                painter.setOpacity(0.55)
                painter.drawImage(QRectF(gx * g.tile_w, gy * g.tile_h, g.tile_w, g.tile_h),
                                  self._qimage_for(tid))
                painter.setOpacity(1.0)
            pen = QPen(QColor(theme.OK), 0)
            pen.setCosmetic(True)
            pen.setWidthF(2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(gx * g.tile_w, gy * g.tile_h, g.tile_w, g.tile_h))

        if self.show_numbers and z > 1.2:
            font = QFont()
            font.setPixelSize(max(6, int(10 / max(z, 0.3))))
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 70))
            for gy in range(g.rows):
                for gx in range(g.cols):
                    slot = gy * g.cols + gx
                    painter.drawText(QRectF(gx * g.tile_w + 2, gy * g.tile_h + 1,
                                            g.tile_w, g.tile_h),
                                     Qt.AlignLeft | Qt.AlignTop, str(slot))


# ---------------------------------------------------------------------------
# Résolution automatique (thread)
# ---------------------------------------------------------------------------


class SolverThread(QThread):
    progress = Signal(float, str)
    finished_ok = Signal(list, float)

    def __init__(self, model: CostModel, cols: int, rows: int, method: str,
                 options: dict, parent=None):
        super().__init__(parent)
        self.model = model
        self.cols = cols
        self.rows = rows
        self.method = method
        self.options = options

    def run(self):
        t0 = time.time()
        try:
            if self.method == "ALL":
                res = solvers.solve_all(self.model, self.cols, self.rows, self.options,
                                        lambda f, m: self.progress.emit(f, m))
            else:
                res = solvers.solve(self.method, self.model, self.cols, self.rows,
                                    self.options, lambda f, m: self.progress.emit(f, m))
        except Exception as exc:
            res = []
            self.progress.emit(1.0, f"Erreur : {exc}")
        self.finished_ok.emit(res, time.time() - t0)


class AutoAssembleDialog(QDialog):
    """Panneau « assemblage automatique » : méthode, poids, résultats classés."""

    def __init__(self, parent, sheet, tile_ids: list[int], cols: int, rows: int,
                 weights: CostWeights | None = None):
        super().__init__(parent)
        self.setWindowTitle("Assemblage automatique")
        fit_to_screen(self, 900, 620)
        self.sheet = sheet
        self.tile_ids = tile_ids
        self.cols, self.rows = cols, rows
        self.weights = weights or CostWeights()
        self.solutions = []
        self.chosen = None
        self._thread = None
        self._model = None

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        gb = QGroupBox("Méthode")
        form = QFormLayout(gb)
        self.method_combo = QComboBox()
        for key, label in solvers.METHODS:
            self.method_combo.addItem(f"{key} — {label}", key)
        self.method_combo.addItem("Tout essayer (classement fusionné)", "ALL")
        form.addRow("Algorithme", self.method_combo)
        self.iterations = QSpinBox()
        self.iterations.setRange(200, 200000)
        self.iterations.setValue(6000)
        self.iterations.setSingleStep(500)
        form.addRow("Itérations (M4)", self.iterations)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(10, 5000)
        self.width_spin.setValue(300)
        form.addRow("Largeur du faisceau (M3)", self.width_spin)
        lv.addWidget(gb)

        gb2 = QGroupBox("Poids des indices")
        f2 = QFormLayout(gb2)
        self.weight_sliders = {}
        for key, label in (("silhouette", "C1 Silhouette"), ("color", "C2 Couleur"),
                           ("gradient", "C3 Contour"), ("hole", "C4 Trous"),
                           ("palette", "C5 Palette"), ("duplicate", "C6 Doublons")):
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 200)
            slider.setValue(int(getattr(self.weights, key) * 100))
            value = QLabel(f"{getattr(self.weights, key):.2f}")
            slider.valueChanged.connect(
                lambda v, label=value: label.setText(f"{v / 100:.2f}"))
            row = QHBoxLayout()
            row.addWidget(slider, 1)
            row.addWidget(value)
            f2.addRow(label, row)
            self.weight_sliders[key] = (slider, value)
        lv.addWidget(gb2)

        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("Lancer")
        self.run_btn.setProperty("accent", True)
        self.run_btn.clicked.connect(self.run_solver)
        btn_row.addWidget(self.run_btn)
        lv.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        lv.addWidget(self.progress)
        self.progress_label = hint_label("Prêt.")
        lv.addWidget(self.progress_label)
        lv.addStretch(1)
        left.setFixedWidth(340)
        top.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(10, 0, 0, 0)
        rv.addWidget(section_label("Résultats classés"))
        self.results = QListWidget()
        self.results.setViewMode(QListWidget.IconMode)
        self.results.setIconSize(QSize(150, 150))
        self.results.setGridSize(QSize(170, 190))
        self.results.setResizeMode(QListWidget.Adjust)
        self.results.setMovement(QListWidget.Static)
        self.results.setSpacing(6)
        self.results.itemDoubleClicked.connect(lambda _i: self.accept())
        rv.addWidget(self.results, 1)
        top.addWidget(right, 1)
        root.addLayout(top, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._weights = self.weights
        self.run_solver()

    # -- exécution ----------------------------------------------------------

    def _current_weights(self) -> CostWeights:
        return CostWeights(**{k: s.value() / 100.0 for k, (s, _l) in self.weight_sliders.items()})

    def run_solver(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self.run_btn.setEnabled(False)
        self.results.clear()
        self.progress.setValue(0)
        self.progress_label.setText("Calcul en cours…")
        self._weights = self._current_weights()
        try:
            self._model = build_cost_model(self.sheet, self.tile_ids, self._weights)
        except Exception as exc:
            self.progress_label.setText(f"Impossible de calculer les coûts : {exc}")
            self.run_btn.setEnabled(True)
            return
        method = self.method_combo.currentData()
        options = {"iterations": self.iterations.value(), "width": self.width_spin.value(),
                   "limit": 20, "restarts": 4,
                   "methods": ["M1", "M2", "M3", "M4", "M5", "M6"]}
        self._thread = SolverThread(self._model, self.cols, self.rows, method, options, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished_ok.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, frac: float, message: str) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, frac)) * 100))
        self.progress_label.setText(message)

    def _on_finished(self, solutions, elapsed: float) -> None:
        self.solutions = solutions
        self.run_btn.setEnabled(True)
        self.progress.setValue(100)
        self.progress_label.setText(f"{len(solutions)} solution(s) en {elapsed:.2f} s.")
        for k, sol in enumerate(solutions[:40]):
            pm = image_to_pixmap(self._render(sol.order), max_size=150)
            item = QListWidgetItem(f"#{k + 1}  {sol.method}  {sol.cost:.3f}")
            item.setIcon(pm)
            item.setToolTip(f"{sol.method} — coût {sol.cost:.4f}\n{sol.label}")
            item.setData(Qt.UserRole, k)
            self.results.addItem(item)
        if solutions:
            self.results.setCurrentRow(0)

    def _render(self, order: list[int]) -> Image:
        from ..core.model import Sprite as Sp
        sp = Sp(0, "apercu", self.cols, self.rows, self.sheet.tile_image(self.tile_ids[0]).w,
                self.sheet.tile_image(self.tile_ids[0]).h)
        for slot, idx in enumerate(order):
            if 0 <= idx < len(self.tile_ids):
                sp.placements[slot] = self.tile_ids[idx]
        return sp.render(self.sheet)

    def accept(self) -> None:
        item = self.results.currentItem()
        if item is None:
            return
        self.chosen = self.solutions[item.data(Qt.UserRole)]
        super().accept()

    def chosen_solution(self):
        return self.chosen


# ---------------------------------------------------------------------------
# Écran Atelier
# ---------------------------------------------------------------------------


class AssemblyView(QWidget):
    projectChanged = Signal()
    statusMessage = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window_ref = window
        self.group_index = 0
        self._model = None
        self._weights = CostWeights()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- palette
        left = QWidget()
        self._left_panel = left
        left.setFixedWidth(panel_width(250, 210))
        left.setStyleSheet(f"background: {theme.PANEL};")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 8)
        lv.addWidget(section_label("Tuiles disponibles"))
        self.group_label = hint_label("")
        lv.addWidget(self.group_label)
        self.palette = TilePalette()
        self.palette.itemClicked.connect(self._on_palette_clicked)
        lv.addWidget(self.palette, 1)
        self.palette_info = hint_label("")
        lv.addWidget(self.palette_info)
        root.addWidget(left)

        # -- canevas
        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        self.toolbar = QToolBar()
        self._build_toolbar()
        cv.addWidget(self.toolbar)
        self.canvas = AssemblyCanvas()
        self.canvas.zoomChanged.connect(lambda z: self.zoom_label.setText(f"{z * 100:.0f} %"))
        self.canvas.placementsChanged.connect(self._on_placements_changed)
        self.canvas.set_edit_callbacks(lambda: self.window_ref.history.begin(),
                                       lambda: self.window_ref.history.commit("placement"))
        cv.addWidget(self.canvas, 1)
        root.addWidget(center, 1)

        # -- inspecteur
        right = QWidget()
        right.setFixedWidth(panel_width(290, 240))
        right.setStyleSheet(f"background: {theme.PANEL};")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(10, 10, 10, 10)

        rv.addWidget(section_label("Sprite"))
        row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("nom du sprite")
        self.name_edit.editingFinished.connect(self._on_name_changed)
        row.addWidget(self.name_edit, 1)
        rv.addLayout(row)

        grid_box = QGroupBox("Grille")
        gf = QFormLayout(grid_box)
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 64)
        self.cols_spin.setValue(3)
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 64)
        self.rows_spin.setValue(4)
        self.cols_spin.valueChanged.connect(self._on_grid_changed)
        self.rows_spin.valueChanged.connect(self._on_grid_changed)
        gf.addRow("Colonnes", self.cols_spin)
        gf.addRow("Lignes", self.rows_spin)
        rv.addWidget(grid_box)

        rv.addWidget(section_label("Coût de l'assemblage"))
        self.cost_value = QLabel("—")
        f = QFont()
        f.setPointSize(22)
        f.setBold(True)
        self.cost_value.setFont(f)
        rv.addWidget(self.cost_value)
        self.cost_bars = CostBars()
        rv.addWidget(self.cost_bars)

        rv.addSpacing(6)
        self.auto_btn = QPushButton("Assemblage automatique…")
        self.auto_btn.setProperty("accent", True)
        self.auto_btn.clicked.connect(self.open_auto)
        rv.addWidget(self.auto_btn)

        self.grid_btn = QPushButton("Tester les grilles…")
        self.grid_btn.clicked.connect(self.open_grid_tester)
        rv.addWidget(self.grid_btn)

        self.recipe_btn = QPushButton("Appliquer la recette")
        self.recipe_btn.clicked.connect(self.apply_recipe)
        rv.addWidget(self.recipe_btn)

        rv.addSpacing(6)
        self.validate_btn = QPushButton("Valider le sprite  (Entrée)")
        self.validate_btn.setProperty("accent", True)
        self.validate_btn.clicked.connect(self.validate)
        rv.addWidget(self.validate_btn)

        row = QHBoxLayout()
        self.next_btn = QPushButton("Sprite suivant")
        self.next_btn.clicked.connect(self.next_group)
        self.clear_btn = QPushButton("Vider")
        self.clear_btn.clicked.connect(self.clear_canvas)
        row.addWidget(self.next_btn)
        row.addWidget(self.clear_btn)
        rv.addLayout(row)

        rv.addWidget(section_label("Remplissage rapide"))
        row = QHBoxLayout()
        b1 = QPushButton("Ordre de stockage")
        b1.clicked.connect(lambda: self.fill_from_storage())
        b2 = QPushButton("Inversé")
        b2.clicked.connect(lambda: self.fill_from_storage(reverse=True))
        row.addWidget(b1)
        row.addWidget(b2)
        rv.addLayout(row)
        rv.addStretch(1)
        root.addWidget(right)

        # Entrée valide le sprite, comme l'annonce le bouton
        shortcut = QShortcut(QKeySequence(Qt.Key_Return), self)
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.validate)
        escape = QShortcut(QKeySequence(Qt.Key_Escape), self)
        escape.setContext(Qt.WidgetWithChildrenShortcut)
        escape.activated.connect(self._cancel_pending)

    # -- toolbar ------------------------------------------------------------

    def _build_toolbar(self) -> None:
        tb = self.toolbar
        self.act_panel = QAction("Panneau", self)
        self.act_panel.setCheckable(True)
        self.act_panel.setChecked(True)
        self.act_panel.toggled.connect(self.toggle_panel)
        tb.addAction(self.act_panel)
        tb.addSeparator()
        tb.addWidget(QLabel("  Sprite : "))
        self.sprite_label = QLabel("—")
        self.sprite_label.setStyleSheet("font-weight: 600;")
        tb.addWidget(self.sprite_label)
        tb.addSeparator()
        tb.addWidget(QLabel("  Groupe : "))
        self.group_nav = QLabel("—")
        tb.addWidget(self.group_nav)
        b_prev = QPushButton("◀")
        b_prev.setFixedWidth(30)
        b_prev.clicked.connect(lambda: self.shift_group(-1))
        b_next = QPushButton("▶")
        b_next.setFixedWidth(30)
        b_next.clicked.connect(lambda: self.shift_group(1))
        tb.addWidget(b_prev)
        tb.addWidget(b_next)
        tb.addSeparator()
        spacer = QWidget()
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.act_pan = QAction("Déplacer", self)
        self.act_pan.setCheckable(True)
        self.act_pan.setShortcut("H")
        self.act_pan.toggled.connect(self._toggle_pan)
        tb.addAction(self.act_pan)
        tb.addSeparator()
        tb.addWidget(QLabel("Zoom "))
        self.zoom_label = QLabel("100 %")
        self.zoom_label.setProperty("hint", True)
        tb.addWidget(self.zoom_label)
        tb.addWidget(QLabel("  "))

    # -- groupe de tuiles ---------------------------------------------------

    def _ordered_tiles(self):
        sheet = self.window_ref.project.sheet
        if sheet is None:
            return []
        return sheet.tiles_sorted()

    def group_tiles(self) -> list[int]:
        tiles = self._ordered_tiles()
        sprite = self.window_ref.project.current
        n = sprite.cols * sprite.rows
        start = self.group_index * n
        if start >= len(tiles):
            start = 0
        return [t.id for t in tiles[start:start + n]]

    def _unplaced(self) -> list[int]:
        sprite = self.window_ref.project.current
        placed = set(sprite.placements.values())
        return [tid for tid in self.group_tiles() if tid not in placed]

    def _refresh_palette(self) -> None:
        sheet = self.window_ref.project.sheet
        self.palette.set_sheet(sheet)
        if sheet is None:
            self.palette.clear()
            self.palette_info.setText("")
            return
        unplaced = self._unplaced()
        labels = {}
        for tid in unplaced:
            t = sheet.tile(tid)
            if t and t.storage_index is not None:
                labels[tid] = f"indice de stockage {t.storage_index}"
        self.palette.populate(unplaced, labels)
        total = len(self.group_tiles())
        if self.canvas.pending_tile is not None:
            self.palette_info.setText(
                "Tuile choisie — touchez une case vide pour la poser (Échap)")
        else:
            self.palette_info.setText(f"{len(unplaced)} tuiles libres sur {total}")
        self.group_label.setText(
            f"Groupe {self.group_index + 1} — "
            f"{len(self.window_ref.project.current.placements)}/{total} placées")

    def _on_palette_clicked(self, item) -> None:
        """Mode tactile : mémorise la tuile choisie pour la poser au clic suivant."""
        if item is None:
            return
        self.canvas.pending_tile = item.data(Qt.UserRole)
        tile = self.window_ref.project.sheet.tile(self.canvas.pending_tile)
        if tile is not None:
            index = tile.storage_index if tile.storage_index is not None else tile.id
            self.palette_info.setText(
                f"Tuile {index} choisie — touchez une case vide pour la poser "
                f"(Échap pour annuler)")
        self.canvas.setFocus()

    def _toggle_pan(self, enabled: bool) -> None:
        self.canvas.pan_mode = enabled
        self.canvas.setCursor(Qt.OpenHandCursor if enabled else Qt.ArrowCursor)

    def toggle_panel(self, visible: bool) -> None:
        self._left_panel.setVisible(visible)
        if self.act_panel.isChecked() != visible:
            self.act_panel.blockSignals(True)
            self.act_panel.setChecked(visible)
            self.act_panel.blockSignals(False)

    # -- rafraîchissement ---------------------------------------------------

    def refresh(self) -> None:
        project = self.window_ref.project
        sprite = project.current
        if project.sheet is None:
            self.canvas.set_context(None, None)
            self.sprite_label.setText("aucune planche")
            return
        self.cols_spin.blockSignals(True)
        self.rows_spin.blockSignals(True)
        self.cols_spin.setValue(sprite.cols)
        self.rows_spin.setValue(sprite.rows)
        self.cols_spin.blockSignals(False)
        self.rows_spin.blockSignals(False)
        if not self.name_edit.hasFocus():
            self.name_edit.setText(sprite.name)
        self.canvas.set_context(project.sheet, sprite)
        self.sprite_label.setText(f"{sprite.name} (id {sprite.id})")
        self.group_nav.setText(f"{self.group_index + 1} / "
                               f"{max(1, math.ceil(len(self._ordered_tiles()) / max(1, sprite.cols * sprite.rows)))}")
        self._refresh_palette()
        self._recompute_cost()

    def _on_placements_changed(self) -> None:
        self.window_ref.project.dirty = True
        self._refresh_palette()
        self._recompute_cost()
        self.projectChanged.emit()

    def _recompute_cost(self) -> None:
        project = self.window_ref.project
        sprite = project.current
        sheet = project.sheet
        placed = [tid for _s, tid in sorted(sprite.placements.items())]
        if sheet is None or len(placed) < 2:
            self._model = None
            self.cost_value.setText("—")
            self.cost_bars.clear()
            return
        try:
            self._model = build_cost_model(sheet, placed, self._weights)
        except Exception:
            self._model = None
            return
        index = {tid: i for i, tid in enumerate(placed)}
        order = [index.get(sprite.placements.get(slot), -1)
                 for slot in range(sprite.cols * sprite.rows)]
        breakdown = self._model.breakdown(order, sprite.cols, sprite.rows)
        self.cost_value.setText(f"{breakdown['total']:.3f}")
        self.cost_bars.set_values(breakdown)
        sprite.cost = breakdown["total"]

    def _on_name_changed(self) -> None:
        self.window_ref.project.current.name = self.name_edit.text()
        self.sprite_label.setText(f"{self.name_edit.text()} "
                                  f"(id {self.window_ref.project.current.id})")

    def _on_grid_changed(self) -> None:
        sprite = self.window_ref.project.current
        sprite.cols = self.cols_spin.value()
        sprite.rows = self.rows_spin.value()
        project = self.window_ref.project
        project.grid.cols = sprite.cols
        project.grid.rows = sprite.rows
        self.canvas.set_context(project.sheet, sprite)
        self._refresh_palette()
        self._recompute_cost()

    # -- actions ------------------------------------------------------------

    def open_auto(self) -> None:
        project = self.window_ref.project
        if project.sheet is None:
            return
        tiles = self.group_tiles()
        sprite = project.current
        n = sprite.cols * sprite.rows
        if len(tiles) < n:
            QMessageBox.information(self, "Assemblage",
                                    f"Le groupe ne contient que {len(tiles)} tuiles "
                                    f"pour une grille de {n} cases.")
        dlg = AutoAssembleDialog(self, project.sheet, tiles, sprite.cols, sprite.rows,
                                 self._weights)
        if dlg.exec() == QDialog.Accepted and dlg.chosen_solution():
            sol = dlg.chosen_solution()
            self._weights = dlg._weights
            self.window_ref.history.begin()
            self.canvas.place_ids(sol.order, tiles)
            self.window_ref.history.commit(f"assemblage {sol.method}")
            self.statusMessage.emit(
                f"Solution {sol.method} appliquée (coût {sol.cost:.3f}, {sol.label})")

    def _cancel_pending(self) -> None:
        self.canvas.pending_tile = None
        self._refresh_palette()

    def open_grid_tester(self) -> None:
        """Compare plusieurs grilles sur le même paquet de tuiles."""
        from .grid_tester import GridTesterDialog
        project = self.window_ref.project
        if project.sheet is None:
            return
        sprite = project.current
        tiles = self._ordered_tiles()
        # on teste sur un paquet représentatif : 24 tuiles suffisent
        pool = [t.id for t in tiles[:24]]
        if len(pool) < 4:
            QMessageBox.information(self, "Grilles", "Pas assez de tuiles.")
            return
        dlg = GridTesterDialog(self, project.sheet, pool, (sprite.cols, sprite.rows))
        if dlg.exec() != QDialog.Accepted:
            return
        grid = dlg.chosen_grid()
        if not grid:
            return
        cols, rows = grid
        sprite.cols, sprite.rows = cols, rows
        project.grid.cols, project.grid.rows = cols, rows
        self.cols_spin.blockSignals(True)
        self.rows_spin.blockSignals(True)
        self.cols_spin.setValue(cols)
        self.rows_spin.setValue(rows)
        self.cols_spin.blockSignals(False)
        self.rows_spin.blockSignals(False)
        self.canvas.set_context(project.sheet, sprite)
        self.refresh()
        self.statusMessage.emit(f"Grille appliquée : {cols} × {rows}.")

    def validate(self) -> None:
        project = self.window_ref.project
        sprite = project.current
        if not sprite.placements:
            QMessageBox.information(self, "Validation", "Le canevas est vide.")
            return
        if not sprite.is_complete():
            n = sprite.cols * sprite.rows
            missing = n - len(sprite.placements)
            answer = QMessageBox.question(
                self, "Sprite incomplet",
                f"{missing} case(s) vide(s) sur {n}. Valider quand même ?",
                QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        self.window_ref.history.begin()
        validated = project.validate_current(self.name_edit.text() or None)
        self.window_ref.history.commit("validation")
        self.statusMessage.emit(f"Sprite « {validated.name} » validé et ajouté à l'atlas.")
        self.next_group()
        self.projectChanged.emit()

    def next_group(self) -> None:
        self.shift_group(1)

    def shift_group(self, delta: int) -> None:
        project = self.window_ref.project
        sprite = project.current
        n = max(1, sprite.cols * sprite.rows)
        total = len(self._ordered_tiles())
        groups = max(1, math.ceil(total / n))
        self.group_index = (self.group_index + delta) % groups
        new_sprite = project.new_sprite()
        new_sprite.origin_tile = self.group_index * n
        self.canvas.set_context(project.sheet, new_sprite)
        self.refresh()
        self.projectChanged.emit()

    def clear_canvas(self) -> None:
        self.window_ref.history.begin()
        self.window_ref.project.current.placements.clear()
        self.window_ref.history.commit("vider le canevas")
        self.canvas.viewport().update()
        self._on_placements_changed()

    def fill_from_storage(self, reverse: bool = False) -> None:
        tiles = self.group_tiles()
        sprite = self.window_ref.project.current
        n = sprite.cols * sprite.rows
        order = list(range(min(n, len(tiles))))
        if reverse:
            order.reverse()
        self.window_ref.history.begin()
        self.canvas.place_ids(order, tiles)
        self.window_ref.history.commit("remplissage")
        self._on_placements_changed()

    def apply_recipe(self) -> None:
        project = self.window_ref.project
        if not project.recipes:
            QMessageBox.information(self, "Recette",
                                    "Aucune recette enregistrée. Validez des sprites puis "
                                    "inférez une règle dans l'onglet Analyse.")
            return
        from PySide6.QtWidgets import QInputDialog
        names = [r.name for r in project.recipes]
        name, ok = QInputDialog.getItem(self, "Recette", "Appliquer la recette :", names, 0, False)
        if not ok:
            return
        recipe = project.recipes[names.index(name)]
        sheet = project.sheet
        sprite = project.current
        tiles = self.group_tiles()
        by_index = {sheet.tile(t).storage_index: t for t in tiles if sheet.tile(t) is not None}
        base = min((k for k in by_index if k is not None), default=0)
        self.window_ref.history.begin()
        sprite.placements.clear()
        placed = 0
        for slot, off in enumerate(recipe.mapping):
            if slot >= sprite.cols * sprite.rows or off < 0:
                continue
            tid = by_index.get(base + off)
            if tid is not None:
                sprite.placements[slot] = tid
                placed += 1
        self.window_ref.history.commit("application de recette")
        self._on_placements_changed()
        self.statusMessage.emit(f"Recette « {recipe.name} » : {placed} tuiles placées.")
