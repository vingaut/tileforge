"""Dialogue « Mémoire d'émulateur » : exécuter une ROM et lire sa mémoire.

Quand un jeu décompresse ses graphismes à l'exécution, on ne peut pas les
retrouver dans la ROM. Ce dialogue lance un cœur libretro sans fenêtre, avance
de quelques centaines de trames, puis écrit la RAM système, la VRAM et la SRAM
dans un dossier. Les fichiers produits se rouvrent comme des banques brutes.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..core import archives as archives_mod
from ..core import emulation as emulation_mod
from ..core.formats import FORMATS
from ..core.i18n import t

#: Format de tuiles proposé d'après la machine du cœur.
DEFAULT_FORMATS: dict[str, str] = {
    "gba": "gba_4bpp", "gameboy": "gameboy", "snes": "snes_4bpp",
    "nes": "nes", "megadrive": "megadrive", "atarist": "st_sprite_4pl",
    "pcengine": "pc_engine", "c64": "c64", "amiga": "amiga_sprite",
}


class MemoryWorker(QThread):
    """Exécute la ROM et, si demandé, balaye la mémoire, hors du fil graphique."""

    finished_result = Signal(object)
    failed = Signal(str)

    def __init__(self, core: str, rom: str, frames: int, buttons: str,
                 output: str, screenshot: bool, scan: bool, tile_format: str,
                 member: str = "", system_dir: str = "", parent=None):
        super().__init__(parent)
        self.core = core
        self.rom = rom
        self.frames = frames
        self.buttons = buttons
        self.output = output
        self.screenshot = screenshot
        self.scan = scan
        self.tile_format = tile_format
        self.member = member
        self.system_dir = system_dir

    def run(self) -> None:  # pragma: no cover - dépend du fil
        try:
            result = emulation_mod.run_rom(
                self.core, self.rom, frames=self.frames, buttons=self.buttons,
                output_dir=self.output, screenshot=self.screenshot,
                member=self.member, system_dir=self.system_dir or None)
            if self.scan:
                snapshot = emulation_mod.MemorySnapshot.load(result["manifest"])
                result["scan"] = emulation_mod.scan_snapshot(
                    snapshot, self.tile_format, compressions=[],
                    budget=60.0, max_candidates=8)
            self.finished_result.emit(result)
        except Exception as exc:  # noqa: BLE001 - remonté à l'interface
            self.failed.emit(str(exc))


class EmulatorDialog(QDialog):
    """Choisit un cœur, une ROM et un dossier, puis extrait la mémoire."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mémoire d'émulateur")
        self.resize(680, 360)
        self.worker: MemoryWorker | None = None

        root = QVBoxLayout(self)
        intro = QLabel(
            "Exécute la ROM dans un cœur libretro puis lit la RAM et la VRAM : "
            "les graphismes y sont déjà décompressés. Installez un cœur "
            "(RetroArch, paquet système) ou choisissez un fichier .so.")
        intro.setWordWrap(True)
        intro.setProperty("hint", True)
        root.addWidget(intro)

        form = QFormLayout()
        self.core_combo = QComboBox()
        self.core_combo.setEditable(True)
        for core in emulation_mod.discover_cores():
            label = core.name
            if core.system:
                label += f" — {core.system}"
            self.core_combo.addItem(label, core.path)
        if self.core_combo.count() == 0:
            self.core_combo.addItem("(aucun cœur trouvé)", "")
        browse_core = QPushButton("Parcourir…")
        browse_core.clicked.connect(self._browse_core)
        core_row = QHBoxLayout()
        core_row.addWidget(self.core_combo, 1)
        core_row.addWidget(browse_core)
        form.addRow("Cœur libretro", core_row)

        self.rom_edit = QLineEdit()
        browse_rom = QPushButton("Parcourir…")
        browse_rom.clicked.connect(self._browse_rom)
        rom_row = QHBoxLayout()
        rom_row.addWidget(self.rom_edit, 1)
        rom_row.addWidget(browse_rom)
        form.addRow("ROM", rom_row)

        self.member_combo = QComboBox()
        self.member_label = QLabel("Membre")
        self.member_combo.setVisible(False)
        self.member_label.setVisible(False)
        member_row = QHBoxLayout()
        member_row.addWidget(self.member_label)
        member_row.addWidget(self.member_combo, 1)
        form.addRow("", member_row)
        self.rom_edit.editingFinished.connect(self._refresh_members)

        self.frames_spin = QSpinBox()
        self.frames_spin.setRange(1, 100000)
        self.frames_spin.setValue(600)
        self.frames_spin.setSuffix(t(" trames"))
        form.addRow("Trames à exécuter", self.frames_spin)

        self.buttons_edit = QLineEdit()
        self.buttons_edit.setPlaceholderText("start@120-140,a@200")
        form.addRow("Script d'entrée", self.buttons_edit)

        self.system_edit = QLineEdit()
        self.system_edit.setPlaceholderText(
            "dossier des BIOS/firmwares (Fuse, VICE, Cap32…)")
        browse_system = QPushButton("Parcourir…")
        browse_system.clicked.connect(self._browse_system)
        system_row = QHBoxLayout()
        system_row.addWidget(self.system_edit, 1)
        system_row.addWidget(browse_system)
        form.addRow("Dossier système", system_row)

        self.output_edit = QLineEdit(str(Path.cwd() / "memoire"))
        browse_output = QPushButton("Parcourir…")
        browse_output.clicked.connect(self._browse_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(browse_output)
        form.addRow("Dossier de sortie", output_row)

        self.screenshot_check = QCheckBox("Enregistrer une capture")
        self.screenshot_check.setChecked(True)
        form.addRow("", self.screenshot_check)

        self.scan_check = QCheckBox("Balayer la mémoire après extraction")
        self.scan_check.toggled.connect(self._scan_toggled)
        form.addRow("", self.scan_check)

        self.format_combo = QComboBox()
        for fmt in FORMATS:
            self.format_combo.addItem(fmt.name, fmt.key)
        self.format_combo.setEnabled(False)
        form.addRow("Format de tuiles", self.format_combo)
        root.addLayout(form)

        self.status = QLabel("")
        self.status.setProperty("hint", True)
        root.addWidget(self.status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        buttons = QDialogButtonBox()
        self.start_button = buttons.addButton(
            "Extraire la mémoire", QDialogButtonBox.ActionRole)
        self.start_button.clicked.connect(self._start)
        self.close_button = buttons.addButton(QDialogButtonBox.Close)
        self.close_button.clicked.connect(self.reject)
        root.addWidget(buttons)

        self.core_combo.currentIndexChanged.connect(lambda _index: self._core_changed())
        self._core_changed()

        from .i18n_qt import apply_to
        apply_to(self)

    # -- chemins ------------------------------------------------------------

    def _browse_core(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un cœur libretro", "",
            "Cœurs libretro (*.so *.dylib *.dll);;Tous les fichiers (*)")
        if path:
            self.core_combo.addItem(path, path)
            self.core_combo.setCurrentIndex(self.core_combo.count() - 1)

    def _browse_rom(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une ROM", "",
            "ROMs et archives (*.bin *.md *.smc *.sfc *.nes *.gb *.gbc *.gba "
            "*.pce *.a26 *.dsk *.d64 *.st *.stx *.rom *.zip *.7z);;"
            "Tous les fichiers (*)")
        if path:
            self.rom_edit.setText(path)
            self._refresh_members()

    def _refresh_members(self) -> None:
        """Remplit la liste des membres si la ROM est une archive."""
        path = self.rom_edit.text().strip()
        self.member_combo.clear()
        entries = []
        if path and Path(path).exists() and archives_mod.is_archive(path):
            try:
                entries = archives_mod.list_archive(path)
            except Exception:
                entries = []
        for entry in entries:
            self.member_combo.addItem(
                f"{entry.name} — {entry.size} octets", entry.name)
        visible = bool(entries)
        self.member_combo.setVisible(visible)
        self.member_label.setVisible(visible)
        if entries:
            try:
                chosen = archives_mod.choose_member(entries)
            except Exception:
                chosen = entries[0].name
            index = self.member_combo.findData(chosen)
            if index >= 0:
                self.member_combo.setCurrentIndex(index)

    def _browse_system(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier système", self.system_edit.text())
        if folder:
            self.system_edit.setText(folder)

    def _browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choisir un dossier de sortie", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)

    def _core_changed(self) -> None:
        path = self.core_combo.currentData() or self.core_combo.currentText()
        system = emulation_mod.guess_system(Path(str(path)).name)
        key = DEFAULT_FORMATS.get(system)
        if key:
            index = self.format_combo.findData(key)
            if index >= 0:
                self.format_combo.setCurrentIndex(index)

    def _scan_toggled(self, checked: bool) -> None:
        self.format_combo.setEnabled(checked)

    # -- extraction ---------------------------------------------------------

    def _start(self) -> None:
        core = str(self.core_combo.currentData() or self.core_combo.currentText())
        rom = self.rom_edit.text().strip()
        if not core or not Path(core).exists():
            QMessageBox.warning(self, "Mémoire d'émulateur",
                                "Choisissez un cœur libretro.")
            return
        if not rom or not Path(rom).exists():
            QMessageBox.warning(self, "Mémoire d'émulateur",
                                "Choisissez une ROM.")
            return
        self.start_button.setEnabled(False)
        self.progress.setVisible(True)
        self.status.setText("Extraction en cours…")
        member = (str(self.member_combo.currentData())
                  if self.member_combo.count() else "")
        self.worker = MemoryWorker(
            core, rom, self.frames_spin.value(), self.buttons_edit.text().strip(),
            self.output_edit.text().strip(), self.screenshot_check.isChecked(),
            self.scan_check.isChecked(), str(self.format_combo.currentData()),
            member=member, system_dir=self.system_edit.text().strip(),
            parent=self)
        self.worker.finished_result.connect(self._finished)
        self.worker.failed.connect(self._failed)
        self.worker.start()

    def _finished(self, result: dict) -> None:
        self.progress.setVisible(False)
        self.start_button.setEnabled(True)
        snapshot = emulation_mod.MemorySnapshot.load(result["manifest"])
        lines = [f"{len(snapshot.regions)} région(s) mémoire, "
                 f"{snapshot.frames} trames exécutées.",
                 f"Dossier : {result['directory']}"]
        if result.get("screenshot"):
            lines.append(f"Capture : {result['screenshot']}")
        if result.get("scan"):
            total = sum(len(region["candidates"])
                        for region in result["scan"]["regions"])
            lines.append(f"Candidats graphiques : {total}")
            for region in result["scan"]["regions"]:
                for candidate in region["candidates"][:3]:
                    lines.append(
                        f"  {region['region']} +0x{candidate['offset']:X} — "
                        f"note {candidate['score']:.2f}")
        self.status.setText("Extraction terminée.")
        box = QMessageBox(self)
        box.setWindowTitle("Mémoire extraite")
        box.setText("\n".join(lines))
        open_button = box.addButton("Ouvrir le dossier", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if box.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(result["directory"]))

    def _failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.start_button.setEnabled(True)
        self.status.setText("Échec de l'extraction.")
        QMessageBox.critical(self, "Mémoire d'émulateur", message)

    def reject(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
        super().reject()


def run_emulator(parent) -> None:
    """Ouvre le dialogue de mémoire d'émulateur."""
    EmulatorDialog(parent).exec()
