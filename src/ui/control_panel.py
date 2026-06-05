"""Control panel sidebar with acquisition controls and quick settings.

Styled as an instrument front-panel with clear operational groupings,
monospace readouts, and LED-style status indicators.  No decorative
elements — purely functional.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QGroupBox,
    QFormLayout,
    QFrame,
    QSizePolicy,
)

from src.ui.sensor_panel import SensorPanel
from src.ui.styles import (
    ACCENT_RECORD,
    ACCENT_INFO,
    ACCENT_ACTIVE,
    ACCENT_WARNING,
    BG_CARD,
    BG_DARK,
    BG_INPUT,
    BORDER,
    LED_ERROR,
    LED_IDLE,
    LED_RECORDING,
    LED_RUNNING,
    LED_OFF,
    TEXT_BRIGHT,
    TEXT_DATA,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    FONT_MONO,
)


def _make_separator() -> QFrame:
    """Create a horizontal separator line."""
    sep = QFrame()
    sep.setObjectName("separator")
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFixedHeight(1)
    return sep


class ControlPanel(QWidget):
    """Instrument-style sidebar panel with acquisition controls.

    Signals
    -------
    start_clicked
        User pressed the *Start* button.
    stop_clicked
        User pressed the *Stop* button.
    save_toggled : bool
        User toggled recording on/off.
    export_clicked
        User pressed the *Export* button.
    settings_clicked
        User pressed the *Settings* button.
    sample_rate_changed : float
        Quick-access sample rate changed.
    window_seconds_changed : float
        Quick-access visualisation window changed.
    """

    start_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    save_toggled = pyqtSignal(bool)
    export_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    manage_sensors_clicked = pyqtSignal()
    ica_clicked = pyqtSignal()
    qzfm_clicked = pyqtSignal()
    sample_rate_changed = pyqtSignal(float)
    window_seconds_changed = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(264)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._is_recording = False
        self._settings = QSettings("OPM", "OPM-Acquisition")
        self._setup_ui()

    # ── UI Construction ───────────────────────────────────────────────── #

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────── #
        title = QLabel("OPM CONTROL SYSTEM")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        device_lbl = QLabel("Sensors & DAQ")
        device_lbl.setObjectName("subtitle")
        device_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(device_lbl)

        layout.addWidget(_make_separator())

        # ── Sensor Calibration ────────────────────────────────────────── #
        cal_group = QGroupBox("SENSOR CALIBRATION")
        cal_layout = QVBoxLayout(cal_group)
        cal_layout.setSpacing(6)

        self._btn_qzfm = QPushButton("QZFM SENSORS")
        self._btn_qzfm.clicked.connect(self.qzfm_clicked.emit)
        cal_layout.addWidget(self._btn_qzfm)

        layout.addWidget(cal_group)

        # ── Status indicator ──────────────────────────────────────────── #
        status_group = QGroupBox("STATUS")
        status_layout = QVBoxLayout(status_group)
        status_layout.setSpacing(4)

        self._status_label = QLabel("IDLE")
        self._status_label.setObjectName("status")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(
            f"border-left: 3px solid {LED_IDLE}; color: {LED_IDLE};"
        )
        status_layout.addWidget(self._status_label)

        layout.addWidget(status_group)

        # ── Acquisition controls ──────────────────────────────────────── #
        acq_group = QGroupBox("DAQ CONNECTION")
        acq_layout = QVBoxLayout(acq_group)
        acq_layout.setSpacing(6)

        # ON / OFF in a row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._btn_start = QPushButton("ON")
        self._btn_start.setObjectName("btn_start")
        self._btn_start.clicked.connect(self.start_clicked.emit)
        btn_row.addWidget(self._btn_start)

        self._btn_stop = QPushButton("OFF")
        self._btn_stop.setObjectName("btn_stop")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self.stop_clicked.emit)
        btn_row.addWidget(self._btn_stop)

        acq_layout.addLayout(btn_row)

        layout.addWidget(acq_group)

        # ── Logging controls ────────────────────────────────────────── #
        rec_group = QGroupBox("RECORDING")
        rec_layout = QVBoxLayout(rec_group)
        rec_layout.setSpacing(6)

        self._btn_record = QPushButton("START REC")
        self._btn_record.setObjectName("btn_record")
        self._btn_record.setCheckable(True)
        self._btn_record.setEnabled(False)
        self._btn_record.toggled.connect(self._on_record_toggled)
        rec_layout.addWidget(self._btn_record)

        self._btn_export = QPushButton("EXPORT DATA")
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self.export_clicked.emit)
        rec_layout.addWidget(self._btn_export)

        self._btn_settings = QPushButton("SETTINGS")
        self._btn_settings.clicked.connect(self.settings_clicked.emit)
        rec_layout.addWidget(self._btn_settings)

        layout.addWidget(rec_group)

        # ── Data Visualization ────────────────────────────────────────── #
        viz_group = QGroupBox("DATA VISUALIZATION")
        viz_layout = QVBoxLayout(viz_group)
        viz_layout.setSpacing(6)

        param_layout = QFormLayout()
        param_layout.setSpacing(6)
        param_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._spin_sample_rate = QDoubleSpinBox()
        self._spin_sample_rate.setRange(100.0, 51200.0)
        self._spin_sample_rate.setValue(float(self._settings.value("acq/sample_rate", 1000.0)))
        self._spin_sample_rate.setSuffix("  Hz")
        self._spin_sample_rate.setDecimals(0)
        self._spin_sample_rate.valueChanged.connect(self._on_sample_rate_changed)
        param_layout.addRow("RATE:", self._spin_sample_rate)

        self._spin_window = QDoubleSpinBox()
        self._spin_window.setRange(1.0, 30.0)
        self._spin_window.setValue(float(self._settings.value("acq/window_seconds", 5.0)))
        self._spin_window.setSuffix("  s")
        self._spin_window.setDecimals(1)
        self._spin_window.setSingleStep(0.5)
        self._spin_window.valueChanged.connect(self._on_window_changed)
        param_layout.addRow("TIME:", self._spin_window)

        viz_layout.addLayout(param_layout)

        self._btn_ica = QPushButton("REALTIME ICA")
        self._btn_ica.clicked.connect(self.ica_clicked.emit)
        viz_layout.addWidget(self._btn_ica)

        layout.addWidget(viz_group)

        # ── Stretch ───────────────────────────────────────────────────── #
        layout.addStretch()

        # ── Footer ────────────────────────────────────────────────────── #
        layout.addWidget(_make_separator())
        footer = QLabel("OPM-NI-ACQUISITION  v0.1")
        footer.setObjectName("subtitle")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)

    # ── Slots ─────────────────────────────────────────────────────────── #

    def _on_record_toggled(self, checked: bool) -> None:
        self._is_recording = checked
        if checked:
            self._btn_record.setText("STOP REC")
        else:
            self._btn_record.setText("REC  TDMS")
        self.save_toggled.emit(checked)
        
    def _on_sample_rate_changed(self, value: float) -> None:
        self._settings.setValue("acq/sample_rate", value)
        self.sample_rate_changed.emit(value)

    def _on_window_changed(self, value: float) -> None:
        self._settings.setValue("acq/window_seconds", value)
        self.window_seconds_changed.emit(value)

    # ── Public methods for MainWindow to update state ─────────────────── #

    def set_acquiring(self, active: bool) -> None:
        """Update button states when acquisition starts/stops."""
        self._btn_start.setEnabled(not active)
        self._btn_stop.setEnabled(active)
        self._btn_record.setEnabled(active)
        self._btn_export.setEnabled(not active)
        self._spin_sample_rate.setEnabled(not active)

        if not active:
            # Force-stop recording if acquisition stops.
            if self._btn_record.isChecked():
                self._btn_record.setChecked(False)

    def set_status(self, text: str, level: str = "info") -> None:
        """Update the status label with LED-style left border.

        Parameters
        ----------
        text : str
            Status message (displayed uppercase).
        level : str
            One of ``"info"``, ``"success"``, ``"warning"``, ``"error"``.
        """
        color_map = {
            "info": LED_IDLE,
            "success": LED_RUNNING,
            "warning": LED_RECORDING,
            "error": LED_ERROR,
        }
        color = color_map.get(level, LED_IDLE)
        self._status_label.setText(text.upper())
        self._status_label.setStyleSheet(
            f"border-left: 3px solid {color}; color: {color};"
        )

    def get_sample_rate(self) -> float:
        return self._spin_sample_rate.value()

    def get_window_seconds(self) -> float:
        return self._spin_window.value()

    def set_sample_rate(self, value: float) -> None:
        self._spin_sample_rate.setValue(value)

    def set_window_seconds(self, value: float) -> None:
        self._spin_window.setValue(value)
