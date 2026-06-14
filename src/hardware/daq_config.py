"""Configuration dataclass for the NI DAQ hardware.

Encapsulates all parameters needed to configure an analog input
voltage task on a National Instruments cDAQ chassis.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DaqConfig:
    """Immutable configuration for a DAQ acquisition session.

    Attributes:
        device_name: NI-DAQmx device/module name (e.g. ``"cDAQ1Mod1"``).
        active_channels: List of channel indices to acquire (e.g. ``[0, 1, 5]``).
        channel_prefix: Channel name prefix (e.g. ``"ai"`` -> ai0, ai1, ...).
        sample_rate: Sampling rate in Hz.
        samples_per_read: Number of samples read per block (per channel).
        min_voltage: Minimum expected voltage (V) of the input range.
        max_voltage: Maximum expected voltage (V) of the input range.
        terminal_config: Terminal configuration string.
            One of ``"RSE"``, ``"NRSE"``, ``"DIFF"``, ``"PSEUDO_DIFF"``.
    """

    device_name: str = "cDAQ1Mod1"
    total_channels: int = 24
    active_channels: list[int] = field(default_factory=lambda: list(range(24)))
    channel_prefix: str = "ai"
    sample_rate: float = 1000.0
    samples_per_read: int = 1000
    min_voltage: float = -10.0
    max_voltage: float = 10.0
    terminal_config: str = "RSE"

    @property
    def num_channels(self) -> int:
        return len(self.active_channels)

    # ---- derived helpers -------------------------------------------------- #

    @property
    def channel_list(self) -> list[str]:
        """Return the full list of physical channel strings.

        Example: ``["cDAQ1Mod1/ai0", "cDAQ1Mod1/ai1", ..., "cDAQ1Mod1/ai23"]``
        """
        return [
            f"{self.device_name}/{self.channel_prefix}{i}"
            for i in self.active_channels
        ]

    @property
    def physical_channels_str(self) -> str:
        """Return the NI-DAQmx channel string (comma-separated).

        Example: ``"cDAQ1Mod1/ai0, cDAQ1Mod1/ai2, cDAQ1Mod1/ai5"``
        """
        return ", ".join(self.channel_list)

    @property
    def channel_names(self) -> list[str]:
        """Return human-readable channel labels.

        Example: ``["CH-01", "CH-03", ..., "CH-06"]``
        """
        return [f"CH {i + 1:02d}" for i in self.active_channels]

    def validate(self) -> None:
        """Raise ``ValueError`` if any parameter is out of acceptable range."""
        if not self.active_channels:
            raise ValueError("active_channels cannot be empty")
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be > 0")
        if self.samples_per_read < 1:
            raise ValueError("samples_per_read must be >= 1")
        if self.min_voltage >= self.max_voltage:
            raise ValueError("min_voltage must be < max_voltage")
        valid_terminals = {"RSE", "NRSE", "DIFF", "PSEUDO_DIFF"}
        if self.terminal_config not in valid_terminals:
            raise ValueError(
                f"terminal_config must be one of {valid_terminals}, "
                f"got '{self.terminal_config}'"
            )
