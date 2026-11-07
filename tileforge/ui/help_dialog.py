"""Page d'aide, tutoriel et écran d'accueil."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from ..version import APP_NAME, __version__, changelog_text
from . import theme
from .help_content import DOC_SECTIONS, doc_html
from .widgets import fit_to_screen


class HelpDialog(QDialog):
    """Documentation complète avec sommaire et recherche."""

    def __init__(self, parent=None, section: str = ""):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — aide et tutoriel")
        fit_to_screen(self, 1040, 760)

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        title = QLabel(f"<b style='font-size:16px'>Aide de {APP_NAME}</b> "
                       f"<span style='color:{theme.TEXT_DIM}'>v{__version__}</span>")
        top.addWidget(title)
        top.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher dans l'aide…")
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self._on_search)
        top.addWidget(self.search)
        root.addLayout(top)

        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setFixedWidth(230)
        self.list.setAlternatingRowColors(True)
        for anchor, name, _html in DOC_SECTIONS:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, anchor)
            self.list.addItem(item)
        self.list.currentRowChanged.connect(self._on_section)
        body.addWidget(self.list)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setHtml(doc_html(__version__))
        self.browser.setStyleSheet(
            f"QTextBrowser {{ background: {theme.PANEL};"
            f" border: 1px solid {theme.BORDER}; padding: 10px; }}")
        body.addWidget(self.browser, 1)
        root.addLayout(body, 1)

        bottom = QHBoxLayout()
        self.status = QLabel("")
        self.status.setProperty("hint", True)
        bottom.addWidget(self.status, 1)
        export_btn = QPushButton("Exporter en HTML…")
        export_btn.clicked.connect(self._export)
        bottom.addWidget(export_btn)
        close_btn = QPushButton("Fermer")
        close_btn.setProperty("accent", True)
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

        if section:
            self.show_section(section)
        else:
            self.list.setCurrentRow(0)

    # -- navigation ---------------------------------------------------------

    def show_section(self, anchor: str) -> None:
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole) == anchor:
                self.list.setCurrentRow(row)
                return

    def _on_section(self, row: int) -> None:
        if row < 0:
            return
        anchor = self.list.item(row).data(Qt.UserRole)
        self.browser.scrollToAnchor(anchor)

    def _on_search(self, text: str) -> None:
        text = text.strip().lower()
        if not text:
            self.status.setText("")
            for row in range(self.list.count()):
                self.list.item(row).setHidden(False)
            return
        found = 0
        for row in range(self.list.count()):
            item = self.list.item(row)
            anchor, name, html = DOC_SECTIONS[row]
            hit = text in name.lower() or text in html.lower()
            item.setHidden(not hit)
            found += hit
        self.status.setText(f"{found} section(s) contiennent « {text} »")
        for row in range(self.list.count()):
            if not self.list.item(row).isHidden():
                self.list.setCurrentRow(row)
                cursor = self.browser.textCursor()
                self.browser.moveCursor(cursor.Start)
                if self.browser.find(text):
                    break

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter l'aide",
                                              "aide_tileforge.html", "HTML (*.html)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(doc_html(__version__))
            self.status.setText(f"Aide exportée : {path}")


class WelcomeDialog(QDialog):
    """Écran d'accueil du premier lancement."""

    actionChosen = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Bienvenue dans {APP_NAME}")
        self.setMinimumWidth(320)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(10)

        title = QLabel(f"{APP_NAME}")
        font = QFont()
        font.setPointSize(22)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet(f"color: {theme.ACCENT};")
        root.addWidget(title)

        subtitle = QLabel("Reconstruisez les sprites de vos jeux 8 et 16 bits.")
        subtitle.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 14px;")
        root.addWidget(subtitle)

        root.addSpacing(8)
        intro = QLabel(
            "<p>TileForge charge une planche de tuiles, la découpe, vous aide à "
            "retrouver l'assemblage d'origine, produit un atlas et apprend la "
            "logique d'ordonnancement du jeu.</p>"
            "<p><b>Pour commencer :</b></p>")
        intro.setWordWrap(True)
        root.addWidget(intro)

        for text, action, hint in (
            ("Ouvrir la disquette Barbarian (.stx)", "barbarian",
             "le cas d'école : 252 tuiles de 24 × 21 px, prêtes à assembler"),
            ("Ouvrir une planche PNG", "png", "une planche déjà rendue"),
            ("Ouvrir une banque brute de ROM", "raw",
             "fichier binaire, offset et format de tuile"),
        ):
            button = QPushButton(text)
            button.setProperty("accent", action == "barbarian")
            button.setMinimumHeight(34)
            button.clicked.connect(lambda _c=False, a=action: self._choose(a))
            root.addWidget(button)
            label = QLabel(hint)
            label.setProperty("hint", True)
            label.setContentsMargins(10, 0, 0, 6)
            root.addWidget(label)

        root.addSpacing(6)
        bottom = QHBoxLayout()
        help_btn = QPushButton("Lire le tutoriel")
        help_btn.clicked.connect(self._open_help)
        bottom.addWidget(help_btn)
        bottom.addStretch(1)
        skip = QPushButton("Fermer")
        skip.clicked.connect(self.reject)
        bottom.addWidget(skip)
        root.addLayout(bottom)

    def _choose(self, action: str) -> None:
        self.actionChosen.emit(action)
        self.accept()

    def _open_help(self) -> None:
        dlg = HelpDialog(self)
        dlg.exec()


class ChangelogDialog(QDialog):
    """Notes de version."""

    def __init__(self, parent=None, title: str = "Nouveautés"):
        super().__init__(parent)
        self.setWindowTitle(title)
        fit_to_screen(self, 620, 520)
        root = QVBoxLayout(self)
        browser = QTextBrowser()
        text = changelog_text().replace("\n", "<br>").replace("  •", "&nbsp;&nbsp;•")
        browser.setHtml(f"<div style='font-family:monospace; font-size:12px'>{text}</div>")
        root.addWidget(browser, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)
