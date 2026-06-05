"""Floating window for monitoring Field Zeroing process."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QGroupBox,
    QFormLayout
)

from src.ui.styles import (
    BG_DARKEST,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    FONT_MONO,
    ACCENT_WARNING,
    ACCENT_ACTIVE
)

class ZeroingWindow(QDialog):
    """Shows real-time magnetic field gradients and cell temperature error
    during the automated Field Zeroing process.
    """
    
    def __init__(self, sensor_id: str, sensor_name: str, parent=None):
        super().__init__(parent)
        self.sensor_id = sensor_id
        self.setWindowTitle(f"Field Zeroing - {sensor_name}")
        self.setFixedSize(300, 250)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        self.lbl_info = QLabel("Wait a little bit, stabilizing fields...")
        self.lbl_info.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: bold;")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_info)
        
        group = QGroupBox("CLICK OK WHEN FIELD VALUES ARE STABILIZED")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.lbl_bz = QLabel("--- pT")
        self.lbl_by = QLabel("--- pT")
        self.lbl_b0 = QLabel("--- pT")
        self.lbl_temp = QLabel("---")
        
        for lbl in (self.lbl_bz, self.lbl_by, self.lbl_b0, self.lbl_temp):
            lbl.setStyleSheet(f"font-family: {FONT_MONO}; color: {ACCENT_WARNING};")
            
        form.addRow("Bz Field:", self.lbl_bz)
        form.addRow("By Field:", self.lbl_by)
        form.addRow("B0 Field:", self.lbl_b0)
        form.addRow("Temp Err:", self.lbl_temp)
        
        layout.addWidget(group)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Indeterminate
        layout.addWidget(self.progress)
        
        button_row = QHBoxLayout()
        button_row.addStretch()

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setEnabled(False)
        button_row.addWidget(self.btn_ok)

        self.btn_stop = QPushButton("CANCEL")
        self.btn_stop.setStyleSheet(f"color: {TEXT_PRIMARY};")
        button_row.addWidget(self.btn_stop)

        layout.addLayout(button_row)
        
    @pyqtSlot(str, float, float, float, float)
    def update_data(self, s_id: str, bz: float, by: float, b0: float, t_err: float):
        if s_id != self.sensor_id:
            return
            
        self.lbl_bz.setText(f"{bz:8.2f} pT")
        self.lbl_by.setText(f"{by:8.2f} pT")
        self.lbl_b0.setText(f"{b0:8.2f} pT")
        
        color = ACCENT_ACTIVE if abs(t_err) <= 0.001 else ACCENT_WARNING
        self.lbl_temp.setText(f"{t_err:8.3f}")
        self.lbl_temp.setStyleSheet(f"font-family: {FONT_MONO}; color: {color};")
