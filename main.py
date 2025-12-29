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

from PySide6.QtWidgets import QApplication

from app import MainWindow


def main():
    """Application entry point."""
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("Process Monitor")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("PC Gadgets")

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
