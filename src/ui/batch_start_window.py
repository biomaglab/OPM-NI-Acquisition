"""Window to monitor the batch initialization of all sensors."""

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
    QFrame,
    QProgressBar
)

from src.hardware.sensor_manager import SensorManager, SensorInfo
from src.hardware.sensor_worker import SensorWorker, SensorCommand
from src.ui.styles import (
    BG_DARKEST,
    BG_CARD,
    BG_INPUT,
    BORDER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    ACCENT_PRIMARY,
    ACCENT_ACTIVE,
    SENSOR_ERROR
)

class BatchStartWindow(QDialog):
    def __init__(self, manager: SensorManager, worker: SensorWorker, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.worker = worker
        self._led_labels = {}  # s_id -> dict of led labels
        self._status_labels = {}  # s_id -> QLabel for per-sensor status

        self.setWindowTitle("Batch Initialization Progress")
        self.setMinimumSize(600, 400)
        # Prevent interaction with main window while running
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self._setup_ui()
        self._connect_signals()
        self._populate_sensors()

        # Start the batch command immediately upon opening
        self.worker.queue_command("all", SensorCommand.AUTO_START_ALL)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title / Global Phase
        title = QLabel("STARTING ALL SENSORS")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {TEXT_PRIMARY};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.lbl_phase = QLabel("Initializing...")
        self.lbl_phase.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {ACCENT_PRIMARY};")
        self.lbl_phase.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_phase.setWordWrap(True)
        layout.addWidget(self.lbl_phase)

        # Progress bar (indeterminate)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # Scroll area for sensor cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(f"QScrollArea {{ border: none; background-color: {BG_DARKEST}; }}")
        layout.addWidget(self.scroll)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.scroll_content)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet(
            f"background-color: #5C2020; color: #E8A0A0; border: 1px solid #8B3030;"
            f" font-weight: bold; padding: 6px 18px;"
        )
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_close = QPushButton("Close")
        self.btn_close.setEnabled(False)  # Disabled until finished
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)

    def _populate_sensors(self):
        configs = self.manager.get_configs()
        for s_id, cfg in configs.items():
            card = QFrame()
            card.setStyleSheet(f"QFrame {{ background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 4px; }}")
            card_layout = QHBoxLayout(card)

            lbl_name = QLabel(f"{cfg['name']} ({s_id})")
            lbl_name.setStyleSheet("font-weight: bold; border: none;")
            card_layout.addWidget(lbl_name)
            card_layout.addStretch()

            # LEDs
            led_dict = {}
            leds = [
                ("Laser", "laser_on"),
                ("Temp Lock", "cell_temp_locked"),
                ("Laser Lock", "laser_locked"),
                ("Field Zero", "field_zeroed")
            ]

            for label_text, key in leds:
                led_lbl = QLabel(label_text)
                led_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                led_lbl.setFixedSize(65, 20)
                led_lbl.setStyleSheet(f"background-color: {BG_INPUT}; color: {TEXT_SECONDARY}; border-radius: 10px; font-size: 10px; border: none;")
                card_layout.addWidget(led_lbl)
                led_dict[key] = led_lbl

            # Per-sensor status label
            lbl_status = QLabel("Waiting...")
            lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_status.setFixedSize(90, 20)
            lbl_status.setStyleSheet(
                f"background-color: {BG_INPUT}; color: {TEXT_SECONDARY};"
                f" border-radius: 10px; font-size: 10px; border: none; font-weight: bold;"
            )
            card_layout.addWidget(lbl_status)
            self._status_labels[s_id] = lbl_status

            self._led_labels[s_id] = led_dict
            self.scroll_layout.addWidget(card)
            
            # Initial update
            info = self.manager.get_info(s_id)
            self._update_leds(s_id, info)

    def _connect_signals(self):
        self.worker.progress.connect(self._on_progress)
        self.worker.status_updated.connect(self._on_status_updated)
        self.worker.command_finished.connect(self._on_command_finished)

    def _update_leds(self, s_id: str, info: SensorInfo):
        if s_id not in self._led_labels:
            return
            
        leds = self._led_labels[s_id]
        
        def update_single_led(lbl, is_on):
            if is_on:
                lbl.setStyleSheet(f"background-color: {ACCENT_PRIMARY}; color: {TEXT_PRIMARY}; border-radius: 10px; font-weight: bold; font-size: 10px; border: none;")
            else:
                lbl.setStyleSheet(f"background-color: {BG_INPUT}; color: {TEXT_SECONDARY}; border-radius: 10px; font-size: 10px; border: none;")

        update_single_led(leds["laser_on"], info.laser_on)
        update_single_led(leds["cell_temp_locked"], info.cell_temp_locked)
        update_single_led(leds["laser_locked"], info.laser_locked)
        update_single_led(leds["field_zeroed"], info.field_zeroed)

    @pyqtSlot(str, str)
    def _on_progress(self, s_id: str, message: str):
        if s_id == "all":
            self.lbl_phase.setText(message)
        elif s_id in self._status_labels:
            lbl = self._status_labels[s_id]
            # Color-code based on message content
            msg_lower = message.lower()
            if "timeout" in msg_lower or "failed" in msg_lower or "skipping" in msg_lower:
                lbl.setStyleSheet(
                    f"background-color: {SENSOR_ERROR}; color: {TEXT_PRIMARY};"
                    f" border-radius: 10px; font-size: 10px; border: none; font-weight: bold;"
                )
                if "timeout" in msg_lower:
                    lbl.setText("TIMEOUT")
                else:
                    lbl.setText("SKIPPED")
            elif "calibrating" in msg_lower:
                lbl.setStyleSheet(
                    f"background-color: {ACCENT_PRIMARY}; color: {TEXT_PRIMARY};"
                    f" border-radius: 10px; font-size: 10px; border: none; font-weight: bold;"
                )
                lbl.setText("Calibrating...")
            elif "zeroing" in msg_lower and "completed" not in msg_lower:
                lbl.setStyleSheet(
                    f"background-color: {ACCENT_PRIMARY}; color: {TEXT_PRIMARY};"
                    f" border-radius: 10px; font-size: 10px; border: none; font-weight: bold;"
                )
                lbl.setText("Zeroing...")
            elif "restoring" in msg_lower or "temp lock" in msg_lower:
                lbl.setStyleSheet(
                    f"background-color: {ACCENT_PRIMARY}; color: {TEXT_PRIMARY};"
                    f" border-radius: 10px; font-size: 10px; border: none; font-weight: bold;"
                )
                lbl.setText("Temp Lock...")
            elif "completed" in msg_lower or "auto-start completed" in msg_lower:
                lbl.setStyleSheet(
                    f"background-color: {ACCENT_ACTIVE}; color: {TEXT_PRIMARY};"
                    f" border-radius: 10px; font-size: 10px; border: none; font-weight: bold;"
                )
                lbl.setText("Done \u2713")

    @pyqtSlot(str, object)
    def _on_status_updated(self, s_id: str, info: SensorInfo):
        self._update_leds(s_id, info)

    @pyqtSlot(str, str, bool)
    def _on_command_finished(self, s_id: str, cmd_name: str, success: bool):
        if s_id == "all" and cmd_name == "auto_start_all":
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
            self.btn_close.setEnabled(True)
            self.btn_cancel.setVisible(False)
            if success:
                self.lbl_phase.setText("Initialization Complete!")
                self.lbl_phase.setStyleSheet("font-size: 14px; font-weight: bold; color: #3D8B37;")
            else:
                self.lbl_phase.setText("Initialization Failed or Cancelled.")
                self.lbl_phase.setStyleSheet("font-size: 14px; font-weight: bold; color: #E74C3C;")

    def _on_cancel(self):
        self.worker.request_cancel()
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Cancelling...")
        self.lbl_phase.setText("Cancelling... waiting for current step to finish.")
