#!/usr/bin/env python3
"""
Vitals - Entry Point

Real-time CPU and Memory usage monitoring for Windows processes.
"""

import json
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import CPUWindow, MemoryWindow, NetworkWindow
from app.monitor import SharedDataCollector
from app.persistence import get_base_path
from app.settings_dialog import InitialSettingsDialog
from app.tray import TrayController


def main():
    """Application entry point."""
    # Set Windows taskbar icon (must be before QApplication)
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PCGadgets.Vitals")
    except Exception as e:
        print(f"[Vitals] Failed to set AppUserModelID (cosmetic, taskbar grouping may be affected): {e}", file=sys.stderr)

    app = QApplication(sys.argv)

    # Load app metadata (single source of truth)
    base = get_base_path()
    with open(base / "setup" / "app_info.json", encoding="utf-8") as f:
        app_info = json.load(f)
    # company.json: bundled at root in frozen exe, two levels up in dev
    company_path = base / "company.json" if getattr(sys, 'frozen', False) else base.parent.parent / "company.json"
    with open(company_path, encoding="utf-8") as f:
        company = json.load(f)
    app.setApplicationName(app_info["name"])
    app.setApplicationVersion(app_info["version"])
    app.setOrganizationName(company["company_name"])

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

    network_window = None
    if settings.network_enabled:
        network_window = NetworkWindow(settings, collector)
        if len(windows) > 0:
            last = windows[-1]
            network_window.move(last.x() + last.width() + 20, last.y())
        network_window.show()
        windows.append(network_window)

    # Link refresh rates: changing one window's rate syncs to the other
    if cpu_window is not None and memory_window is not None:
        cpu_window._peer_window = memory_window
        memory_window._peer_window = cpu_window

    # Gadget mode: windows are Qt.Tool (no taskbar/Alt-Tab presence) and
    # closing one only hides it — the tray icon is the app's single identity
    # and its Exit action (or File > Exit) is the way to quit
    app.setQuitOnLastWindowClosed(False)
    tray = TrayController(app.windowIcon(), windows)  # noqa: F841 — must outlive app.exec()

    # Tray Exit hides everything synchronously in its click handler; the
    # aboutToQuit hook covers the File > Exit path the same way, so every
    # quit route saves visible layouts and hides all windows at once before
    # the slow teardown (collector stop, ETW session stop) begins.
    app.aboutToQuit.connect(tray.prepare_exit)

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
