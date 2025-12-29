#!/usr/bin/env python3
"""
Process Monitor - Entry Point

Real-time CPU and Memory usage monitoring for Windows processes.

Usage:
    python main.py

Requirements:
    - Python 3.11+
    - PySide6
    - psutil
"""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app import MainWindow


def get_base_path() -> Path:
    """Get base path for resources (handles PyInstaller frozen exe)."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller exe
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

    # Set application metadata
    app.setApplicationName("Process Monitor")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("PC Gadgets")

    # Set app icon (prefer .ico for Windows)
    base = get_base_path()
    icon_path = base / "assets" / "icon.ico"
    if not icon_path.exists():
        icon_path = base / "assets" / "icon.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
