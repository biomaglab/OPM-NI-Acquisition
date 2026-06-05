"""Application-wide visual theme, QSS styles, and colour constants.

Implements a professional instrumentation theme inspired by LabVIEW,
NI SignalExpress, and scientific data-acquisition software.  Emphasises
readability, clear hierarchy, and a utilitarian aesthetic over
decorative elements.
"""

from __future__ import annotations

# ── Colour Palette (Instrumentation / Industrial) ────────────────────────── #

# Surface colours — steel-gray gradient
BG_DARKEST = "#14161A"       # Main window background (darker for contrast)
BG_DARK = "#1F2229"          # Sidebar / panel background
BG_CARD = "#2A2E38"          # Card / group box background
BG_HOVER = "#2F3440"         # Hover state
BG_INPUT = "#1E2128"         # Input field background
BG_HEADER = "#1F2229"        # Header / toolbar background
BORDER = "#4A5263"           # Standard border (brighter)
BORDER_LIGHT = "#5C657A"     # Lighter border for inner elements
BORDER_FOCUS = "#5B9BD5"     # Focus ring (instrument blue)

# Accent colours — functional, not decorative
ACCENT_PRIMARY = "#5B9BD5"   # Instrument blue (NI-style)
ACCENT_ACTIVE = "#3D8B37"    # Operational green (LED on)
ACCENT_RECORD = "#C0392B"    # Recording red
ACCENT_WARNING = "#D4A017"   # Caution amber
ACCENT_INFO = "#5B9BD5"      # Same as primary — informational

# Text colours
TEXT_PRIMARY = "#F0F2F5"     # Main text (high contrast on dark)
TEXT_SECONDARY = "#A9B1C2"   # Labels, secondary info (brighter)
TEXT_DISABLED = "#70788A"    # Disabled elements (more visible)
TEXT_BRIGHT = "#EBEDF0"     # Emphasized / active text
TEXT_DATA = "#A8D8A8"        # Data readout (greenish, oscilloscope-style)

# LED indicator colours (for status)
LED_OFF = "#3A3E47"
LED_IDLE = "#5B9BD5"
LED_RUNNING = "#3D8B37"
LED_RECORDING = "#C0392B"
LED_ERROR = "#E74C3C"

# Sensor status colors
SENSOR_ONLINE = "#3D8B37"
SENSOR_WARMING = "#D4A017"
SENSOR_OFFLINE = "#70788A"
SENSOR_ERROR = "#E74C3C"

# Wizard step colors  
WIZARD_DONE = "#3D8B37"
WIZARD_ACTIVE = "#5B9BD5"
WIZARD_PENDING = "#4A5263"

# ── Channel colour palette (24 distinct, muted scientific tones) ─────────── #

CHANNEL_COLORS: list[str] = [
    "#5B9BD5",  # 1  — Steel blue
    "#70AD47",  # 2  — Olive green
    "#ED7D31",  # 3  — Burnt orange
    "#FFC000",  # 4  — Amber
    "#44546A",  # 5  — Slate
    "#A5A5A5",  # 6  — Silver
    "#4472C4",  # 7  — Cobalt
    "#C55A11",  # 8  — Rust
    "#7030A0",  # 9  — Deep purple
    "#00B0F0",  # 10 — Cyan
    "#92D050",  # 11 — Lime
    "#FF6F61",  # 12 — Coral
    "#4EA6DC",  # 13 — Sky
    "#BF8F00",  # 14 — Dark gold
    "#548235",  # 15 — Forest
    "#C45911",  # 16 — Copper
    "#2E75B6",  # 17 — Ocean
    "#A9D18E",  # 18 — Sage
    "#F4B183",  # 19 — Peach
    "#8FAADC",  # 20 — Periwinkle
    "#D09A44",  # 21 — Bronze
    "#2DC6B8",  # 22 — Teal
    "#B4C7E7",  # 23 — Ice
    "#E2C044",  # 24 — Mustard
]

# ── Fonts ────────────────────────────────────────────────────────────────── #

FONT_FAMILY = "Segoe UI, Tahoma, Arial, sans-serif"
FONT_MONO = "Consolas, Courier New, monospace"
FONT_SIZE_XS = "10px"
FONT_SIZE_SM = "11px"
FONT_SIZE_MD = "12px"
FONT_SIZE_LG = "14px"
FONT_SIZE_XL = "16px"
FONT_SIZE_TITLE = "15px"

# ── Spacing & Radius ────────────────────────────────────────────────────── #

RADIUS_SM = "2px"
RADIUS_MD = "3px"
RADIUS_LG = "4px"

# ── QSS Stylesheet ──────────────────────────────────────────────────────── #

APP_STYLESHEET = f"""
/* ── Global ───────────────────────────────────────────────────────────── */
QWidget {{
    background-color: {BG_DARKEST};
    color: {TEXT_PRIMARY};
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_MD};
}}

QMainWindow {{
    background-color: {BG_DARKEST};
}}

/* ── Labels ───────────────────────────────────────────────────────────── */
QLabel {{
    background: transparent;
    padding: 0px;
}}

QLabel#title {{
    font-size: {FONT_SIZE_TITLE};
    font-weight: 600;
    color: {TEXT_BRIGHT};
    text-transform: uppercase;
}}

QLabel#subtitle {{
    font-size: {FONT_SIZE_SM};
    color: {TEXT_SECONDARY};
    font-family: {FONT_MONO};
}}

QLabel#status {{
    font-size: {FONT_SIZE_MD};
    font-weight: 600;
    font-family: {FONT_MONO};
    padding: 6px 12px;
    border-radius: {RADIUS_SM};
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-left: 3px solid {ACCENT_PRIMARY};
}}

QLabel#readout {{
    font-family: {FONT_MONO};
    font-size: {FONT_SIZE_MD};
    color: {TEXT_DATA};
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    padding: 4px 8px;
}}

/* ── Push Buttons ─────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    padding: 5px 12px;
    font-size: {FONT_SIZE_MD};
    font-weight: 600;
    min-height: 26px;
    text-transform: uppercase;
}}

QPushButton:hover {{
    background-color: {BG_HOVER};
    border-color: {BORDER_LIGHT};
}}

QPushButton:pressed {{
    background-color: {ACCENT_PRIMARY};
    color: {TEXT_BRIGHT};
    border-color: {ACCENT_PRIMARY};
}}

QPushButton:disabled {{
    background-color: #20232A;
    color: {TEXT_DISABLED};
    border: 1px solid #303540;
}}

QPushButton#btn_start {{
    background-color: #2D5F2D;
    color: #B8E6B8;
    border: 1px solid #3D8B37;
}}

QPushButton#btn_start:hover {{
    background-color: #357A35;
    color: {TEXT_BRIGHT};
}}

QPushButton#btn_start:disabled {{
    background-color: #1A2E1A;
    color: {TEXT_DISABLED};
    border: 1px solid #254025;
}}

QPushButton#btn_stop {{
    background-color: #5C2020;
    color: #E8A0A0;
    border: 1px solid #8B3030;
}}

QPushButton#btn_stop:hover {{
    background-color: #7A2D2D;
    color: {TEXT_BRIGHT};
}}

QPushButton#btn_stop:disabled {{
    background-color: #2E1A1A;
    color: {TEXT_DISABLED};
    border: 1px solid #402525;
}}

QPushButton#btn_record {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
}}

QPushButton#btn_record:checked {{
    background-color: #5C2020;
    color: #FF8080;
    border: 1px solid {ACCENT_RECORD};
}}

QPushButton#btn_record:disabled {{
    background-color: #20232A;
    color: {TEXT_DISABLED};
    border: 1px solid #303540;
}}

/* ── Spin Boxes / Line Edits ──────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox, QLineEdit {{
    background-color: {BG_INPUT};
    color: {TEXT_DATA};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    padding: 4px 8px;
    min-height: 24px;
    font-family: {FONT_MONO};
    font-size: {FONT_SIZE_MD};
    selection-background-color: {ACCENT_PRIMARY};
}}

QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border-color: {ACCENT_PRIMARY};
}}

QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {{
    background-color: {BG_DARK};
    color: {TEXT_DISABLED};
    border-color: {BG_DARK};
}}

QSpinBox::up-button, QDoubleSpinBox::up-button {{
    background-color: {BG_CARD};
    border-left: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    width: 20px;
}}

QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background-color: {BG_CARD};
    border-left: 1px solid {BORDER};
    width: 20px;
}}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {BG_HOVER};
}}

/* ── Combo Boxes ──────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    padding: 4px 8px;
    font-size: {FONT_SIZE_MD};
}}

QComboBox:focus {{
    border-color: {ACCENT_PRIMARY};
}}

QComboBox QAbstractItemView {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_PRIMARY};
    border: 1px solid {BORDER};
    outline: none;
}}

QComboBox::drop-down {{
    background-color: {BG_CARD};
    border-left: 1px solid {BORDER};
    width: 20px;
}}

/* ── Tab Widget ───────────────────────────────────────────────────────── */
QTabWidget::pane {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    padding: 10px;
    margin-top: -1px;
}}

QTabBar::tab {{
    background-color: {BG_DARK};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-bottom: none;
    padding: 6px 16px;
    margin-right: 1px;
    font-size: {FONT_SIZE_SM};
    font-weight: 600;
    text-transform: uppercase;
}}

QTabBar::tab:selected {{
    background-color: {BG_CARD};
    color: {TEXT_BRIGHT};
    border-bottom: 2px solid {ACCENT_PRIMARY};
}}

QTabBar::tab:hover:!selected {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}

/* ── Check Boxes ──────────────────────────────────────────────────────── */
QCheckBox {{
    spacing: 8px;
    background: transparent;
    font-size: {FONT_SIZE_MD};
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border-radius: {RADIUS_SM};
    border: 1px solid {BORDER_LIGHT};
    background-color: {BG_INPUT};
}}

QCheckBox::indicator:checked {{
    background-color: {ACCENT_PRIMARY};
    border-color: {ACCENT_PRIMARY};
}}

/* ── Group Boxes ──────────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    margin-top: 22px;
    padding: 8px;
    padding-top: 8px;
    font-weight: 600;
    font-size: {FONT_SIZE_SM};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    top: 2px;
    padding: 0px;
    color: {TEXT_SECONDARY};
    font-size: {FONT_SIZE_SM};
    text-transform: uppercase;
    background-color: transparent;
}}

/* ── Scroll Bars ──────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {BG_DARK};
    width: 8px;
}}

QScrollBar::handle:vertical {{
    background: {BORDER};
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {BORDER_LIGHT};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* ── Dialog ───────────────────────────────────────────────────────────── */
QDialog {{
    background-color: {BG_DARKEST};
}}

/* ── Splitter ─────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {BORDER};
    width: 1px;
}}

QSplitter::handle:hover {{
    background-color: {ACCENT_PRIMARY};
}}

/* ── Status Bar ───────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {BG_HEADER};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    font-family: {FONT_MONO};
    font-size: {FONT_SIZE_XS};
    padding: 2px 8px;
}}

/* ── Separator lines ──────────────────────────────────────────────────── */
QFrame#separator {{
    background-color: {BORDER};
    max-height: 1px;
    margin: 4px 0px;
}}

/* ── Form labels ──────────────────────────────────────────────────────── */
QFormLayout QLabel {{
    font-size: {FONT_SIZE_SM};
    color: {TEXT_SECONDARY};
    text-transform: uppercase;
}}

/* ── List Widget ──────────────────────────────────────────────────────── */
QListWidget {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 4px;
    outline: none;
}}

QListWidget::item {{
    padding: 8px 12px;
    border-radius: {RADIUS_SM};
    color: {TEXT_BRIGHT};
    font-size: {FONT_SIZE_MD};
    font-weight: 500;
}}

QListWidget::item:selected {{
    background-color: {ACCENT_PRIMARY};
    color: {TEXT_PRIMARY};
}}

QListWidget::item:hover:!selected {{
    background-color: {BG_HOVER};
}}

/* ── Sensor & Wizard Styles ───────────────────────────────────────────── */
QFrame.sensor-card {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
}}
QFrame.sensor-card:hover {{
    border-color: {BORDER_LIGHT};
}}
QLabel.sensor-led {{
    border-radius: 5px;
    background-color: {LED_OFF};
    min-width: 10px;
    min-height: 10px;
    max-width: 10px;
    max-height: 10px;
}}
QFrame.wizard-step {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 16px;
}}
QProgressBar.wizard-progress {{
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    text-align: center;
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
}}
QProgressBar.wizard-progress::chunk {{
    background-color: {ACCENT_PRIMARY};
    width: 10px;
}}
"""
