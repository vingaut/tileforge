"""Thème visuel de TileForge (feuille de style Qt)."""

from __future__ import annotations

BG = "#16171b"
PANEL = "#1e1f25"
PANEL_ALT = "#25262e"
BORDER = "#32343f"
TEXT = "#d7dae2"
TEXT_DIM = "#8b90a0"
ACCENT = "#4c9aff"
ACCENT_DARK = "#2f6fbf"
OK = "#4cc38a"
WARN = "#e8b339"
ERR = "#e5534b"
GRID = "#3a3d4a"

STYLESHEET = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-size: 13px;
}}
QLabel {{ background: transparent; }}
QCheckBox {{ background: transparent; }}
QRadioButton {{ background: transparent; }}
QMainWindow, QDialog {{ background-color: {BG}; }}

QToolBar {{
    background: {PANEL};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 3px;
    spacing: 3px;
}}
QToolBar QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 8px;
    color: {TEXT};
}}
QToolBar QToolButton:hover {{ background: {PANEL_ALT}; border-color: {BORDER}; }}
QToolBar QToolButton:checked {{ background: {ACCENT_DARK}; border-color: {ACCENT}; }}
QToolBar::separator {{ background: {BORDER}; width: 1px; margin: 4px 6px; }}

QTabWidget::pane {{ border: none; background: {BG}; }}
QTabBar::tab {{
    background: {PANEL};
    color: {TEXT_DIM};
    padding: 8px 20px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; background: {PANEL_ALT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QGroupBox {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 18px;
    padding: 10px 8px 8px 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    top: 4px;
    padding: 0 4px;
    color: {TEXT_DIM};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
}}

QPushButton {{
    background: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 6px 12px;
}}
QPushButton:hover {{ border-color: {ACCENT}; background: #2b2d36; }}
QPushButton:pressed {{ background: #1a1b21; }}
QPushButton:disabled {{ color: {TEXT_DIM}; border-color: #26272e; }}
QPushButton[accent="true"] {{
    background: {ACCENT_DARK};
    border-color: {ACCENT};
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{ background: {ACCENT}; }}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 6px;
    selection-background-color: {ACCENT_DARK};
}}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{ border-color: #454a5a; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {PANEL_ALT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DARK};
    outline: none;
}}

QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {PANEL_ALT};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QSlider::groove:horizontal {{
    height: 4px; background: {BORDER}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 12px; margin: -5px 0; border-radius: 6px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT_DARK}; border-radius: 2px; }}

QListWidget, QTreeWidget, QTableWidget, QTextEdit, QPlainTextEdit {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 4px;
    alternate-background-color: #22232a;
    selection-background-color: {ACCENT_DARK};
    outline: none;
}}
QListWidget::item {{ padding: 2px; }}
QListWidget::item:selected {{ background: {ACCENT_DARK}; }}
QHeaderView::section {{
    background: {PANEL_ALT};
    color: {TEXT_DIM};
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 5px;
    font-weight: 600;
}}
QTableWidget {{ gridline-color: {BORDER}; }}

QScrollBar:vertical {{ background: {BG}; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #3a3d4a; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #4a4e5e; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: {BG}; height: 11px; }}
QScrollBar::handle:horizontal {{ background: #3a3d4a; border-radius: 5px; min-width: 24px; }}

QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; color: {TEXT_DIM}; }}
QStatusBar QLabel {{ color: {TEXT_DIM}; padding: 0 8px; }}

QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

QMenuBar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 6px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {PANEL_ALT}; }}
QMenu {{ background: {PANEL_ALT}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 20px; border-radius: 3px; }}
QMenu::item:selected {{ background: {ACCENT_DARK}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QToolTip {{
    background: #2b2d36;
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px;
}}

QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{
    background: {PANEL_ALT};
    padding: 6px 10px;
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
}}

QProgressBar {{
    background: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    height: 16px;
}}
QProgressBar::chunk {{ background: {ACCENT_DARK}; border-radius: 3px; }}

QScrollArea {{ border: none; background: {PANEL}; }}
QLabel[dim="true"] {{ color: {TEXT_DIM}; }}
QLabel[hint="true"] {{ color: {TEXT_DIM}; font-size: 11px; }}
"""


def hex_color(rgb) -> str:
    """Tuple RGB → chaîne #rrggbb (utilisée dans les feuilles de style)."""
    r, g, b = (int(v) for v in rgb[:3])
    return f"#{r:02x}{g:02x}{b:02x}"
