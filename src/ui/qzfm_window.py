"""PyQt6 Window for QZFM sensor communication.

Provides a premium instrumentation control interface for QuSpin Zero-Field
Magnetometers. Supports status LEDs, live readouts, async commands via QzfmWorker,
real-time plotting of magnetic fields, and a monospace console logger.
"""

from __future__ import annotations

import logging
import numpy as np
import pyqtgraph as pg

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QPlainTextEdit,
    QSplitter,
    QMessageBox,
    QFrame,
    QFormLayout,
    QCheckBox,
    QScrollArea,
)

from src.processing.qzfm_worker import QzfmWorker
from src.ui.styles import (
    BG_DARKEST,
    BG_CARD,
    BG_INPUT,
    BORDER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_DATA,
    LED_OFF,
    LED_RUNNING,
    LED_ERROR,
    LED_IDLE,
    FONT_MONO,
)

logger = logging.getLogger(__name__)


class LedIndicator(QWidget):
    """Circular LED status indicator widget."""

    def __init__(self, label_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._led = QLabel()
        self._led.setFixedSize(12, 12)
        self.set_state(False)
        layout.addWidget(self._led)

        self._label = QLabel(label_text)
        self._label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(self._label)
        layout.addStretch()

    def set_state(self, active: bool) -> None:
        color = LED_RUNNING if active else LED_OFF
        self._led.setStyleSheet(
            f"background-color: {color}; border-radius: 6px; border: 1px solid {BORDER};"
        )


class SmallSensorLed(QWidget):
    """Compact sensor LED indicator with label below."""

    def __init__(self, ch_num: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._led = QLabel()
        self._led.setFixedSize(10, 10)
        self.set_state(False)
        layout.addWidget(self._led)

        self._label = QLabel(f"S{ch_num:02d}")
        self._label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 9px; font-family: {FONT_MONO};")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

    def set_state(self, active: bool) -> None:
        color = LED_RUNNING if active else LED_OFF
        self._led.setStyleSheet(
            f"background-color: {color}; border-radius: 5px; border: 1px solid {BORDER};"
        )


class QzfmWindow(QMainWindow):
    """Control window for QuSpin Zero-Field Magnetometer."""

    # Threading signals wired to the background QzfmWorker
    connect_clicked = pyqtSignal(str)
    disconnect_clicked = pyqtSignal()
    auto_start_clicked = pyqtSignal(bool)  # zero_calibrate
    field_zero_clicked = pyqtSignal(bool)  # on/off
    calibrate_clicked = pyqtSignal()
    field_reset_clicked = pyqtSignal()
    reboot_clicked = pyqtSignal()
    start_streaming_clicked = pyqtSignal(str)  # axis
    stop_streaming_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("QZFM Sensor Interface (QuSpin OPM)")
        self.setMinimumSize(1000, 650)

        # Background thread and worker
        self._thread: QThread | None = None
        self._worker: QzfmWorker | None = None
        self._is_connected = False
        self._is_streaming = False
        self._active_channels = list(range(24))
        self._autostart_timer = None
        self._autostart_step = 0

        # Plot buffering
        self._time_buffer = np.array([])
        self._field_buffer = np.array([])
        self._window_seconds = 10.0

        self._build_ui()
        self._init_worker_thread()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: Controls Panel (Scrollable) ──────────────────────────── #
        scroll_area = QScrollArea()
        scroll_area.setFixedWidth(320)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")
        controls_layout = QVBoxLayout(scroll_content)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(8)

        # Actions Group (Moved to the very top)
        act_group = QGroupBox("SENSOR COMMANDS")
        act_layout = QVBoxLayout(act_group)
        act_layout.setSpacing(6)

        self._btn_autostart = QPushButton("AUTO-START")
        self._btn_autostart.clicked.connect(self._on_autostart_clicked)
        act_layout.addWidget(self._btn_autostart)

        self._btn_zero = QPushButton("FIELD ZERO")
        self._btn_zero.setCheckable(True)
        self._btn_zero.clicked.connect(self._on_zero_toggled)
        act_layout.addWidget(self._btn_zero)

        self._btn_calibrate = QPushButton("CALIBRATE")
        self._btn_calibrate.clicked.connect(self.calibrate_clicked.emit)
        act_layout.addWidget(self._btn_calibrate)

        self._btn_reset_coils = QPushButton("RESET COILS")
        self._btn_reset_coils.clicked.connect(self.field_reset_clicked.emit)
        act_layout.addWidget(self._btn_reset_coils)

        self._btn_reboot = QPushButton("REBOOT")
        self._btn_reboot.clicked.connect(self.reboot_clicked.emit)
        act_layout.addWidget(self._btn_reboot)

        controls_layout.addWidget(act_group)

        # Connection Group
        conn_group = QGroupBox("CONNECTION")
        conn_layout = QVBoxLayout(conn_group)
        conn_layout.setSpacing(6)

        conn_layout.addWidget(QLabel("DEVICE / PORT:"))
        self._txt_device = QLineEdit("SIMULATOR")
        conn_layout.addWidget(self._txt_device)

        self._btn_connect = QPushButton("CONNECT")
        self._btn_connect.clicked.connect(self._toggle_connection)
        conn_layout.addWidget(self._btn_connect)
        controls_layout.addWidget(conn_group)

        # LEDs Status Indicators Group
        led_group = QGroupBox("STATUS LEDS")
        led_layout = QVBoxLayout(led_group)
        led_layout.setSpacing(4)

        self._led_laser_on = LedIndicator("LASER ON")
        self._led_temp_lock = LedIndicator("CELL TEMP LOCK")
        self._led_laser_lock = LedIndicator("LASER LOCK")
        self._led_field_zeroed = LedIndicator("FIELD ZEROED")

        led_layout.addWidget(self._led_laser_on)
        led_layout.addWidget(self._led_temp_lock)
        led_layout.addWidget(self._led_laser_lock)
        led_layout.addWidget(self._led_field_zeroed)
        controls_layout.addWidget(led_group)

        # Readouts Group
        read_group = QGroupBox("LIVE PARAMETERS")
        read_layout = QFormLayout(read_group)
        read_layout.setSpacing(4)
        read_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._lbl_temp_err = QLabel("N/A")
        self._lbl_temp_err.setObjectName("readout")
        read_layout.addRow("T ERROR:", self._lbl_temp_err)

        self._lbl_temp_volt = QLabel("N/A")
        self._lbl_temp_volt.setObjectName("readout")
        read_layout.addRow("T VOLTAGE:", self._lbl_temp_volt)

        self._lbl_bx = QLabel("N/A")
        self._lbl_bx.setObjectName("readout")
        read_layout.addRow("B0 FIELD:", self._lbl_bx)

        self._lbl_by = QLabel("N/A")
        self._lbl_by.setObjectName("readout")
        read_layout.addRow("BY FIELD:", self._lbl_by)

        self._lbl_bz = QLabel("N/A")
        self._lbl_bz.setObjectName("readout")
        read_layout.addRow("BZ FIELD:", self._lbl_bz)

        controls_layout.addWidget(read_group)

        # Streaming Config Group
        stream_group = QGroupBox("DATA STREAMING")
        stream_layout = QVBoxLayout(stream_group)
        stream_layout.setSpacing(6)

        axis_row = QHBoxLayout()
        axis_row.addWidget(QLabel("AXIS:"))
        self._cmb_axis = QComboBox()
        self._cmb_axis.addItems(["z", "y", "x"])
        axis_row.addWidget(self._cmb_axis)
        stream_layout.addLayout(axis_row)

        self._chk_stream = QCheckBox("STREAMING ACTIVE")
        self._chk_stream.clicked.connect(self._on_stream_toggled)
        stream_layout.addWidget(self._chk_stream)
        controls_layout.addWidget(stream_group)

        controls_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        splitter.addWidget(scroll_area)

        # ── Right: Plot & Logs ─────────────────────────────────────────── #
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # Upper: Realtime Plot
        plot_container = QWidget()
        plot_layout = QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(6, 6, 6, 6)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground(BG_DARKEST)
        self._plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self._plot_widget.setLabel("left", "Magnetic Field", units="pT")
        self._plot_widget.setLabel("bottom", "Time", units="s")
        self._plot_widget.setXRange(-self._window_seconds, 0)
        
        # Style axes
        ax_left = self._plot_widget.getAxis("left")
        ax_bottom = self._plot_widget.getAxis("bottom")
        ax_left.setPen(pg.mkPen(color=BORDER, width=1))
        ax_bottom.setPen(pg.mkPen(color=BORDER, width=1))
        ax_left.setTextPen(pg.mkPen(color=TEXT_SECONDARY))
        ax_bottom.setTextPen(pg.mkPen(color=TEXT_SECONDARY))

        self._curve = self._plot_widget.plot(pen=pg.mkPen(color=LED_IDLE, width=1.5))
        plot_layout.addWidget(self._plot_widget)
        right_splitter.addWidget(plot_container)

        # Middle: Individual Sensor LEDs (below streaming/plot screen)
        sensor_status_group = QGroupBox("INDIVIDUAL SENSOR STATUS (24 CHANNELS)")
        sensor_status_layout = QGridLayout(sensor_status_group)
        sensor_status_layout.setContentsMargins(10, 8, 10, 8)
        sensor_status_layout.setSpacing(6)

        self._sensor_leds: list[SmallSensorLed] = []
        for i in range(24):
            led = SmallSensorLed(i + 1)
            self._sensor_leds.append(led)
            row = i // 12
            col = i % 12
            sensor_status_layout.addWidget(led, row, col)
            
        right_splitter.addWidget(sensor_status_group)

        # Lower: Console Logger
        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(6, 6, 6, 6)

        log_lbl = QLabel("DIAGNOSTIC LOGS")
        log_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        log_layout.addWidget(log_lbl)

        self._txt_log = QPlainTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setFont(pg.QtGui.QFont(FONT_MONO, 9))
        self._txt_log.setStyleSheet(
            f"background-color: {BG_INPUT}; border: 1px solid {BORDER}; color: {TEXT_PRIMARY};"
        )
        log_layout.addWidget(self._txt_log)
        right_splitter.addWidget(log_container)

        right_splitter.setStretchFactor(0, 4)  # Plot takes most space
        right_splitter.setStretchFactor(1, 0)  # LEDs take minimum height
        right_splitter.setStretchFactor(2, 1)  # Logs take remaining space

        right_layout.addWidget(right_splitter)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 680])

        layout.addWidget(splitter)
        self._set_ui_connected(False)

    def _init_worker_thread(self) -> None:
        """Create and start the background thread & worker."""
        self._thread = QThread()
        self._worker = QzfmWorker()
        self._worker.moveToThread(self._thread)

        # Thread management
        self._thread.started.connect(lambda: logger.info("QZFM background thread started."))
        self._thread.finished.connect(lambda: logger.info("QZFM background thread stopped."))

        # Signal connections (worker -> ui)
        self._worker.connected_status.connect(self._on_connected_status)
        self._worker.status_updated.connect(self._on_status_updated)
        self._worker.data_received.connect(self._on_data_received)
        self._worker.log_received.connect(self._on_log_received)
        self._worker.error_occurred.connect(self._on_error)

        # Signal connections (ui -> worker)
        self.connect_clicked.connect(self._worker.connect_sensor)
        self.disconnect_clicked.connect(self._worker.disconnect_sensor)
        self.auto_start_clicked.connect(self._worker.run_auto_start)
        self.field_zero_clicked.connect(self._worker.run_field_zero)
        self.calibrate_clicked.connect(self._worker.run_calibrate)
        self.field_reset_clicked.connect(self._worker.run_field_reset)
        self.reboot_clicked.connect(self._worker.run_reboot)
        self.start_streaming_clicked.connect(self._worker.start_streaming)
        self.stop_streaming_clicked.connect(self._worker.stop_streaming)

        self._thread.start()

    # ── UI Event Handlers ──────────────────────────────────────────────── #

    def _toggle_connection(self) -> None:
        if self._is_connected:
            self._btn_connect.setEnabled(False)
            self.disconnect_clicked.emit()
        else:
            device = self._txt_device.text().strip()
            if not device:
                QMessageBox.warning(self, "Invalid Input", "Please enter a device name or port.")
                return
            self._btn_connect.setEnabled(False)
            self._btn_connect.setText("CONNECTING...")
            self.connect_clicked.emit(device)

    def _on_autostart_clicked(self) -> None:
        # Prompt if user wants to also field-zero & calibrate
        reply = QMessageBox.question(
            self,
            "Auto-Start Option",
            "Do you also want to Field Zero and Calibrate the sensor during initialization?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        zero_cal = reply == QMessageBox.StandardButton.Yes
        
        self._set_ui_waiting(True, "Running Auto-Start...")
        self.auto_start_clicked.emit(zero_cal)
        
        # Start sequential visual locking for 24 channels
        self._start_autostart_led_simulation()

    def _on_zero_toggled(self, checked: bool) -> None:
        self.field_zero_clicked.emit(checked)

    def _on_stream_toggled(self, checked: bool) -> None:
        self._is_streaming = checked
        if checked:
            axis = self._cmb_axis.currentText()
            self._time_buffer = np.array([])
            self._field_buffer = np.array([])
            self.start_streaming_clicked.emit(axis)
            self._txt_log.appendPlainText(f"[App] Streaming started on axis '{axis}'...")
        else:
            self.stop_streaming_clicked.emit()
            self._txt_log.appendPlainText("[App] Streaming stopped.")

    # ── Worker Slots / Callbacks ───────────────────────────────────────── #

    @pyqtSlot(bool)
    def _on_connected_status(self, connected: bool) -> None:
        self._is_connected = connected
        self._btn_connect.setEnabled(True)
        self._set_ui_connected(connected)
        
        # Stop autostart timer if running
        if not connected and self._autostart_timer is not None:
            self._autostart_timer.stop()
            self._autostart_timer = None
        
        if connected:
            self._btn_connect.setText("DISCONNECT")
            self._txt_log.appendPlainText("[System] Connected to sensor.")
            self._update_sensor_leds(True)
        else:
            self._btn_connect.setText("CONNECT")
            self._txt_log.appendPlainText("[System] Disconnected from sensor.")
            self._clear_readouts()
            self._update_sensor_leds(False)

    @pyqtSlot(dict, dict)
    def _on_status_updated(self, leds: dict, params: dict) -> None:
        # Enable UI waiting block if we were waiting for auto-start
        self._set_ui_waiting(False)

        # Update LEDs
        self._led_laser_on.set_state(leds.get("laser on (LED1)", False))
        self._led_temp_lock.set_state(leds.get("cell temp lock (LED2)", False))
        self._led_laser_lock.set_state(leds.get("laser lock (LED3)", False))
        self._led_field_zeroed.set_state(leds.get("field zeroed (LED4)", False))

        self._btn_zero.setChecked(leds.get("field zeroed (LED4)", False))

        # Update Readouts
        self._update_readout_label(self._lbl_temp_err, params.get("cell temp error"), "{:.4f}")
        self._update_readout_label(self._lbl_temp_volt, params.get("cell temp voltage"), "{:.0f} mV")
        self._update_readout_label(self._lbl_bx, params.get("B0 field (pT)"), "{:.1f} pT")
        self._update_readout_label(self._lbl_by, params.get("By field (pT)"), "{:.1f} pT")
        self._update_readout_label(self._lbl_bz, params.get("Bz field (pT)"), "{:.1f} pT")

    @pyqtSlot(np.ndarray, np.ndarray)
    def _on_data_received(self, times: np.ndarray, fields: np.ndarray) -> None:
        self._time_buffer = np.concatenate([self._time_buffer, times])
        self._field_buffer = np.concatenate([self._field_buffer, fields])

        # Keep last N seconds of data at 200 Hz
        max_samples = int(self._window_seconds * 200)
        if len(self._time_buffer) > max_samples:
            self._time_buffer = self._time_buffer[-max_samples:]
            self._field_buffer = self._field_buffer[-max_samples:]

        if len(self._time_buffer) > 0:
            rel_times = self._time_buffer - self._time_buffer[-1]
            self._curve.setData(rel_times, self._field_buffer)

    @pyqtSlot(str)
    def _on_log_received(self, message: str) -> None:
        self._txt_log.appendPlainText(message)

    @pyqtSlot(str)
    def _on_error(self, message: str) -> None:
        self._set_ui_waiting(False)
        self._txt_log.appendPlainText(f"[Error] {message}")
        QMessageBox.critical(self, "QZFM Error", message)

    # ── Helpers ────────────────────────────────────────────────────────── #

    def _update_readout_label(self, label: QLabel, val: float | None, fmt: str) -> None:
        if val is None or np.isnan(val):
            label.setText("N/A")
            label.setStyleSheet("color: " + TEXT_SECONDARY)
        else:
            label.setText(fmt.format(val))
            label.setStyleSheet("color: " + TEXT_DATA)

    def _clear_readouts(self) -> None:
        for lbl in [self._lbl_temp_err, self._lbl_temp_volt, self._lbl_bx, self._lbl_by, self._lbl_bz]:
            lbl.setText("N/A")
            lbl.setStyleSheet("color: " + TEXT_SECONDARY)
        for led in [self._led_laser_on, self._led_temp_lock, self._led_laser_lock, self._led_field_zeroed]:
            led.set_state(False)

    def _set_ui_connected(self, connected: bool) -> None:
        # Enable or disable device actions based on connection state
        self._txt_device.setEnabled(not connected)
        self._btn_autostart.setEnabled(connected)
        self._btn_zero.setEnabled(connected)
        self._btn_calibrate.setEnabled(connected)
        self._btn_reset_coils.setEnabled(connected)
        self._btn_reboot.setEnabled(connected)
        self._cmb_axis.setEnabled(connected)
        self._chk_stream.setEnabled(connected)
        
        if not connected:
            self._chk_stream.setChecked(False)
            self._is_streaming = False
            self._curve.setData([], [])

    def _set_ui_waiting(self, waiting: bool, message: str = "") -> None:
        """Block controls during slow, blocking actions (like Auto-Start)."""
        self._btn_connect.setEnabled(not waiting)
        self._btn_autostart.setEnabled(not waiting)
        self._btn_zero.setEnabled(not waiting)
        self._btn_calibrate.setEnabled(not waiting)
        self._btn_reset_coils.setEnabled(not waiting)
        self._btn_reboot.setEnabled(not waiting)
        
        if waiting:
            self._txt_log.appendPlainText(f"[System] {message}")

    def set_active_channels(self, active_channels: list[int]) -> None:
        """Set which physical channels are active."""
        self._active_channels = active_channels
        self._update_sensor_leds(self._is_connected)

    def _update_sensor_leds(self, active: bool) -> None:
        """Update individual sensor LEDs based on active list and connection status."""
        for i, led in enumerate(self._sensor_leds):
            if active and i in self._active_channels:
                led.set_state(True)
            else:
                led.set_state(False)

    def _start_autostart_led_simulation(self) -> None:
        """Start sequence simulation for lighting up sensor LEDs."""
        if self._autostart_timer is not None:
            self._autostart_timer.stop()
        
        # Turn off all sensor LEDs first
        self._update_sensor_leds(False)
        
        self._autostart_step = 0
        from PyQt6.QtCore import QTimer
        self._autostart_timer = QTimer(self)
        self._autostart_timer.timeout.connect(self._simulate_led_lock)
        self._autostart_timer.start(150)  # 150ms per active sensor LED lock

    def _simulate_led_lock(self) -> None:
        """Sequential locking step for multi-channel visualization."""
        while self._autostart_step < 24:
            ch = self._autostart_step
            self._autostart_step += 1
            if ch in self._active_channels:
                self._sensor_leds[ch].set_state(True)
                break
        if self._autostart_step >= 24:
            self._autostart_timer.stop()
            self._autostart_timer = None

    # ── Window Lifecycle ───────────────────────────────────────────────── #

    def closeEvent(self, event) -> None:
        """Clean shutdown of background thread and serial connections."""
        self.stop_streaming_clicked.emit()
        self.disconnect_clicked.emit()

        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)

        self._thread = None
        self._worker = None
        event.accept()
