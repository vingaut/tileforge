"""Fenêtre de désassemblage 6502, 65816 et Z80."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..core import disasm6502, disasm65816, disasm68000, disasmz80


class DisasmDialog(QDialog):
    """Affiche un listing 65816, en mode linéaire ou en suivant le code."""

    def __init__(self, parent, path: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Désassembler (65816)")
        self.resize(860, 620)
        self.data = b""
        self.path = ""

        root = QVBoxLayout(self)

        source = QHBoxLayout()
        source.addWidget(QLabel("Fichier"))
        self.path_edit = QLineEdit(path)
        source.addWidget(self.path_edit, 1)
        browse = QPushButton("Parcourir…")
        browse.clicked.connect(self._browse)
        source.addWidget(browse)
        root.addLayout(source)

        options = QHBoxLayout()
        from PySide6.QtWidgets import QComboBox

        options.addWidget(QLabel("Processeur"))
        self.cpu_combo = QComboBox()
        self.cpu_combo.addItem("65816 (Super Nintendo)", "65816")
        self.cpu_combo.addItem("6502 (NES, C64, Apple II…)", "6502")
        self.cpu_combo.addItem("Z80 (Spectrum, CPC, MSX…)", "z80")
        self.cpu_combo.addItem("SM83 (Game Boy)", "sm83")
        self.cpu_combo.addItem("68000 (Mega Drive, Amiga, Atari ST…)", "68000")
        self.cpu_combo.currentIndexChanged.connect(self.run_disasm)
        options.addWidget(self.cpu_combo)

        options.addWidget(QLabel("Chargement"))
        self.base = QSpinBox()
        self.base.setRange(0, 0xFFFF)
        self.base.setDisplayIntegerBase(16)
        self.base.setPrefix("0x")
        self.base.setValue(0)
        self.base.setToolTip(
            "Adresse de chargement du fichier : 0x8000 pour une cartouche NES, "
            "0 pour une image mémoire. Utilisé par le 6502.")
        self.base.valueChanged.connect(self.run_disasm)
        options.addWidget(self.base)

        self.follow = QCheckBox("Suivre le fil d'exécution")
        self.follow.setChecked(True)
        self.follow.setToolTip(
            "Partir de l'adresse donnée et suivre les sauts et sous-programmes, "
            "au lieu de désassembler octet par octet.")
        options.addWidget(self.follow)

        options.addWidget(QLabel("Adresse"))
        self.address = QSpinBox()
        self.address.setRange(0, 0xFFFFFF)
        self.address.setDisplayIntegerBase(16)
        self.address.setPrefix("0x")
        self.address.setValue(0x8000)
        options.addWidget(self.address)

        options.addWidget(QLabel("Instructions"))
        self.count = QSpinBox()
        self.count.setRange(8, 20000)
        self.count.setValue(400)
        self.count.setSingleStep(100)
        options.addWidget(self.count)

        self.run_button = QPushButton("Désassembler")
        self.run_button.clicked.connect(self.run_disasm)
        options.addWidget(self.run_button)
        options.addStretch(1)
        root.addLayout(options)

        self.info = QLabel("")
        self.info.setProperty("hint", True)
        root.addWidget(self.info)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.view.setFont(QFont("DejaVu Sans Mono", 9))
        root.addWidget(self.view, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("Fermer")
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        from .i18n_qt import apply_to
        apply_to(self)
        if path:
            self.load(path)

    # -- chargement --------------------------------------------------------

    def _browse(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Choisir une ROM", "",
            "ROMs et binaires (*.bin *.md *.smc *.sfc *.nes *.gb *.rom);;"
            "Tous les fichiers (*)")
        if chosen:
            self.load(chosen)

    def load(self, path: str) -> None:
        try:
            with open(path, "rb") as handle:
                self.data = handle.read()
        except OSError as exc:
            self.info.setText(f"Lecture impossible : {exc}")
            return
        self.path = path
        self.path_edit.setText(path)
        self.info.setText(f"{len(self.data)} octets chargés.")
        self.run_disasm()

    # -- exécution ---------------------------------------------------------

    def run_disasm(self) -> None:
        if not self.data:
            self.load(self.path_edit.text().strip())
            if not self.data:
                return
        count = self.count.value()
        cpu = self.cpu_combo.currentData()
        extra = {}
        if cpu == "sm83":
            module = disasmz80
            extra["variant"] = "sm83"
        elif cpu == "z80":
            module = disasmz80
        elif cpu == "6502":
            module = disasm6502
        elif cpu == "68000":
            module = disasm68000
        else:
            module = disasm65816
        uses_base = cpu in ("6502", "z80", "sm83", "68000")
        base = self.base.value()
        if self.follow.isChecked():
            entry = self.address.value()
            try:
                if uses_base:
                    instructions = module.trace(self.data, entry,
                                                max_instructions=count, base=base,
                                                **extra)
                else:
                    instructions = module.trace(self.data, entry,
                                                max_instructions=count)
            except Exception as exc:  # noqa: BLE001 - remonté à l'écran
                self.info.setText(f"Traçage impossible : {exc}")
                return
            self.info.setText(
                f"{len(instructions)} instructions tracées depuis 0x{entry:04X}")
        else:
            offset = self.address.value()
            if offset >= len(self.data):
                self.info.setText("Adresse hors du fichier.")
                return
            instructions = (module.disassemble(self.data, offset, count, base=base,
                                               **extra)
                            if uses_base else module.disassemble(self.data, offset, count))
            self.info.setText(
                f"{len(instructions)} instructions à partir de 0x{offset:06X}")
        self.view.setPlainText(module.format_listing(instructions))


def run_disasm(parent) -> None:
    """Demande une ROM et ouvre le désassembleur."""
    path, _ = QFileDialog.getOpenFileName(
        parent, "Désassembler une ROM", "",
        "ROMs et binaires (*.bin *.md *.smc *.sfc *.nes *.gb *.rom);;"
        "Tous les fichiers (*)")
    if not path:
        return
    dialog = DisasmDialog(parent, path)
    dialog.exec()
