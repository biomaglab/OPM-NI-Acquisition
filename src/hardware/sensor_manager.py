"""Manager for multiple QZFM sensors."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from PyQt6.QtCore import QSettings
from serial.tools import list_ports
import serial
import time

try:
    from QZFM import QZFM
    HAS_QZFM = True

    # Monkey-patch QZFM.update_status to avoid IndexError crashes on bad reads
    _original_update_status = QZFM.update_status
    def _safe_update_status(self, clear_buffer=True):
        try:
            _original_update_status(self, clear_buffer=clear_buffer)
        except Exception as e:
            logger.debug(f"Ignored error in QZFM update_status: {e}")
    QZFM.update_status = _safe_update_status

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
        self.status_last_updated = time.time()
        
        self.led = {
            "laser on (LED1)": False,
            "cell temp lock (LED2)": False,
            "laser lock (LED3)": False,
            "field zeroed (LED4)": False,
            "is master": False,
        }
        
        self.sensor_par = {
            "cell temp error": float('nan'),
            "cell temp voltage": float('nan'),
            "Bz field (pT)": 0.0,
            "By field (pT)": 0.0,
            "B0 field (pT)": 0.0,
        }
        
        class MockSerial:
            def __init__(self, parent):
                self.parent = parent
            def write(self, data: bytes):
                if data == b'>':
                    self.parent._auto_start_time = time.time()
                    self.parent.led["laser on (LED1)"] = True
                    self.parent.messages.append(("Auto Start triggered via serial", time.time()))

        self.ser = MockSerial(self)
        self._auto_start_time = None
        
        self.messages = []
        self._start_time = time.time()

        if device_name is not None:
            self.connect(device_name)

    def connect(self, device_name: str) -> None:
        self.device_name = device_name
        self.messages.append(("Connected to simulated device: " + device_name, time.time()))
        self.led["laser on (LED1)"] = True
        self.led["is master"] = True

    def auto_start(self, block: bool = True, show: bool = True, zero_calibrate: bool = True, zero_cond: float = 100.0) -> None:
        self.messages.append(("Starting simulated auto-start...", time.time()))
        self.led["laser lock (LED3)"] = True
        self.messages.append(("Simulated Laser Locked.", time.time()))
        self.led["cell temp lock (LED2)"] = True
        self.sensor_par["cell temp error"] = 0.0002
        self.sensor_par["cell temp voltage"] = 3100
        self.messages.append(("Simulated Cell Temp Locked.", time.time()))
        if zero_calibrate:
            self.field_zero(on=True)
            self.messages.append(("Simulated Field Zeroing complete.", time.time()))
            self.calibrate()
            self.messages.append(("Simulated Calibration complete.", time.time()))

    def field_zero(self, on: bool = True, axes_xyz: bool = True, show: bool = True) -> None:
        if on:
            self.messages.append(("Field zeroing ON", time.time()))
            self.sensor_par["Bz field (pT)"] = 12.3
            self.sensor_par["By field (pT)"] = -5.4
            self.sensor_par["B0 field (pT)"] = 23.1
            self.led["field zeroed (LED4)"] = True
            self.is_field_zeroed = True
        else:
            self.messages.append(("Field zeroing OFF", time.time()))

    def calibrate(self, show: bool = True) -> None:
        self.messages.append(("Calibration ON", time.time()))
        self.is_calibrated = True

    def field_reset(self) -> None:
        self.messages.append(("Field reset", time.time()))
        self.sensor_par["Bz field (pT)"] = 0.0
        self.sensor_par["By field (pT)"] = 0.0
        self.sensor_par["B0 field (pT)"] = 0.0
        self.led["field zeroed (LED4)"] = False
        self.is_field_zeroed = False
        self.is_calibrated = False

    def reboot(self) -> None:
        self.messages.append(("Device rebooted", time.time()))
        self.led = {k: False for k in self.led}
        self.sensor_par = {k: float('nan') for k in self.sensor_par}

    def set_master(self, master: bool) -> None:
        self.led["is master"] = master
        self.messages.append((f"Set master to {master}", time.time()))

    def set_gain(self, mode: str) -> None:
        self.messages.append((f"Set gain to {mode}", time.time()))

    def save_state(self) -> None:
        self.messages.append(("State saved", time.time()))

    def update_status(self, clear_buffer: bool = True) -> None:
        self.status_last_updated = time.time()
        import math
        import random
        
        if self._auto_start_time is not None:
            elapsed = time.time() - self._auto_start_time
            if elapsed > 2.0:
                self.led["laser lock (LED3)"] = True
            if elapsed > 4.0:
                self.led["cell temp lock (LED2)"] = True
                
        if self.led["cell temp lock (LED2)"]:
            self.sensor_par["cell temp error"] = 0.0001 * math.sin(time.time())
            self.sensor_par["cell temp voltage"] = 3100 + int(10 * math.sin(time.time() / 5))
        if self.led["field zeroed (LED4)"]:
            self.sensor_par["Bz field (pT)"] = 12.3 + 0.1 * (random.random() - 0.5) * 2
            self.sensor_par["By field (pT)"] = -5.4 + 0.1 * (random.random() - 0.5) * 2
            self.sensor_par["B0 field (pT)"] = 23.1 + 0.1 * (random.random() - 0.5) * 2

    def _set_read_axis(self, axis: str) -> None:
        self.read_axis = axis

    def _set_data_stream(self, on: bool = True) -> None:
        self.is_data_streaming = on

    def read_data(self, seconds: float, axis: str = "z", clear_buffer: bool = True) -> tuple[list[float], list[float]]:
        npts = int(seconds * self.data_read_rate)
        self.read_axis = axis
        self.is_data_streaming = True
        
        time_stop = time.time()
        time_start = time_stop - seconds
        
        times = []
        field = []
        freq = 2.0
        
        import math
        import random
        
        offset = 0.0
        if axis == "z": offset = self.sensor_par.get("Bz field (pT)", 0.0)
        elif axis == "y": offset = self.sensor_par.get("By field (pT)", 0.0)
        elif axis == "x": offset = self.sensor_par.get("B0 field (pT)", 0.0)
        if math.isnan(offset): offset = 0.0
            
        for i in range(npts):
            t = time_start + i * (seconds / max(1, npts-1))
            noise = 0.5 * (random.random() - 0.5) * 2
            f = 100.0 * math.sin(2 * math.pi * freq * (t - self._start_time)) \
                + 15.0 * math.cos(2 * math.pi * freq * 3.5 * (t - self._start_time)) \
                + 2.0 * math.sin(2 * math.pi * 60 * t) \
                + noise + offset
            times.append(t)
            field.append(f)
            
        time.sleep(seconds)
        return times, field

@dataclass
class SensorInfo:
    """Immutable snapshot of sensor state."""
    sensor_id: str
    port: str
    name: str
    is_master: bool = False
    gain: float = 2.7  # V/nT
    axis_mode: str = "z"
    
    # State fields
    connected: bool = False
    laser_on: bool = False
    cell_temp_locked: bool = False
    laser_locked: bool = False
    field_zeroed: bool = False
    is_calibrated: bool = False
    
    # Measurements
    cell_temp_error: float = 0.0
    bz_field: float = 0.0
    by_field: float = 0.0
    b0_field: float = 0.0
    
    # Message log
    messages: list[tuple[str, float]] = field(default_factory=list)

class SensorManager:
    """Manages multiple QZFM instances."""
    
    def __init__(self):
        self._sensors: dict[str, QZFM | MockQZFM] = {}
        self._configs: dict[str, dict] = {}  # id -> {port, name, master, gain}
        
    def add_sensor(self, sensor_id: str, port: str, name: str = "", is_master: bool = False, gain: float = 2.7, axis_mode: str = "z") -> None:
        if not name:
            name = f"Sensor {len(self._configs) + 1}"
            
        self._configs[sensor_id] = {
            "port": port,
            "name": name,
            "is_master": is_master,
            "gain": gain,
            "axis_mode": axis_mode,
        }
        logger.info(f"Added sensor config: {sensor_id} ({name}) on port {port}")
        
    def remove_sensor(self, sensor_id: str) -> None:
        if sensor_id in self._sensors:
            self.disconnect_sensor(sensor_id)
        if sensor_id in self._configs:
            del self._configs[sensor_id]
            logger.info(f"Removed sensor config: {sensor_id}")
            
    def get_configs(self) -> dict[str, dict]:
        return self._configs
        
    def get_sensor(self, sensor_id: str) -> QZFM | MockQZFM | None:
        return self._sensors.get(sensor_id)
        
    def connect_sensor(self, sensor_id: str) -> None:
        if sensor_id not in self._configs:
            raise ValueError(f"Unknown sensor: {sensor_id}")
            
        if sensor_id in self._sensors:
            return  # Already connected
            
        try:
            port = self._configs[sensor_id]["port"]
            if "SIM" in port.upper() or not HAS_QZFM:
                sensor = MockQZFM(port)
                logger.info(f"Connected {sensor_id} in SIMULATOR mode")
            else:
                sensor = QZFM(port)
                logger.info(f"Connected {sensor_id} on {port}")
            self._sensors[sensor_id] = sensor
            logger.info(f"Connected to {sensor_id}")
        except Exception as e:
            logger.error(f"Failed to connect {sensor_id}: {e}")
            raise
            
    def disconnect_sensor(self, sensor_id: str) -> None:
        if sensor_id in self._sensors:
            try:
                # Mock objects may not have disconnect()
                if hasattr(self._sensors[sensor_id], 'disconnect'):
                    self._sensors[sensor_id].disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting {sensor_id}: {e}")
            finally:
                del self._sensors[sensor_id]
                logger.info(f"Disconnected {sensor_id}")
                
    def disconnect_all(self) -> None:
        for sensor_id in list(self._sensors.keys()):
            self.disconnect_sensor(sensor_id)
            
    def get_info(self, sensor_id: str) -> SensorInfo:
        if sensor_id not in self._configs:
            raise ValueError(f"Unknown sensor: {sensor_id}")
            
        config = self._configs[sensor_id]
        sensor = self._sensors.get(sensor_id)
        
        info = SensorInfo(
            sensor_id=sensor_id,
            port=config["port"],
            name=config["name"],
            is_master=config["is_master"],
            gain=config.get("gain", 2.7),
            axis_mode=config.get("axis_mode", "z")
        )
        
        if sensor is not None:
            info.connected = True
            try:
                info.laser_on = sensor.led.get('laser on (LED1)', False)
                info.cell_temp_locked = sensor.led.get('cell temp lock (LED2)', False)
                info.laser_locked = sensor.led.get('laser lock (LED3)', False)
                info.field_zeroed = sensor.led.get('field zeroed (LED4)', False)
                info.is_calibrated = sensor.is_calibrated
                info.axis_mode = getattr(sensor, 'axis_mode', info.axis_mode)
                
                info.cell_temp_error = sensor.sensor_par.get('cell temp error', 0.0)
                info.bz_field = sensor.sensor_par.get('Bz field (pT)', 0.0)
                info.by_field = sensor.sensor_par.get('By field (pT)', 0.0)
                info.b0_field = sensor.sensor_par.get('B0 field (pT)', 0.0)
                
                info.messages = list(sensor.messages)
            except Exception as e:
                logger.debug(f"Error reading sensor info for {sensor_id}: {e}")
                
        return info

    def get_all_info(self) -> dict[str, SensorInfo]:
        return {s_id: self.get_info(s_id) for s_id in self._configs}
        
    @staticmethod
    def list_available_ports() -> list[str]:
        """Return a list of available COM ports for QZFM devices, plus SIMULATOR."""
        ports = [port.device for port in list_ports.comports()]
        ports.append("SIMULATOR")
        return ports
        
    def save_config(self, settings: QSettings) -> None:
        settings.beginGroup("sensors")
        settings.setValue("count", len(self._configs))
        for i, (s_id, config) in enumerate(self._configs.items()):
            settings.beginGroup(f"sensor_{i}")
            settings.setValue("id", s_id)
            settings.setValue("port", config["port"])
            settings.setValue("name", config["name"])
            settings.setValue("is_master", config["is_master"])
            settings.setValue("gain", config["gain"])
            settings.setValue("axis_mode", config.get("axis_mode", "z"))
            settings.endGroup()
        settings.endGroup()
        
    def load_config(self, settings: QSettings) -> None:
        self.disconnect_all()
        self._configs.clear()
        
        settings.beginGroup("sensors")
        count = int(settings.value("count", 0))
        for i in range(count):
            settings.beginGroup(f"sensor_{i}")
            s_id = str(settings.value("id", f"s{i}"))
            port = str(settings.value("port", ""))
            name = str(settings.value("name", f"Sensor {i+1}"))
            
            is_master = settings.value("is_master", False, type=bool)
            
            gain_val = settings.value("gain", 2.7)
            gain = float(gain_val) if gain_val else 2.7
            
            axis_mode = str(settings.value("axis_mode", "z"))
                
            if port:
                self.add_sensor(s_id, port, name, is_master, gain, axis_mode)
            settings.endGroup()
        settings.endGroup()
