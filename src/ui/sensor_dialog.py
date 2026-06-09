"""Full management dialog for configuring and calibrating QZFM sensors."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
    QGroupBox,
    QFormLayout,
    QComboBox,
    QWidget,
    QSplitter,
    QInputDialog,
    QMessageBox,
    QLineEdit,
    QCheckBox,
    QTabWidget,
    QPlainTextEdit
)

from src.hardware.sensor_manager import SensorManager, SensorInfo
from src.hardware.sensor_worker import SensorWorker, SensorCommand
from src.ui.calibration_wizard import CalibrationWizard
from src.ui.zeroing_window import ZeroingWindow
from src.ui.batch_start_window import BatchStartWindow
from src.ui.styles import (
    BG_DARKEST,
    BG_CARD,
    BG_INPUT,
    BORDER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    ACCENT_PRIMARY,
    LED_IDLE,
    FONT_MONO
)

class SensorDialog(QDialog):
    """Dialog for full sensor configuration and manual control."""
    
    def __init__(self, manager: SensorManager, worker: SensorWorker, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.worker = worker
        self._zeroing_windows: dict[str, ZeroingWindow] = {}
        
        # Plot streaming state
        self._is_streaming = False
        self._time_buffer = np.array([])
        self._field_buffer = np.array([])
        self._window_seconds = 10.0
        
        self.setWindowTitle("OPM Sensor Management")
        self.setMinimumSize(850, 600)
        self._setup_ui()
        self._connect_signals()
        self._populate_list()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # ── Left pane: List of sensors ──────────────────────────────────────── #
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(10, 10, 10, 10)
        
        lbl_list_title = QLabel("OPM SENSORS")
        lbl_list_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        left_layout.addWidget(lbl_list_title)
        
        self.list_sensors = QListWidget()
        self.list_sensors.currentRowChanged.connect(self._on_sensor_selected)
        left_layout.addWidget(self.list_sensors)
        
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("ADD")
        self.btn_add.clicked.connect(self._on_add_sensor)
        self.btn_remove = QPushButton("REMOVE")
        self.btn_remove.clicked.connect(self._on_remove_sensor)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_remove)
        left_layout.addLayout(btn_layout)
        
        self.btn_start_all = QPushButton("START ALL SENSORS")
        self.btn_start_all.setStyleSheet(f"background-color: {ACCENT_PRIMARY}; color: {BG_DARKEST}; font-weight: bold; padding: 10px; margin-top: 10px;")
        self.btn_start_all.clicked.connect(self._on_start_all_sensors)
        left_layout.addWidget(self.btn_start_all)
        
        splitter.addWidget(left_pane)
        
        # ── Right pane: Details ────────────────────────────────────────────── #
        self.right_pane = QWidget()
        right_layout = QVBoxLayout(self.right_pane)
        right_layout.setContentsMargins(10, 10, 10, 10)
        
        # Wizard banner
        wizard_banner = QGroupBox("GUIDED CALIBRATION")
        wizard_banner.setStyleSheet(f"QGroupBox {{ border-left: 4px solid {ACCENT_PRIMARY}; }}")
        wl = QHBoxLayout(wizard_banner)
        
        lbl_wizard = QLabel("For new users, use the wizard to initialize and calibrate.")
        lbl_wizard.setWordWrap(True)
        wl.addWidget(lbl_wizard)
        
        self.btn_wizard = QPushButton("START WIZARD")
        self.btn_wizard.setMinimumHeight(40)
        self.btn_wizard.setStyleSheet("font-weight: bold;")
        self.btn_wizard.clicked.connect(self._on_run_wizard)
        wl.addWidget(self.btn_wizard)
        
        right_layout.addWidget(wizard_banner)
        
        # TABS
        self.tabs = QTabWidget()
        right_layout.addWidget(self.tabs)
        
        # ── Tab 1: Control & Status ──
        tab_control = QWidget()
        tc_layout = QVBoxLayout(tab_control)
        
        # Details group
        details_group = QGroupBox("SENSOR DETAILS")
        form = QFormLayout(details_group)
        
        self.lbl_id = QLabel()
        self.lbl_port = QLabel()
        self.edit_name = QLineEdit()
        self.edit_name.editingFinished.connect(self._on_name_changed)
        
        self.chk_master = QCheckBox("Master")
        self.chk_master.toggled.connect(self._on_master_toggled)
        
        self.cmb_sensor_axis_mode = QComboBox()
        self.cmb_sensor_axis_mode.addItems(["z", "y", "dual"])
        self.cmb_sensor_axis_mode.currentTextChanged.connect(self._on_axis_mode_changed)
        
        form.addRow("ID:", self.lbl_id)
        form.addRow("Port:", self.lbl_port)
        form.addRow("Name:", self.edit_name)
        form.addRow("Synchronization:", self.chk_master)
        form.addRow("Axis Mode:", self.cmb_sensor_axis_mode)
        
        tc_layout.addWidget(details_group)
        
        # Status group
        status_group = QGroupBox("REAL-TIME STATUS")
        sf = QFormLayout(status_group)
        
        # LEDs Container
        led_container = QWidget()
        led_container.setStyleSheet("background-color: transparent;")
        led_layout = QHBoxLayout(led_container)
        led_layout.setContentsMargins(0, 0, 0, 0)
        led_layout.setSpacing(8)
        
        self.led_laser = QLabel("Lsr On")
        self.led_temp = QLabel("Tmp Lck")
        self.led_lock = QLabel("Lsr Lck")
        self.led_zero = QLabel("Fld Zro")
        
        self._leds = [self.led_laser, self.led_temp, self.led_lock, self.led_zero]
        for led in self._leds:
            led.setAlignment(Qt.AlignmentFlag.AlignCenter)
            led.setFixedSize(55, 20)
            led.setStyleSheet(f"background-color: {BG_INPUT}; color: {TEXT_SECONDARY}; border-radius: 10px; font-size: 10px;")
            led_layout.addWidget(led)
            
        led_layout.addStretch()
        
        self.lbl_b0 = QLabel()
        self.lbl_bz = QLabel()
        self.lbl_temp_err = QLabel()
        
        for lbl in (self.lbl_b0, self.lbl_bz, self.lbl_temp_err):
            lbl.setStyleSheet(f"font-family: {FONT_MONO};")
            
        sf.addRow("LEDs Lock:", led_container)
        sf.addRow("B0 Field:", self.lbl_b0)
        sf.addRow("Bz Field:", self.lbl_bz)
        sf.addRow("Temp Error:", self.lbl_temp_err)
        
        tc_layout.addWidget(status_group)
        
        # Manual Actions
        actions_group = QGroupBox("MANUAL CONTROL")
        al = QHBoxLayout(actions_group)
        
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self._on_connect_toggle)
        al.addWidget(self.btn_connect)
        
        self.btn_auto_start = QPushButton("Auto Start")
        self.btn_auto_start.clicked.connect(self._on_auto_start)
        al.addWidget(self.btn_auto_start)
        
        self.btn_zero = QPushButton("Field Zero")
        self.btn_zero.clicked.connect(self._on_zero_toggle)
        al.addWidget(self.btn_zero)
        
        self.btn_calibrate = QPushButton("Calibrate")
        self.btn_calibrate.clicked.connect(self._on_calibrate)
        al.addWidget(self.btn_calibrate)
        
        self.btn_reset = QPushButton("Reset Field")
        self.btn_reset.clicked.connect(self._on_reset)
        al.addWidget(self.btn_reset)
        
        self.btn_reboot = QPushButton("Reboot")
        self.btn_reboot.clicked.connect(self._on_reboot)
        al.addWidget(self.btn_reboot)
        
        tc_layout.addWidget(actions_group)
        tc_layout.addStretch()
        
        self.tabs.addTab(tab_control, "Status & Control")
        
        # ── Tab 2: Signal Monitor (Pyqtgraph) ──
        tab_monitor = QWidget()
        tm_layout = QVBoxLayout(tab_monitor)
        
        stream_ctrls = QHBoxLayout()
        stream_ctrls.addWidget(QLabel("Read Axis:"))
        self.cmb_axis = QComboBox()
        self.cmb_axis.addItems(["z", "y", "x"])
        stream_ctrls.addWidget(self.cmb_axis)
        
        self.chk_stream = QCheckBox("ENABLE STREAMING (Serial)")
        self.chk_stream.clicked.connect(self._on_stream_toggled)
        stream_ctrls.addWidget(self.chk_stream)
        stream_ctrls.addStretch()
        
        tm_layout.addLayout(stream_ctrls)
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(BG_DARKEST)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setLabel("left", "Magnetic Field", units="pT")
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setXRange(-self._window_seconds, 0)
        
        ax_left = self.plot_widget.getAxis("left")
        ax_bottom = self.plot_widget.getAxis("bottom")
        ax_left.setPen(pg.mkPen(color=BORDER, width=1))
        ax_bottom.setPen(pg.mkPen(color=BORDER, width=1))
        
        self.curve = self.plot_widget.plot(pen=pg.mkPen(color=LED_IDLE, width=1.5))
        tm_layout.addWidget(self.plot_widget)
        
        self.tabs.addTab(tab_monitor, "Signal Monitor")
        
        # ── Tab 3: Diagnostic Logs ──
        tab_logs = QWidget()
        tl_layout = QVBoxLayout(tab_logs)
        
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(pg.QtGui.QFont(FONT_MONO, 9))
        self.txt_log.setStyleSheet(
            f"background-color: {BG_INPUT}; border: 1px solid {BORDER}; color: {TEXT_PRIMARY};"
        )
        tl_layout.addWidget(self.txt_log)
        
        self.tabs.addTab(tab_logs, "Diagnostic Logs")
        
        # ── Finish layout ──
        splitter.addWidget(self.right_pane)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 590])
        
        layout.addWidget(splitter)
        
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close, alignment=Qt.AlignmentFlag.AlignRight)
        
        # Disable auto default on all buttons to prevent Enter key in QLineEdit from triggering them
        for btn in self.findChildren(QPushButton):
            btn.setAutoDefault(False)
        
    def _connect_signals(self):
        self.worker.status_updated.connect(self._on_status_updated)
        self.worker.zeroing_data.connect(self._on_zeroing_data)
        self.worker.field_zero_completed.connect(self._on_field_zero_completed)
        self.worker.data_received.connect(self._on_data_received)
        self.worker.log_received.connect(self._on_log_received)
        
    def _populate_list(self):
        self.list_sensors.clear()
        configs = self.manager.get_configs()
        for s_id, cfg in configs.items():
            item = QListWidgetItem(f"{cfg['name']} ({cfg['port']})")
            item.setData(Qt.ItemDataRole.UserRole, s_id)
            self.list_sensors.addItem(item)
            
        if self.list_sensors.count() > 0:
            self.list_sensors.setCurrentRow(0)
        else:
            self.right_pane.setEnabled(False)
            
    def _current_sensor_id(self) -> str | None:
        item = self.list_sensors.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None
        
    def _on_sensor_selected(self, row: int):
        s_id = self._current_sensor_id()
        if not s_id:
            self.right_pane.setEnabled(False)
            return
            
        self.right_pane.setEnabled(True)
        info = self.manager.get_info(s_id)
        
        # Reset streaming state when switching sensors
        self.chk_stream.setChecked(False)
        self._on_stream_toggled(False)
        self._time_buffer = np.array([])
        self._field_buffer = np.array([])
        self.curve.setData([], [])
        
        # Load logs for this sensor
        self.txt_log.clear()
        for msg, _ in info.messages:
            self.txt_log.appendPlainText(msg)
            
        self._update_details_pane(info)
        
    @pyqtSlot(str, object)
    def _on_status_updated(self, s_id: str, info: SensorInfo):
        for i in range(self.list_sensors.count()):
            item = self.list_sensors.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == s_id:
                new_text = f"{info.name} ({info.port})"
                if item.text() != new_text:
                    item.setText(new_text)
                break
                
        if s_id == self._current_sensor_id():
            self._update_details_pane(info)
            
    def _update_details_pane(self, info: SensorInfo):
        if self.lbl_id.text() != info.sensor_id:
            self.lbl_id.setText(info.sensor_id)
        if self.lbl_port.text() != info.port:
            self.lbl_port.setText(info.port)
        
        if self.edit_name.text() != info.name and not self.edit_name.hasFocus():
            self.edit_name.setText(info.name)
            
        self.chk_master.blockSignals(True)
        if self.chk_master.isChecked() != info.is_master:
            self.chk_master.setChecked(info.is_master)
        self.chk_master.blockSignals(False)
        
        self.cmb_sensor_axis_mode.blockSignals(True)
        if self.cmb_sensor_axis_mode.currentText() != info.axis_mode:
            self.cmb_sensor_axis_mode.setCurrentText(info.axis_mode)
        self.cmb_sensor_axis_mode.blockSignals(False)
        
        def _update_led(lbl: QLabel, active: bool):
            if getattr(lbl, "_active_state", None) == active:
                return
            lbl._active_state = active
            if active:
                lbl.setStyleSheet(f"background-color: {ACCENT_PRIMARY}; color: {TEXT_PRIMARY}; border-radius: 10px; font-weight: bold; font-size: 10px;")
            else:
                lbl.setStyleSheet(f"background-color: {BG_INPUT}; color: {TEXT_SECONDARY}; border-radius: 10px; font-size: 10px;")
                
        _update_led(self.led_laser, info.laser_on)
        _update_led(self.led_temp, info.cell_temp_locked)
        _update_led(self.led_lock, info.laser_locked)
        _update_led(self.led_zero, info.field_zeroed)
        
        b0_str = f"{info.b0_field:.2f} pT"
        if self.lbl_b0.text() != b0_str:
            self.lbl_b0.setText(b0_str)
            
        bz_str = f"{info.bz_field:.2f} pT"
        if self.lbl_bz.text() != bz_str:
            self.lbl_bz.setText(bz_str)
            
        temp_err_str = f"{info.cell_temp_error:.4f}"
        if self.lbl_temp_err.text() != temp_err_str:
            self.lbl_temp_err.setText(temp_err_str)
        
        if info.connected:
            self.btn_connect.setText("Disconnect")
            self.btn_zero.setEnabled(True)
            self.btn_reset.setEnabled(True)
            self.btn_auto_start.setEnabled(True)
            self.btn_calibrate.setEnabled(True)
            self.btn_reboot.setEnabled(True)
            self.btn_wizard.setEnabled(True)
            self.chk_stream.setEnabled(True)
        else:
            self.btn_connect.setText("Connect")
            self.btn_zero.setEnabled(False)
            self.btn_reset.setEnabled(False)
            self.btn_auto_start.setEnabled(False)
            self.btn_calibrate.setEnabled(False)
            self.btn_reboot.setEnabled(False)
            self.btn_wizard.setEnabled(False)
            self.chk_stream.setEnabled(False)
            self.chk_stream.setChecked(False)
            self._is_streaming = False
            
    def _on_add_sensor(self):
        ports = self.manager.list_available_ports()
        if not ports:
            QMessageBox.warning(self, "Warning", "No COM port found.")
            return
            
        port, ok = QInputDialog.getItem(self, "Add Sensor", "Select port:", ports, 0, False)
        if ok and port:
            s_id = f"qzfm_{len(self.manager.get_configs())}"
            self.manager.add_sensor(s_id, port)
            self._populate_list()
            
    def _on_remove_sensor(self):
        s_id = self._current_sensor_id()
        if s_id:
            reply = QMessageBox.question(self, "Confirm", f"Remove {s_id}?")
            if reply == QMessageBox.StandardButton.Yes:
                self.manager.remove_sensor(s_id)
                self._populate_list()
                
    def _on_name_changed(self):
        s_id = self._current_sensor_id()
        if s_id:
            cfg = self.manager.get_configs()[s_id]
            cfg["name"] = self.edit_name.text()
            self._populate_list()
            
    def _on_master_toggled(self, checked: bool):
        s_id = self._current_sensor_id()
        if s_id:
            if self.manager.get_info(s_id).connected:
                self.worker.queue_command(s_id, SensorCommand.SET_MASTER, is_master=checked)
            else:
                self.manager.get_configs()[s_id]["is_master"] = checked
                
    def _on_axis_mode_changed(self, text: str):
        s_id = self._current_sensor_id()
        if s_id:
            if self.manager.get_info(s_id).connected:
                self.worker.queue_command(s_id, SensorCommand.SET_AXIS_MODE, mode=text)
            else:
                self.manager.get_configs()[s_id]["axis_mode"] = text
            
    def _on_connect_toggle(self):
        s_id = self._current_sensor_id()
        if not s_id: return
        
        info = self.manager.get_info(s_id)
        if info.connected:
            self.worker.queue_command(s_id, SensorCommand.DISCONNECT)
        else:
            self.worker.queue_command(s_id, SensorCommand.CONNECT)
            
    def _on_zero_toggle(self):
        s_id = self._current_sensor_id()
        if not s_id: return
        
        if s_id in self._zeroing_windows and self._zeroing_windows[s_id].isVisible():
            self.worker.queue_command(s_id, SensorCommand.FIELD_ZERO_STOP)
            self._zeroing_windows[s_id].close()
        else:
            self.worker.queue_command(s_id, SensorCommand.FIELD_ZERO_START, axes_xyz=True)
            info = self.manager.get_info(s_id)
            zw = ZeroingWindow(s_id, info.name, self)
            zw.btn_ok.setEnabled(False)
            zw.btn_ok.clicked.connect(lambda: self._confirm_zeroing(s_id))
            zw.btn_stop.clicked.connect(lambda: self._stop_zeroing(s_id))
            zw.show()
            self._zeroing_windows[s_id] = zw
            
    def _stop_zeroing(self, s_id: str):
        self.worker.queue_command(s_id, SensorCommand.FIELD_ZERO_STOP)
        if s_id in self._zeroing_windows:
            self._zeroing_windows[s_id].close()
            del self._zeroing_windows[s_id]

    def _confirm_zeroing(self, s_id: str):
        self.worker.queue_command(s_id, SensorCommand.CALIBRATE)
        if s_id in self._zeroing_windows:
            self._zeroing_windows[s_id].close()
            del self._zeroing_windows[s_id]

    def _on_field_zero_completed(self, s_id: str):
        if s_id in self._zeroing_windows:
            window = self._zeroing_windows[s_id]
            window.btn_ok.setEnabled(True)
            if hasattr(window, 'lbl_info'):
                window.lbl_info.setText("Field zeroing complete. Press OK to continue.")
            
    def _on_reset(self):
        s_id = self._current_sensor_id()
        if s_id:
            self.worker.queue_command(s_id, SensorCommand.FIELD_RESET)
            
    def _on_auto_start(self):
        s_id = self._current_sensor_id()
        if s_id:
            self.worker.queue_command(s_id, SensorCommand.AUTO_START)
            
    def _on_calibrate(self):
        s_id = self._current_sensor_id()
        if s_id:
            self.worker.queue_command(s_id, SensorCommand.CALIBRATE)
            
    def _on_reboot(self):
        s_id = self._current_sensor_id()
        if s_id:
            reply = QMessageBox.question(self, "Confirm Reboot", f"Reboot sensor {s_id}?\nCommunication will be temporarily interrupted.")
            if reply == QMessageBox.StandardButton.Yes:
                self.worker.queue_command(s_id, SensorCommand.REBOOT)
            
    def _on_run_wizard(self):
        s_id = self._current_sensor_id()
        if not s_id: return
        
        # Stop streaming if running
        if self.chk_stream.isChecked():
            self.chk_stream.setChecked(False)
            self._on_stream_toggled(False)
            
        info = self.manager.get_info(s_id)
        wizard = CalibrationWizard(s_id, info.name, self.worker, self)
        wizard.exec()
        
    def _on_start_all_sensors(self):
        configs = self.manager.get_configs()
        if not configs:
            QMessageBox.warning(self, "Warning", "No sensors configured.")
            return
            
        masters = [cid for cid, c in configs.items() if c.get('is_master')]
        if len(masters) == 0:
            QMessageBox.warning(self, "Warning", "No Master sensor configured! Please set exactly one sensor as Master before starting all.")
            return
        elif len(masters) > 1:
            QMessageBox.warning(self, "Warning", "Multiple Master sensors configured! Please set exactly ONE sensor as Master.")
            return
            
        reply = QMessageBox.question(
            self,
            "Start All Sensors",
            "This will orchestrate the heating, zeroing, and calibration sequence for ALL configured sensors.\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            window = BatchStartWindow(self.manager, self.worker, self)
            window.exec()
        
    def _on_stream_toggled(self, checked: bool):
        s_id = self._current_sensor_id()
        if not s_id: return
        
        self._is_streaming = checked
        if checked:
            axis = self.cmb_axis.currentText()
            self._time_buffer = np.array([])
            self._field_buffer = np.array([])
            self.worker.queue_command(s_id, SensorCommand.START_STREAMING, axis=axis)
        else:
            self.worker.queue_command(s_id, SensorCommand.STOP_STREAMING)
            
    @pyqtSlot(str, float, float, float, float)
    def _on_zeroing_data(self, s_id: str, bz: float, by: float, b0: float, t_err: float):
        if s_id in self._zeroing_windows and self._zeroing_windows[s_id].isVisible():
            self._zeroing_windows[s_id].update_data(s_id, bz, by, b0, t_err)

    @pyqtSlot(str, object, object)
    def _on_data_received(self, s_id: str, times: np.ndarray, fields: np.ndarray):
        if s_id != self._current_sensor_id() or not self._is_streaming:
            return
            
        self._time_buffer = np.concatenate([self._time_buffer, times])
        self._field_buffer = np.concatenate([self._field_buffer, fields])

        max_samples = int(self._window_seconds * 200)
        if len(self._time_buffer) > max_samples:
            self._time_buffer = self._time_buffer[-max_samples:]
            self._field_buffer = self._field_buffer[-max_samples:]

        if len(self._time_buffer) > 0:
            rel_times = self._time_buffer - self._time_buffer[-1]
            self.curve.setData(rel_times, self._field_buffer)
            
    @pyqtSlot(str, str)
    def _on_log_received(self, s_id: str, message: str):
        if s_id == self._current_sensor_id():
            self.txt_log.appendPlainText(message)
