"""Real-time chart grid for 24-channel OPM visualisation.

Uses ``pyqtgraph`` for high-performance waveform rendering with a
circular buffer for each channel to keep a configurable time window
visible (e.g. the last 5 seconds).

Styled to resemble an oscilloscope / strip-chart recorder with
minimal decoration and maximum data density.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt

from src.ui.styles import (
    CHANNEL_COLORS,
    BG_DARKEST,
    BG_INPUT,
    BORDER,
    TEXT_SECONDARY,
    TEXT_DATA,
    FONT_MONO,
)


class ChartWidget(QWidget):
    """Grid of 24 real-time PlotItems (6 rows x 4 columns).

    Each plot shows a rolling window of the most recent *N* seconds
    of data for one OPM channel.

    Parameters
    ----------
    num_channels : int
        Number of physical slots to display (usually 24).
    active_channels : list[int] | None
        List of indices that are currently active and receiving data.
    sample_rate : float
        Samples per second (used to compute time axis).
    window_seconds : float
        Length of the visible time window in seconds.
    rows : int
        Number of rows in the plot grid.
    cols : int
        Number of columns in the plot grid.
    """

    def __init__(
        self,
        active_channels: list[int] | None = None,
        sample_rate: float = 1000.0,
        window_seconds: float = 5.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._active_channels = active_channels if active_channels is not None else list(range(24))
        self._sample_rate = sample_rate
        self._window_seconds = window_seconds

        # Circular buffer: we only need buffers for ACTIVE channels
        self._window_samples = int(sample_rate * window_seconds)
        self._buffers: list[np.ndarray] = [
            np.zeros(self._window_samples, dtype=np.float64)
            for _ in self._active_channels
        ]
        self._write_pos = 0  # position in the circular buffer

        # Time axis (shared across all plots).
        self._time_axis = np.linspace(0, window_seconds, self._window_samples)

        # ── Build the layout ──────────────────────────────────────────── #
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Configure pyqtgraph global settings — oscilloscope look.
        pg.setConfigOptions(
            antialias=False,       # faster rendering for 24 channels
            useOpenGL=False,       # avoid driver issues; still very fast
            background=BG_DARKEST,
            foreground=TEXT_SECONDARY,
        )

        self._graphics_layout = pg.GraphicsLayoutWidget()
        self._graphics_layout.setBackground(BG_DARKEST)
        self._graphics_layout.ci.layout.setSpacing(0)  # Removes gap between channels
        self._graphics_layout.ci.setContentsMargins(0, 0, 0, 0) # Remove padding around the entire grid
        layout.addWidget(self._graphics_layout)

        self._plots: list[pg.PlotItem] = []
        self._curves: list[pg.PlotDataItem] = []

        self._build_plots()

    # ── Public API ────────────────────────────────────────────────────── #

    def set_active_channels(self, active_channels: list[int]) -> None:
        """Update the list of active channels, clearing inactive ones."""
        self._active_channels = active_channels
        self._buffers = [
            np.zeros(self._window_samples, dtype=np.float64)
            for _ in self._active_channels
        ]
        self._write_pos = 0
        self._build_plots()

    def update_data(self, data: np.ndarray) -> None:
        """Append a new block of data and refresh all curves.

        Parameters
        ----------
        data : np.ndarray
            Shape ``(num_channels, num_new_samples)``.
        """
        num_ch, num_new = data.shape
        ws = self._window_samples

        if num_new >= ws:
            # Block is larger than the window -> take the tail.
            for i, _ in enumerate(self._active_channels):
                if i < num_ch:
                    self._buffers[i][:] = data[i, -ws:]
            self._write_pos = 0
        else:
            # Append into circular buffer.
            start = self._write_pos
            end = start + num_new
            for i, _ in enumerate(self._active_channels):
                if i >= num_ch:
                    continue
                if end <= ws:
                    self._buffers[i][start:end] = data[i]
                else:
                    # Wrap around.
                    first_part = ws - start
                    self._buffers[i][start:] = data[i, :first_part]
                    self._buffers[i][: num_new - first_part] = data[i, first_part:]
            self._write_pos = end % ws

        # Update curves (no clear+re-plot -> reuse PlotDataItem for speed).
        for i, ch_idx in enumerate(self._active_channels):
            if i < num_ch:
                # Roll buffer so that the oldest sample is at x=0.
                rolled = np.roll(self._buffers[i], -self._write_pos)
                self._curves[i].setData(self._time_axis, rolled)

    def set_window_seconds(self, seconds: float) -> None:
        """Change the visible time window and reallocate buffers."""
        self._window_seconds = seconds
        self._window_samples = int(self._sample_rate * seconds)
        self._time_axis = np.linspace(0, seconds, self._window_samples)
        self._buffers = [
            np.zeros(self._window_samples, dtype=np.float64)
            for _ in self._active_channels
        ]
        self._write_pos = 0

        for plot in self._plots:
            plot.setXRange(0, seconds, padding=0)

    def clear_data(self) -> None:
        """Zero all buffers and reset curves."""
        for i, ch_idx in enumerate(self._active_channels):
            self._buffers[i][:] = 0.0
            self._curves[i].setData(self._time_axis, self._buffers[i])
        self._write_pos = 0

    def reset_views(self) -> None:
        """Reset the auto-range and X-axis for all active plots."""
        for plot in self._plots:
            plot.setXRange(0, self._window_seconds, padding=0)
            plot.enableAutoRange(axis=pg.ViewBox.YAxis)

    # ── Internal helpers ──────────────────────────────────────────────── #

    def _build_plots(self) -> None:
        """Dynamically build the plot grid based on active channels."""
        self._graphics_layout.clear()
        self._plots.clear()
        self._curves.clear()

        n_active = len(self._active_channels)
        if n_active == 0:
            return

        import math
        cols = math.ceil(math.sqrt(n_active))
        rows = math.ceil(n_active / cols) if cols > 0 else 0

        total_cells = rows * cols

        for i in range(total_cells):
            row = i // cols
            col = i % cols
            
            if i < n_active:
                ch_idx = self._active_channels[i]
                plot = self._graphics_layout.addPlot(row=row, col=col)
                self._configure_plot(plot, i, rows, cols, is_active=True)

                color = CHANNEL_COLORS[ch_idx % len(CHANNEL_COLORS)]
                curve = plot.plot(
                    self._time_axis,
                    np.zeros(self._window_samples),
                    pen=pg.mkPen(color=color, width=1.5),
                )

                # Channel name label — drawn as a legend-like overlay in scene coords
                label = pg.LabelItem(
                    text=f"<span style='color:{color}; font-size:8pt; font-weight:bold; font-family:{FONT_MONO};'>CH {ch_idx + 1:02d}</span>",
                    justify='left',
                )
                label.setParentItem(plot.vb)
                label.anchor(itemPos=(0, 0), parentPos=(0, 0), offset=(4, 2))

                self._plots.append(plot)
                self._curves.append(curve)
            else:
                # Add a dummy invisible plot to fill the hole and maintain grid symmetry
                plot = self._graphics_layout.addPlot(row=row, col=col)
                self._configure_plot(plot, i, rows, cols, is_active=False)

    def _configure_plot(self, plot: pg.PlotItem, index: int, rows: int, cols: int, is_active: bool = True) -> None:
        """Style a single plot widget for an instrument / oscilloscope look."""
        # Remove the title row from the internal layout to eliminate vertical gaps
        plot.setTitle(None)
        plot.titleLabel.setMaximumHeight(0)
        plot.titleLabel.setMinimumHeight(0)
        plot.titleLabel.setVisible(False)

        # Hide the right and top axes to remove any extra horizontal/vertical padding
        plot.hideAxis('right')
        plot.hideAxis('top')

        if not is_active:
            plot.hideAxis('left')
            plot.hideAxis('bottom')
            plot.hideButtons()
            plot.setMenuEnabled(False)
            plot.setContentsMargins(0, 0, 0, 0)
            plot.layout.setContentsMargins(0, 0, 0, 0)
            plot.layout.setSpacing(0)
            return

        plot.setXRange(0, self._window_seconds, padding=0)

        # Grid: subtle lines resembling oscilloscope graticule.
        plot.showGrid(x=True, y=True, alpha=0.2)
        plot.hideButtons()
        plot.setMenuEnabled(False)
        
        # Extreme performance optimizations for high-density rendering.
        plot.setDownsampling(auto=True, mode='peak')
        plot.setClipToView(True)

        # Minimal axis labels — only leftmost column shows Y, bottom row shows X.
        row = index // cols
        col = index % cols

        ax_left = plot.getAxis("left")
        ax_bottom = plot.getAxis("bottom")

        # Axis styling — thin, muted.
        for ax in (ax_left, ax_bottom):
            ax.setPen(pg.mkPen(color=BORDER, width=1))
            ax.setTextPen(pg.mkPen(color=TEXT_SECONDARY))

        # Force constant dimensions for axes to prevent text from shifting plot widths
        ax_left.setWidth(45)
        ax_bottom.setHeight(18)

        # Show Y axis ticks and label on ALL plots
        ax_left.setStyle(showValues=True, tickLength=-4)
        ax_bottom.setStyle(showValues=(row == rows - 1), tickLength=-4)

        ax_left.setLabel("V", color=TEXT_SECONDARY, **{"font-size": "9pt", "font-weight": "bold"})
        if row == rows - 1:
            ax_bottom.setLabel("s", color=TEXT_SECONDARY, **{"font-size": "9pt"})

        # Tight layout for maximum data density.
        plot.setContentsMargins(0, 0, 0, 0)
        plot.layout.setContentsMargins(0, 0, 0, 0)
        plot.layout.setSpacing(0)
