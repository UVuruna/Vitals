"""
System Tray Controller

Single tray icon representing the whole application (gadget mode).

The monitor windows use Qt.Tool, so they have no taskbar button and no
Alt-Tab entry — like desktop gadgets. This tray icon is the application's
only shell identity: its menu shows/hides each monitor window, and Exit
is the way to quit the application (closing a window only hides it).
"""

from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .styles import CONTEXT_MENU_STYLE


class TrayController:
    """Owns the tray icon and its menu. Keep a reference for the app lifetime."""

    def __init__(self, icon, windows: list):
        self._tray = QSystemTrayIcon(icon)
        self._tray.setToolTip("Vitals")

        self._menu = QMenu()
        self._menu.setStyleSheet(CONTEXT_MENU_STYLE)

        self._window_actions = []
        for window in windows:
            action = self._menu.addAction(window.windowTitle())
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked, w=window: self._toggle_window(w, checked)
            )
            self._window_actions.append((action, window))

        self._menu.addSeparator()
        minimize_action = self._menu.addAction("Minimize")
        minimize_action.triggered.connect(self._minimize_all)
        exit_action = self._menu.addAction("Exit")
        exit_action.triggered.connect(self._exit_app)

        self._menu.aboutToShow.connect(self._refresh_checks)
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def prepare_exit(self):
        """Save visible layouts, then hide the tray icon and ALL windows at once.

        Runs synchronously in the Exit click handler (and again via
        aboutToQuit for the File > Exit path — the second run is a no-op on
        already-hidden windows), so every window vanishes together before
        the slow teardown (collector stop, ETW session stop) begins.
        """
        self._tray.hide()
        for _action, window in self._window_actions:
            if window.isVisible():
                window._save_window_layout()
            window.hide()

    def _exit_app(self):
        """Complete application exit: hide everything instantly, then quit."""
        self.prepare_exit()
        QApplication.instance().quit()

    def _minimize_all(self):
        """Hide every visible monitor window to the tray at once.

        The counterpart to a double-click, which re-shows them all. Monitors
        keep running while hidden, so peaks/history stay continuous.
        """
        for _action, window in self._window_actions:
            if window.isVisible():
                window._hide_to_tray()

    def _toggle_window(self, window, visible: bool):
        """Show or hide a monitor window from its menu checkbox."""
        if visible:
            window.show_from_tray()
        else:
            window._hide_to_tray()

    def _refresh_checks(self):
        """Sync menu checkmarks with actual window visibility."""
        for action, window in self._window_actions:
            action.setChecked(window.isVisible())

    def _on_activated(self, reason):
        """Double-click toggles all windows: hide them if any is visible, else show all."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if any(window.isVisible() for _action, window in self._window_actions):
                self._minimize_all()
            else:
                for _action, window in self._window_actions:
                    window.show_from_tray()
