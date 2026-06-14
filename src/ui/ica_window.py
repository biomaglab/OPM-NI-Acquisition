"""Standalone window for real-time Independent Component Analysis (ICA).

Manages its own QThread and IcaWorker to compute and visualize
independent components without blocking the main DAQ thread.
"""

from __future__ import annotations

import logging
import numpy as np
import pyqtgraph as pg

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QGroupBox,
    QGridLayout,
    QCheckBox,
    QLabel,
    QMessageBox,
    QSplitter,
    QDoubleSpinBox,
    QSpinBox,
    QFormLayout,
)

from src.processing.ica_worker import IcaWorker
from src.ui.styles import (
    BG_DARKEST,
    TEXT_SECONDARY,
    CHANNEL_COLORS,
    BORDER,
)

logger = logging.getLogger(__name__)


class IcaWindow(QMainWindow):
    """Windowed interface for Real-Time ICA.
    
    Contains a side panel for channel selection and a main area
    for displaying the estimated independent components.
    """

    def __init__(self, sample_rate: float, active_physical_channels: list[int], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Real-Time Independent Component Analysis (FastICA)")
        self.setMinimumSize(1000, 600)
        
        self._sample_rate = sample_rate
        self._available_channels = active_physical_channels
        self._selected_channels = list(active_physical_channels)
        
        self._worker: IcaWorker | None = None
        self._thread: QThread | None = None
        self._is_running = False
        self._current_window_seconds = 4.0
        
        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # ── Left: Controls ────────────────────────────────────────────── #
        control_panel = QWidget()
        control_panel.setFixedWidth(260)
        cp_layout = QVBoxLayout(control_panel)
        cp_layout.setContentsMargins(10, 10, 10, 10)
        
        # Channel Selection Group
        ch_group = QGroupBox("ICA CHANNELS")
        v_ch = QVBoxLayout(ch_group)
        v_ch.setContentsMargins(10, 0, 10, 10)
        
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        
        self._btn_all = QPushButton("ALL")
        self._btn_all.setFixedHeight(22)
        self._btn_all.clicked.connect(lambda: self._set_all(True))
        
        self._btn_none = QPushButton("NONE")
        self._btn_none.setFixedHeight(22)
        self._btn_none.clicked.connect(lambda: self._set_all(False))
        
        btn_row.addWidget(self._btn_all)
        btn_row.addWidget(self._btn_none)
        v_ch.addLayout(btn_row)
        v_ch.addSpacing(10)
        
        ch_grid = QGridLayout()
        self._checkboxes: list[QCheckBox] = []
        
        for i, ch_idx in enumerate(self._available_channels):
            chk = QCheckBox(f"CH {ch_idx + 1:02d}")
            chk.setChecked(True)
            chk.setProperty("ch_idx", ch_idx)
            chk.stateChanged.connect(self._update_components_range)
            self._checkboxes.append(chk)
            ch_grid.addWidget(chk, i // 3, i % 3)
            
        v_ch.addLayout(ch_grid)
        cp_layout.addWidget(ch_group)
        
        # Parameters Group
        param_group = QGroupBox("PARAMETERS")
        param_layout = QFormLayout(param_group)
        param_layout.setContentsMargins(10, 10, 10, 10)
        self._spin_window = QDoubleSpinBox()
        self._spin_window.setRange(1.0, 30.0)
        self._spin_window.setValue(4.0)
        self._spin_window.setSuffix(" s")
        self._spin_window.setDecimals(1)
        self._spin_window.setSingleStep(0.5)
        param_layout.addRow("WINDOW:", self._spin_window)
        
        self._spin_components = QSpinBox()
        self._spin_components.setRange(1, len(self._available_channels))
        self._spin_components.setValue(len(self._available_channels))
        param_layout.addRow("COMPONENTS:", self._spin_components)
        cp_layout.addWidget(param_group)
        
        # Run Button
        self._btn_run = QPushButton("START ICA")
        self._btn_run.setObjectName("btn_start")
        self._btn_run.clicked.connect(self._toggle_ica)
        cp_layout.addWidget(self._btn_run)
        
        cp_layout.addStretch()
        splitter.addWidget(control_panel)
        
        # ── Right: Chart ──────────────────────────────────────────────── #
        self._chart_widget = QWidget()
        chart_layout = QVBoxLayout(self._chart_widget)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        
        self._gl = pg.GraphicsLayoutWidget()
        self._gl.setBackground(BG_DARKEST)
        chart_layout.addWidget(self._gl)
        
        splitter.addWidget(self._chart_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        
        layout.addWidget(splitter)
        
        self._plots: list[pg.PlotItem] = []
        self._curves: list[pg.PlotDataItem] = []

    def _set_all(self, state: bool) -> None:
        for chk in self._checkboxes:
            chk.setChecked(state)

    def _get_selected_channels(self) -> list[int]:
        return [
            chk.property("ch_idx") 
            for chk in self._checkboxes 
            if chk.isChecked()
        ]

    def _update_components_range(self) -> None:
        """Update the maximum number of components based on active channels."""
        num_selected = len(self._get_selected_channels())
        if num_selected > 0:
            self._spin_components.setMaximum(num_selected)
            # Ensure the current value isn't higher than the new maximum
            if self._spin_components.value() > num_selected:
                self._spin_components.setValue(num_selected)

    def _toggle_ica(self) -> None:
        if self._is_running:
            self._stop_ica()
        else:
            self._start_ica()

    def _stop_ica(self) -> None:
        self._is_running = False
        
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
            
        self._worker = None
        self._thread = None
        
        self._btn_all.setEnabled(True)
        self._btn_none.setEnabled(True)
        for chk in self._checkboxes:
            chk.setEnabled(True)
        self._spin_window.setEnabled(True)
        self._spin_components.setEnabled(True)
            
        self._btn_run.setText("START ICA")
        self._btn_run.setObjectName("btn_start")
        self.style().unpolish(self._btn_run)
        self.style().polish(self._btn_run)
        logger.info("ICA stopped.")

    def _setup_chart(self, num_components: int) -> None:
        self._gl.clear()
        self._plots.clear()
        self._curves.clear()
        
        for i in range(num_components):
            plot = self._gl.addPlot(row=i, col=0)
            plot.hideButtons()
            plot.setMenuEnabled(False)
            plot.showGrid(x=True, y=True, alpha=0.2)
            
            color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
            plot.setTitle(f"IC {i + 1}", color=color, size="9pt")
            
            ax_left = plot.getAxis("left")
            ax_bottom = plot.getAxis("bottom")
            ax_left.setPen(pg.mkPen(color=BORDER, width=1))
            ax_bottom.setPen(pg.mkPen(color=BORDER, width=1))
            ax_left.setTextPen(pg.mkPen(color=TEXT_SECONDARY))
            ax_bottom.setTextPen(pg.mkPen(color=TEXT_SECONDARY))
            
            ax_left.setStyle(showValues=False)
            ax_bottom.setStyle(showValues=(i == num_components - 1))
            
            curve = plot.plot(pen=pg.mkPen(color=color, width=1.5))
            self._plots.append(plot)
            self._curves.append(curve)

    @pyqtSlot(np.ndarray)
    def add_data(self, raw_data: np.ndarray) -> None:
        """Called by MainWindow to feed data into the ICA worker."""
        if self._is_running and self._worker:
            # We call the worker's slot directly. Since they are in different
            # threads, PyQt will automatically Queue the connection/call.
            # But since we are calling a method explicitly, we should use
            # QMetaObject.invokeMethod, OR just let the MainWindow connect 
            # its signal directly to the worker's slot!
            # For simplicity, we just pass it along by directly invoking it
            # if we trust the underlying C++ to handle the array safely.
            # A safer way is to have a signal here:
            self.data_routed.emit(raw_data)

    # Internal signal to route data cross-thread safely
    data_routed = pyqtSignal(np.ndarray)

    def _on_ica_computed(self, sources: np.ndarray) -> None:
        """Update the charts with the new ICA sources."""
        num_comp, num_samples = sources.shape
        time_axis = np.linspace(0, self._current_window_seconds, num_samples)
        
        for i in range(min(num_comp, len(self._curves))):
            self._curves[i].setData(time_axis, sources[i])

    def _on_error(self, msg: str) -> None:
        self._stop_ica()
        QMessageBox.critical(self, "ICA Error", f"An error occurred during ICA computation:\n{msg}")

    def closeEvent(self, event) -> None:
        self._stop_ica()
        event.accept()

    def showEvent(self, event) -> None:
        """Wire up the internal routing signal when shown."""
        super().showEvent(event)
        # Ensure we connect the routing signal to the worker if running
        # Actually, it's safer to connect it when starting the worker.
    def _start_ica(self) -> None:
        selected_physical = self._get_selected_channels()
        if len(selected_physical) < 2:
            QMessageBox.warning(self, "Invalid Selection", "Please select at least 2 channels for ICA.")
            return
            
        self._selected_channels = selected_physical
        self._current_window_seconds = self._spin_window.value()
        
        # Determine number of components (PCA dimensionality reduction)
        num_components = self._spin_components.value()
        
        # Data array from MainWindow only contains the active physical channels.
        # We must convert the selected physical channels into logical indices (rows)
        logical_indices = [
            self._available_channels.index(ch) 
            for ch in selected_physical
        ]
        
        self._btn_all.setEnabled(False)
        self._btn_none.setEnabled(False)
        for chk in self._checkboxes:
            chk.setEnabled(False)
        self._spin_window.setEnabled(False)
        self._spin_components.setEnabled(False)
            
        self._btn_run.setText("STOP ICA")
        self._btn_run.setObjectName("btn_stop")
        self.style().unpolish(self._btn_run)
        self.style().polish(self._btn_run)
        
        self._setup_chart(num_components)
        
        self._thread = QThread()
        self._worker = IcaWorker(
            sample_rate=self._sample_rate,
            active_channels=logical_indices,
            window_seconds=self._current_window_seconds,
            update_interval_ms=500,
            num_components=num_components
        )
        self._worker.moveToThread(self._thread)
        
        self._thread.started.connect(self._worker.start_timer)
        self._worker.ica_computed.connect(self._on_ica_computed)
        self._worker.error_occurred.connect(self._on_error)
        
        # Route data from IcaWindow to IcaWorker safely across threads
        self.data_routed.connect(self._worker.add_data)
        
        self._is_running = True
        self._thread.start()
        logger.info("ICA started with channels: %s", selected_physical)
