"""Worker thread for computing Independent Component Analysis (ICA).

Runs FastICA in a separate thread to avoid blocking the DAQ or Main UI.
Receives data via Qt Signals and maintains an internal rolling window.
"""

from __future__ import annotations

import logging
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, pyqtSlot
from sklearn.decomposition import FastICA
from scipy.signal import detrend

logger = logging.getLogger(__name__)


class IcaWorker(QObject):
    """Computes ICA on a rolling window of selected channels.

    Expected to run in a dedicated QThread.
    """

    # Signal emitted when a new ICA estimation is ready.
    # Emits an array of shape (num_components, window_samples).
    ica_computed = pyqtSignal(np.ndarray)
    
    # Emitted if an error occurs during computation
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        sample_rate: float,
        active_channels: list[int],
        window_seconds: float = 3.0,
        update_interval_ms: int = 500,
        num_components: int | None = None,
    ) -> None:
        super().__init__()
        self._sample_rate = sample_rate
        self._active_channels = active_channels
        self._window_samples = int(sample_rate * window_seconds)
        self._update_interval_ms = update_interval_ms
        self._num_channels = len(active_channels)
        self._num_components = num_components if num_components is not None else self._num_channels

        # Buffer: shape (num_active_channels, window_samples)
        self._buffer = np.zeros((self._num_channels, self._window_samples), dtype=np.float64)
        self._write_pos = 0
        self._samples_accumulated = 0

        self._timer: QTimer | None = None
        self._ica = FastICA(n_components=self._num_components, random_state=42, max_iter=200)

    @pyqtSlot()
    def start_timer(self) -> None:
        """Start the internal computation timer. Must be called from the worker thread."""
        if self._num_channels == 0:
            logger.warning("IcaWorker started with 0 active channels.")
            return

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._compute_ica)
        self._timer.start(self._update_interval_ms)
        logger.info("IcaWorker timer started (%d ms).", self._update_interval_ms)

    @pyqtSlot()
    def stop_timer(self) -> None:
        """Stop the internal timer."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        logger.info("IcaWorker timer stopped.")

    @pyqtSlot(np.ndarray)
    def add_data(self, data: np.ndarray) -> None:
        """Slot to receive a chunk of data.
        
        Parameters
        ----------
        data : np.ndarray
            Shape (total_channels, num_samples). Only the configured
            `active_channels` are extracted and buffered.
        """
        if self._num_channels == 0:
            return

        # Extract only the channels we care about
        try:
            selected_data = data[self._active_channels, :]
        except IndexError:
            # Safely handle if data shape mismatches
            return

        num_new = selected_data.shape[1]
        ws = self._window_samples

        if num_new >= ws:
            self._buffer[:] = selected_data[:, -ws:]
            self._write_pos = 0
            self._samples_accumulated = ws
        else:
            start = self._write_pos
            end = start + num_new
            if end <= ws:
                self._buffer[:, start:end] = selected_data
            else:
                first_part = ws - start
                self._buffer[:, start:] = selected_data[:, :first_part]
                self._buffer[:, : num_new - first_part] = selected_data[:, first_part:]
            
            self._write_pos = end % ws
            self._samples_accumulated = min(ws, self._samples_accumulated + num_new)

    @pyqtSlot()
    def _compute_ica(self) -> None:
        """Run FastICA on the current buffer contents."""
        # Wait until we have a full window
        if self._samples_accumulated < self._window_samples:
            return

        # Roll the buffer so the oldest sample is at index 0
        rolled = np.roll(self._buffer, -self._write_pos, axis=1)

        # Scikit-learn expects shape (n_samples, n_features).
        # We detrend first to improve stability of FastICA.
        X = rolled.T
        X = detrend(X, axis=0)

        try:
            # Compute ICA
            S_ = self._ica.fit_transform(X)
            # Transpose back to (n_components, n_samples)
            estimated_sources = S_.T
            self.ica_computed.emit(estimated_sources)
        except Exception as e:
            logger.error("FastICA computation failed: %s", str(e))
            self.error_occurred.emit(str(e))
