"""Cartographie d'une ROM : bande de zones, en-tête et tables de pointeurs."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import cartography as cartography_mod

#: Couleur de chaque nature de zone.
ZONE_COLORS: dict[str, str] = {
    "vide": "#20242e",
    "données structurées": "#3f7d55",
    "code probable": "#b8860b",
    "compressé ou aléatoire": "#8b3a3a",
}


class ZoneStrip(QWidget):
    """Bande horizontale représentant la ROM, colorée par nature de zone."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.report: dict | None = None
        self.setMinimumHeight(72)

    def set_report(self, report: dict) -> None:
        self.report = report
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        rect = self.rect().adjusted(0, 0, -1, -1)
        painter.fillRect(rect, QColor("#12151c"))
        if not self.report or not self.report.get("size"):
            painter.end()
            return
        total = self.report["size"]
        width = rect.width()
        for zone in self.report["zones"]:
            x = rect.left() + int(zone["offset"] / total * width)
            zone_width = max(1, int(zone["size"] / total * width))
            painter.fillRect(QRectF(x, rect.top(), zone_width, rect.height()),
                             QColor(ZONE_COLORS.get(zone["kind"], "#444")))
        painter.setPen(QPen(QColor("#2a3140"), 1))
        painter.drawRect(rect)

        # repères tous les quarts
        painter.setPen(QPen(QColor("#4a5266"), 1, Qt.DotLine))
        for fraction in (0.25, 0.5, 0.75):
            x = rect.left() + int(fraction * width)
            painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.end()


class CartographyDialog(QDialog):
    """Affiche le rapport de cartographie d'une ROM."""

    def __init__(self, parent, report: dict, source: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Cartographie de la ROM")
        self.resize(900, 520)
        self.report = report

        root = QVBoxLayout(self)
        platform = report["platform"]
        title = platform["name"]
        if platform["title"]:
            title += f" — « {platform['title']} »"
        if platform["confidence"]:
            title += f" (confiance {platform['confidence']:.0%})"
        heading = QLabel(f"<b>{title}</b>")
        heading.setTextFormat(Qt.RichText)
        root.addWidget(heading)

        if source:
            path = QLabel(source)
            path.setProperty("hint", True)
            root.addWidget(path)

        self.strip = ZoneStrip(self)
        self.strip.set_report(report)
        root.addWidget(self.strip)

        legend = QHBoxLayout()
        for kind, color in ZONE_COLORS.items():
            swatch = QLabel()
            swatch.setFixedSize(12, 12)
            swatch.setStyleSheet(f"background:{color}; border:1px solid #2a3140;")
            legend.addWidget(swatch)
            legend.addWidget(QLabel(kind))
            legend.addSpacing(12)
        legend.addStretch(1)
        root.addLayout(legend)

        summary = report.get("summary", {})
        root.addWidget(QLabel(
            f"{summary.get('zones', 0)} zones · "
            f"{summary.get('structured_bytes', 0)} octets de données structurées · "
            f"{summary.get('compressed_bytes', 0)} octets compressés · "
            f"{summary.get('pointer_tables', 0)} tables de pointeurs"))

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Offset", "Pointeurs", "Largeur", "Ordre"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        for item in report.get("pointer_tables", []):
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [item["offset_hex"], str(item["count"]),
                      f"{item['width']} octets",
                      "gros-boutiste" if item["big_endian"] else "petit-boutiste"]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        root.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("Fermer")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

        from .i18n_qt import apply_to
        apply_to(self)


def run_cartography(parent) -> dict | None:
    """Demande un fichier, cartographie, affiche le rapport."""
    path, _ = QFileDialog.getOpenFileName(
        parent, "Cartographier une ROM", "",
        "ROMs et binaires (*.bin *.md *.smc *.sfc *.nes *.gb *.gbc *.rom *.stx *.st);;"
        "Tous les fichiers (*)")
    if not path:
        return None
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(parent, "Cartographie", f"Lecture impossible : {exc}")
        return None
    report = cartography_mod.cartography(data)
    dialog = CartographyDialog(parent, report, source=path)
    dialog.exec()
    return report
