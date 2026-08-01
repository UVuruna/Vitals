"""Vitals Application."""

from .collect.collector import SharedDataCollector
from .collect.monitor_data import MonitorMode
from .collect.process_stats import ProcessMonitor
from .dialogs.mode_dialogs import (
    CPUSettingsDialog,
    MemorySettingsDialog,
    NetworkSettingsDialog,
)
from .dialogs.setup_dialog import InitialSettingsDialog
from .settings import (
    CPUSettings,
    InitialSettings,
    MemorySettings,
    NetworkSettings,
)
from .theme import ThemeScope, app_theme, window_theme
from .window_manager import WindowManager
from .windows.base_window import BaseMonitorWindow
from .windows.cpu_window import CPUWindow
from .windows.memory_window import MemoryWindow
from .windows.network_window import NetworkWindow

__all__ = [
    "CPUWindow",
    "MemoryWindow",
    "NetworkWindow",
    "BaseMonitorWindow",
    "MonitorMode",
    "ProcessMonitor",
    "SharedDataCollector",
    "ThemeScope",
    "app_theme",
    "window_theme",
    "WindowManager",
    "InitialSettingsDialog",
    "CPUSettingsDialog",
    "MemorySettingsDialog",
    "NetworkSettingsDialog",
    "InitialSettings",
    "CPUSettings",
    "MemorySettings",
    "NetworkSettings",
]
