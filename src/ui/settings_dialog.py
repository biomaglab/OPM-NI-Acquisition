"""Settings dialog for the OPM acquisition system.

Provides a tabbed interface to configure hardware, acquisition,
filter, and export parameters.  Settings are persisted between
sessions using ``QSettings``.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QGridLayout,
)

from src.hardware.daq_config import DaqConfig

# ── Constants ────────────────────────────────────────────────────────────── #

_ORG = "OPM"
_APP = "OPM-Acquisition"


class SettingsDialog(QDialog):
    """Modal dialog for editing system settings.

    Tabs
    ----
    - **Hardware** : device, terminal config, voltage range, samples/read, active channels.
    - **Filters** : enable/disable and tune notch & bandpass filters.
    - **Export** : default output directory and format.

    Parameters
    ----------
    daq_config : DaqConfig
        Current DAQ configuration (used to populate initial values).
    parent : QWidget | None
        Parent widget.
    """

    def __init__(
        self,
        daq_config: DaqConfig | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("SETTINGS")
        self.setMinimumSize(520, 480)
        self.setModal(True)

        self._settings = QSettings(_ORG, _APP)
        cfg = daq_config or DaqConfig()
        self._total_channels = cfg.total_channels

        # ── Main layout ───────────────────────────────────────────────── #
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        self._tabs = QTabWidget()
        main_layout.addWidget(self._tabs)

        # ── Build tabs ────────────────────────────────────────────────── #
        self._build_hardware_tab(cfg)
        self._build_filters_tab()
        self._build_export_tab()

        # ── Buttons ───────────────────────────────────────────────────── #
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        restore_btn = buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        if restore_btn:
            restore_btn.clicked.connect(self._restore_defaults)
        main_layout.addWidget(buttons)

        # ── Load persisted values ─────────────────────────────────────── #
        self._load_settings()

    # ── Tab builders ──────────────────────────────────────────────────── #

    def _build_hardware_tab(self, cfg: DaqConfig) -> None:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setSpacing(10)

        self._edit_device = QLineEdit(cfg.device_name)
        layout.addRow("DEVICE NAME:", self._edit_device)

        self._edit_prefix = QLineEdit(cfg.channel_prefix)
        layout.addRow("CH PREFIX:", self._edit_prefix)

        self._combo_terminal = QComboBox()
        self._combo_terminal.addItems(["RSE", "NRSE", "DIFF", "PSEUDO_DIFF"])
        self._combo_terminal.setCurrentText(cfg.terminal_config)
        layout.addRow("TERMINAL:", self._combo_terminal)

        self._spin_vmin = QDoubleSpinBox()
        self._spin_vmin.setRange(-100.0, 0.0)
        self._spin_vmin.setValue(cfg.min_voltage)
        self._spin_vmin.setSuffix(" V")
        self._spin_vmin.setDecimals(1)
        layout.addRow("V MIN:", self._spin_vmin)

        self._spin_vmax = QDoubleSpinBox()
        self._spin_vmax.setRange(0.0, 100.0)
        self._spin_vmax.setValue(cfg.max_voltage)
        self._spin_vmax.setSuffix(" V")
        self._spin_vmax.setDecimals(1)
        layout.addRow("V MAX:", self._spin_vmax)
        
        self._spin_sample_rate = QDoubleSpinBox()
        self._spin_sample_rate.setRange(100.0, 51200.0)
        self._spin_sample_rate.setValue(float(self._settings.value("acq/sample_rate", cfg.sample_rate)))
        self._spin_sample_rate.setSuffix(" Hz")
        self._spin_sample_rate.setDecimals(0)
        layout.addRow("SAMPLE RATE:", self._spin_sample_rate)

        # ── Active Channels Group ─────────────────────────────────────── #
        ch_group = QGroupBox("ACTIVE CHANNELS")
        v_layout = QVBoxLayout(ch_group)
        # PyQt6 ignora margens negativas e volta pro padrão. O mínimo é 0.
        v_layout.setContentsMargins(10, 0, 10, 10)
        v_layout.setSpacing(8)
        
        # Select All / None buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(10)
        
        btn_all = QPushButton("ALL")
        btn_all.setFixedHeight(22)
        btn_all.clicked.connect(lambda: self._set_all_channels(True))
        
        btn_none = QPushButton("NONE")
        btn_none.setFixedHeight(22)
        btn_none.clicked.connect(lambda: self._set_all_channels(False))
        
        btn_detect = QPushButton("DETECT")
        btn_detect.setFixedHeight(22)
        btn_detect.clicked.connect(self._detect_channels)
        
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addWidget(btn_detect)
        v_layout.addLayout(btn_row)
        
        # Aumenta a distância entre os botões e o grid
        v_layout.addSpacing(15) 

        # Checkboxes Grid
        self._ch_layout = QGridLayout()
        self._ch_layout.setSpacing(6)
        
        self._chk_channels: list[QCheckBox] = []
        self._rebuild_checkboxes(self._total_channels, cfg.active_channels)

        v_layout.addLayout(self._ch_layout)
        layout.addRow(ch_group)
        self._tabs.addTab(page, "Hardware")

    def _rebuild_checkboxes(self, total: int, active: list[int]) -> None:
        for chk in self._chk_channels:
            chk.deleteLater()
        self._chk_channels.clear()
        
        for i in range(total):
            chk = QCheckBox(f"CH {i+1:02d}")
            chk.setMinimumHeight(24)
            chk.setChecked(i in active)
            self._chk_channels.append(chk)
            row = i // 4
            col = i % 4
            self._ch_layout.addWidget(chk, row, col)

    def _detect_channels(self) -> None:
        try:
            import nidaqmx
            import nidaqmx.system
            
            system = nidaqmx.system.System.local()
            device_name = self._edit_device.text().strip()
            
            if not device_name:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Warning", "Please enter a device name.")
                return
                
            if device_name not in system.devices:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Not Found", f"Device '{device_name}' not found in system.")
                return
                
            dev = system.devices[device_name]
            chans = dev.ai_physical_chans
            num_chans = len(chans)
            
            self._total_channels = num_chans
            current_active = [i for i, chk in enumerate(self._chk_channels) if chk.isChecked() and i < num_chans]
            if not current_active:
                current_active = list(range(num_chans))
            self._rebuild_checkboxes(num_chans, current_active)
            
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Success", f"Detected {num_chans} channels on '{device_name}'.")
        except ImportError:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", "nidaqmx is not installed.")
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to detect channels: {e}")

    def _set_all_channels(self, state: bool) -> None:
        for chk in self._chk_channels:
            chk.setChecked(state)

    def _build_filters_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        # ── Notch ─────────────────────────────────────────────────────── #
        notch_group = QGroupBox("NOTCH FILTER  (60 Hz REJECTION)")
        notch_layout = QFormLayout(notch_group)

        self._chk_notch = QCheckBox("Enabled")
        self._chk_notch.setChecked(
            self._settings.value("filters/notch_enabled", True, type=bool)
        )
        notch_layout.addRow(self._chk_notch)

        self._spin_notch_low = QDoubleSpinBox()
        self._spin_notch_low.setRange(1.0, 500.0)
        self._spin_notch_low.setValue(
            float(self._settings.value("filters/notch_low", 59.0))
        )
        self._spin_notch_low.setSuffix(" Hz")
        notch_layout.addRow("LOW FREQ:", self._spin_notch_low)

        self._spin_notch_high = QDoubleSpinBox()
        self._spin_notch_high.setRange(1.0, 500.0)
        self._spin_notch_high.setValue(
            float(self._settings.value("filters/notch_high", 61.0))
        )
        self._spin_notch_high.setSuffix(" Hz")
        notch_layout.addRow("HIGH FREQ:", self._spin_notch_high)

        self._spin_notch_order = QSpinBox()
        self._spin_notch_order.setRange(1, 10)
        self._spin_notch_order.setValue(
            int(self._settings.value("filters/notch_order", 2))
        )
        notch_layout.addRow("ORDER:", self._spin_notch_order)

        layout.addWidget(notch_group)

        # ── Bandpass ──────────────────────────────────────────────────── #
        bp_group = QGroupBox("BANDPASS FILTER  (OPM BAND)")
        bp_layout = QFormLayout(bp_group)

        self._chk_bp = QCheckBox("Enabled")
        self._chk_bp.setChecked(
            self._settings.value("filters/bp_enabled", True, type=bool)
        )
        bp_layout.addRow(self._chk_bp)

        self._spin_bp_low = QDoubleSpinBox()
        self._spin_bp_low.setRange(0.01, 100.0)
        self._spin_bp_low.setValue(
            float(self._settings.value("filters/bp_low", 2.0))
        )
        self._spin_bp_low.setSuffix(" Hz")
        bp_layout.addRow("LOW FREQ:", self._spin_bp_low)

        self._spin_bp_high = QDoubleSpinBox()
        self._spin_bp_high.setRange(1.0, 500.0)
        self._spin_bp_high.setValue(
            float(self._settings.value("filters/bp_high", 50.0))
        )
        self._spin_bp_high.setSuffix(" Hz")
        bp_layout.addRow("HIGH FREQ:", self._spin_bp_high)

        self._spin_bp_order = QSpinBox()
        self._spin_bp_order.setRange(1, 10)
        self._spin_bp_order.setValue(
            int(self._settings.value("filters/bp_order", 4))
        )
        bp_layout.addRow("ORDER:", self._spin_bp_order)

        layout.addWidget(bp_group)
        layout.addStretch()

        self._tabs.addTab(page, "Filters")

    def _build_export_tab(self) -> None:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setSpacing(10)

        # Default format
        self._combo_format = QComboBox()
        self._combo_format.addItems(["TDMS", "CSV", "Excel (.xlsx)"])
        self._combo_format.setCurrentText(
            self._settings.value("export/default_format", "TDMS")
        )
        layout.addRow("DEFAULT FORMAT:", self._combo_format)

        self._tabs.addTab(page, "Export")

    # ── Persistence ───────────────────────────────────────────────────── #

    def _load_settings(self) -> None:
        """Load persisted values from QSettings and apply to widgets."""
        s = self._settings

        # Hardware
        self._edit_device.setText(s.value("hw/device", self._edit_device.text()))
        self._edit_prefix.setText(s.value("hw/prefix", self._edit_prefix.text()))
        self._combo_terminal.setCurrentText(
            s.value("hw/terminal", self._combo_terminal.currentText())
        )
        self._spin_vmin.setValue(float(s.value("hw/vmin", self._spin_vmin.value())))
        self._spin_vmax.setValue(float(s.value("hw/vmax", self._spin_vmax.value())))
        self._spin_sample_rate.setValue(float(s.value("acq/sample_rate", self._spin_sample_rate.value())))
        
        total = int(s.value("hw/total_channels", self._total_channels))
        if total != self._total_channels:
            self._total_channels = total
            self._rebuild_checkboxes(total, [])

        # Channels
        active_channels = s.value("hw/active_channels", list(range(self._total_channels)))
        # Handle cases where QSettings returns strings due to persistence limits
        if isinstance(active_channels, str):
            active_channels = [int(x.strip()) for x in active_channels.split(",") if x.strip()]
        elif isinstance(active_channels, list):
            active_channels = [int(x) for x in active_channels]
            
        for i, chk in enumerate(self._chk_channels):
            chk.setChecked(i in active_channels)

    def _save_settings(self) -> None:
        """Persist current widget values to QSettings."""
        s = self._settings

        # Hardware
        s.setValue("hw/device", self._edit_device.text())
        s.setValue("hw/prefix", self._edit_prefix.text())
        s.setValue("hw/terminal", self._combo_terminal.currentText())
        s.setValue("hw/vmin", self._spin_vmin.value())
        s.setValue("hw/vmax", self._spin_vmax.value())
        s.setValue("acq/sample_rate", self._spin_sample_rate.value())
        s.setValue("hw/total_channels", self._total_channels)
        
        active_channels = [i for i, chk in enumerate(self._chk_channels) if chk.isChecked()]
        s.setValue("hw/active_channels", active_channels)

        # Filters
        s.setValue("filters/notch_enabled", self._chk_notch.isChecked())
        s.setValue("filters/notch_low", self._spin_notch_low.value())
        s.setValue("filters/notch_high", self._spin_notch_high.value())
        s.setValue("filters/notch_order", self._spin_notch_order.value())
        s.setValue("filters/bp_enabled", self._chk_bp.isChecked())
        s.setValue("filters/bp_low", self._spin_bp_low.value())
        s.setValue("filters/bp_high", self._spin_bp_high.value())
        s.setValue("filters/bp_order", self._spin_bp_order.value())

        # Export
        s.setValue("export/default_format", self._combo_format.currentText())

    def _save_and_accept(self) -> None:
        self._save_settings()
        self.accept()

    def _restore_defaults(self) -> None:
        """Reset all widgets to factory defaults."""
        cfg = DaqConfig()
        self._edit_device.setText(cfg.device_name)
        self._edit_prefix.setText(cfg.channel_prefix)
        self._combo_terminal.setCurrentText(cfg.terminal_config)
        self._spin_vmin.setValue(cfg.min_voltage)
        self._spin_vmax.setValue(cfg.max_voltage)
        self._spin_sample_rate.setValue(cfg.sample_rate)
        self._total_channels = cfg.total_channels
        self._rebuild_checkboxes(self._total_channels, list(range(self._total_channels)))
        self._set_all_channels(True)

        self._chk_notch.setChecked(True)
        self._spin_notch_low.setValue(59.0)
        self._spin_notch_high.setValue(61.0)
        self._spin_notch_order.setValue(2)

        self._chk_bp.setChecked(True)
        self._spin_bp_low.setValue(2.0)
        self._spin_bp_high.setValue(50.0)
        self._spin_bp_order.setValue(4)

        self._combo_format.setCurrentText("TDMS")

    # ── Public getters for MainWindow ─────────────────────────────────── #

    def get_daq_config(self) -> DaqConfig:
        """Build a ``DaqConfig`` from the current dialog values."""
        active_channels = [i for i, chk in enumerate(self._chk_channels) if chk.isChecked()]
        
        return DaqConfig(
            device_name=self._edit_device.text(),
            total_channels=self._total_channels,
            active_channels=active_channels,
            channel_prefix=self._edit_prefix.text(),
            sample_rate=self._spin_sample_rate.value(),
            min_voltage=self._spin_vmin.value(),
            max_voltage=self._spin_vmax.value(),
            terminal_config=self._combo_terminal.currentText(),
        )

    def get_filter_settings(self) -> dict:
        """Return filter parameters as a dict for ``OpmProcessor``."""
        return {
            "notch_enabled": self._chk_notch.isChecked(),
            "notch_low": self._spin_notch_low.value(),
            "notch_high": self._spin_notch_high.value(),
            "notch_order": self._spin_notch_order.value(),
            "bandpass_enabled": self._chk_bp.isChecked(),
            "bp_low": self._spin_bp_low.value(),
            "bp_high": self._spin_bp_high.value(),
            "bp_order": self._spin_bp_order.value(),
        }

    def get_default_format(self) -> str:
        return self._combo_format.currentText()
