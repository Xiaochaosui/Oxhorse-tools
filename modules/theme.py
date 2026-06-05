DARK_TECH = """
/* ===== Global ===== */
QWidget {
    background-color: #0a0e1a;
    color: #c8d8f0;
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New', monospace;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: #0a0e1a;
}

/* ===== Tab Bar ===== */
QTabWidget::pane {
    border: 1px solid #1e3a5f;
    background-color: #0d1220;
    border-radius: 4px;
}

QTabBar::tab {
    background-color: #0d1220;
    color: #5a7a9a;
    padding: 8px 18px;
    border: 1px solid #1a2d4a;
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    min-width: 80px;
    font-size: 12px;
    letter-spacing: 1px;
}

QTabBar::tab:selected {
    background-color: #0f1e35;
    color: #4fc3f7;
    border-color: #1e3a5f;
    border-bottom: 2px solid #4fc3f7;
}

QTabBar::tab:hover:!selected {
    background-color: #0f1e35;
    color: #90caf9;
}

/* ===== Scroll Bars ===== */
QScrollBar:vertical {
    background: #0d1220;
    width: 6px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #1e3a5f;
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ===== Buttons ===== */
QPushButton {
    background-color: #0f1e35;
    color: #4fc3f7;
    border: 1px solid #1e3a5f;
    border-radius: 4px;
    padding: 6px 16px;
    font-size: 12px;
    letter-spacing: 0.5px;
}
QPushButton:hover {
    background-color: #1a3a5c;
    border-color: #4fc3f7;
    color: #81d4fa;
}
QPushButton:pressed {
    background-color: #0d2a45;
}

/* ===== LineEdit ===== */
QLineEdit {
    background-color: #0d1a2e;
    border: 1px solid #1e3a5f;
    border-radius: 4px;
    padding: 5px 10px;
    color: #c8d8f0;
    selection-background-color: #1e3a5f;
}
QLineEdit:focus {
    border-color: #4fc3f7;
}

/* ===== SpinBox / TimeEdit ===== */
QTimeEdit, QSpinBox, QDoubleSpinBox {
    background-color: #0d1a2e;
    border: 1px solid #1e3a5f;
    border-radius: 4px;
    padding: 4px 8px;
    color: #c8d8f0;
}
QTimeEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #4fc3f7;
}
QTimeEdit::up-button, QSpinBox::up-button, QDoubleSpinBox::up-button,
QTimeEdit::down-button, QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: #1e3a5f;
    border: none;
    width: 16px;
}

/* ===== Label ===== */
QLabel {
    color: #c8d8f0;
    background: transparent;
}

/* ===== GroupBox ===== */
QGroupBox {
    border: 1px solid #1e3a5f;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 8px;
    color: #4fc3f7;
    font-size: 11px;
    letter-spacing: 1px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #4fc3f7;
}

/* ===== Table ===== */
QTableWidget {
    background-color: #0d1220;
    alternate-background-color: #0f1830;
    gridline-color: #1a2d4a;
    border: 1px solid #1e3a5f;
    border-radius: 4px;
    selection-background-color: #1a3a5c;
}
QTableWidget::item {
    padding: 4px 8px;
    color: #c8d8f0;
}
QTableWidget::item:selected {
    background-color: #1a3a5c;
    color: #81d4fa;
}
QHeaderView::section {
    background-color: #0f1e35;
    color: #4fc3f7;
    padding: 6px;
    border: none;
    border-right: 1px solid #1e3a5f;
    border-bottom: 1px solid #1e3a5f;
    font-size: 11px;
    letter-spacing: 1px;
}

/* ===== CheckBox ===== */
QCheckBox {
    color: #c8d8f0;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #1e3a5f;
    border-radius: 3px;
    background: #0d1a2e;
}
QCheckBox::indicator:checked {
    background-color: #1565c0;
    border-color: #4fc3f7;
}

/* ===== ComboBox ===== */
QComboBox {
    background-color: #0d1a2e;
    border: 1px solid #1e3a5f;
    border-radius: 4px;
    padding: 4px 10px;
    color: #c8d8f0;
    min-width: 100px;
}
QComboBox:focus { border-color: #4fc3f7; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #0d1a2e;
    border: 1px solid #1e3a5f;
    selection-background-color: #1a3a5c;
    color: #c8d8f0;
}

/* ===== Tooltip ===== */
QToolTip {
    background-color: #0f1e35;
    color: #4fc3f7;
    border: 1px solid #1e3a5f;
    border-radius: 4px;
    padding: 4px 8px;
}
"""

NEON_COLORS = {
    "cyan": "#4fc3f7",
    "blue": "#1565c0",
    "green": "#00e676",
    "red": "#ff5252",
    "orange": "#ff9800",
    "yellow": "#ffd740",
    "purple": "#ce93d8",
    "dim": "#5a7a9a",
    "bg_card": "#0f1e35",
    "bg_dark": "#0a0e1a",
    "bg_mid": "#0d1220",
    "border": "#1e3a5f",
    "text": "#c8d8f0",
    "text_dim": "#5a7a9a",
}
