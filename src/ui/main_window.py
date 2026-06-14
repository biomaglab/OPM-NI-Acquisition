"""Main application window — the Controller in the MVC architecture.

``MainWindow`` wires together:
- ``DaqWorker`` (hardware, background thread)
- ``OpmProcessor`` (signal processing)
- ``TdmsRecorder`` / ``DataExporter`` (data persistence)
- ``ChartWidget`` + ``ControlPanel`` + ``SettingsDialog`` (UI)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QSplitter,
    QStatusBar,
    QFileDialog,
    QMessageBox,
    QPushButton,
)

from src.hardware.daq_config import DaqConfig
from src.hardware.daq_worker import DaqWorker
from src.processing.opm_processor import OpmProcessor
from src.data.tdms_recorder import TdmsRecorder
from src.data.exporter import DataExporter
from src.hardware.sensor_manager import SensorManager
from src.hardware.sensor_worker import SensorWorker
from src.ui.sensor_dialog import SensorDialog
from src.ui.chart_widget import ChartWidget
from src.ui.control_panel import ControlPanel
from src.ui.settings_dialog import SettingsDialog
from src.ui.ica_window import IcaWindow
from src.ui.qzfm_window import QzfmWindow

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Primary application window -- orchestrates all subsystems.

    Layout::

        +----------------------------+-----------------------------+
        |  ControlPanel (264px)      |   ChartWidget (stretch)     |
        |  ~~~~~~~~~~~~~~~~~~~~~~~~  |   ~~~~~~~~~~~~~~~~~~~~~~~~~ |
        |  [START] [STOP]            |   24x rolling waveforms     |
        |  [REC TDMS] [EXPORT DATA]  |                             |
        |  RATE: [____] Hz           |                             |
        |  WINDOW: [____] s          |                             |
        |  [SETTINGS]                |                             |
        +----------------------------+-----------------------------+
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OPM Sensor Management & Control  --  cDAQ-9171  |  24 Channels")
        self.setMinimumSize(1200, 700)

        # ── State ─────────────────────────────────────────────────────── #
        self._daq_config = DaqConfig()
        self._daq_worker: DaqWorker | None = None
        self._processor: OpmProcessor | None = None
        self._recorder = TdmsRecorder()
        self._exporter = DataExporter()
        self._ica_window: IcaWindow | None = None
        self._qzfm_window: QzfmWindow | None = None

        # Accumulator for export (keeps filtered data while acquiring).
        self._export_buffer: list[np.ndarray] = []
        
        # Sensor Integration
        self._sensor_manager = SensorManager()
        self._sensor_worker = SensorWorker(self._sensor_manager)
        
        # Load persisted settings 
        self._apply_persisted_settings()
        
        # Start SensorWorker
        self._sensor_worker.start_worker()

        # ── UI construction ───────────────────────────────────────────── #
        self._build_ui()
        self._connect_signals()

        # ── Status bar ────────────────────────────────────────────────── #
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("READY")
        
        # Add reset view icon to status bar (bottom right corner)
        self._btn_reset_view = QPushButton("⌂")
        self._btn_reset_view.setToolTip("Reset Chart View")
        self._btn_reset_view.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_reset_view.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #888;
                font-size: 26px;
                padding: 0px 6px 6px 0px;
            }
            QPushButton:hover { color: #FFF; }
        """)
        self._btn_reset_view.clicked.connect(self._chart.reset_views)
        self._statusbar.addPermanentWidget(self._btn_reset_view)

    # ── UI Construction ───────────────────────────────────────────────── #

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: control panel
        self._control_panel = ControlPanel()
        self._control_panel.set_sample_rate(self._daq_config.sample_rate)
        splitter.addWidget(self._control_panel)

        # Right: chart grid
        self._chart = ChartWidget(
            active_channels=self._daq_config.active_channels,
            sample_rate=self._daq_config.sample_rate,
            window_seconds=self._control_panel.get_window_seconds(),
        )
        splitter.addWidget(self._chart)

        # Splitter proportions (control panel stays narrow).
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([264, 936])

        layout.addWidget(splitter)

    def _connect_signals(self) -> None:
        cp = self._control_panel
        cp.start_clicked.connect(self._start_acquisition)
        cp.stop_clicked.connect(self._stop_acquisition)
        cp.save_toggled.connect(self._toggle_recording)
        cp.export_clicked.connect(self._export_data)
        cp.settings_clicked.connect(self._open_settings)
        cp.ica_clicked.connect(self._open_ica)
        cp.qzfm_clicked.connect(self._open_sensors)
        cp.sample_rate_changed.connect(self._on_sample_rate_changed)
        cp.window_seconds_changed.connect(self._on_window_changed)

    # ── Acquisition start / stop ──────────────────────────────────────── #

    def _start_acquisition(self) -> None:
        """Create DaqWorker + OpmProcessor and begin reading."""
        try:
            # Apply quick-settings sample rate.
            self._daq_config.sample_rate = self._control_panel.get_sample_rate()
            
            # Auto-calculate samples per read (10 updates per second)
            self._daq_config.samples_per_read = max(10, int(self._daq_config.sample_rate / 10))

            # Rebuild processor with current filter settings.
            self._rebuild_processor()

            # Clear chart and export buffer.
            self._chart.clear_data()
            self._export_buffer.clear()

            # Create and start DAQ worker.
            self._daq_worker = DaqWorker(self._daq_config)
            self._daq_worker.data_ready.connect(self._on_data_received)
            self._daq_worker.error_occurred.connect(self._on_daq_error)
            self._daq_worker.status_changed.connect(self._on_daq_status)
            self._daq_worker.finished.connect(self._on_daq_finished)
            self._daq_worker.start()

            self._control_panel.set_acquiring(True)
            self._control_panel.set_status("ACQUIRING", "success")
            self._statusbar.showMessage(
                f"DAQ: {self._daq_config.device_name} @ "
                f"{self._daq_config.sample_rate:.0f} Hz  |  "
                f"{self._daq_config.num_channels} Active CH"
            )
            logger.info("Acquisition started.")

        except Exception as exc:
            QMessageBox.critical(self, "DAQ Error", str(exc))
            logger.exception("Failed to start acquisition")

    def _stop_acquisition(self) -> None:
        """Stop the DaqWorker and clean up."""
        if self._daq_worker is not None and self._daq_worker.is_running:
            self._daq_worker.stop()
            self._daq_worker.wait(5000)  # wait up to 5s for thread to finish
        self._control_panel.set_acquiring(False)
        self._control_panel.set_status("STOPPED", "info")
        self._statusbar.showMessage("Acquisition stopped.")
        logger.info("Acquisition stopped.")

    # ── Data flow (Signal / Slot) ─────────────────────────────────────── #

    def _on_data_received(self, raw_data: np.ndarray) -> None:
        """Slot: receives raw block from DaqWorker, processes, and displays."""
        # 1. Filter
        if self._processor is not None:
            filtered = self._processor.process(raw_data)
        else:
            filtered = raw_data

        # 2. Update chart
        self._chart.update_data(filtered)

        # 3. Record if active (saving raw data)
        if self._recorder.is_recording:
            self._recorder.write(raw_data)
            
        # 4. Route to ICA if active
        if self._ica_window is not None and self._ica_window.isVisible():
            self._ica_window.add_data(filtered)

        # 5. Accumulate for potential export (saving raw data)
        self._export_buffer.append(raw_data)

        # Limit buffer to ~60 seconds to avoid unbounded memory usage.
        max_blocks = int(
            60 * self._daq_config.sample_rate / self._daq_config.samples_per_read
        )
        if len(self._export_buffer) > max_blocks:
            self._export_buffer.pop(0)

    def _on_daq_error(self, message: str) -> None:
        """Slot: handle DAQ errors."""
        self._control_panel.set_status("DAQ ERROR", "error")
        self._statusbar.showMessage(f"ERROR: {message}")
        QMessageBox.warning(self, "DAQ Error", message)
        logger.error("DAQ error: %s", message)

    def _on_daq_status(self, status: str) -> None:
        """Slot: forward DAQ status changes."""
        self._statusbar.showMessage(f"DAQ: {status}")

    def _on_daq_finished(self) -> None:
        """Slot: DaqWorker thread finished."""
        self._control_panel.set_acquiring(False)
        logger.info("DaqWorker thread finished.")

    # ── Recording ─────────────────────────────────────────────────────── #

    def _toggle_recording(self, active: bool) -> None:
        """Start or stop TDMS recording."""
        if active:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"opm_recording_{timestamp}.tdms"

            filepath, _ = QFileDialog.getSaveFileName(
                self,
                "Save Recording As",
                default_name,
                "TDMS Files (*.tdms)",
            )

            if not filepath:
                # User cancelled the dialog, uncheck the button
                self._control_panel._btn_record.setChecked(False)
                return

            self._recorder.start(
                filepath=Path(filepath),
                channel_names=self._daq_config.channel_names,
                sample_rate=self._daq_config.sample_rate,
            )
            self._control_panel.set_status("RECORDING", "warning")
            self._statusbar.showMessage(f"Recording to: {filepath}")
        else:
            if self._recorder.is_recording:
                self._recorder.stop()
            self._control_panel.set_status("ACQUIRING", "success")
            self._statusbar.showMessage("Recording stopped.")

    # ── Export ─────────────────────────────────────────────────────────── #

    def _export_data(self) -> None:
        """Export the accumulated data buffer to CSV or Excel."""
        if not self._export_buffer:
            QMessageBox.information(
                self, "No Data", "No data available for export."
            )
            return

        # Concatenate all buffered blocks.
        full_data = np.concatenate(self._export_buffer, axis=1)

        filepath, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Data",
            f"opm_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "CSV (*.csv);;Excel (*.xlsx)",
        )
        if not filepath:
            return

        try:
            path = Path(filepath)
            names = self._daq_config.channel_names
            sr = self._daq_config.sample_rate

            if path.suffix == ".xlsx":
                self._exporter.to_excel(full_data, path, names, sr)
            else:
                self._exporter.to_csv(full_data, path, names, sr)

            self._statusbar.showMessage(f"Exported: {path}")
            QMessageBox.information(
                self,
                "Export Complete",
                f"Data exported to:\n{path}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))
            logger.exception("Export failed")

    # ── Settings & Analysis ───────────────────────────────────────────── #

    def _open_ica(self) -> None:
        """Open the Real-Time ICA Window."""
        if self._ica_window is None:
            self._ica_window = IcaWindow(
                sample_rate=self._daq_config.sample_rate,
                active_physical_channels=self._daq_config.active_channels,
            )
        self._ica_window.show()
        self._ica_window.raise_()
        self._ica_window.activateWindow()

    def _open_qzfm(self) -> None:
        """Open the QZFM Sensor Control Window."""
        if self._qzfm_window is None:
            self._qzfm_window = QzfmWindow(parent=self)
        self._qzfm_window.set_active_channels(self._daq_config.active_channels)
        self._qzfm_window.show()
        self._qzfm_window.raise_()
        self._qzfm_window.activateWindow()

    def _open_sensors(self) -> None:
        """Open the Sensor Manager dialog."""
        dialog = SensorDialog(self._sensor_manager, self._sensor_worker, parent=self)
        dialog.exec()

    def _open_settings(self) -> None:
        """Open the settings dialog."""
        dialog = SettingsDialog(daq_config=self._daq_config, parent=self)
        if dialog.exec():
            self._daq_config = dialog.get_daq_config()
            
            # Update chart active channels and reset
            self._chart.set_active_channels(self._daq_config.active_channels)

            # Synchronize control panel sample rate
            self._control_panel.set_sample_rate(self._daq_config.sample_rate)

            # Rebuild processor with new filter settings.
            self._rebuild_processor()

            self._statusbar.showMessage("Settings updated.")
            logger.info("Settings updated via dialog.")

    def _on_sample_rate_changed(self, rate: float) -> None:
        """Quick-settings: sample rate changed in ControlPanel."""
        self._daq_config.sample_rate = rate

    def _on_window_changed(self, seconds: float) -> None:
        """Quick-settings: visualisation window changed."""
        self._chart.set_window_seconds(seconds)

    # ── Internal helpers ──────────────────────────────────────────────── #

    def _rebuild_processor(self) -> None:
        """Create a fresh OpmProcessor from current settings."""
        settings = QSettings("OPM", "OPM-Acquisition")
        self._processor = OpmProcessor(
            sample_rate=self._daq_config.sample_rate,
            num_channels=self._daq_config.num_channels,
            notch_enabled=settings.value("filters/notch_enabled", True, type=bool),
            bandpass_enabled=settings.value("filters/bp_enabled", True, type=bool),
            notch_low=float(settings.value("filters/notch_low", 59.0)),
            notch_high=float(settings.value("filters/notch_high", 61.0)),
            notch_order=int(settings.value("filters/notch_order", 2)),
            bp_low=float(settings.value("filters/bp_low", 2.0)),
            bp_high=float(settings.value("filters/bp_high", 50.0)),
            bp_order=int(settings.value("filters/bp_order", 4)),
        )

    def _apply_persisted_settings(self) -> None:
        """Apply QSettings-persisted values to the DaqConfig at startup."""
        s = QSettings("OPM", "OPM-Acquisition")
        self._daq_config = DaqConfig(
            device_name=s.value("hw/device", self._daq_config.device_name),
            channel_prefix=s.value("hw/prefix", self._daq_config.channel_prefix),
            sample_rate=float(s.value("acq/sample_rate", self._daq_config.sample_rate)),
            min_voltage=float(s.value("hw/vmin", self._daq_config.min_voltage)),
            max_voltage=float(s.value("hw/vmax", self._daq_config.max_voltage)),
            terminal_config=s.value("hw/terminal", self._daq_config.terminal_config),
        )
        
        # Load active channels safely
        active_channels = s.value("hw/active_channels", list(range(24)))
        if isinstance(active_channels, str):
            active_channels = [int(x.strip()) for x in active_channels.split(",") if x.strip()]
        elif isinstance(active_channels, list):
            active_channels = [int(x) for x in active_channels]
        self._daq_config.active_channels = active_channels
        
        self._sensor_manager.load_config(s)

    # ── Window lifecycle ──────────────────────────────────────────────── #

    def closeEvent(self, event) -> None:
        """Ensure clean shutdown of worker and recorder."""
        # Save sensor configurations
        s = QSettings("OPM", "OPM-Acquisition")
        self._sensor_manager.save_config(s)
        
        if self._daq_worker is not None and self._daq_worker.is_running:
            self._daq_worker.stop()
            self._daq_worker.wait(3000)
        if self._recorder.is_recording:
            self._recorder.stop()
        if self._ica_window is not None:
            self._ica_window.close()
        if self._qzfm_window is not None:
            self._qzfm_window.close()
        event.accept()
