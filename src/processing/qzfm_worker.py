"""QThread Worker to communicate with QZFM sensors.

Handles serial communication with the QuSpin Zero-Field Magnetometer
in a background thread to prevent UI freezing. Implements a simulation
mode for hardware-less testing.
"""

from __future__ import annotations

import logging
import time as time_lib
import numpy as np

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

# Import QZFM, handling serial errors gracefully
try:
    from QZFM import QZFM
    HAS_QZFM = True
except ImportError:
    HAS_QZFM = False

logger = logging.getLogger(__name__)


class MockQZFM:
    """Mock implementation of the QZFM class for simulation and testing."""

    def __init__(self, device_name: str | None = None) -> None:
        self.device_name = device_name
        self.is_data_streaming = False
        self.is_field_zeroed = False
        self.is_xyz_zeroing = True
        self.is_calibrated = False
        self.axis_mode = "z"
        self.read_axis = "z"
        self.gain = 2.7
        self.data_read_rate = 200  # 200 Hz
        self.status_last_updated = time_lib.time()
        
        self.led = {
            "laser on (LED1)": False,
            "cell temp lock (LED2)": False,
            "laser lock (LED3)": False,
            "field zeroed (LED4)": False,
            "is master": False,
        }
        
        self.sensor_par = {
            "cell temp error": np.nan,
            "cell temp voltage": np.nan,
            "Bz field (pT)": 0.0,
            "By field (pT)": 0.0,
            "B0 field (pT)": 0.0,
        }
        
        self.messages: list[tuple[str, float]] = []
        self._start_time = time_lib.time()

        if device_name is not None:
            self.connect(device_name)

    def connect(self, device_name: str) -> None:
        self.device_name = device_name
        self.messages.append(("Connected to simulated device: " + device_name, time_lib.time()))
        self.led["laser on (LED1)"] = True
        self.led["is master"] = True

    def auto_start(self, block: bool = True, show: bool = True, zero_calibrate: bool = True, zero_cond: float = 100.0) -> None:
        self.messages.append(("Starting simulated auto-start...", time_lib.time()))
        # Lock laser
        self.led["laser lock (LED3)"] = True
        self.messages.append(("Simulated Laser Locked.", time_lib.time()))
        
        # Lock cell temp
        self.led["cell temp lock (LED2)"] = True
        self.sensor_par["cell temp error"] = 0.0002
        self.sensor_par["cell temp voltage"] = 3100
        self.messages.append(("Simulated Cell Temp Locked.", time_lib.time()))
        
        if zero_calibrate:
            self.field_zero(on=True)
            self.messages.append(("Simulated Field Zeroing complete.", time_lib.time()))
            self.calibrate()
            self.messages.append(("Simulated Calibration complete.", time_lib.time()))

    def field_zero(self, on: bool = True, axes_xyz: bool = True, show: bool = True) -> None:
        if on:
            self.messages.append(("Field zeroing ON", time_lib.time()))
            self.sensor_par["Bz field (pT)"] = 12.3
            self.sensor_par["By field (pT)"] = -5.4
            self.sensor_par["B0 field (pT)"] = 23.1
            self.led["field zeroed (LED4)"] = True
            self.is_field_zeroed = True
        else:
            self.messages.append(("Field zeroing OFF", time_lib.time()))

    def calibrate(self, show: bool = True) -> None:
        self.messages.append(("Calibration ON", time_lib.time()))
        self.is_calibrated = True

    def field_reset(self) -> None:
        self.messages.append(("Field reset", time_lib.time()))
        self.sensor_par["Bz field (pT)"] = 0.0
        self.sensor_par["By field (pT)"] = 0.0
        self.sensor_par["B0 field (pT)"] = 0.0
        self.led["field zeroed (LED4)"] = False
        self.is_field_zeroed = False
        self.is_calibrated = False

    def reboot(self) -> None:
        self.messages.append(("Device rebooted", time_lib.time()))
        self.led = {k: False for k in self.led}
        self.sensor_par = {k: np.nan for k in self.sensor_par}

    def update_status(self, clear_buffer: bool = True) -> None:
        self.status_last_updated = time_lib.time()
        # Add slight fluctuations to simulated parameter values
        if self.led["cell temp lock (LED2)"]:
            self.sensor_par["cell temp error"] = 0.0001 * np.sin(time_lib.time())
            self.sensor_par["cell temp voltage"] = 3100 + int(10 * np.sin(time_lib.time() / 5))
        if self.led["field zeroed (LED4)"]:
            self.sensor_par["Bz field (pT)"] = 12.3 + 0.1 * np.random.randn()
            self.sensor_par["By field (pT)"] = -5.4 + 0.1 * np.random.randn()
            self.sensor_par["B0 field (pT)"] = 23.1 + 0.1 * np.random.randn()

    def _set_read_axis(self, axis: str) -> None:
        self.read_axis = axis

    def _set_data_stream(self, on: bool = True) -> None:
        self.is_data_streaming = on

    def read_data(self, seconds: float, axis: str = "z", clear_buffer: bool = True) -> tuple[np.ndarray, np.ndarray]:
        npts = int(seconds * self.data_read_rate)
        self.read_axis = axis
        self.is_data_streaming = True
        
        # Simulate time and magnetic field (sine wave + noise)
        time_stop = time_lib.time()
        time_start = time_stop - seconds
        times = np.linspace(time_start, time_stop, npts)
        
        freq = 2.0  # Hz
        noise = 0.5 * np.random.randn(npts)
        
        # Base signal with harmonics + 60Hz power line noise
        field = 100.0 * np.sin(2 * np.pi * freq * (times - self._start_time)) \
                + 15.0 * np.cos(2 * np.pi * freq * 3.5 * (times - self._start_time)) \
                + 2.0 * np.sin(2 * np.pi * 60 * times) \
                + noise
                
        # Offset according to current zeroing values
        offset = 0.0
        if axis == "z":
            offset = self.sensor_par.get("Bz field (pT)", 0.0)
        elif axis == "y":
            offset = self.sensor_par.get("By field (pT)", 0.0)
        elif axis == "x":
            offset = self.sensor_par.get("B0 field (pT)", 0.0)
        
        # Apply nan check if simulation reset
        if np.isnan(offset):
            offset = 0.0
            
        field += offset
        
        # Simulate blocking time
        time_lib.sleep(seconds)
        
        return times, field


class QzfmWorker(QObject):
    """QObject that executes blocking QZFM tasks in a background thread."""

    connected_status = pyqtSignal(bool)
    status_updated = pyqtSignal(dict, dict)  # leds, sensor_par
    data_received = pyqtSignal(np.ndarray, np.ndarray)  # times, field
    log_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.qzfm: QZFM | MockQZFM | None = None
        self.is_simulated = False
        self._axis = "z"
        self._is_streaming = False
        self._last_msg_idx = 0
        
        # Timers for periodic tasks
        self._status_timer: QTimer | None = None
        self._data_timer: QTimer | None = None

    @pyqtSlot(str)
    def connect_sensor(self, device_name: str) -> None:
        """Establish connection to the serial device or simulation."""
        try:
            device_upper = device_name.upper()
            if "SIM" in device_upper or not HAS_QZFM:
                self.is_simulated = True
                self.qzfm = MockQZFM(device_name)
                logger.info("QZFM connected in SIMULATION mode.")
                self.log_received.emit(f"CONNECTED TO SIMULATION: {device_name} (QZFM package fallback: {not HAS_QZFM})")
            else:
                self.is_simulated = False
                self.qzfm = QZFM(device_name)
                logger.info("QZFM connected to device %s.", device_name)
                self.log_received.emit(f"Connected to device: {device_name}")

            self.connected_status.emit(True)
            self._start_status_timer()
        except Exception as exc:
            logger.exception("Failed to connect QZFM")
            self.error_occurred.emit(f"Connection Error: {exc}")
            self.connected_status.emit(False)

    @pyqtSlot()
    def disconnect_sensor(self) -> None:
        """Stop threads, timers and close the serial port."""
        self.stop_streaming()
        self._stop_status_timer()
        
        if self.qzfm is not None:
            try:
                if not self.is_simulated and hasattr(self.qzfm, "ser") and self.qzfm.ser is not None:
                    self.qzfm.ser.close()
                self.log_received.emit("Disconnected sensor.")
            except Exception as exc:
                logger.warning("Error during QZFM serial close: %s", exc)
                
        self.qzfm = None
        self.connected_status.emit(False)

    @pyqtSlot(bool)
    def run_auto_start(self, zero_calibrate: bool) -> None:
        """Run the blocking autostart routine in the background."""
        if self.qzfm is None:
            self.error_occurred.emit("Not connected to a sensor.")
            return

        try:
            self.log_received.emit("Starting auto-lock laser & temperature...")
            
            # Disable streaming during calibration
            was_streaming = self._is_streaming
            if was_streaming:
                self.stop_streaming()
                
            self._stop_status_timer()

            # Execute blocking auto-start
            # We use zero_cond=100.0 as standard stability criterion
            self.qzfm.auto_start(block=True, show=False, zero_calibrate=zero_calibrate, zero_cond=100.0)
            
            self._emit_new_messages()
            self._update_and_emit_status()
            
            self.log_received.emit("Auto-Start routine completed successfully.")
            
            # Restart status timer
            self._start_status_timer()
            
            # Resume streaming if it was active
            if was_streaming:
                self.start_streaming(self._axis)
                
        except Exception as exc:
            logger.exception("Error during QZFM Auto-Start")
            self.error_occurred.emit(f"Auto-Start Error: {exc}")
            self._start_status_timer()

    @pyqtSlot(bool)
    def run_field_zero(self, on: bool) -> None:
        """Toggle field zeroing."""
        if self.qzfm is None:
            return
        try:
            was_streaming = self._is_streaming
            if was_streaming:
                self.stop_streaming()
                
            self._stop_status_timer()
            
            self.log_received.emit(f"Field Zeroing: {'START' if on else 'STOP'}...")
            self.qzfm.field_zero(on=on, show=False)
            
            self._emit_new_messages()
            self._update_and_emit_status()
            self._start_status_timer()
            
            if was_streaming:
                self.start_streaming(self._axis)
        except Exception as exc:
            self.error_occurred.emit(f"Field Zero Error: {exc}")
            self._start_status_timer()

    @pyqtSlot()
    def run_calibrate(self) -> None:
        """Calibrate the sensor."""
        if self.qzfm is None:
            return
        try:
            was_streaming = self._is_streaming
            if was_streaming:
                self.stop_streaming()
                
            self._stop_status_timer()
            
            self.log_received.emit("Calibrating sensor response...")
            self.qzfm.calibrate(show=False)
            
            self._emit_new_messages()
            self._update_and_emit_status()
            self._start_status_timer()
            
            if was_streaming:
                self.start_streaming(self._axis)
        except Exception as exc:
            self.error_occurred.emit(f"Calibration Error: {exc}")
            self._start_status_timer()

    @pyqtSlot()
    def run_field_reset(self) -> None:
        """Reset internal compensation coil currents."""
        if self.qzfm is None:
            return
        try:
            was_streaming = self._is_streaming
            if was_streaming:
                self.stop_streaming()
                
            self._stop_status_timer()
            
            self.log_received.emit("Resetting field coils...")
            self.qzfm.field_reset()
            
            self._emit_new_messages()
            self._update_and_emit_status()
            self._start_status_timer()
            
            if was_streaming:
                self.start_streaming(self._axis)
        except Exception as exc:
            self.error_occurred.emit(f"Coil Reset Error: {exc}")
            self._start_status_timer()

    @pyqtSlot()
    def run_reboot(self) -> None:
        """Reboot the sensor."""
        if self.qzfm is None:
            return
        try:
            self.stop_streaming()
            self._stop_status_timer()
            
            self.log_received.emit("Rebooting sensor electronics...")
            self.qzfm.reboot()
            
            self._emit_new_messages()
            self._update_and_emit_status()
            self._start_status_timer()
        except Exception as exc:
            self.error_occurred.emit(f"Reboot Error: {exc}")
            self._start_status_timer()

    @pyqtSlot(str)
    def start_streaming(self, axis: str) -> None:
        """Start reading magnetic field values periodically."""
        if self.qzfm is None:
            return
        self._axis = axis
        self._is_streaming = True
        
        # Stop data timer if active
        if self._data_timer is not None:
            self._data_timer.stop()
            self._data_timer = None

        # Setup periodic 100ms reading intervals
        self._data_timer = QTimer()
        self._data_timer.timeout.connect(self._read_stream_data)
        self._data_timer.start(100)
        logger.info("QZFM streaming started on axis %s.", axis)

    @pyqtSlot()
    def stop_streaming(self) -> None:
        """Stop data reading timer."""
        self._is_streaming = False
        if self._data_timer is not None:
            self._data_timer.stop()
            self._data_timer = None
        if self.qzfm is not None and self.qzfm.is_data_streaming:
            try:
                self.qzfm._set_data_stream(False)
            except Exception:
                pass
        logger.info("QZFM streaming stopped.")

    # ── Timers / Event Handling ────────────────────────────────────────── #

    def _start_status_timer(self) -> None:
        self._stop_status_timer()
        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._poll_status)
        self._status_timer.start(500)  # Update status every 0.5s

    def _stop_status_timer(self) -> None:
        if self._status_timer is not None:
            self._status_timer.stop()
            self._status_timer = None

    def _poll_status(self) -> None:
        """Periodic status polling."""
        if self.qzfm is None or self._is_streaming:
            # Skip polling status if data streaming is active, since
            # QZFM status updates require stopping print streaming.
            return
        try:
            self.qzfm.update_status(clear_buffer=True)
            self._emit_new_messages()
            self._update_and_emit_status()
        except Exception as exc:
            logger.debug("Failed to update QZFM status: %s", exc)

    def _read_stream_data(self) -> None:
        """Read 100ms of data and emit."""
        if self.qzfm is None or not self._is_streaming:
            return
        try:
            # 0.1 seconds = 20 samples (at 200 Hz)
            times, fields = self.qzfm.read_data(seconds=0.1, axis=self._axis, clear_buffer=False)
            
            # Check for invalid array returns
            if isinstance(times, np.ndarray) and isinstance(fields, np.ndarray):
                self.data_received.emit(times, fields)
        except Exception as exc:
            logger.warning("Error reading stream data: %s", exc)

    def _update_and_emit_status(self) -> None:
        """Format and emit status parameters."""
        if self.qzfm is None:
            return
        leds = dict(self.qzfm.led)
        params = dict(self.qzfm.sensor_par)
        self.status_updated.emit(leds, params)

    def _emit_new_messages(self) -> None:
        """Extract and emit new console logs from QZFM."""
        if self.qzfm is None:
            return
        msgs = self.qzfm.messages
        if len(msgs) > self._last_msg_idx:
            for msg_txt, _ in msgs[self._last_msg_idx:]:
                self.log_received.emit(msg_txt)
            self._last_msg_idx = len(msgs)
