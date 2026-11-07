"""Comparaison automatique des grilles d'assemblage (plan §2.6).

L'outil essaie toutes les grilles plausibles sur un même paquet de tuiles,
classe les résultats par coût et montre un aperçu de la meilleure disposition
pour chacune.  C'est ce qui permet de trancher entre « 3 × 4 », « 2 × 4 »,
« 4 × 3 »… sans faire les tests à la main.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..assemble.cost import build_cost_model
from ..assemble.hypotheses import rank as rank_hypotheses
from ..assemble.solvers import solve_greedy
from ..core.model import Sprite
from . import theme
from .widgets import fit_to_screen, hint_label, image_to_pixmap


class GridTesterDialog(QDialog):
    """Essaie un ensemble de grilles et classe les hypothèses."""

    def __init__(self, parent, sheet, tile_ids: list[int], current: tuple[int, int]):
        super().__init__(parent)
        self.setWindowTitle("Quelle grille pour ces tuiles ?")
        fit_to_screen(self, 820, 620)
        self.sheet = sheet
        self.tile_ids = tile_ids
        self.current = current
        self.results = []
        self.chosen = None

        root = QVBoxLayout(self)
        root.addWidget(hint_label(
            "Chaque grille est testée sur les mêmes tuiles : le coût indique la "
            "cohérence des raccords (plus bas = mieux). Attention, une grille plus "
            "petite a mécaniquement moins de raccords à rater : les grilles dont le "
            "nombre de tuiles divise exactement la banque passent donc en premier, "
            "puis le coût tranche entre elles."))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Aperçu", "Grille", "Tuiles / sprite", "Sprites dans la banque", "Coût"])
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QSize(64, 64))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (2, 3, 4):
            header.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 76)
        self.table.verticalHeader().setDefaultSectionSize(70)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self.accept())
        root.addWidget(self.table, 1)

        self.info = QLabel("")
        self.info.setProperty("hint", True)
        root.addWidget(self.info)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.run_tests()

    # ------------------------------------------------------------------

    def run_tests(self) -> None:
        total_tiles = len(self.tile_ids)
        candidates = []
        for cols in range(1, 7):
            for rows in range(1, 7):
                n = cols * rows
                if n < 4 or n > 24 or n > total_tiles:
                    continue
                candidates.append((cols, rows, n))

        rows_out = []
        for cols, rows, n in candidates:
            group = self.tile_ids[:n]
            try:
                model = build_cost_model(self.sheet, group)
            except Exception:
                continue
            hyps = rank_hypotheses(model, cols, rows, limit=6)
            if not hyps:
                continue
            best_order = hyps[0][0].order
            best_cost = hyps[0][1]
            if n <= 12:
                try:
                    for sol in solve_greedy(model, cols, rows, restarts=2):
                        if sol.cost < best_cost:
                            best_cost, best_order = sol.cost, sol.order
                except Exception:
                    pass
            # Une grille dont le nombre de tuiles ne divise pas la banque est
            # peu plausible : on la pénalise légèrement au classement.
            bank = len(self.sheet.tiles)
            exact = (bank % n == 0) if bank else True
            rows_out.append({
                "cols": cols, "rows": rows, "n": n,
                "cost": best_cost, "order": best_order,
                "label": hyps[0][0].name,
                "exact": exact,
                "adjusted": best_cost,
            })

        # Priorité 1 : le nombre de tuiles doit diviser la banque (indice fort
        # du plan §2.6). Priorité 2 : le coût des raccords.
        rows_out.sort(key=lambda r: (0 if r["exact"] else 1, r["adjusted"]))
        self.results = rows_out
        self.table.setRowCount(len(rows_out))
        for i, r in enumerate(rows_out):
            sprite = Sprite(0, "apercu", r["cols"], r["rows"],
                            self.sheet.tile_image(self.tile_ids[0]).w,
                            self.sheet.tile_image(self.tile_ids[0]).h)
            for slot, idx in enumerate(r["order"]):
                if 0 <= idx < r["n"]:
                    sprite.placements[slot] = self.tile_ids[idx]
            pm = image_to_pixmap(sprite.render(self.sheet), max_size=64)

            item = QTableWidgetItem()
            item.setIcon(pm)
            self.table.setItem(i, 0, item)
            name = QTableWidgetItem(f"{r['cols']} × {r['rows']}   ({r['label']})")
            if (r["cols"], r["rows"]) == self.current:
                name.setText(name.text() + "   ← actuelle")
            self.table.setItem(i, 1, name)
            self.table.setItem(i, 2, QTableWidgetItem(str(r["n"])))
            bank = len(self.sheet.tiles)
            exact = "oui" if r["exact"] else "non"
            self.table.setItem(i, 3, QTableWidgetItem(f"{bank // r['n']}  ({exact})"))
            cost_item = QTableWidgetItem(f"{r['cost']:.3f}")
            if i == 0:
                cost_item.setForeground(QColor(theme.OK))
            self.table.setItem(i, 4, cost_item)

        if rows_out:
            self.table.selectRow(0)
            best = rows_out[0]
            self.info.setText(
                f"{len(rows_out)} grilles testées sur {min(24, total_tiles)} tuiles — "
                f"meilleure : {best['cols']} × {best['rows']} "
                f"(coût {best['cost']:.3f}, {bank // best['n'] if bank % best['n'] == 0 else '—'} "
                f"sprites par banque).")

    # ------------------------------------------------------------------

    def accept(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.results):
            return
        self.chosen = self.results[row]
        super().accept()

    def chosen_grid(self):
        return (self.chosen["cols"], self.chosen["rows"]) if self.chosen else None

    def chosen_order(self):
        return self.chosen["order"] if self.chosen else None
