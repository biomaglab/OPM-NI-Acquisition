"""Dialog for configuring batch start parameters."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox
)

from src.ui.styles import (
    BG_DARKEST, TEXT_PRIMARY, ACCENT_PRIMARY, BG_INPUT
)

class BatchConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Start Configuration")
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Title
        lbl_title = QLabel("CONFIGURE BATCH INITIALIZATION")
        lbl_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {TEXT_PRIMARY};")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_title)

        # Actions Group
        grp_actions = QGroupBox("STEPS TO PERFORM")
        form_actions = QFormLayout(grp_actions)
        
        self.chk_zero_cal = QCheckBox("Perform Field Zero and Calibration")
        self.chk_zero_cal.setChecked(True)
        form_actions.addRow("", self.chk_zero_cal)
        
        layout.addWidget(grp_actions)

        # Precision Group
        grp_precision = QGroupBox("ZEROING PRECISION")
        form_precision = QFormLayout(grp_precision)

        self.cmb_precision = QComboBox()
        self.cmb_precision.addItem("Fast (200 pT/s) - Debug/Testing", 200.0)
        self.cmb_precision.addItem("Standard (100 pT/s) - Default", 100.0)
        self.cmb_precision.addItem("High Precision (50 pT/s) - MEG Quality", 50.0)
        self.cmb_precision.addItem("Ultra Precision (20 pT/s)", 20.0)
        
        # Set default to Standard
        self.cmb_precision.setCurrentIndex(1)
        
        form_precision.addRow("Target Gradient:", self.cmb_precision)
        
        layout.addWidget(grp_precision)

        # Timeouts Group
        grp_timeouts = QGroupBox("TIMEOUTS (SECONDS)")
        form_timeouts = QFormLayout(grp_timeouts)

        self.spin_warmup = QSpinBox()
        self.spin_warmup.setRange(60, 900)
        self.spin_warmup.setValue(300)
        
        self.spin_zero = QSpinBox()
        self.spin_zero.setRange(30, 300)
        self.spin_zero.setValue(120)
        
        self.spin_temp = QSpinBox()
        self.spin_temp.setRange(10, 180)
        self.spin_temp.setValue(60)

        self.spin_cal = QSpinBox()
        self.spin_cal.setRange(10, 120)
        self.spin_cal.setValue(30)

        form_timeouts.addRow("Laser & Temp Warm-up:", self.spin_warmup)
        form_timeouts.addRow("Field Zeroing:", self.spin_zero)
        form_timeouts.addRow("Temp Recovery:", self.spin_temp)
        form_timeouts.addRow("Calibration:", self.spin_cal)

        layout.addWidget(grp_timeouts)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_start = QPushButton("Start Batch")
        self.btn_start.setStyleSheet(f"background-color: {ACCENT_PRIMARY}; color: {BG_DARKEST}; font-weight: bold;")
        self.btn_start.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_start)

        layout.addLayout(btn_layout)

    def get_config(self) -> dict:
        """Return the user configuration as a dictionary."""
        return {
            "perform_zero_calibrate": self.chk_zero_cal.isChecked(),
            "zero_cond": self.cmb_precision.currentData(),
            "timeouts": {
                "laser_temp_lock": self.spin_warmup.value(),
                "field_zero": self.spin_zero.value(),
                "temp_recovery": self.spin_temp.value(),
                "calibration": self.spin_cal.value(),
            }
        }
