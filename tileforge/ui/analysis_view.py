"""Écran « Analyse » : hypothèses d'ordre, inférence de règle, journal, exports."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..assemble import inference
from ..assemble.cost import CostWeights, build_cost_model
from ..assemble.hypotheses import rank as rank_hypotheses
from ..core import project_io
from ..core.model import Sprite
from . import theme
from .widgets import hint_label


class AnalysisView(QWidget):
    """Onglet « Analyse »."""

    statusMessage = Signal(str)
    requestTab = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window_ref = window
        self._hypotheses = []
        self._models = []
        self._obs = []

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split)

        # -- colonne gauche
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 6, 0)

        gb = QGroupBox("Hypothèses d'ordre sur le groupe courant")
        gv = QVBoxLayout(gb)
        self.hyp_info = hint_label("Lancez l'analyse pour classer les permutations candidates.")
        gv.addWidget(self.hyp_info)
        self.hyp_table = QTableWidget(0, 4)
        self.hyp_table.setHorizontalHeaderLabels(["#", "Hypothèse", "Coût", "Famille"])
        self.hyp_table.verticalHeader().setVisible(False)
        self.hyp_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hyp_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hyp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        gv.addWidget(self.hyp_table, 1)
        row = QHBoxLayout()
        b = QPushButton("Analyser le groupe")
        b.clicked.connect(self.run_hypotheses)
        row.addWidget(b)
        b2 = QPushButton("Appliquer au canevas")
        b2.clicked.connect(self.apply_hypothesis)
        row.addWidget(b2)
        gv.addLayout(row)
        lv.addWidget(gb, 1)

        gb2 = QGroupBox("Règle d'ordonnancement")
        gv2 = QVBoxLayout(gb2)
        self.rule_info = hint_label(
            "Validez au moins deux sprites, puis lancez l'inférence pour découvrir "
            "la fonction qui relie l'ordre de stockage aux cases de la grille.")
        gv2.addWidget(self.rule_info)
        self.rule_table = QTableWidget(0, 4)
        self.rule_table.setHorizontalHeaderLabels(["Modèle", "Sprites exacts", "Tuiles", "Score"])
        self.rule_table.verticalHeader().setVisible(False)
        self.rule_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rule_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rule_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        gv2.addWidget(self.rule_table, 1)
        row = QHBoxLayout()
        b = QPushButton("Inférer")
        b.setProperty("accent", True)
        b.clicked.connect(self.run_inference)
        row.addWidget(b)
        b2 = QPushButton("Créer la recette")
        b2.clicked.connect(self.make_recipe)
        row.addWidget(b2)
        gv2.addLayout(row)
        row2 = QHBoxLayout()
        b3 = QPushButton("Appliquer au groupe suivant")
        b3.clicked.connect(lambda: self.apply_recipe(all_bank=False))
        row2.addWidget(b3)
        b4 = QPushButton("Appliquer à toute la banque")
        b4.clicked.connect(lambda: self.apply_recipe(all_bank=True))
        row2.addWidget(b4)
        gv2.addLayout(row2)
        lv.addWidget(gb2, 1)
        split.addWidget(left)

        # -- colonne droite
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 0, 0, 0)

        gb3 = QGroupBox("Journal des mouvements")
        gv3 = QVBoxLayout(gb3)
        self.log_info = hint_label("Chaque placement, déplacement et validation est horodaté.")
        gv3.addWidget(self.log_info)
        self.log_table = QTableWidget(0, 6)
        self.log_table.setHorizontalHeaderLabels(["Heure", "Type", "Sprite", "Tuile", "De", "Vers"])
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        gv3.addWidget(self.log_table, 1)
        rv.addWidget(gb3, 3)

        gb4 = QGroupBox("Exports pour analyse")
        gv4 = QVBoxLayout(gb4)
        gv4.addWidget(hint_label(
            "CSV et JSON des placements, plus un fichier texte des permutations "
            "lisibles (indice de stockage → case)."))
        row = QHBoxLayout()
        b = QPushButton("CSV des placements…")
        b.clicked.connect(self.export_csv)
        row.addWidget(b)
        b = QPushButton("JSON des placements…")
        b.clicked.connect(self.export_json)
        row.addWidget(b)
        b = QPushButton("Permutations (.txt)…")
        b.clicked.connect(self.export_permutations)
        row.addWidget(b)
        gv4.addLayout(row)
        self.export_log = QTextEdit()
        self.export_log.setReadOnly(True)
        self.export_log.setMaximumHeight(110)
        gv4.addWidget(self.export_log)
        gv4.addStretch(1)
        rv.addWidget(gb4, 2)
        split.addWidget(right)
        split.setSizes([560, 440])

    # -- hypothèses ---------------------------------------------------------

    def run_hypotheses(self) -> None:
        project = self.window_ref.project
        sheet = project.sheet
        if sheet is None:
            QMessageBox.information(self, "Analyse", "Chargez d'abord une planche.")
            return
        sprite = project.current
        n = sprite.cols * sprite.rows
        ordered = sheet.tiles_sorted()
        start = 0
        if sprite.placements:
            tids = sorted(sprite.placements.values())
            first = sheet.tile(tids[0])
            if first is not None and first.storage_index is not None:
                for i, t in enumerate(ordered):
                    if t.storage_index is not None and t.storage_index >= first.storage_index:
                        start = i
                        break
        group = ordered[start:start + n]
        if len(group) < n:
            group = ordered[:n]
        if len(group) < n:
            QMessageBox.information(self, "Analyse", "Pas assez de tuiles pour cette grille.")
            return
        try:
            model = build_cost_model(sheet, [t.id for t in group],
                                     CostWeights(**self.window_ref.weights))
        except Exception as exc:
            QMessageBox.critical(self, "Analyse", f"Calcul impossible : {exc}")
            return
        results = rank_hypotheses(model, sprite.cols, sprite.rows, limit=25)
        self._hypotheses = [(h, c) for h, c, _b in results]
        self.hyp_table.setRowCount(len(results))
        for row, (hyp, cost, _b) in enumerate(results):
            self.hyp_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.hyp_table.setItem(row, 1, QTableWidgetItem(hyp.name))
            item = QTableWidgetItem(f"{cost:.3f}")
            if row == 0:
                item.setForeground(QColor(theme.OK))
            self.hyp_table.setItem(row, 2, item)
            self.hyp_table.setItem(row, 3, QTableWidgetItem(hyp.family))
        if results:
            self.hyp_table.selectRow(0)
            best = results[0]
            median = results[len(results) // 2][1]
            self.hyp_info.setText(
                f"{len(results)} hypothèses — meilleure : « {best[0].name} » "
                f"(coût {best[1]:.3f}, médiane {median:.3f})")
        self._last_group = [t.id for t in group]
        self._last_model = model

    def apply_hypothesis(self) -> None:
        row = self.hyp_table.currentRow()
        if row < 0 or row >= len(self._hypotheses):
            return
        hyp, _cost = self._hypotheses[row]
        project = self.window_ref.project
        sprite = project.current
        group_ids = getattr(self, "_last_group", None)
        if not group_ids:
            return
        self.window_ref.history.begin()
        sprite.placements.clear()
        for slot, idx in enumerate(hyp.order):
            if 0 <= idx < len(group_ids):
                sprite.placements[slot] = group_ids[idx]
        self.window_ref.history.commit("hypothèse appliquée")
        self.requestTab.emit("atelier")
        self.statusMessage.emit(f"Hypothèse « {hyp.name} » appliquée au canevas.")

    # -- inférence ----------------------------------------------------------

    def run_inference(self) -> None:
        project = self.window_ref.project
        obs = inference.observations(project)
        self._obs = obs
        if not obs:
            self.rule_info.setText(
                "Aucune observation : validez au moins un sprite dont les tuiles "
                "ont un indice de stockage.")
            self.rule_table.setRowCount(0)
            return
        models = inference.infer(obs)
        self._models = models
        self.rule_table.setRowCount(min(len(models), 15))
        for row, m in enumerate(models[:15]):
            self.rule_table.setItem(row, 0, QTableWidgetItem(m.label))
            self.rule_table.setItem(row, 1, QTableWidgetItem(f"{m.exact}/{m.total}"))
            self.rule_table.setItem(row, 2, QTableWidgetItem(f"{m.tiles_ok}/{m.tiles_total}"))
            item = QTableWidgetItem(f"{m.score():.2f}")
            if row == 0:
                item.setForeground(QColor(theme.OK))
            self.rule_table.setItem(row, 3, item)
        if models:
            self.rule_table.selectRow(0)
            best = models[0]
            self.rule_info.setText(
                f"{len(obs)} sprite(s) analysé(s) — meilleur modèle : « {best.label} » "
                f"({best.exact}/{best.total} sprites exacts, "
                f"{best.tile_ratio * 100:.0f} % des tuiles).")
        self._refresh_log()

    def make_recipe(self) -> None:
        row = self.rule_table.currentRow()
        if row < 0 or row >= len(self._models):
            return
        model = self._models[row]
        project = self.window_ref.project
        recipe = inference.make_recipe(model, self._obs, name=model.label)
        project.recipes = [r for r in project.recipes if r.name != recipe.name]
        project.recipes.append(recipe)
        self.window_ref.history.commit("recette créée")
        self.statusMessage.emit(f"Recette « {recipe.name} » créée ({len(recipe.mapping)} cases).")

    def apply_recipe(self, all_bank: bool) -> None:
        project = self.window_ref.project
        if not project.recipes:
            QMessageBox.information(self, "Recette", "Créez d'abord une recette.")
            return
        from PySide6.QtWidgets import QInputDialog
        names = [r.name for r in project.recipes]
        name, ok = QInputDialog.getItem(self, "Recette", "Recette à appliquer :", names, 0, False)
        if not ok:
            return
        recipe = project.recipes[names.index(name)]
        sheet = project.sheet
        ordered = sheet.tiles_sorted()
        n = recipe.count
        if n <= 0:
            return

        if not all_bank:
            idx = min(self.window_ref.assembly.group_index * n, max(0, len(ordered) - n))
            group = ordered[idx:idx + n]
            if not group:
                return
            sprite = project.current
            self.window_ref.history.begin()
            sprite.placements.clear()
            base = group[0].storage_index or 0
            for slot, off in enumerate(recipe.mapping):
                if slot >= sprite.cols * sprite.rows or off < 0:
                    continue
                for t in group:
                    if t.storage_index == base + off:
                        sprite.placements[slot] = t.id
                        break
            self.window_ref.history.commit("recette appliquée")
            self.requestTab.emit("atelier")
            self.statusMessage.emit(f"Recette appliquée au groupe {self.window_ref.assembly.group_index + 1}.")
            return

        groups = len(ordered) // n
        answer = QMessageBox.question(
            self, "Appliquer à toute la banque",
            f"Générer {groups} sprites de {n} tuiles et les valider tous ?",
            QMessageBox.Yes | QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self.window_ref.history.begin()
        made = 0
        for g in range(groups):
            group = ordered[g * n:(g + 1) * n]
            base = group[0].storage_index or 0
            project.next_sprite_id += 1
            sp = Sprite(project.next_sprite_id, f"pose_{g:02d}",
                        recipe.cols, recipe.rows,
                        project.grid.tile_w, project.grid.tile_h)
            placed = inference.apply_to_sprite(recipe, [t.storage_index for t in group],
                                               base, sheet, sp)
            if placed:
                sp.validated = True
                project.sprites.append(sp)
                made += 1
        project.atlas.compute(project.validated_sprites())
        self.window_ref.history.commit("banque entière")
        self.statusMessage.emit(f"{made} sprites générés et validés.")
        self.requestTab.emit("atlas")

    # -- journal ------------------------------------------------------------

    def _refresh_log(self) -> None:
        project = self.window_ref.project
        events = project.moves.events[-500:]
        self.log_table.setRowCount(len(events))
        for row, ev in enumerate(reversed(events)):
            self.log_table.setItem(row, 0, QTableWidgetItem(ev.t.split("T")[-1][:12]))
            self.log_table.setItem(row, 1, QTableWidgetItem(ev.type))
            self.log_table.setItem(row, 2, QTableWidgetItem(str(ev.sprite)))
            self.log_table.setItem(row, 3, QTableWidgetItem("" if ev.tile is None else str(ev.tile)))
            self.log_table.setItem(row, 4, QTableWidgetItem(str(ev.frm) if ev.frm else ""))
            self.log_table.setItem(row, 5, QTableWidgetItem(str(ev.to) if ev.to else ""))
        self.log_info.setText(f"{len(project.moves.events)} événement(s) enregistré(s).")

    # -- exports ------------------------------------------------------------

    def _default_dir(self) -> str:
        from ..core.settings import default_dir
        return default_dir("graphisme")

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV",
                                              os.path.join(self._default_dir(), "analyse_placements.csv"),
                                              "CSV (*.csv)")
        if not path:
            return
        n = project_io.export_placements_csv(self.window_ref.project, path)
        self._log_export(f"CSV : {n} lignes → {path}")

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON",
                                              os.path.join(self._default_dir(), "analyse_placements.json"),
                                              "JSON (*.json)")
        if not path:
            return
        project_io.export_placements_json(self.window_ref.project, path)
        self._log_export(f"JSON → {path}")

    def export_permutations(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export permutations",
                                              os.path.join(self._default_dir(), "analyse_permutations.txt"),
                                              "Texte (*.txt)")
        if not path:
            return
        project_io.export_permutations_txt(self.window_ref.project, path)
        self._log_export(f"Permutations → {path}")

    def _log_export(self, text: str) -> None:
        self.export_log.append(text)
        self.statusMessage.emit(text)

    def refresh(self) -> None:
        self._refresh_log()
