#!/usr/bin/env python3
"""
Process Monitor - Entry Point

Real-time CPU and Memory usage monitoring for Windows processes.
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import CPUWindow, MemoryWindow
from app.monitor import SharedDataCollector
from app.settings_dialog import InitialSettingsDialog


def get_base_path() -> Path:
    """Get base path for resources (handles PyInstaller frozen exe)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def main():
    """Application entry point."""
    # Set Windows taskbar icon (must be before QApplication)
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PCGadgets.PMUsage")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Process Monitor")
    app.setApplicationVersion("1.1.160")
    app.setOrganizationName("PC Gadgets")

    # Set app icon
    base = get_base_path()
    icon_path = base / "assets" / "icon.ico"
    if not icon_path.exists():
        icon_path = base / "assets" / "icon.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Show initial settings dialog
    dialog = InitialSettingsDialog()
    if not dialog.exec():
        return 0

    settings = dialog.get_settings()

    # Create shared data collector
    collector = SharedDataCollector()

    # Track windows
    windows = []

    # Create windows — second window is a child of the first so
    # Windows groups them under a single taskbar icon
    primary = None

    if settings.cpu_enabled:
        cpu_window = CPUWindow(settings, collector)
        cpu_window.show()
        windows.append(cpu_window)
        primary = cpu_window

    if settings.memory_enabled:
        # Child of primary window: shares taskbar entry but stays independently movable
        parent = primary
        memory_window = MemoryWindow(settings, collector, parent)
        if parent:
            memory_window.setWindowFlags(memory_window.windowFlags() | Qt.WindowType.Window)
        memory_window.show()
        # Offset second window
        if primary:
            memory_window.move(
                primary.x() + primary.width() + 20,
                primary.y()
            )
        windows.append(memory_window)

    # Start collector if not already running
    if not collector.isRunning():
        collector.start()

    # Run event loop
    result = app.exec()

    # Cleanup
    collector.stop()
    SharedDataCollector.reset_instance()

    return result


if __name__ == "__main__":
    sys.exit(main())
