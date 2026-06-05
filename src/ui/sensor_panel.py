"""Sensor panel sidebar widget for displaying QZFM status."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox
)

from src.hardware.sensor_manager import SensorInfo
from src.ui.styles import TEXT_SECONDARY, TEXT_BRIGHT

class SensorPanel(QGroupBox):
    """Sidebar panel to summarize sensor statuses.
    
    Signals
    -------
    manage_clicked
        User requested to open the full sensor management dialog.
    """
    
    manage_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__("QZFM SENSORS", parent)
        self._states: dict[str, bool] = {}
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Summary Label
        self.lbl_summary = QLabel("No sensors connected")
        self.lbl_summary.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: bold;")
        self.lbl_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_summary)
        
        # Action button centered
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_manage = QPushButton("MANAGE SENSORS")
        self.btn_manage.setToolTip("Open Sensor Manager and Calibration Wizard")
        self.btn_manage.setMinimumHeight(28)
        self.btn_manage.setStyleSheet("padding: 4px 16px; font-weight: bold;")
        self.btn_manage.clicked.connect(self.manage_clicked.emit)
        btn_layout.addWidget(self.btn_manage)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
    @pyqtSlot(str, object)
    def update_sensor(self, s_id: str, info: SensorInfo):
        """Track the connected status of a sensor and update the summary label."""
        self._states[s_id] = info.connected
        self._update_label()
        
    def remove_sensor(self, sensor_id: str):
        if sensor_id in self._states:
            del self._states[sensor_id]
            self._update_label()
            
    def clear(self):
        self._states.clear()
        self._update_label()

    def _update_label(self):
        total = len(self._states)
        if total == 0:
            self.lbl_summary.setText("No sensors added")
            self.lbl_summary.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: bold;")
            return
            
        connected = sum(1 for v in self._states.values() if v)
        self.lbl_summary.setText(f"{connected} / {total} Online")
        
        if connected == total:
            self.lbl_summary.setStyleSheet(f"color: {TEXT_BRIGHT}; font-weight: bold;")
        else:
            self.lbl_summary.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: bold;")
