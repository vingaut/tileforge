"""Recherche de graphismes : progression et liste des résultats.

Le balayage peut durer plusieurs dizaines de secondes : il tourne dans un
fil d'exécution séparé, l'interface reste réactive, et l'utilisateur peut
l'interrompre. Les résultats s'affichent avec un aperçu, pour trancher à
l'œil plutôt que sur une note.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressDialog,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core.formats import load_raw_bank
from ..core.scan import DEFAULT_BUDGET, Candidate, Scanner, ScanReport
from .widgets import to_qimage

# ---------------------------------------------------------------------------
# Fil d'exécution
# ---------------------------------------------------------------------------


class ScanWorker(QThread):
    """Exécute un balayage hors du fil graphique."""

    progress = Signal(float, str)
    finished_report = Signal(object)
    failed = Signal(str)

    def __init__(self, data: bytes, formats, compressions, options: dict,
                 source: str = "", parent=None):
        super().__init__(parent)
        self.data = data
        self.formats = formats
        self.compressions = compressions
        self.options = options
        self.source = source
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:  # pragma: no cover - dépend du fil
        try:
            scanner = Scanner(self.data, self.formats, self.compressions,
                              source=self.source)
            report = scanner.run(
                progress=lambda fraction, message: self.progress.emit(fraction, message),
                should_stop=lambda: self._cancelled,
                **self.options)
            self.finished_report.emit(report)
        except Exception as exc:  # noqa: BLE001 - remonté à l'interface
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
# Aperçu d'un candidat
# ---------------------------------------------------------------------------


def candidate_image(data: bytes, candidate: Candidate, max_tiles: int = 128):
    """Décode un candidat en image d'aperçu (``None`` si indécodable)."""
    from ..core.compression import decompress
    from ..core.formats import FORMATS_BY_KEY

    fmt = FORMATS_BY_KEY.get(candidate.tile_format)
    if fmt is None:
        return None
    if candidate.compression:
        try:
            blob = decompress(candidate.compression, data, candidate.offset)
        except Exception:
            return None
    else:
        blob = data[candidate.offset:candidate.offset + candidate.size]
    if not blob:
        return None
    count = max(1, min(len(blob) // max(1, fmt.real_bytes), max_tiles))
    try:
        bank = load_raw_bank(None, 0, count, fmt, per_row=16, data=blob)
    except Exception:
        return None
    return bank.image


# ---------------------------------------------------------------------------
# Dialogue de résultats
# ---------------------------------------------------------------------------


class ScanResultsDialog(QDialog):
    """Liste les blocs trouvés, avec aperçu et choix."""

    def __init__(self, parent, data: bytes, report: ScanReport):
        super().__init__(parent)
        self.setWindowTitle("Blocs de graphismes trouvés")
        self.resize(980, 560)
        self.data = data
        self.report = report
        self.candidate: Candidate | None = None

        root = QVBoxLayout(self)
        summary = QLabel(
            f"{len(report.candidates)} bloc(s) · {report.tested} positions examinées · "
            f"{report.elapsed:.1f} s"
            + (" · recherche interrompue (budget ou annulation)" if report.truncated else ""))
        summary.setProperty("hint", True)
        root.addWidget(summary)

        body = QHBoxLayout()
        root.addLayout(body, 1)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Offset", "Compression", "Taille", "Tuiles", "Note"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.currentCellChanged.connect(self._on_selection)
        self.table.doubleClicked.connect(self._accept_current)
        body.addWidget(self.table, 3)

        right = QVBoxLayout()
        self.preview = QLabel("Sélectionnez un bloc")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(300, 240)
        self.preview.setStyleSheet("background:#12151c; border:1px solid #2a3140;")
        right.addWidget(self.preview, 1)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setProperty("hint", True)
        right.addWidget(self.detail)
        body.addLayout(right, 2)

        for candidate in report.candidates:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [f"0x{candidate.offset:06X}", candidate.compression or "brut",
                      str(candidate.size), str(candidate.tiles),
                      f"{candidate.score:.3f}"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, candidate)
                self.table.setItem(row, column, item)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Charger ce bloc")
        buttons.button(QDialogButtonBox.Cancel).setText("Fermer")
        buttons.accepted.connect(self._accept_current)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if report.candidates:
            self.table.selectRow(0)

    def _on_selection(self, row: int, column: int, previous_row: int, previous_column: int) -> None:
        if row < 0:
            return
        item = self.table.item(row, 0)
        candidate = item.data(Qt.UserRole) if item else None
        if candidate is None:
            return
        image = candidate_image(self.data, candidate)
        if image is None:
            self.preview.setText("Aperçu indisponible")
        else:
            pixmap = QPixmap.fromImage(to_qimage(image))
            if pixmap.width() > 460:
                pixmap = pixmap.scaledToWidth(460, Qt.SmoothTransformation)
            self.preview.setPixmap(pixmap)
        self.detail.setText(
            f"{candidate.tile_format} · {candidate.tiles} tuiles · "
            f"note {candidate.score:.3f}")

    def _accept_current(self) -> None:
        row = self.table.currentRow()
        if row < 0 and self.table.rowCount():
            row = 0
        if row < 0:
            return
        item = self.table.item(row, 0)
        self.candidate = item.data(Qt.UserRole) if item else None
        self.accept()


# ---------------------------------------------------------------------------
# Lancement
# ---------------------------------------------------------------------------


def run_scan(parent, data: bytes, formats, compressions, *, source: str = "",
             budget: float = DEFAULT_BUDGET, threshold: float = 0.45,
             title: str = "Recherche de graphismes"):
    """Lance un balayage avec progression, puis affiche les résultats.

    Renvoie le candidat choisi, ou ``None``.
    """
    dialog = QProgressDialog("Analyse du fichier…", "Interrompre", 0, 100, parent)
    dialog.setWindowTitle(title)
    dialog.setWindowModality(Qt.WindowModal)
    dialog.setMinimumDuration(0)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)

    # workers=0 : un processus par décompresseur, dans la limite des cœurs.
    options = {"budget": budget, "threshold": threshold, "workers": 0}
    worker = ScanWorker(data, formats, compressions, options, source=source,
                        parent=dialog)

    def on_progress(fraction: float, message: str) -> None:
        dialog.setValue(int(max(0.0, min(1.0, fraction)) * 100))
        if message:
            dialog.setLabelText(f"{title} — {message}")

    worker.progress.connect(on_progress)
    dialog.canceled.connect(worker.cancel)

    result: dict = {}

    def on_finished(report) -> None:
        result["report"] = report
        dialog.close()

    def on_failed(message: str) -> None:
        result["error"] = message
        dialog.close()

    worker.finished_report.connect(on_finished)
    worker.failed.connect(on_failed)
    worker.start()
    dialog.exec()
    worker.wait(3000)

    if "error" in result:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(parent, title, f"Recherche impossible : {result['error']}")
        return None
    report = result.get("report")
    if report is None:
        return None
    if not report.candidates:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            parent, title,
            "Aucun bloc de graphismes trouvé.\n\n"
            "Essayez un autre format de tuiles, un budget plus long, "
            "ou vérifiez que le fichier contient bien des graphismes.")
        return None
    results = ScanResultsDialog(parent, data, report)
    if results.exec() != QDialog.Accepted:
        return None
    return results.candidate
