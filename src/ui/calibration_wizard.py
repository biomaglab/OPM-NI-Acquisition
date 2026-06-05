"""Guided step-by-step wizard for sensor startup and calibration."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QWidget,
    QProgressBar,
    QMessageBox
)

from src.hardware.sensor_worker import SensorCommand, SensorWorker
from src.ui.styles import (
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    ACCENT_PRIMARY,
    ACCENT_ACTIVE,
    WIZARD_DONE,
    WIZARD_ACTIVE,
    WIZARD_PENDING
)

class CalibrationWizard(QDialog):
    """5-step guided wizard for setting up a QZFM sensor.
    
    Steps:
    1. Introduction & Connection Check
    2. Auto Start (Laser & Temp lock)
    3. Field Zeroing
    4. Calibration
    5. Conclusion
    """
    
    def __init__(self, sensor_id: str, sensor_name: str, worker: SensorWorker, parent=None):
        super().__init__(parent)
        self.sensor_id = sensor_id
        self.sensor_name = sensor_name
        self.worker = worker
        
        self.setWindowTitle(f"Calibration Wizard - {sensor_name}")
        self.setFixedSize(500, 350)
        
        self._current_step = 0
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header / Progress
        self.lbl_title = QLabel("Step 1: Preparation")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.lbl_title)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 4)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setProperty("class", "wizard-progress")
        layout.addWidget(self.progress)
        
        # Pages stack
        self.stack = QStackedWidget()
        
        # Page 0: Intro
        page0 = QWidget()
        l0 = QVBoxLayout(page0)
        l0.addWidget(QLabel("This wizard will guide you through the process of\ninitializing and calibrating the OPM sensor."))
        l0.addWidget(QLabel("Make sure the sensor is connected\nand inside the magnetic shield."))
        l0.addStretch()
        self.stack.addWidget(page0)
        
        # Page 1: Auto Start
        page1 = QWidget()
        l1 = QVBoxLayout(page1)
        l1.addWidget(QLabel("Turning on lasers and heating the cell..."))
        l1.addWidget(QLabel("This may take a few minutes."))
        self.lbl_status1 = QLabel("Waiting to start...")
        self.lbl_status1.setStyleSheet(f"color: {TEXT_SECONDARY};")
        l1.addWidget(self.lbl_status1)
        l1.addStretch()
        self.stack.addWidget(page1)
        
        # Page 2: Field Zero
        page2 = QWidget()
        l2 = QVBoxLayout(page2)
        l2.addWidget(QLabel("Nulling residual magnetic field..."))
        self.lbl_status2 = QLabel("Internal coils are optimizing the zero field.")
        l2.addWidget(self.lbl_status2)
        l2.addStretch()
        self.stack.addWidget(page2)
        
        # Page 3: Calibrate
        page3 = QWidget()
        l3 = QVBoxLayout(page3)
        l3.addWidget(QLabel("Applying calibration signal..."))
        self.lbl_status3 = QLabel("The sensor is adjusting the V/nT gain.")
        l3.addWidget(self.lbl_status3)
        l3.addStretch()
        self.stack.addWidget(page3)
        
        # Page 4: Done
        page4 = QWidget()
        l4 = QVBoxLayout(page4)
        l4.addWidget(QLabel("✓ Calibration completed successfully!"))
        l4.addWidget(QLabel("The sensor is ready for data acquisition."))
        l4.addStretch()
        self.stack.addWidget(page4)
        
        layout.addWidget(self.stack)
        
        # Footer buttons
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        btn_layout.addStretch()
        
        self.btn_next = QPushButton("Start >")
        self.btn_next.clicked.connect(self._on_next)
        btn_layout.addWidget(self.btn_next)
        
        layout.addLayout(btn_layout)
        
    def _connect_signals(self):
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.command_finished.connect(self._on_worker_finished)
        self.worker.error_occurred.connect(self._on_worker_error)
        
    @pyqtSlot(str, str)
    def _on_worker_progress(self, s_id: str, msg: str):
        if s_id != self.sensor_id:
            return
            
        if self._current_step == 1:
            self.lbl_status1.setText(msg)
        elif self._current_step == 2:
            self.lbl_status2.setText(msg)
        elif self._current_step == 3:
            self.lbl_status3.setText(msg)
            
    @pyqtSlot(str, str, bool)
    def _on_worker_finished(self, s_id: str, cmd: str, success: bool):
        if s_id != self.sensor_id:
            return
            
        if not success:
            QMessageBox.critical(self, "Error", f"Operation failed: {cmd}")
            self.btn_next.setEnabled(True)
            return
            
        if cmd == SensorCommand.AUTO_START.value:
            # Here we actually use a modified auto_start that does everything,
            # or we do them step by step. If we do step by step:
            # We used our custom AUTO_START in worker which does all in one go!
            # Wait, if our worker does all in one go, the wizard just shows progress on one page
            # Or we can break it down in the wizard.
            
            # Since our worker's AUTO_START does everything (laser -> zero -> calibrate),
            # we can just advance the UI based on the progress messages, or just have 1 step.
            
            # Let's just jump to conclusion since the command finished.
            self._current_step = 4
            self._update_ui_state()

    @pyqtSlot(str, str)
    def _on_worker_error(self, s_id: str, error: str):
        if s_id != self.sensor_id:
            return
        self.lbl_status1.setText(f"Error: {error}")
        self.lbl_status1.setStyleSheet(f"color: #E74C3C;")
        self.btn_next.setEnabled(True)

    def _on_next(self):
        if self._current_step == 0:
            # Start full auto_start sequence
            self.btn_next.setEnabled(False)
            self.btn_cancel.setEnabled(False)
            self.worker.queue_command(self.sensor_id, SensorCommand.AUTO_START, zero_calibrate=True)
            self._current_step = 1
            self._update_ui_state()
            
        elif self._current_step == 4:
            self.accept()
            
    def _update_ui_state(self):
        self.progress.setValue(self._current_step)
        self.stack.setCurrentIndex(self._current_step)
        
        titles = [
            "Step 1: Preparation",
            "Step 2: Heating and Lock",
            "Step 3: Field Zeroing",
            "Step 4: Calibration",
            "Done"
        ]
        self.lbl_title.setText(titles[self._current_step])
        
        if self._current_step == 1:
            self.btn_next.setText("Processing...")
        elif self._current_step == 4:
            self.btn_next.setText("Finish")
            self.btn_next.setEnabled(True)
            self.btn_cancel.setEnabled(True)
