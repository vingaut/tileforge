"""Boîtes de dialogue : choix de machine, banque brute, palette."""

from __future__ import annotations

import contextlib
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core import archives
from ..core.compression import DECOMPRESSORS, decompress
from ..core.formats import (
    FORMATS,
    FORMATS_BY_KEY,
    LAYOUTS,
    TileFormat,
    load_raw_bank,
    scan_tile_sizes,
)
from ..core.palettes import BUILTIN_PALETTES, ROM_PALETTES, Palette, read_rom_palette
from ..core.profiles import GameProfile
from ..core.systems import SYSTEMS
from . import theme
from .widgets import fit_to_screen, image_to_pixmap

# ---------------------------------------------------------------------------
# Choix de la machine
# ---------------------------------------------------------------------------


class SystemPickerDialog(QDialog):
    """Catalogue des consoles, ordinateurs et bornes d'arcade."""

    def __init__(self, parent=None, current_key: str = "", detected: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Résolutions des machines")
        fit_to_screen(self, 860, 620)
        self._selected = None
        self._detected = set(detected or [])

        root = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addWidget(QLabel("Filtrer :"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("nom, famille, résolution…")
        self.filter_edit.textChanged.connect(self._apply_filter)
        head.addWidget(self.filter_edit, 1)
        self.only_compatible = QCheckBox("Seulement les machines proches de la résolution détectée")
        self.only_compatible.toggled.connect(self._apply_filter)
        head.addWidget(self.only_compatible)
        root.addLayout(head)

        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.currentItemChanged.connect(self._on_select)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        split.addWidget(self.list)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 0, 0, 0)
        self.title = QLabel("—")
        self.title.setStyleSheet("font-size: 17px; font-weight: 600;")
        self.subtitle = QLabel("")
        self.subtitle.setProperty("dim", True)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.RichText)
        rl.addWidget(self.title)
        rl.addWidget(self.subtitle)
        rl.addSpacing(8)
        rl.addWidget(self.detail, 1)
        split.addWidget(right)
        split.setSizes([420, 420])
        root.addWidget(split, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._populate(current_key)

    def _populate(self, current_key: str) -> None:
        families = {"console": "Consoles", "computer": "Ordinateurs",
                    "arcade": "Bornes d'arcade"}
        for fam, title in families.items():
            header = QListWidgetItem(title.upper())
            header.setFlags(Qt.NoItemFlags)
            header.setForeground(QColor(theme.TEXT_DIM))
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            self.list.addItem(header)
            for spec in SYSTEMS:
                if spec.family != fam:
                    continue
                res = ", ".join(f"{w}×{h}" for w, h in spec.resolutions[:3])
                item = QListWidgetItem(f"  {spec.name}")
                item.setData(Qt.UserRole, spec.key)
                item.setToolTip(f"{res} — {spec.colors} couleurs — {spec.notes}")
                if spec.key in self._detected:
                    item.setForeground(QColor(theme.OK))
                self.list.addItem(item)
                if spec.key == current_key:
                    self.list.setCurrentItem(item)

    def _apply_filter(self) -> None:
        text = self.filter_edit.text().strip().lower()
        compat = self.only_compatible.isChecked()
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.UserRole) is None:
                continue
            spec = next(s for s in SYSTEMS if s.key == item.data(Qt.UserRole))
            visible = True
            if text:
                hay = " ".join([spec.name, spec.family, str(spec.year),
                                " ".join(f"{w}x{h}" for w, h in spec.resolutions),
                                spec.notes]).lower()
                visible = text in hay
            if compat and self._detected and spec.key not in self._detected:
                visible = False
            item.setHidden(not visible)

    def _on_select(self, item, _prev=None) -> None:
        if item is None or item.data(Qt.UserRole) is None:
            return
        spec = next(s for s in SYSTEMS if s.key == item.data(Qt.UserRole))
        self._selected = spec
        self.title.setText(spec.name)
        fam = {"console": "console", "computer": "ordinateur",
               "arcade": "borne d'arcade"}.get(spec.family, spec.family)
        self.subtitle.setText(f"{fam.capitalize()} · {spec.year}")
        rows = []
        rows.append(f"<b>Résolutions</b> : {', '.join(f'{w}×{h}' for w, h in spec.resolutions)}")
        rows.append(f"<b>Couleurs simultanées</b> : {spec.colors}")
        rows.append(f"<b>Profondeur des tuiles</b> : {spec.bpp} bits/pixel")
        rows.append(f"<b>Tailles de tuile</b> : {', '.join(f'{w}×{h}' for w, h in spec.tile_sizes)}")
        if spec.pixel_aspect != 1.0:
            rows.append(f"<b>Rapport de pixel</b> : {spec.pixel_aspect:.3f}")
        rows.append(f"<br><span style='color:{theme.TEXT_DIM}'>{spec.notes}</span>")
        self.detail.setText("<br>".join(rows))

    def selected_system(self):
        return self._selected


# ---------------------------------------------------------------------------
# Banque brute
# ---------------------------------------------------------------------------


class RawBankDialog(QDialog):
    """Chargement d'une banque binaire : fichier, compression, offset, format."""

    def __init__(self, parent=None, path: str = "", system_key: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Ouvrir une banque brute")
        fit_to_screen(self, 1040, 700)
        self._path = path
        self._preview_image = None
        self._result = None
        self._raw = b""
        self._decoded = b""
        self._member = ""

        root = QVBoxLayout(self)

        src = QHBoxLayout()
        src.addWidget(QLabel("Fichier"))
        self.path_edit = QLineEdit(path)
        src.addWidget(self.path_edit, 1)
        browse = QPushButton("Parcourir…")
        browse.clicked.connect(self._browse)
        src.addWidget(browse)
        root.addLayout(src)

        member_row = QHBoxLayout()
        self.member_label = QLabel("Membre")
        self.member_combo = QComboBox()
        self.member_combo.setVisible(False)
        self.member_label.setVisible(False)
        self.member_combo.currentIndexChanged.connect(self._member_changed)
        member_row.addWidget(self.member_label)
        member_row.addWidget(self.member_combo, 1)
        root.addLayout(member_row)
        self.path_edit.editingFinished.connect(self._refresh_archive)

        body = QHBoxLayout()
        root.addLayout(body, 1)

        left = QWidget()
        form_box = QVBoxLayout(left)
        form_box.setContentsMargins(0, 0, 0, 0)

        # -- format de tuile
        gb = QGroupBox("Format")
        form = QFormLayout(gb)
        self.format_combo = QComboBox()
        self.format_combo.addItem("Personnalisé…", "custom")
        for f in FORMATS:
            self.format_combo.addItem(f.name, f.key)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        form.addRow("Préréglage", self.format_combo)

        identify_row = QHBoxLayout()
        self.identify_btn = QPushButton("Identifier le format…")
        self.identify_btn.setToolTip(
            "Analyse le bloc à l'offset courant et propose le format de tuiles "
            "qui l'explique le mieux (taille, profondeur, disposition).")
        self.identify_btn.clicked.connect(self._identify_format)
        identify_row.addWidget(self.identify_btn)
        identify_row.addStretch(1)
        form.addRow("", identify_row)

        self.system_combo = QComboBox()
        self.system_combo.addItem("— aucune —", "")
        for spec in SYSTEMS:
            self.system_combo.addItem(spec.name, spec.key)
        form.addRow("Machine", self.system_combo)
        form_box.addWidget(gb)

        # -- compression
        gb_c = QGroupBox("Compression")
        form_c = QFormLayout(gb_c)
        self.compression_combo = QComboBox()
        self.compression_combo.addItem("Aucune (données brutes)", "")
        for entry in DECOMPRESSORS:
            label = entry.name
            if entry.machine:
                label = f"{entry.name}"
            self.compression_combo.addItem(label, entry.key)
        self.compression_combo.setToolTip(
            "Format de compression des graphismes dans la ROM")
        self.compression_combo.currentIndexChanged.connect(self._update_preview)
        form_c.addRow("Format", self.compression_combo)

        detect_row = QHBoxLayout()
        self.detect_btn = QPushButton("Chercher des graphismes…")
        self.detect_btn.setToolTip(
            "Balaye tout le fichier (données brutes et blocs compressés) et "
            "propose les zones qui ressemblent à des tuiles.")
        self.detect_btn.clicked.connect(self._detect_compressed)
        detect_row.addWidget(self.detect_btn)
        self.comp_info = QLabel("")
        self.comp_info.setProperty("hint", True)
        detect_row.addWidget(self.comp_info, 1)
        form_c.addRow("", detect_row)
        form_box.addWidget(gb_c)

        # -- découpage
        gb2 = QGroupBox("Découpage")
        form2 = QFormLayout(gb2)
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(0, 2 ** 31 - 1)
        self.offset_spin.setDisplayIntegerBase(16)
        self.offset_spin.setPrefix("0x")
        self.offset_spin.setValue(0)
        self.offset_spin.valueChanged.connect(self._update_preview)
        form2.addRow("Offset", self.offset_spin)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(0, 200000)
        self.count_spin.setValue(256)
        self.count_spin.valueChanged.connect(self._update_preview)
        form2.addRow("Nombre de tuiles", self.count_spin)

        self.tilew_spin = QSpinBox()
        self.tilew_spin.setRange(1, 512)
        self.tilew_spin.setValue(8)
        self.tileh_spin = QSpinBox()
        self.tileh_spin.setRange(1, 512)
        self.tileh_spin.setValue(8)
        row = QHBoxLayout()
        row.addWidget(self.tilew_spin)
        row.addWidget(QLabel("×"))
        row.addWidget(self.tileh_spin)
        row.addStretch(1)
        form2.addRow("Taille de tuile", row)
        self.tilew_spin.valueChanged.connect(self._update_preview)
        self.tileh_spin.valueChanged.connect(self._update_preview)

        self.bpp_combo = QComboBox()
        for b in (1, 2, 3, 4, 8):
            self.bpp_combo.addItem(f"{b} bits", b)
        self.bpp_combo.setCurrentIndex(3)
        self.bpp_combo.currentIndexChanged.connect(self._update_preview)
        form2.addRow("Bits par pixel", self.bpp_combo)

        self.layout_combo = QComboBox()
        for key, label in LAYOUTS:
            self.layout_combo.addItem(label, key)
        self.layout_combo.setCurrentIndex(0)
        self.layout_combo.currentIndexChanged.connect(self._update_preview)
        form2.addRow("Disposition", self.layout_combo)

        self.bytes_spin = QSpinBox()
        self.bytes_spin.setRange(0, 65536)
        self.bytes_spin.setSpecialValueText("auto")
        self.bytes_spin.valueChanged.connect(self._update_preview)
        form2.addRow("Octets / tuile", self.bytes_spin)

        self.perrow_spin = QSpinBox()
        self.perrow_spin.setRange(1, 64)
        self.perrow_spin.setValue(16)
        self.perrow_spin.valueChanged.connect(self._update_preview)
        form2.addRow("Tuiles par ligne", self.perrow_spin)
        form_box.addWidget(gb2)

        # -- palette
        gb3 = QGroupBox("Palette")
        form3 = QFormLayout(gb3)
        self.palette_combo = QComboBox()
        self.palette_combo.addItem("— selon le format —", "")
        for key, pal in BUILTIN_PALETTES.items():
            self.palette_combo.addItem(pal.name, key)
        self.palette_combo.currentIndexChanged.connect(self._update_preview)
        form3.addRow("Palette", self.palette_combo)

        self.rom_palette_check = QCheckBox("Lire la palette dans la ROM")
        self.rom_palette_check.toggled.connect(self._update_preview)
        form3.addRow("", self.rom_palette_check)

        self.rom_palette_kind = QComboBox()
        for key, label in ROM_PALETTES:
            self.rom_palette_kind.addItem(label, key)
        self.rom_palette_kind.currentIndexChanged.connect(self._update_preview)
        form3.addRow("Type", self.rom_palette_kind)

        self.rom_palette_offset = QSpinBox()
        self.rom_palette_offset.setRange(0, 2 ** 31 - 1)
        self.rom_palette_offset.setDisplayIntegerBase(16)
        self.rom_palette_offset.setPrefix("0x")
        self.rom_palette_offset.valueChanged.connect(self._update_preview)
        form3.addRow("Offset palette", self.rom_palette_offset)

        self.rom_palette_count = QSpinBox()
        self.rom_palette_count.setRange(2, 256)
        self.rom_palette_count.setValue(16)
        self.rom_palette_count.valueChanged.connect(self._update_preview)
        form3.addRow("Couleurs", self.rom_palette_count)
        form_box.addWidget(gb3)

        row_actions = QHBoxLayout()
        scan = QPushButton("Analyser le fichier (tailles probables)")
        scan.clicked.connect(self._scan)
        row_actions.addWidget(scan)
        save_profile = QPushButton("Enregistrer le profil…")
        save_profile.setToolTip("Mémorise ces réglages pour les rejouer en un clic")
        save_profile.clicked.connect(self._save_profile)
        row_actions.addWidget(save_profile)
        form_box.addLayout(row_actions)
        form_box.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(400)
        body.addWidget(scroll)

        # -- aperçu
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("Aperçu des 128 premières tuiles"))
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.preview.setMinimumSize(400, 400)
        self.preview.setStyleSheet(f"background: {theme.PANEL}; border: 1px solid {theme.BORDER};")
        rl.addWidget(self.preview, 1)
        self.info = QLabel("")
        self.info.setProperty("hint", True)
        self.info.setWordWrap(True)
        rl.addWidget(self.info)
        body.addWidget(right, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if system_key:
            idx = self.system_combo.findData(system_key)
            if idx >= 0:
                self.system_combo.setCurrentIndex(idx)
        self._update_preview()

    # -- données ------------------------------------------------------------

    def _refresh_archive(self) -> None:
        """Remplit la liste des membres si le chemin est une archive."""
        path = self.path_edit.text().strip()
        self.member_combo.blockSignals(True)
        self.member_combo.clear()
        entries = []
        if path and os.path.exists(path) and archives.is_archive(path):
            try:
                entries = archives.list_archive(path)
            except Exception:
                entries = []
        for entry in entries:
            label = f"{entry.name} — {entry.size} octets"
            self.member_combo.addItem(label, entry.name)
        visible = bool(entries)
        self.member_combo.setVisible(visible)
        self.member_label.setVisible(visible)
        if entries:
            try:
                chosen = archives.choose_member(entries)
            except Exception:
                chosen = entries[0].name
            index = self.member_combo.findData(chosen)
            if index >= 0:
                self.member_combo.setCurrentIndex(index)
        self.member_combo.blockSignals(False)
        self._raw = b""
        self._member = ""
        self._update_preview()

    def _member_changed(self, _index: int) -> None:
        self._raw = b""
        self._member = ""
        self._update_preview()

    def _read_file(self) -> bytes:
        path = self.path_edit.text().strip()
        if not path or not os.path.exists(path):
            return b""
        member = (str(self.member_combo.currentData())
                  if self.member_combo.count() else "")
        if path != self._path or member != self._member or not self._raw:
            try:
                self._raw = archives.read_rom(path, member)
            except Exception:
                self._raw = b""
            self._path = path
            self._member = member
        return self._raw

    def _compressed(self) -> tuple[bytes, int]:
        """Renvoie (données à décoder, offset effectif)."""
        raw = self._read_file()
        key = self.compression_combo.currentData()
        offset = self.offset_spin.value()
        if not key:
            return raw, offset
        try:
            data = decompress(key, raw, offset)
        except Exception as exc:
            self.comp_info.setText(f"échec : {exc}")
            return b"", 0
        self.comp_info.setText(f"{len(data)} octets décompressés")
        return data, 0

    def _rom_palette(self, data: bytes):
        if not self.rom_palette_check.isChecked() or not data:
            return None
        try:
            return read_rom_palette(data, self.rom_palette_offset.value(),
                                    self.rom_palette_count.value(),
                                    self.rom_palette_kind.currentData())
        except Exception:
            return None

    # -- actions ------------------------------------------------------------

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir une banque", self.path_edit.text() or os.path.expanduser("~"),
            "ROMs et archives (*.bin *.rom *.md *.smc *.sfc *.nes *.gb *.gbc "
            "*.gba *.pce *.a26 *.dsk *.d64 *.st *.stx *.zip *.7z);;"
            "Archives (*.zip *.7z);;Tous les fichiers (*)")
        if path:
            self.path_edit.setText(path)
            self._raw = b""
            self._member = ""
            self._refresh_archive()

    def _current_format(self) -> TileFormat:
        key = self.format_combo.currentData()
        if key != "custom":
            return FORMATS_BY_KEY[key]
        return TileFormat(
            key="custom", name="Personnalisé",
            tile_w=self.tilew_spin.value(), tile_h=self.tileh_spin.value(),
            bpp=self.bpp_combo.currentData(),
            layout=self.layout_combo.currentData(),
            bytes_per_tile=self.bytes_spin.value(),
            system_key=self.system_combo.currentData() or "",
        )

    def _on_format_changed(self) -> None:
        key = self.format_combo.currentData()
        if key != "custom":
            f = FORMATS_BY_KEY[key]
            self.tilew_spin.blockSignals(True)
            self.tilew_spin.setValue(f.tile_w)
            self.tilew_spin.blockSignals(False)
            self.tileh_spin.blockSignals(True)
            self.tileh_spin.setValue(f.tile_h)
            self.tileh_spin.blockSignals(False)
            idx = self.bpp_combo.findData(f.bpp)
            if idx >= 0:
                self.bpp_combo.blockSignals(True)
                self.bpp_combo.setCurrentIndex(idx)
                self.bpp_combo.blockSignals(False)
            idx = self.layout_combo.findData(f.layout)
            if idx >= 0:
                self.layout_combo.blockSignals(True)
                self.layout_combo.setCurrentIndex(idx)
                self.layout_combo.blockSignals(False)
            self.bytes_spin.blockSignals(True)
            self.bytes_spin.setValue(f.bytes_per_tile)
            self.bytes_spin.blockSignals(False)
            if f.system_key:
                i = self.system_combo.findData(f.system_key)
                if i >= 0:
                    self.system_combo.setCurrentIndex(i)
            i = self.palette_combo.findData(f.palette_key)
            if i >= 0:
                self.palette_combo.setCurrentIndex(i)
        self._update_preview()

    def _scan(self) -> None:
        data, offset = self._compressed()
        if not data:
            return
        cands = scan_tile_sizes(self.path_edit.text().strip(), offset)
        if not cands:
            self.info.setText("Aucune taille de tuile ne divise exactement la taille des données.")
            return
        best = cands[0]
        self.tilew_spin.setValue(best["tile_w"])
        self.tileh_spin.setValue(best["tile_h"])
        idx = self.bpp_combo.findData(best["bpp"])
        if idx >= 0:
            self.bpp_combo.setCurrentIndex(idx)
        self.count_spin.setValue(best["count"])
        lines = [f"{c['tile_w']}×{c['tile_h']} {c['bpp']}bpp → {c['count']} tuiles"
                 for c in cands[:6]]
        self.info.setText("Candidats : " + " · ".join(lines))
        self._update_preview()

    def _identify_format(self) -> None:
        """Devine le format de tuiles du bloc affiché.

        L'analyse compare chaque format candidat à son propre plancher de bruit :
        un format à 1 bit « explique » n'importe quoi, il ne doit donc pas
        gagner parce qu'il obtient la meilleure note brute.
        """
        raw = self._read_file()
        if not raw:
            return
        start = min(self.offset_spin.value(), max(0, len(raw) - 512))
        length = min(len(raw) - start, 16384)
        if length < 512:
            QMessageBox.information(self, "Identification",
                                    "Le bloc est trop court pour être analysé.")
            return
        from ..core.identify import explain
        result = explain(raw[start:start + length])
        ranking = "\n".join(
            f"{index + 1}. {guess['name']} — marge {guess['margin']:+.3f}"
            for index, guess in enumerate(result["ranking"]))
        if not result["confident"]:
            QMessageBox.information(
                self, "Identification",
                f"{result['message']}\n\nClassement :\n{ranking}")
            return
        chosen = result["best"]
        index = self.format_combo.findData(chosen["key"])
        if index >= 0:
            self.format_combo.setCurrentIndex(index)
        self.comp_info.setText(f"Format probable : {chosen['name']}")
        QMessageBox.information(
            self, "Identification",
            f"{result['message']}\n\nClassement :\n{ranking}")
        self._update_preview()

    def _detect_compressed(self) -> None:
        """Cherche des graphismes dans le fichier, bruts ou compressés.

        Le balayage tourne dans un fil séparé (voir :mod:`.scan_dialog`) : il
        peut durer plusieurs dizaines de secondes sans figer la fenêtre, et
        l'utilisateur choisit son bloc dans une liste avec aperçu.
        """
        raw = self._read_file()
        if not raw:
            return
        fmt = self._current_format()
        from ..core.scan import compressions_for
        chosen = self.compression_combo.currentData()
        keys = [chosen] if chosen else compressions_for(fmt.key)
        from .scan_dialog import run_scan
        candidate = run_scan(self, raw, [fmt], keys,
                             source=self.path_edit.text(),
                             budget=60.0,
                             title="Recherche de graphismes")
        if candidate is None:
            return
        index = self.compression_combo.findData(candidate.compression)
        if index >= 0:
            self.compression_combo.setCurrentIndex(index)
        self.offset_spin.setValue(candidate.offset)
        count = candidate.size // max(1, fmt.real_bytes)
        if count:
            self.count_spin.setValue(min(count, 200000))
        self.comp_info.setText(
            f"{candidate.compression or 'brut'} à 0x{candidate.offset:X} — "
            f"{candidate.size} octets (note {candidate.score:.2f})")
        self._update_preview()

    def _update_preview(self) -> None:
        path = self.path_edit.text().strip()
        if not path or not os.path.exists(path):
            self.preview.setText("Choisissez un fichier.")
            return
        try:
            fmt = self._current_format()
            data, offset = self._compressed()
            if not data:
                return
            palette = self._rom_palette(data)
            if palette is None:
                key = self.palette_combo.currentData()
                if key:
                    palette = BUILTIN_PALETTES[key]
            count = self.count_spin.value() or 64
            count = min(count, 128)
            bank = load_raw_bank(None, offset, count, fmt,
                                 per_row=self.perrow_spin.value(), gap=1,
                                 palette=palette, data=data)
        except Exception as exc:
            self.preview.setText(f"Erreur : {exc}")
            return
        self._preview_image = bank.image
        pix = image_to_pixmap(bank.image)
        scale = max(1, min(3, 520 // max(1, pix.width())))
        if scale > 1:
            pix = pix.scaled(pix.width() * scale, pix.height() * scale,
                             Qt.KeepAspectRatio, Qt.FastTransformation)
        self.preview.setPixmap(pix)
        total = max(0, (len(data) - offset) // max(1, fmt.real_bytes))
        self.info.setText(
            f"{len(data)} octets utiles · {fmt.real_bytes} octets/tuile · "
            f"{total} tuiles possibles · aperçu {bank.count} tuiles en "
            f"{fmt.tile_w}×{fmt.tile_h}")

    def current_profile(self):
        """Construit un profil à partir des réglages affichés."""
        from ..core.profiles import GameProfile
        fmt = self._current_format()
        data, offset = self._compressed()
        path = self.path_edit.text().strip()
        return GameProfile(
            key=os.path.splitext(os.path.basename(path))[0].lower().replace(" ", "_"),
            name=os.path.splitext(os.path.basename(path))[0],
            offset=self.offset_spin.value() if self.compression_combo.currentData() else offset,
            tile_format=fmt.key if self.format_combo.currentData() != "custom" else "custom",
            compression=self.compression_combo.currentData() or "",
            count=self.count_spin.value(),
            per_row=self.perrow_spin.value(),
            machine=self.system_combo.currentData() or "",
            rom_name=os.path.basename(path),
            palette_kind=self.rom_palette_kind.currentData() if self.rom_palette_check.isChecked() else "",
            palette_offset=self.rom_palette_offset.value() if self.rom_palette_check.isChecked() else -1,
            palette_count=self.rom_palette_count.value(),
        )

    def _save_profile(self) -> None:
        from ..core.profiles import profiles_dir, save_profile
        profile = self.current_profile()
        suggested = os.path.join(str(profiles_dir()), f"{profile.key}.json")
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le profil", suggested,
                                              "Profil TileForge (*.json)")
        if not path:
            return
        save_profile(profile, path)
        QMessageBox.information(self, "Profil",
                                f"Profil enregistré :\n{path}\n\n"
                                "Il apparaît dans Fichier ▸ Profils de jeu…")

    # -- résultat -----------------------------------------------------------

    def accept(self) -> None:
        path = self.path_edit.text().strip()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Fichier manquant", "Choisissez un fichier valide.")
            return
        fmt = self._current_format()
        data, offset = self._compressed()
        palette = self._rom_palette(data)
        if palette is None:
            palette = BUILTIN_PALETTES.get(self.palette_combo.currentData() or "", None)
        self._result = {
            "path": path,
            "offset": offset,
            "count": self.count_spin.value(),
            "format": fmt,
            "per_row": self.perrow_spin.value(),
            "palette": palette,
            "system": self.system_combo.currentData() or "",
            "compression": self.compression_combo.currentData() or "",
            "compression_offset": self.offset_spin.value(),
        }
        super().accept()

    def result_config(self) -> dict | None:
        return self._result


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


class PaletteEditorDialog(QDialog):
    """Édition d'une palette (jusqu'à 256 couleurs)."""

    def __init__(self, palette: Palette, parent=None, size: int = 16):
        super().__init__(parent)
        self.setWindowTitle("Palette")
        fit_to_screen(self, 560, 420)
        self.palette = palette.copy()
        self._size = max(size, len(self.palette))

        root = QVBoxLayout(self)
        head = QHBoxLayout()
        self.name_label = QLabel(self.palette.name)
        self.name_label.setStyleSheet("font-weight: 600;")
        head.addWidget(self.name_label, 1)
        load_btn = QPushButton("Charger…")
        load_btn.clicked.connect(self._load)
        save_btn = QPushButton("Enregistrer…")
        save_btn.clicked.connect(self._save)
        head.addWidget(load_btn)
        head.addWidget(save_btn)
        root.addLayout(head)

        self.grid = QGridLayout()
        self.grid.setSpacing(4)
        holder = QWidget()
        holder.setLayout(self.grid)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        root.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Couleur transparente :"))
        self.transparent_spin = QSpinBox()
        self.transparent_spin.setRange(-1, 255)
        self.transparent_spin.setSpecialValueText("aucune")
        self.transparent_spin.setValue(-1 if self.palette.transparent is None
                                       else self.palette.transparent)
        bottom.addWidget(self.transparent_spin)
        bottom.addStretch(1)
        root.addLayout(bottom)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._swatches = []
        self._rebuild()

    def _rebuild(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._swatches = []
        cols = 8
        for i in range(self._size):
            btn = QPushButton()
            btn.setFixedSize(46, 34)
            color = self.palette.colors[i] if i < len(self.palette.colors) else (0, 0, 0)
            btn.setStyleSheet(f"background: {theme.hex_color(color)}; border: 1px solid #000;")
            btn.setToolTip(f"Couleur {i}")
            btn.clicked.connect(lambda _c=False, idx=i: self._edit(idx))
            self.grid.addWidget(btn, i // cols, i % cols)
            self._swatches.append(btn)
        self.grid.setRowStretch(self._size // cols + 1, 1)

    def _edit(self, index: int) -> None:
        current = self.palette.colors[index] if index < len(self.palette.colors) else (0, 0, 0)
        color = QColorDialog.getColor(QColor(*current), self, f"Couleur {index}")
        if not color.isValid():
            return
        while len(self.palette.colors) <= index:
            self.palette.colors.append((0, 0, 0))
        self.palette.colors[index] = (color.red(), color.green(), color.blue())
        self._rebuild()

    def _load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Charger une palette", "",
                                              "Palettes (*.pal *.gpl *.txt);;Tous (*)")
        if not path:
            return
        try:
            pal = Palette.load(path)
        except Exception as exc:
            QMessageBox.warning(self, "Palette", f"Lecture impossible : {exc}")
            return
        self.palette = pal
        self._size = max(16, len(pal))
        self.name_label.setText(pal.name)
        self._rebuild()

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer la palette", "palette.pal",
                                              "Palette JASC (*.pal);;GIMP (*.gpl)")
        if path:
            self.palette.save(path)

    def accept(self) -> None:
        value = self.transparent_spin.value()
        self.palette.transparent = None if value < 0 else value
        super().accept()

    def result_palette(self) -> Palette:
        return self.palette


# ---------------------------------------------------------------------------
# Profils de jeu
# ---------------------------------------------------------------------------


class ProfileDialog(QDialog):
    """Liste les profils fournis et ceux enregistrés par l'utilisateur."""

    def __init__(self, parent=None, current_key: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Profils de jeu")
        fit_to_screen(self, 780, 560)
        self.selected: GameProfile | None = None

        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "Un profil mémorise l'offset, le format de tuile, la compression et la "
            "palette d'un jeu : le charger suffit à retrouver ses graphismes."))

        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.currentRowChanged.connect(self._on_select)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        body.addWidget(self.list, 1)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(12, 0, 0, 0)
        self.title = QLabel("—")
        self.title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setProperty("hint", True)
        self.detail.setTextFormat(Qt.RichText)
        rv.addWidget(self.title)
        rv.addWidget(self.detail)
        rv.addStretch(1)
        body.addWidget(right, 1)
        root.addLayout(body, 1)

        row = QHBoxLayout()
        self.delete_btn = QPushButton("Supprimer")
        self.delete_btn.clicked.connect(self._delete)
        row.addWidget(self.delete_btn)
        row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Open).setText("Charger")
        buttons.button(QDialogButtonBox.Cancel).setText("Fermer")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        root.addLayout(row)

        self._populate(current_key)

    def _populate(self, current_key: str) -> None:
        from ..core.profiles import all_profiles
        self.list.clear()
        self._profiles = all_profiles()
        for profile in self._profiles:
            label = profile.name + ("  (fourni)" if profile.builtin else "")
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, profile.key)
            self.list.addItem(item)
            if profile.key == current_key:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self._profiles:
            self.list.setCurrentRow(0)

    def _current(self) -> GameProfile | None:
        row = self.list.currentRow()
        if 0 <= row < len(self._profiles):
            return self._profiles[row]
        return None

    def _on_select(self, row: int) -> None:
        profile = self._current()
        if profile is None:
            return
        self.selected = profile
        self.title.setText(profile.name)
        rows = [
            f"<b>Machine</b> : {profile.machine or '—'}",
            f"<b>Fichier</b> : {profile.rom_name or '—'}",
            f"<b>Offset</b> : 0x{profile.offset:X}",
            f"<b>Format</b> : {profile.tile_format}",
            f"<b>Compression</b> : {profile.compression or 'aucune'}",
            "<b>Palette</b> : " + (f"{profile.palette_kind} @ 0x{profile.palette_offset:X}"
                                     if profile.palette_enabled else "celle du format"),
            f"<b>Grille</b> : {profile.grid[0]} × {profile.grid[1]}",
        ]
        if profile.notes:
            rows.append(f"<br>{profile.notes}")
        self.detail.setText("<br>".join(rows))
        self.delete_btn.setEnabled(not profile.builtin)

    def _delete(self) -> None:
        profile = self._current()
        if profile is None or profile.builtin or not profile.path:
            return
        answer = QMessageBox.question(self, "Supprimer le profil",
                                      f"Supprimer « {profile.name} » ?",
                                      QMessageBox.Yes | QMessageBox.No)
        if answer == QMessageBox.Yes:
            with contextlib.suppress(OSError):
                os.unlink(profile.path)
            self._populate("")

    def accept(self) -> None:
        profile = self._current()
        if profile is None:
            return
        self.selected = profile
        super().accept()
