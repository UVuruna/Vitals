#!/usr/bin/env python3
"""
Process Monitor - Entry Point

Real-time CPU and Memory usage monitoring for Windows processes.
"""

import json
import sys
from pathlib import Path

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

    # Load app metadata from app_info.json (single source of truth)
    app_info_path = get_base_path() / "setup" / "app_info.json"
    if app_info_path.exists():
        with open(app_info_path, encoding="utf-8") as f:
            app_info = json.load(f)
        app.setApplicationName(app_info.get("name", "PMUsage"))
        app.setApplicationVersion(app_info.get("version", "0.0.0"))
    else:
        app.setApplicationName("PMUsage")
        app.setApplicationVersion("0.0.0")
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
    cpu_window = None
    memory_window = None

    if settings.cpu_enabled:
        cpu_window = CPUWindow(settings, collector)
        cpu_window.show()
        windows.append(cpu_window)

    if settings.memory_enabled:
        memory_window = MemoryWindow(settings, collector)
        if len(windows) > 0:
            # Default side-by-side position; overridden by saved layout during showEvent
            memory_window.move(
                windows[0].x() + windows[0].width() + 20,
                windows[0].y()
            )
        memory_window.show()
        windows.append(memory_window)

    # Link refresh rates: changing one window's rate syncs to the other
    if cpu_window is not None and memory_window is not None:
        cpu_window._peer_window = memory_window
        memory_window._peer_window = cpu_window

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
