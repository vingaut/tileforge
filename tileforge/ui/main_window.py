"""Fenêtre principale de TileForge."""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QStyle,
    QTabWidget,
    QToolBar,
    QWidget,
)

from ..core import project_io
from ..core.history import History
from ..core.model import Project
from ..core.settings import Settings, default_dir, is_android
from ..core.updates import UpdateManager
from ..version import APP_NAME, __version__
from .analysis_view import AnalysisView
from .assembly_view import AssemblyView
from .atlas_view import AtlasView
from .dialogs import SystemPickerDialog
from .help import HelpController, auto_bind, bind
from .help_dialog import ChangelogDialog, HelpDialog, WelcomeDialog
from .sheet_view import SheetView
from .update_dialog import UpdateDialog


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings | None = None):
        super().__init__()
        self.settings = settings or Settings()
        self.mobile = is_android() or os.environ.get("TILEFORGE_MOBILE") == "1"
        self.setWindowTitle(f"{APP_NAME} — reconstruction de sprites")
        self.resize(1440, 900)

        self.project = Project()
        self.weights = dict(self.settings.get("weights") or {})
        self.history = History(lambda: self.project, self._on_history_change)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.sheet_view = SheetView(self)
        self.assembly = AssemblyView(self)
        self.atlas_view = AtlasView(self)
        self.analysis = AnalysisView(self)
        self.tabs.addTab(self.sheet_view, "Planche")
        self.tabs.addTab(self.assembly, "Atelier")
        self.tabs.addTab(self.atlas_view, "Atlas")
        self.tabs.addTab(self.analysis, "Analyse")
        self.setCentralWidget(self.tabs)

        for view in (self.sheet_view, self.assembly, self.analysis):
            view.statusMessage.connect(self.show_message)
        for view in (self.sheet_view, self.assembly):
            view.projectChanged.connect(self._on_project_changed)
        self.analysis.requestTab.connect(self._goto_tab)
        self.atlas_view.statusMessage.connect(self.show_message)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()

        self.tabs.currentChanged.connect(self._on_tab_changed)

        # -- aide interactive
        self.help = HelpController(self, int(self.settings.get("help_delay_ms", 2000)))
        self.help.on_enabled_changed(self._on_help_mode_changed)
        bind(self.act_help_mode, "app.help_mode")
        bind(self.act_help, "app.help")
        bind(self.act_updates, "app.updates")
        auto_bind(self)
        self.help.set_enabled(bool(self.settings.get("help_interactive", False)))
        self.act_help_mode.setChecked(self.help.enabled)

        # -- sauvegarde automatique
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(60000)
        self.autosave_timer.timeout.connect(self._autosave)
        self.autosave_timer.start()

        from .i18n_qt import apply_to
        apply_to(self)

        self._update_title()
        self._restore_geometry()

        if self.mobile:
            self.showMaximized()
            self._apply_mobile_style()

        QTimer.singleShot(500, self._startup_checks)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    #: Icônes standard de Qt remplacées par celles du jeu maison.
    _ICON_NAMES = {
        QStyle.SP_FileIcon: "new",
        QStyle.SP_DialogOpenButton: "open",
        QStyle.SP_DialogSaveButton: "save",
        QStyle.SP_ArrowBack: "undo",
        QStyle.SP_ArrowForward: "redo",
        QStyle.SP_TitleBarMaxButton: "fullscreen",
        QStyle.SP_ComputerIcon: "machines",
        QStyle.SP_MessageBoxQuestion: "help",
        QStyle.SP_DialogHelpButton: "help",
        QStyle.SP_BrowserReload: "updates",
        QStyle.SP_DriveHDIcon: "cartography",
        QStyle.SP_FileDialogDetailedView: "disassemble",
    }

    def _icon(self, standard):
        from .icons import icon
        name = self._ICON_NAMES.get(standard)
        if name:
            return icon(name)
        return self.style().standardIcon(standard)

    def _build_actions(self) -> None:
        self.act_new = QAction(self._icon(QStyle.SP_FileIcon), "Nouveau projet", self)
        self.act_new.setShortcut(QKeySequence.New)
        self.act_new.triggered.connect(self.new_project)

        self.act_open = QAction(self._icon(QStyle.SP_DialogOpenButton),
                                "Ouvrir un projet…", self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(self.open_project)

        self.act_save = QAction(self._icon(QStyle.SP_DialogSaveButton),
                                "Enregistrer", self)
        self.act_save.setShortcut(QKeySequence.Save)
        self.act_save.triggered.connect(self.save_project)

        self.act_save_as = QAction("Enregistrer sous…", self)
        self.act_save_as.setShortcut(QKeySequence.SaveAs)
        self.act_save_as.triggered.connect(self.save_project_as)

        self.act_undo = QAction(self._icon(QStyle.SP_ArrowBack), "Annuler", self)
        self.act_undo.setShortcut(QKeySequence.Undo)
        self.act_undo.triggered.connect(self.undo)

        self.act_redo = QAction(self._icon(QStyle.SP_ArrowForward), "Refaire", self)
        self.act_redo.setShortcut(QKeySequence.Redo)
        self.act_redo.triggered.connect(self.redo)

        self.act_quit = QAction("Quitter", self)
        self.act_quit.setShortcut(QKeySequence.Quit)
        self.act_quit.triggered.connect(self.close)

        self.act_fullscreen = QAction(self._icon(QStyle.SP_TitleBarMaxButton),
                                      "Plein écran", self)
        self.act_fullscreen.setShortcut("F11")
        self.act_fullscreen.triggered.connect(self._toggle_fullscreen)

        self.act_machines = QAction(self._icon(QStyle.SP_ComputerIcon),
                                    "Résolutions des machines…", self)
        self.act_machines.triggered.connect(self.show_machines)

        self.act_cartography = QAction(
            self._icon(QStyle.SP_DriveHDIcon), "Cartographier une ROM…", self)
        self.act_cartography.setStatusTip(
            "Reconnaît la plateforme, découpe la ROM en zones et repère les "
            "tables de pointeurs.")
        self.act_cartography.triggered.connect(self.cartography)

        self.act_disasm = QAction(
            self._icon(QStyle.SP_FileDialogDetailedView), "Désassembler…", self)
        self.act_disasm.setStatusTip(
            "Décode le code 65816 d'une ROM, linéairement ou en suivant le fil "
            "d'exécution depuis un vecteur.")
        self.act_disasm.triggered.connect(self.disassemble)

        self.act_emulator = QAction(
            self._icon(QStyle.SP_MediaPlay), "Mémoire d'émulateur…", self)
        self.act_emulator.setStatusTip(
            "Exécute une ROM dans un cœur libretro et lit la RAM décodée : le "
            "chemin de secours quand le compresseur du jeu est inconnu.")
        self.act_emulator.triggered.connect(self.emulator_memory)

        self.act_weights = QAction("Poids du coût…", self)
        self.act_weights.triggered.connect(self.show_weights)

        self.act_profiles = QAction("Profils de jeu…", self)
        self.act_profiles.triggered.connect(lambda: self.sheet_view.open_profiles())

        self.act_export_atlas = QAction("Exporter l'atlas…", self)
        self.act_export_atlas.triggered.connect(self._export_atlas)

        self.act_help_mode = QAction(self._icon(QStyle.SP_MessageBoxQuestion),
                                     "Aide interactive", self)
        self.act_help_mode.setCheckable(True)
        self.act_help_mode.setShortcut("F1")
        self.act_help_mode.setStatusTip(
            "Survolez un bouton deux secondes pour lire ce qu'il fait")
        self.act_help_mode.toggled.connect(self._toggle_help_mode)

        self.act_help = QAction(self._icon(QStyle.SP_DialogHelpButton),
                                "Aide et tutoriel", self)
        self.act_help.setShortcut("Ctrl+F1")
        self.act_help.triggered.connect(lambda: self.open_help())

        self.act_updates = QAction(self._icon(QStyle.SP_BrowserReload),
                                   "Mises à jour…", self)
        self.act_updates.triggered.connect(lambda: self.open_updates())

        self.act_changelog = QAction("Nouveautés", self)
        self.act_changelog.triggered.connect(
            lambda: ChangelogDialog(self, "Nouveautés").exec())

        self.act_welcome = QAction("Écran d'accueil", self)
        self.act_welcome.triggered.connect(self.show_welcome)

        self.act_about = QAction(f"À propos de {APP_NAME}", self)
        self.act_about.triggered.connect(self.show_about)

        self.act_shortcuts = QAction("Raccourcis clavier", self)
        self.act_shortcuts.triggered.connect(self.show_shortcuts)

    def _build_menus(self) -> None:
        m = self.menuBar()
        f = m.addMenu("&Fichier")
        f.addAction(self.act_new)
        f.addAction(self.act_open)
        self.menu_recent = f.addMenu("Ouvrir récemment")
        self._fill_recent_menu()
        f.addSeparator()
        f.addAction(self.act_save)
        f.addAction(self.act_save_as)
        f.addSeparator()
        f.addAction(self.act_profiles)
        f.addAction(self.act_export_atlas)
        f.addSeparator()
        f.addAction(self.act_quit)

        e = m.addMenu("&Édition")
        e.addAction(self.act_undo)
        e.addAction(self.act_redo)

        v = m.addMenu("&Vue")
        for i, name in enumerate(("Planche", "Atelier", "Atlas", "Analyse")):
            a = QAction(name, self)
            a.setShortcut(f"Ctrl+{i + 1}")
            a.triggered.connect(lambda _c=False, k=i: self.tabs.setCurrentIndex(k))
            v.addAction(a)
        v.addSeparator()
        v.addAction(self.act_fullscreen)

        o = m.addMenu("&Outils")
        o.addAction(self.act_cartography)
        o.addAction(self.act_disasm)
        o.addAction(self.act_emulator)
        o.addAction(self.act_machines)
        o.addAction(self.act_weights)

        h = m.addMenu("&Aide")
        h.addAction(self.act_help)
        h.addAction(self.act_help_mode)
        h.addSeparator()
        h.addAction(self.act_welcome)
        h.addAction(self.act_changelog)
        h.addAction(self.act_updates)
        h.addSeparator()
        self.menu_language = h.addMenu("Langue")
        self._build_language_menu()
        h.addSeparator()
        h.addAction(self.act_shortcuts)
        h.addAction(self.act_about)

    def cartography(self) -> None:
        """Ouvre la cartographie d'une ROM."""
        from .cartography_dialog import run_cartography
        report = run_cartography(self)
        if report:
            platform = report["platform"]
            self.show_message(
                f"Cartographie : {platform['name']} — "
                f"{report['summary']['pointer_tables']} tables de pointeurs")

    def disassemble(self) -> None:
        """Ouvre le désassembleur 65816."""
        from .disasm_dialog import run_disasm
        run_disasm(self)

    def emulator_memory(self) -> None:
        """Ouvre le dialogue de lecture de la mémoire d'un émulateur."""
        from .emulator_dialog import run_emulator
        run_emulator(self)

    def _build_language_menu(self) -> None:
        """Menu des langues disponibles, avec une case par catalogue présent."""
        from ..core import i18n
        self.language_group = QActionGroup(self)
        self.language_group.setExclusive(True)
        for code, label in i18n.available_languages().items():
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(code == i18n.language())
            action.triggered.connect(lambda _checked=False, key=code: self.change_language(key))
            self.language_group.addAction(action)
            self.menu_language.addAction(action)

    def change_language(self, code: str) -> None:
        """Change la langue de l'interface et mémorise le choix."""
        from ..core import i18n
        from .i18n_qt import apply_to
        i18n.set_language(code)
        self.settings.set("language", code)
        apply_to(self)
        self.show_message(f"{i18n.language_name()} — {i18n.t('Prêt.')}")

    def _build_toolbar(self) -> None:
        tb = QToolBar("Principal")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setObjectName("mainToolbar")
        self.addToolBar(tb)
        self.main_toolbar = tb
        tb.addAction(self.act_new)
        tb.addAction(self.act_open)
        tb.addAction(self.act_save)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        tb.addAction(self.act_machines)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self.act_help_mode)
        tb.addAction(self.act_help)
        tb.addAction(self.act_updates)
        tb.addAction(self.act_fullscreen)

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.msg_label = QLabel("Prêt.")
        sb.addWidget(self.msg_label, 1)
        self.coord_label = QLabel("—")
        self.coord_label.setMinimumWidth(120)
        sb.addPermanentWidget(self.coord_label)
        self.help_label = QLabel("")
        self.help_label.setProperty("hint", True)
        sb.addPermanentWidget(self.help_label)
        self.state_label = QLabel("nouveau projet")
        sb.addPermanentWidget(self.state_label)

    # ------------------------------------------------------------------
    # Aide
    # ------------------------------------------------------------------

    def _toggle_help_mode(self, enabled: bool) -> None:
        self.help.set_enabled(enabled)
        self.settings.set("help_interactive", enabled)

    def _on_help_mode_changed(self, enabled: bool) -> None:
        if enabled:
            self.help_label.setText("aide interactive : survolez un bouton 2 s")
            self.show_message(
                "Aide interactive activée : survolez un bouton deux secondes pour "
                "lire ce qu'il fait (F1 pour quitter).")
        else:
            self.help_label.setText("")
            self.show_message("Aide interactive désactivée.")

    def open_help(self, section: str = "") -> None:
        dlg = HelpDialog(self, section)
        dlg.exec()

    def show_welcome(self) -> None:
        dlg = WelcomeDialog(self)
        dlg.actionChosen.connect(self._welcome_action)
        dlg.exec()

    def _welcome_action(self, action: str) -> None:
        self.tabs.setCurrentIndex(0)
        if action == "barbarian":
            self.sheet_view.open_barbarian()
        elif action == "png":
            self.sheet_view.open_png()
        elif action == "raw":
            self.sheet_view.open_raw()

    def _startup_checks(self) -> None:
        if self.settings.get("show_welcome", True) and not self.project.sheet:
            self.settings.set("show_welcome", False)
            if not self.mobile:
                self.show_welcome()
        if self.settings.get("check_updates_startup") and self.settings.get("update_url"):
            self._silent_update_check()

    def _silent_update_check(self) -> None:
        from PySide6.QtCore import QThread, Signal

        class Checker(QThread):
            found = Signal(str)

            def __init__(self, manager):
                super().__init__()
                self.manager = manager

            def run(self):
                try:
                    release = self.manager.check()
                except Exception:
                    return
                if release is not None:
                    self.found.emit(release.version)

        self._update_thread = Checker(UpdateManager(
            self.settings.get("update_url", ""),
            self.settings.get("update_channel", "stable")))
        self._update_thread.found.connect(
            lambda v: self.show_message(
                f"Mise à jour {v} disponible — menu Aide ▸ Mises à jour."))
        self._update_thread.start()

    def open_updates(self) -> None:
        dlg = UpdateDialog(self, settings=self.settings)
        dlg.exec()

    # ------------------------------------------------------------------
    # État
    # ------------------------------------------------------------------

    def show_message(self, text: str) -> None:
        self.msg_label.setText(text)
        QTimer.singleShot(9000, lambda: self.msg_label.setText("Prêt.")
                           if self.msg_label.text() == text else None)

    def show_coords(self, x: float, y: float) -> None:
        self.coord_label.setText(f"x {int(x)} · y {int(y)}")

    def _update_title(self) -> None:
        name = os.path.basename(self.project.path) if self.project.path else "sans titre"
        mark = " •" if self.project.dirty else ""
        self.setWindowTitle(f"{APP_NAME} — {name}{mark}")
        self.state_label.setText(("modifié" if self.project.dirty else "enregistré")
                                 if self.project.path else "nouveau projet")

    def _on_project_changed(self) -> None:
        self.project.dirty = True
        self._update_title()

    def _on_history_change(self) -> None:
        self.act_undo.setEnabled(self.history.can_undo())
        self.act_redo.setEnabled(self.history.can_redo())
        self.project.dirty = True
        self._update_title()

    def _on_tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is self.atlas_view:
            self.atlas_view.refresh()
        elif widget is self.analysis:
            self.analysis.refresh()
        elif widget is self.assembly:
            self.assembly.refresh()
        elif widget is self.sheet_view:
            self.sheet_view.refresh()

    def _goto_tab(self, name: str) -> None:
        index = {"planche": 0, "atelier": 1, "atlas": 2, "analyse": 3}.get(name, 0)
        self.tabs.setCurrentIndex(index)

    def refresh_all(self) -> None:
        self.sheet_view.refresh()
        self.assembly.refresh()
        self.atlas_view.refresh()
        self.analysis.refresh()
        self._update_title()

    # ------------------------------------------------------------------
    # Fichiers
    # ------------------------------------------------------------------

    def _fill_recent_menu(self) -> None:
        self.menu_recent.clear()
        recent = self.settings.get("recent_projects", [])
        if not recent:
            empty = self.menu_recent.addAction("(aucun)")
            empty.setEnabled(False)
            return
        for path in recent[:8]:
            action = self.menu_recent.addAction(os.path.basename(path))
            action.setToolTip(path)
            action.triggered.connect(lambda _c=False, p=path: self.open_path(p))

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.project = Project()
        self.history.clear()
        self.assembly.group_index = 0
        self.refresh_all()
        self.show_message("Nouveau projet.")

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        start = self.settings.get("last_project") or default_dir("projects")
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un projet", os.path.dirname(start),
            "Projets TileForge (*.json *.tileforge.json);;Tous (*)")
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        try:
            self.project = project_io.load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, "Ouverture", f"Impossible d'ouvrir le projet :\n{exc}")
            return
        self.history.clear()
        self.assembly.group_index = 0
        self.settings.add_recent(path)
        self._fill_recent_menu()
        self.refresh_all()
        self.show_message(f"Projet ouvert : {path}")

    def save_project(self) -> bool:
        if not self.project.path:
            return self.save_project_as()
        try:
            project_io.save_project(self.project, self.project.path)
        except Exception as exc:
            QMessageBox.critical(self, "Enregistrement", f"Échec : {exc}")
            return False
        self.settings.add_recent(self.project.path)
        self._update_title()
        self.show_message(f"Enregistré : {self.project.path}")
        return True

    def save_project_as(self) -> bool:
        folder = default_dir("projects")
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le projet",
                                              os.path.join(folder, "projet.tileforge.json"),
                                              "Projet TileForge (*.tileforge.json);;JSON (*.json)")
        if not path:
            return False
        if not path.endswith(".json"):
            path += ".tileforge.json"
        try:
            project_io.save_project(self.project, path)
        except Exception as exc:
            QMessageBox.critical(self, "Enregistrement", f"Échec : {exc}")
            return False
        self.settings.add_recent(path)
        self._fill_recent_menu()
        self._update_title()
        self.show_message(f"Enregistré : {path}")
        return True

    def _autosave(self) -> None:
        if not self.project.dirty or self.project.sheet is None:
            return
        base = self.project.path or os.path.join(default_dir("projects"),
                                                  "autosave.tileforge.json")
        path = base.replace(".tileforge.json", ".autosave.json")
        try:
            project_io.save_project(self.project, path)
            self.show_message(f"Sauvegarde automatique : {os.path.basename(path)}")
        except Exception:
            pass

    def _confirm_discard(self) -> bool:
        if not self.project.dirty:
            return True
        answer = QMessageBox.question(
            self, "Projet modifié", "Enregistrer les modifications avant de continuer ?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if answer == QMessageBox.Save:
            return self.save_project()
        return answer == QMessageBox.Discard

    def closeEvent(self, event):
        if not self._confirm_discard():
            event.ignore()
            return
        self._save_geometry()
        self.settings.set("weights", dict(self.weights))
        self.settings.save()
        self.help.cleanup()
        event.accept()

    # ------------------------------------------------------------------
    # Édition
    # ------------------------------------------------------------------

    def undo(self) -> None:
        if self.history.undo():
            self.refresh_all()
            self.show_message(f"Annulé : {self.history.last_label()}")

    def redo(self) -> None:
        if self.history.redo():
            self.refresh_all()
            self.show_message("Rétabli.")

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ------------------------------------------------------------------
    # Réglages de fenêtre
    # ------------------------------------------------------------------

    def _restore_geometry(self) -> None:
        geometry = self.settings.get("window_geometry") or ""
        if not geometry:
            return
        try:
            from PySide6.QtCore import QByteArray
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        except Exception:
            pass

    def _save_geometry(self) -> None:
        try:
            data = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.settings.set("window_geometry", data, save=False)
        except Exception:
            pass

    def _apply_mobile_style(self) -> None:
        """Agrandit les cibles tactiles quand l'écran est petit."""
        self.setStyleSheet(
            "QToolBar QToolButton { padding: 8px 10px; }"
            "QPushButton { padding: 9px 12px; min-height: 26px; }"
            "QTabBar::tab { padding: 12px 22px; }"
            "QSpinBox, QComboBox, QLineEdit { padding: 7px 8px; }")

    # ------------------------------------------------------------------
    # Dialogues
    # ------------------------------------------------------------------

    def _export_atlas(self) -> None:
        self._goto_tab("atlas")
        self.atlas_view.export_png()

    def show_machines(self) -> None:
        key = (self.project.system or {}).get("key", "")
        dlg = SystemPickerDialog(self, key)
        if dlg.exec():
            spec = dlg.selected_system()
            if spec:
                self.project.system = {"key": spec.key, "name": spec.name,
                                       "resolutions": [list(r) for r in spec.resolutions]}
                self.sheet_view.system_combo.blockSignals(True)
                self.sheet_view.system_combo.clear()
                self.sheet_view.system_combo.addItem(spec.name, spec.key)
                self.sheet_view.system_combo.blockSignals(False)
                self.sheet_view.apply_system()
                self.show_message(f"Machine : {spec.name}")

    def show_weights(self) -> None:
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QDoubleSpinBox,
            QFormLayout,
            QVBoxLayout,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Poids du coût d'assemblage")
        form = QFormLayout()
        spins = {}
        labels = {"silhouette": "C1 Silhouette", "color": "C2 Couleur",
                  "gradient": "C3 Contour", "hole": "C4 Trous",
                  "palette": "C5 Palette", "duplicate": "C6 Doublons"}
        for key, label in labels.items():
            s = QDoubleSpinBox()
            s.setRange(0.0, 5.0)
            s.setSingleStep(0.05)
            s.setDecimals(2)
            s.setValue(float(self.weights.get(key, 0.3)))
            form.addRow(label, s)
            spins[key] = s
        layout = QVBoxLayout(dlg)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec():
            self.weights = {k: s.value() for k, s in spins.items()}
            self.settings.set("weights", dict(self.weights))
            self.assembly._weights = self.assembly._weights.__class__(**self.weights)
            self.assembly._recompute_cost()
            self.show_message("Poids du coût mis à jour.")

    def show_about(self) -> None:
        QMessageBox.about(
            self, f"À propos de {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Reconstruction de sprites à partir de planches de tuiles "
            "extraites de ROM de jeux 8 et 16 bits.</p>"
            "<p>Détection de résolution, découpage automatique, assemblage manuel "
            "ou automatique, inférence de la logique d'ordonnancement, atlas et "
            "exports d'analyse.</p>"
            "<p style='color:#8b90a0'>Python / PySide6 — licence libre.</p>")

    def show_shortcuts(self) -> None:
        QMessageBox.information(
            self, "Raccourcis",
            "<b>Fichier</b><br>"
            "Ctrl+O ouvrir · Ctrl+S enregistrer · Ctrl+Maj+S enregistrer sous<br><br>"
            "<b>Édition</b><br>"
            "Ctrl+Z annuler · Ctrl+Y refaire · Suppr supprimer<br><br>"
            "<b>Planche</b><br>"
            "V sélection · R nouvelle tuile · G aimant · 0 ajuster · 1 taille réelle<br>"
            "Molette zoom · clic du milieu déplacer · flèches décaler<br><br>"
            "<b>Atelier</b><br>"
            "Glisser-déposer depuis la palette · double-clic retirer · Suppr retirer<br><br>"
            "<b>Aide</b><br>"
            "F1 aide interactive · Ctrl+F1 page d'aide<br><br>"
            "<b>Vue</b><br>"
            "Ctrl+1..4 onglets · F11 plein écran")
