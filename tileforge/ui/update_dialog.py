"""Dialogue du gestionnaire de mises à jour."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QProcess, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from ..core.settings import data_dir
from ..core.updates import ReleaseInfo, UpdateError, UpdateManager, is_frozen
from ..version import APP_NAME, __version__, changelog_text
from . import theme
from .widgets import fit_to_screen


class _Worker(QThread):
    """Exécute une fonction longue hors du fil d'interface."""

    progress = Signal(float, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn(lambda f, m="": self.progress.emit(float(f), m))
            self.done.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateDialog(QDialog):
    """Vérification, notes de version et installation."""

    def __init__(self, parent=None, settings=None, manager: UpdateManager | None = None,
                 auto_check: bool = False):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — mises à jour")
        fit_to_screen(self, 720, 620)
        self.settings = settings
        self.manager = manager or UpdateManager(
            manifest_url=(settings.get("update_url") if settings else "") or "",
            channel=(settings.get("update_channel") if settings else "stable") or "stable",
            data_folder=data_dir() / "updates")
        self.release: ReleaseInfo | None = None
        self.worker: _Worker | None = None
        self._installed_version = ""

        root = QVBoxLayout(self)

        head = QLabel(f"<b style='font-size:16px'>{APP_NAME}</b> "
                      f"<span style='color:{theme.TEXT_DIM}'>version installée "
                      f"{__version__}</span>")
        root.addWidget(head)

        # -- source
        gb = QGroupBox("Source des mises à jour")
        form = QFormLayout(gb)
        row = QHBoxLayout()
        self.url_edit = QLineEdit(self.manager.manifest_url)
        self.url_edit.setPlaceholderText(
            "https://exemple.org/tileforge/manifest.json  ou  /chemin/local/manifest.json")
        row.addWidget(self.url_edit, 1)
        browse = QPushButton("Parcourir…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        form.addRow("Manifeste", row)

        self.channel_combo = QComboBox()
        self.channel_combo.addItem("stable", "stable")
        self.channel_combo.addItem("bêta", "beta")
        index = self.channel_combo.findData(self.manager.channel)
        if index >= 0:
            self.channel_combo.setCurrentIndex(index)
        form.addRow("Canal", self.channel_combo)

        self.startup_check = QCheckBox("Vérifier au démarrage")
        self.startup_check.setChecked(bool(settings.get("check_updates_startup"))
                                      if settings else True)
        form.addRow("", self.startup_check)
        root.addWidget(gb)

        # -- actions
        actions = QHBoxLayout()
        self.check_btn = QPushButton("Vérifier maintenant")
        self.check_btn.setProperty("accent", True)
        self.check_btn.clicked.connect(self.check_now)
        actions.addWidget(self.check_btn)
        self.install_btn = QPushButton("Télécharger et installer")
        self.install_btn.setEnabled(False)
        self.install_btn.clicked.connect(self.install_now)
        actions.addWidget(self.install_btn)
        self.rollback_btn = QPushButton("Revenir à la version précédente")
        self.rollback_btn.setEnabled(self.manager.has_backup())
        self.rollback_btn.clicked.connect(self.rollback_now)
        actions.addWidget(self.rollback_btn)
        actions.addStretch(1)
        root.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)
        self.status = QLabel("Prêt.")
        self.status.setProperty("hint", True)
        root.addWidget(self.status)

        # -- notes
        notes_box = QGroupBox("Notes de version")
        nv = QVBoxLayout(notes_box)
        self.notes = QTextBrowser()
        self.notes.setHtml(self._changelog_html())
        nv.addWidget(self.notes)
        root.addWidget(notes_box, 1)

        bottom = QHBoxLayout()
        info = QLabel(f"Données : {data_dir() / 'updates'}")
        info.setProperty("hint", True)
        bottom.addWidget(info, 1)
        close = QPushButton("Fermer")
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        root.addLayout(bottom)

        if is_frozen():
            self.status.setText(
                "Version compilée : l'archive sera téléchargée mais l'installation "
                "automatique est désactivée.")
        if auto_check and self.manager.manifest_url:
            self.check_now()

    # ------------------------------------------------------------------

    def _changelog_html(self) -> str:
        text = changelog_text().replace("\n", "<br>").replace("  •", "&nbsp;&nbsp;•")
        return (f"<div style='font-family:monospace; font-size:12px; "
                f"color:{theme.TEXT}'>{text}</div>")

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Manifeste de mise à jour", "",
            "Manifeste JSON (*.json);;Tous (*)")
        if path:
            self.url_edit.setText(path)

    def _save_settings(self) -> None:
        if not self.settings:
            return
        self.settings.update({
            "update_url": self.url_edit.text().strip(),
            "update_channel": self.channel_combo.currentData(),
            "check_updates_startup": self.startup_check.isChecked(),
        }, save=False)
        self.settings.save()

    # ------------------------------------------------------------------

    def _run(self, fn, on_done) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self.check_btn.setEnabled(False)
        self.install_btn.setEnabled(False)
        self.rollback_btn.setEnabled(False)
        self.progress.setValue(0)
        self.worker = _Worker(fn, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_progress(self, fraction: float, message: str) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, fraction)) * 100))
        if message:
            self.status.setText(message)

    def _on_failed(self, message: str) -> None:
        self.status.setText(f"Échec : {message}")
        QMessageBox.warning(self, "Mise à jour", message)

    def _on_worker_finished(self) -> None:
        self.check_btn.setEnabled(True)
        self.install_btn.setEnabled(self.release is not None)
        self.rollback_btn.setEnabled(self.manager.has_backup())

    # ------------------------------------------------------------------

    def check_now(self) -> None:
        self._save_settings()
        self.manager.manifest_url = self.url_edit.text().strip()
        self.manager.channel = self.channel_combo.currentData()
        self.status.setText("Vérification…")
        self.release = None

        def work(progress):
            progress(0.1, "Lecture du manifeste…")
            release = self.manager.check()
            progress(1.0, "")
            return release

        self._run(work, self._on_checked)

    def _on_checked(self, release) -> None:
        if release is None:
            self.status.setText(f"À jour : la version {__version__} est la plus récente.")
            self.notes.setHtml(self._changelog_html())
            self.release = None
            return
        self.release = release
        self.status.setText(
            f"Version {release.version} disponible ({release.date or 'date inconnue'}).")
        notes = release.notes or "(pas de notes pour cette version)"
        html = (f"<h3 style='color:{theme.ACCENT}'>Version {release.version}</h3>"
                f"<p style='color:{theme.TEXT_DIM}'>{release.date}</p>"
                f"<div style='white-space:pre-wrap; color:{theme.TEXT}'>{notes}</div>"
                f"<hr><div style='font-family:monospace; font-size:11px; "
                f"color:{theme.TEXT_DIM}'>{changelog_text().replace(chr(10), '<br>')}</div>")
        self.notes.setHtml(html)

    def install_now(self) -> None:
        if self.release is None:
            return
        release = self.release
        answer = QMessageBox.question(
            self, "Installer la mise à jour",
            f"Installer la version {release.version} ?\n\n"
            "Le paquet tileforge/ sera remplacé ; une sauvegarde de la version "
            "actuelle est conservée pour pouvoir revenir en arrière.",
            QMessageBox.Yes | QMessageBox.No)
        if answer != QMessageBox.Yes:
            return

        def work(progress):
            progress(0.0, "Téléchargement…")
            archive = self.manager.download(release, lambda f: progress(f * 0.7, "Téléchargement…"))
            progress(0.75, "Installation…")
            version = self.manager.install(archive, release.version,
                                           lambda f: progress(0.75 + f * 0.25, "Installation…"))
            self.manager.cleanup_downloads()
            return version

        self._run(work, self._on_installed)

    def _on_installed(self, version) -> None:
        self._installed_version = str(version)
        self.status.setText(f"Version {version} installée. Redémarrez pour en profiter.")
        answer = QMessageBox.question(
            self, "Mise à jour installée",
            f"La version {version} est installée.\n\nRedémarrer {APP_NAME} maintenant ?",
            QMessageBox.Yes | QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.restart_application()

    def rollback_now(self) -> None:
        version = self.manager.backup_version()
        answer = QMessageBox.question(
            self, "Revenir en arrière",
            f"Restaurer la version {version or 'sauvegardée'} ?",
            QMessageBox.Yes | QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        try:
            restored = self.manager.rollback()
        except UpdateError as exc:
            QMessageBox.warning(self, "Restauration", str(exc))
            return
        self.status.setText(f"Version {restored} restaurée. Redémarrez l'application.")
        if QMessageBox.question(self, "Restauration",
                                "Redémarrer maintenant ?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.restart_application()

    # ------------------------------------------------------------------

    @staticmethod
    def restart_application() -> None:
        from PySide6.QtWidgets import QApplication
        program = sys.executable
        args = ["-m", "tileforge"]
        if getattr(sys, "frozen", False):
            program = sys.executable
            args = []
        QProcess.startDetached(program, args, os.getcwd())
        QApplication.quit()
