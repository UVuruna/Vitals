#!/usr/bin/env python3
"""
Vitals - Entry Point

Real-time CPU and Memory usage monitoring for Windows processes.
"""

import json
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.collect.collector import SharedDataCollector
from app.dialogs.setup_dialog import InitialSettingsDialog
from app.persistence import get_base_path
from app.tray import TrayController
from app.window_manager import WindowManager


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

    # The window manager owns all three monitors: it creates each one the
    # first time it is enabled, so a monitor can be switched on later from
    # the tray's Settings without restarting the app.
    manager = WindowManager(settings, collector)
    manager.apply_settings(settings)

    # Gadget mode: windows are Qt.Tool (no taskbar/Alt-Tab presence) and
    # closing one only hides it — the tray icon is the app's single identity
    # and its Exit action is the way to quit
    app.setQuitOnLastWindowClosed(False)
    tray = TrayController(app.windowIcon(), manager)  # noqa: F841 — must outlive app.exec()

    # Tray Exit hides everything synchronously in its click handler; the
    # aboutToQuit hook covers any other quit route (an OS session end) the
    # same way, so every quit saves visible layouts and hides all windows at
    # once before the slow teardown (collector stop, ETW session stop) begins.
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
