"""QThread-based worker for executing blocking QZFM operations."""

from __future__ import annotations
import logging
from enum import Enum
import time
from typing import TYPE_CHECKING
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal, QWaitCondition, QMutex

if TYPE_CHECKING:
    from src.hardware.sensor_manager import SensorManager, SensorInfo

logger = logging.getLogger(__name__)

# Default timeout constants (seconds) — configurable via SensorWorker.set_timeouts()
DEFAULT_TIMEOUT_LASER_TEMP_LOCK = 240   # 4 min
DEFAULT_TIMEOUT_FIELD_ZERO      = 180   # 3 min
DEFAULT_TIMEOUT_TEMP_RECOVERY   = 90    # 1.5 min
DEFAULT_TIMEOUT_CALIBRATION     = 60    # 1 min

class SensorCommand(Enum):
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    AUTO_START = "auto_start"
    FIELD_ZERO_START = "field_zero_start"
    FIELD_ZERO_STOP = "field_zero_stop"
    CALIBRATE = "calibrate"
    FIELD_RESET = "field_reset"
    SET_GAIN = "set_gain"
    SET_MASTER = "set_master"
    REBOOT = "reboot"
    UPDATE_STATUS = "update_status"
    START_STREAMING = "start_streaming"
    STOP_STREAMING = "stop_streaming"
    SET_AXIS_MODE = "set_axis_mode"
    AUTO_START_ALL = "auto_start_all"

class SensorWorker(QThread):
    progress = pyqtSignal(str, str)          # (sensor_id, message)
    status_updated = pyqtSignal(str, object) # (sensor_id, SensorInfo snapshot)
    command_finished = pyqtSignal(str, str, bool)  # (sensor_id, command_name, success)
    error_occurred = pyqtSignal(str, str)    # (sensor_id, error message)
    zeroing_data = pyqtSignal(str, float, float, float, float) # (sensor_id, bz, by, b0, t_err)
    field_zero_completed = pyqtSignal(str)   # (sensor_id)
    data_received = pyqtSignal(str, object, object) # (sensor_id, times, fields)
    log_received = pyqtSignal(str, str) # (sensor_id, message)

    def __init__(self, manager: SensorManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._queue: list[tuple[str, SensorCommand, dict]] = []
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._running = False
        self._cancel_batch = False
        self._polling_interval = 0.5  # seconds between status updates
        self._zeroing_tasks: set[str] = set()
        self._zeroing_monitor: dict[str, dict[str, list[float]]] = {}
        self._zero_cond = 100.0
        self._streaming_tasks: dict[str, str] = {}  # sensor_id -> axis

        # Configurable timeouts (seconds)
        self.timeout_laser_temp_lock = DEFAULT_TIMEOUT_LASER_TEMP_LOCK
        self.timeout_field_zero = DEFAULT_TIMEOUT_FIELD_ZERO
        self.timeout_temp_recovery = DEFAULT_TIMEOUT_TEMP_RECOVERY
        self.timeout_calibration = DEFAULT_TIMEOUT_CALIBRATION

    def start_worker(self):
        self._running = True
        self.start()

    def stop_worker(self):
        self._mutex.lock()
        self._running = False
        self._cond.wakeAll()
        self._mutex.unlock()
        self.wait(2000)

    def request_cancel(self):
        """Request cancellation of the current batch operation."""
        self._mutex.lock()
        self._cancel_batch = True
        self._mutex.unlock()

    def is_cancelled(self) -> bool:
        """Check if a cancellation has been requested."""
        self._mutex.lock()
        val = self._cancel_batch
        self._mutex.unlock()
        return val

    def queue_command(self, sensor_id: str, command: SensorCommand, **kwargs) -> None:
        self._mutex.lock()
        self._queue.append((sensor_id, command, kwargs))
        self._cond.wakeAll()
        self._mutex.unlock()

    def set_timeouts(self, laser_temp_lock: float = None, field_zero: float = None,
                     temp_recovery: float = None, calibration: float = None):
        """Update timeout values. Pass None to keep the current value."""
        if laser_temp_lock is not None:
            self.timeout_laser_temp_lock = laser_temp_lock
        if field_zero is not None:
            self.timeout_field_zero = field_zero
        if temp_recovery is not None:
            self.timeout_temp_recovery = temp_recovery
        if calibration is not None:
            self.timeout_calibration = calibration

    def set_zero_cond(self, cond: float):
        """Update the global zeroing condition (gradient threshold in pT/s)."""
        self._zero_cond = cond

    def set_polling_interval(self, seconds: float):
        self._polling_interval = seconds
        
    def add_zeroing_task(self, sensor_id: str):
        self._mutex.lock()
        self._zeroing_tasks.add(sensor_id)
        self._zeroing_monitor[sensor_id] = {
            "t": [],
            "b0": [],
            "by": [],
            "bz": [],
        }
        self._mutex.unlock()
        
    def remove_zeroing_task(self, sensor_id: str):
        self._mutex.lock()
        self._zeroing_tasks.discard(sensor_id)
        self._zeroing_monitor.pop(sensor_id, None)
        self._mutex.unlock()

    def run(self):
        while True:
            self._mutex.lock()
            if not self._running:
                self._mutex.unlock()
                break

            if not self._queue:
                # Wait for commands, or timeout to do polling
                timeout_ms = 100 if self._streaming_tasks else (500 if self._zeroing_tasks else int(self._polling_interval * 1000))
                self._cond.wait(self._mutex, timeout_ms)
                
            if not self._running:
                self._mutex.unlock()
                break

            # Process one command if available
            command_item = None
            if self._queue:
                command_item = self._queue.pop(0)
            self._mutex.unlock()

            if command_item:
                sensor_id, command, kwargs = command_item
                try:
                    self._execute_command(sensor_id, command, kwargs)
                    self.command_finished.emit(sensor_id, command.value, True)
                except Exception as e:
                    logger.exception(f"Error executing {command.value} on {sensor_id}")
                    self.error_occurred.emit(sensor_id, str(e))
                    self.command_finished.emit(sensor_id, command.value, False)
            else:
                # Polling phase
                self._poll_sensors()
                
            # Emit zeroing data
            self._mutex.lock()
            active_zeroing = list(self._zeroing_tasks)
            active_streaming = dict(self._streaming_tasks)
            self._mutex.unlock()
            
            # Process streaming
            for s_id, axis in active_streaming.items():
                sensor = self._manager.get_sensor(s_id)
                if sensor:
                    try:
                        times, fields = sensor.read_data(seconds=0.1, axis=axis, clear_buffer=False)
                        if len(times) > 0:
                            self.data_received.emit(s_id, np.array(times), np.array(fields))
                    except Exception as e:
                        logger.debug(f"Streaming error on {s_id}: {e}")
            
            for s_id in active_zeroing:
                sensor = self._manager.get_sensor(s_id)
                if sensor:
                    try:
                        sensor.update_status(clear_buffer=True)
                        self.zeroing_data.emit(
                            s_id,
                            sensor.sensor_par.get('Bz field (pT)', 0.0),
                            sensor.sensor_par.get('By field (pT)', 0.0),
                            sensor.sensor_par.get('B0 field (pT)', 0.0),
                            sensor.sensor_par.get('cell temp error', 0.0)
                        )
                        self._check_zeroing_completion(s_id, sensor)
                    except Exception:
                        pass

    def _execute_command(self, sensor_id: str, command: SensorCommand, kwargs: dict):
        if command == SensorCommand.CONNECT:
            self._manager.connect_sensor(sensor_id)
            sensor = self._manager.get_sensor(sensor_id)
            if sensor:
                try:
                    config = self._manager.get_configs().get(sensor_id, {})
                    axis_mode = config.get("axis_mode", "z")
                    if hasattr(sensor, 'set_axis_mode'):
                        sensor.set_axis_mode(mode=axis_mode)
                    sensor.update_status(clear_buffer=True)
                except Exception as e:
                    logger.debug(f"Error configuring status after connect for {sensor_id}: {e}")
            self._emit_status(sensor_id)
            
        elif command == SensorCommand.DISCONNECT:
            self._manager.disconnect_sensor(sensor_id)
            self._emit_status(sensor_id)
            
        elif command == SensorCommand.UPDATE_STATUS:
            sensor = self._manager.get_sensor(sensor_id)
            if sensor:
                if sensor_id not in self._streaming_tasks:
                    sensor.update_status()
                self._emit_status(sensor_id)

        elif command == SensorCommand.START_STREAMING:
            sensor = self._manager.get_sensor(sensor_id)
            if sensor:
                axis = kwargs.get('axis', 'z')
                self._mutex.lock()
                self._streaming_tasks[sensor_id] = axis
                self._mutex.unlock()
                
        elif command == SensorCommand.STOP_STREAMING:
            self._mutex.lock()
            if sensor_id in self._streaming_tasks:
                del self._streaming_tasks[sensor_id]
            self._mutex.unlock()
            sensor = self._manager.get_sensor(sensor_id)
            if sensor and sensor.is_data_streaming:
                try:
                    sensor._set_data_stream(False)
                except Exception:
                    pass

        elif command == SensorCommand.FIELD_ZERO_START:
            sensor = self._manager.get_sensor(sensor_id)
            if sensor:
                axes_xyz = kwargs.get('axes_xyz', True)
                sensor.field_zero(on=True, axes_xyz=axes_xyz, show=False)
                self.add_zeroing_task(sensor_id)
                self._emit_status(sensor_id)

        elif command == SensorCommand.FIELD_ZERO_STOP:
            sensor = self._manager.get_sensor(sensor_id)
            if sensor:
                sensor.field_zero(on=False, show=False)
                self.remove_zeroing_task(sensor_id)
                self._emit_status(sensor_id)
                
        elif command == SensorCommand.CALIBRATE:
            sensor = self._manager.get_sensor(sensor_id)
            if sensor:
                self.progress.emit(sensor_id, "Calibrating...")
                sensor.calibrate(show=False)
                self._emit_status(sensor_id)
                
        elif command == SensorCommand.FIELD_RESET:
            sensor = self._manager.get_sensor(sensor_id)
            if sensor:
                sensor.field_reset()
                self._emit_status(sensor_id)

        elif command == SensorCommand.SET_GAIN:
            sensor = self._manager.get_sensor(sensor_id)
            if sensor:
                mode = kwargs.get('mode', '1x')
                sensor.set_gain(mode=mode)
                config = self._manager.get_configs()[sensor_id]
                config["gain"] = sensor.gain
                self._emit_status(sensor_id)
                
        elif command == SensorCommand.SET_MASTER:
            sensor = self._manager.get_sensor(sensor_id)
            if sensor:
                is_master = kwargs.get('is_master', True)
                sensor.set_master(master=is_master)
                config = self._manager.get_configs()[sensor_id]
                config["is_master"] = is_master
                self._emit_status(sensor_id)
                
        elif command == SensorCommand.SET_AXIS_MODE:
            sensor = self._manager.get_sensor(sensor_id)
            if sensor:
                mode = kwargs.get('mode', 'z')
                if hasattr(sensor, 'set_axis_mode'):
                    sensor.set_axis_mode(mode=mode)
                config = self._manager.get_configs()[sensor_id]
                config["axis_mode"] = mode
                self._emit_status(sensor_id)
                
        elif command == SensorCommand.REBOOT:
            sensor = self._manager.get_sensor(sensor_id)
            if sensor:
                sensor.reboot()
                self._emit_status(sensor_id)

        elif command == SensorCommand.AUTO_START:
            sensor = self._manager.get_sensor(sensor_id)
            if not sensor:
                raise ValueError(f"Sensor {sensor_id} not connected")
                
            zero_calibrate = kwargs.get('zero_calibrate', True)
            zero_cond = kwargs.get('zero_cond', 100)
            
            self.progress.emit(sensor_id, "Starting auto_start...")
            sensor.ser.write(b'>')
            sensor.update_status()
            
            self.progress.emit(sensor_id, "Waiting for laser lock and temp lock...")
            
            lock_start_time = time.time()
            locked = False
            while not locked:
                if not self._running or self.is_cancelled():
                    return
                if time.time() - lock_start_time > self.timeout_laser_temp_lock:
                    self.progress.emit(sensor_id, f"TIMEOUT — laser/temp lock exceeded {self.timeout_laser_temp_lock}s.")
                    return
                
                sensor.update_status(clear_buffer=False)
                self._emit_status(sensor_id)
                if sensor.led.get("laser lock (LED3)") and sensor.led.get("cell temp lock (LED2)"):
                    locked = True
                else:
                    time.sleep(0.5)
                
            if zero_calibrate:
                success = self._zero_and_calibrate_single(sensor_id, sensor, zero_cond)
                if success:
                    self._emit_status(sensor_id)
                    self.progress.emit(sensor_id, "Auto-start completed!")

        elif command == SensorCommand.AUTO_START_ALL:
            # Reset cancel flag at the start of a new batch
            self._mutex.lock()
            self._cancel_batch = False
            self._mutex.unlock()

            sensors_dict = {}
            for sid, conf in self._manager.get_configs().items():
                s = self._manager.get_sensor(sid)
                if s:
                    sensors_dict[sid] = s

            if not sensors_dict:
                return

            zero_calibrate = kwargs.get('zero_calibrate', True)
            zero_cond = kwargs.get('zero_cond', 100)
            
            self.progress.emit("all", "Assigning roles (Master/Slave)...")
            for sid, s in sensors_dict.items():
                config = self._manager.get_configs().get(sid, {})
                is_master = config.get("is_master", False)
                if hasattr(s, 'set_master'):
                    s.set_master(master=is_master)

            self.progress.emit("all", "Starting auto-start (warming up all lasers)...")
            for sid, s in sensors_dict.items():
                s.ser.write(b'>')
                s.update_status()

            self.progress.emit("all", "Waiting for lasers and temperatures to stabilize...")
            pending_lock = dict(sensors_dict)  # sensors still waiting for lock
            lock_start_times = {sid: time.time() for sid in pending_lock}
            skipped_sensors: set[str] = set()

            while pending_lock:
                if not self._running or self.is_cancelled():
                    if self.is_cancelled():
                        self.progress.emit("all", "Batch initialization cancelled by user.")
                    return

                # If zero_cond was passed via kwargs, apply it globally for this batch
                if "zero_cond" in kwargs:
                    self.set_zero_cond(kwargs["zero_cond"])

                newly_locked = []
                for sid, s in list(pending_lock.items()):
                    s.update_status(clear_buffer=False)
                    self._emit_status(sid)
                    if s.led.get("laser lock (LED3)") and s.led.get("cell temp lock (LED2)"):
                        newly_locked.append(sid)
                    elif time.time() - lock_start_times[sid] > self.timeout_laser_temp_lock:
                        self.progress.emit(sid, f"TIMEOUT — laser/temp lock exceeded {self.timeout_laser_temp_lock}s. Skipping.")
                        self.progress.emit("all", f"Sensor {sid} timed out during warm-up. Skipping.")
                        skipped_sensors.add(sid)
                        newly_locked.append(sid)  # remove from pending

                for sid in newly_locked:
                    del pending_lock[sid]

                if pending_lock:
                    time.sleep(0.5)

            # Remove skipped sensors from the calibration set
            active_sensors = {sid: s for sid, s in sensors_dict.items() if sid not in skipped_sensors}

            if zero_calibrate and active_sensors:
                total = len(active_sensors)
                for idx, (sid, s) in enumerate(active_sensors.items(), 1):
                    if self.is_cancelled():
                        self.progress.emit("all", "Batch initialization cancelled by user.")
                        return
                    self.progress.emit("all", f"Calibrating sensor {idx}/{total} ({sid})...")
                    success = self._zero_and_calibrate_single(sid, s, zero_cond)
                    if not success:
                        if self.is_cancelled():
                            self.progress.emit("all", "Batch initialization cancelled by user.")
                            return
                        # Sensor failed/timed out — skip it, continue with others
                        self.progress.emit(sid, "Zeroing/calibration failed. Skipping.")
                        skipped_sensors.add(sid)
                        continue
                    self._emit_status(sid)

            if skipped_sensors:
                names = ", ".join(skipped_sensors)
                self.progress.emit("all", f"Initialization complete. Skipped sensors: {names}")
            else:
                self.progress.emit("all", "All sensors have been started and calibrated successfully!")

    def _poll_sensors(self):
        for s_id, sensor in list(self._manager._sensors.items()):
            if s_id not in self._zeroing_tasks and s_id not in self._streaming_tasks:
                try:
                    sensor.update_status(clear_buffer=True)
                    self._emit_status(s_id)
                except Exception as e:
                    logger.debug(f"Polling error on {s_id}: {e}")

    def _zero_and_calibrate_single(self, sensor_id: str, sensor: object, zero_cond: float) -> bool:
        """Run field zeroing, temp recovery, and calibration for a single sensor.
        Returns True on success, False on timeout/cancel/failure."""
        # The QZFM firmware requires the sensor to be in 'z' mode to run Field Zero and Calibration.
        # If it is in 'dual' mode, it will fail with "Z alone, Run Field Zero & then Calibration".
        if hasattr(sensor, 'set_axis_mode'):
            sensor.set_axis_mode(mode='z')
        
        self.progress.emit(sensor_id, "Starting field zeroing...")
        sensor.field_zero(on=True, show=False)
        self.add_zeroing_task(sensor_id)
        
        # Mandatory wait to allow sensor hardware to begin the zeroing sweep.
        # If we check too early, we might read frozen values and stop zeroing prematurely.
        self.progress.emit(sensor_id, "Waiting for zeroing sweep to begin...")
        sweep_wait_start = time.time()
        while time.time() - sweep_wait_start < 8.0:
            if not self._running or self.is_cancelled():
                return False
            time.sleep(0.5)
            
        x_comp, y_comp, z_comp, t = [], [], [], []
        zero_start = time.time()
        
        # Wait for 6 initial readings
        while len(x_comp) < 6:
            if not self._running or self.is_cancelled():
                return False
            if time.time() - zero_start > self.timeout_field_zero:
                self.progress.emit(sensor_id, f"TIMEOUT — field zeroing exceeded {self.timeout_field_zero}s.")
                sensor.field_zero(on=False, show=False)
                self.remove_zeroing_task(sensor_id)
                return False
            sensor.update_status()
            t.append(sensor.status_last_updated)
            x_comp.append(sensor.sensor_par.get('B0 field (pT)', 0.0))
            y_comp.append(sensor.sensor_par.get('By field (pT)', 0.0))
            z_comp.append(sensor.sensor_par.get('Bz field (pT)', 0.0))
            self._emit_status(sensor_id)
            time.sleep(0.5)
            
        zeroed = False
        while not zeroed:
            if not self._running or self.is_cancelled():
                return False
            if time.time() - zero_start > self.timeout_field_zero:
                self.progress.emit(sensor_id, f"TIMEOUT — field zeroing exceeded {self.timeout_field_zero}s.")
                sensor.field_zero(on=False, show=False)
                self.remove_zeroing_task(sensor_id)
                return False
            
            t_diff = [j-i for i, j in zip(t[-5:][:-1], t[-5:][1:])]
            x_diff = [j-i for i, j in zip(x_comp[-5:][:-1], x_comp[-5:][1:])]
            y_diff = [j-i for i, j in zip(y_comp[-5:][:-1], y_comp[-5:][1:])]
            z_diff = [j-i for i, j in zip(z_comp[-5:][:-1], z_comp[-5:][1:])]
            
            x_grad = [abs(i/j) if j > 0 else float('inf') for i, j in zip(x_diff, t_diff)]
            y_grad = [abs(i/j) if j > 0 else float('inf') for i, j in zip(y_diff, t_diff)]
            z_grad = [abs(i/j) if j > 0 else float('inf') for i, j in zip(z_diff, t_diff)]
            
            if all(x < zero_cond for x in x_grad) and all(y < zero_cond for y in y_grad) and all(z < zero_cond for z in z_grad):
                zeroed = True
            else:
                sensor.update_status(clear_buffer=False)
                t.append(sensor.status_last_updated)
                x_comp.append(sensor.sensor_par.get('B0 field (pT)', 0.0))
                y_comp.append(sensor.sensor_par.get('By field (pT)', 0.0))
                z_comp.append(sensor.sensor_par.get('Bz field (pT)', 0.0))
                self._emit_status(sensor_id)
                time.sleep(0.5)
                
        # Stop zeroing
        sensor.field_zero(on=False, show=False)
        self.remove_zeroing_task(sensor_id)
        self.progress.emit(sensor_id, "Field zeroing completed. Restoring temp lock...")
        
        temp_start = time.time()
        temp_err_ok = False
        temp_err_last = float('inf')
        while not temp_err_ok:
            if not self._running or self.is_cancelled():
                return False
            if time.time() - temp_start > self.timeout_temp_recovery:
                self.progress.emit(sensor_id, f"TIMEOUT — temp recovery exceeded {self.timeout_temp_recovery}s.")
                return False
            sensor.update_status()
            err = sensor.sensor_par.get('cell temp error', float('inf'))
            temp_err_ok = abs(err) <= 0.001 or abs(temp_err_last - err) <= 0.001
            temp_err_last = err
            self._emit_status(sensor_id)
            time.sleep(0.5)
            
        self.progress.emit(sensor_id, "Calibrating...")
        cal_start = time.time()
        
        # Record number of messages before calibration so we don't parse old logs
        msg_count_before = len(sensor.messages) if hasattr(sensor, 'messages') else 0
        
        sensor.calibrate(show=False)
        cal_elapsed = time.time() - cal_start
        if cal_elapsed > self.timeout_calibration:
            self.progress.emit(sensor_id, f"WARNING — calibration took {cal_elapsed:.0f}s (timeout: {self.timeout_calibration}s).")
            
        # Parse the calibration factor from the NEW messages only
        cal_fact = None
        if hasattr(sensor, 'messages'):
            new_msgs = sensor.messages[msg_count_before:]
            for msg, msg_t in reversed(new_msgs):
                if 'Calib. Fact.' in msg:
                    # Expected format: "Calib. Fact. : 15.90 (z)  -> in Z mode"
                    try:
                        parts = msg.split(':')
                        if len(parts) > 1:
                            val_str = parts[1].strip().split()[0]
                            cal_fact = float(val_str)
                    except Exception as e:
                        logger.debug(f"Failed to parse calibration factor from '{msg}': {e}")
                    break
                    
        if cal_fact is not None:
            self.progress.emit(sensor_id, f"Calibration factor: {cal_fact}")
        
        try:
            sensor.save_state()
        except Exception as e:
            logger.debug(f"Failed to save sensor state: {e}")
            
        # Restore the user's configured axis mode after calibration is complete
        config = self._manager.get_configs().get(sensor_id, {})
        target_axis_mode = config.get("axis_mode", "z")
        if hasattr(sensor, 'set_axis_mode'):
            sensor.set_axis_mode(mode=target_axis_mode)
            
        return True

    def _check_zeroing_completion(self, sensor_id: str, sensor) -> None:
        monitor = self._zeroing_monitor.get(sensor_id)
        if monitor is None:
            return

        monitor["t"].append(sensor.status_last_updated)
        monitor["b0"].append(sensor.sensor_par.get('B0 field (pT)', 0.0))
        monitor["by"].append(sensor.sensor_par.get('By field (pT)', 0.0))
        monitor["bz"].append(sensor.sensor_par.get('Bz field (pT)', 0.0))

        if len(monitor["t"]) < 6:
            return

        t_diff = [j - i for i, j in zip(monitor["t"][-5:][:-1], monitor["t"][-5:][1:])]
        b0_diff = [j - i for i, j in zip(monitor["b0"][-5:][:-1], monitor["b0"][-5:][1:])]
        by_diff = [j - i for i, j in zip(monitor["by"][-5:][:-1], monitor["by"][-5:][1:])]
        bz_diff = [j - i for i, j in zip(monitor["bz"][-5:][:-1], monitor["bz"][-5:][1:])]

        b0_grad = [abs(d / dt) if dt > 0 else float('inf') for d, dt in zip(b0_diff, t_diff)]
        by_grad = [abs(d / dt) if dt > 0 else float('inf') for d, dt in zip(by_diff, t_diff)]
        bz_grad = [abs(d / dt) if dt > 0 else float('inf') for d, dt in zip(bz_diff, t_diff)]

        if all(x < self._zero_cond for x in b0_grad) and all(x < self._zero_cond for x in by_grad) and all(x < self._zero_cond for x in bz_grad):
            sensor.field_zero(on=False, show=False)
            self.remove_zeroing_task(sensor_id)
            self.progress.emit(sensor_id, "Field zeroing completed.")
            self.field_zero_completed.emit(sensor_id)
            self._emit_status(sensor_id)

    def _emit_status(self, sensor_id: str):
        info = self._manager.get_info(sensor_id)
        
        # Emit new logs
        if info.messages:
            idx_key = f"_log_idx_{sensor_id}"
            last_idx = getattr(self, idx_key, 0)
            if len(info.messages) > last_idx:
                for msg_txt, _ in info.messages[last_idx:]:
                    self.log_received.emit(sensor_id, msg_txt)
                setattr(self, idx_key, len(info.messages))
                
        self.status_updated.emit(sensor_id, info)
